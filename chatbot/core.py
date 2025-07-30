import uuid
import time
import logging
import pandas as pd
import os
import json
from typing import List, Dict, Any, Optional, Tuple
from .config import Config, get_store_mappings, get_shop_mappings, get_available_models
from .api_clients import APIClient 
from .bigquery_utils import BigQueryUtils
from .visualizer import create_visualization
from .summarizer import generate_summary

# Google Auth imports for IAP
try:
    import google.auth
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    logging.warning("Google auth libraries not available. Running without IAP authentication.")

logger = logging.getLogger(__name__)

# MCP Toolbox Integration - Single import attempt
try:
    # Try the actual import path first
    from toolbox_core import ToolboxSyncClient
    TOOLBOX_AVAILABLE = True
    logger.info("✅ ToolboxSyncClient imported successfully from toolbox_core")
except ImportError:
    try:
        # Fallback to alternative import path
        from mcp_toolbox import ToolboxSyncClient
        TOOLBOX_AVAILABLE = True
        logger.info("✅ ToolboxSyncClient imported successfully from mcp_toolbox")
    except ImportError as e:
        logger.warning(f"⚠️ ToolboxSyncClient not available: {e}")
        TOOLBOX_AVAILABLE = False
        
        # Create a dummy base class when MCP Toolbox isn't available
        class ToolboxSyncClient:
            def __init__(self, base_url: str):
                self.base_url = base_url
                logger.warning("Using dummy ToolboxSyncClient - MCP Toolbox not available")
            
            async def _request(self, method: str, path: str, **kwargs):
                raise NotImplementedError("MCP Toolbox not available")

# Working Toolbox Client - No authentication needed
class AuthenticatedToolboxClient(ToolboxSyncClient):
    """Extended ToolboxSyncClient - no auth needed since Cloud Run allows unauthenticated access"""
    
    def __init__(self, base_url: str):
        self.toolbox_available = TOOLBOX_AVAILABLE
        
        if not TOOLBOX_AVAILABLE:
            logger.error("Cannot initialize AuthenticatedToolboxClient - ToolboxSyncClient not available")
            super().__init__(base_url)  # Initialize dummy base class
            return
        
        try:
            super().__init__(base_url)
            
            # No authentication needed since we configured Cloud Run to allow unauthenticated access
            self.use_auth = False
            logger.info("✅ Using unauthenticated access (Cloud Run configured for allUsers)")
            
        except Exception as e:
            logger.error(f"Failed to initialize ToolboxSyncClient: {e}")
            self.toolbox_available = False
    
    async def _request(self, method: str, path: str, **kwargs):
        """Simple request without authentication"""
        if not self.toolbox_available:
            raise RuntimeError("MCP Toolbox not available - cannot make requests")
            
        logger.debug(f"Making unauthenticated request: {method} {path}")
        try:
            return await super()._request(method, path, **kwargs)
        except Exception as e:
            logger.error(f"Request failed: {method} {path} - Error: {e}")
            raise

class SuperGeminiRetailChatbot:
    def __init__(self, config):
        self.config = config
        self.store_mappings = get_store_mappings()
        self.shop_mappings = get_shop_mappings()
        self.available_models = get_available_models()
        self.api_clients = APIClient()
        self.bigquery_utils = BigQueryUtils(config)
        self.last_df = None
        self.last_query = None
        self.last_tool_used = None
        self.current_query_id = None
        
        # Add these attributes for app.py compatibility
        self.last_results = None  # Raw results data as list of dicts
        self.last_data = None     # Alias for last_results for chart generation
        
        # Cost tracking
        self.total_cost = 0.0
        self.query_costs = {}
        
        # MCP Toolbox initialization - Make it optional for graceful degradation
        self.toolbox = None
        self.tools = {}
        self.toolbox_enabled = False
        
        if TOOLBOX_AVAILABLE:
            try:
                self._initialize_toolbox()
                logger.info("✅ MCP Toolbox initialization successful")
            except Exception as e:
                logger.error(f"❌ MCP Toolbox initialization failed: {e}")
                logger.warning("🔄 Continuing without MCP Toolbox - some features will be disabled")
        else:
            logger.warning("⚠️ MCP Toolbox not available - some features will be disabled")
            logger.info("📝 To enable MCP features, install: pip install toolbox_core")

    def _initialize_toolbox(self):
        """Initialize MCP Toolbox client with authentication if on Cloud Run"""
        if not TOOLBOX_AVAILABLE:
            logger.warning("Cannot initialize toolbox - library not available")
            return
            
        try:
            # Your deployed Toolbox URL
            toolbox_url = os.getenv("TOOLBOX_URL", "https://toolbox-41815171183.us-central1.run.app")
            logger.info(f"Connecting to MCP Toolbox at: {toolbox_url}")
            
            # Use our authenticated client
            self.toolbox = AuthenticatedToolboxClient(toolbox_url)
            logger.info("MCP Toolbox client initialized successfully")
            
            # Test the connection first
            if os.getenv('K_SERVICE'):
                logger.info("Running on Cloud Run - testing authenticated connection...")
            else:
                logger.info("Running locally - testing unauthenticated connection...")
            
            # Load the retail_analytics toolset defined in tools.yaml
            logger.info("Loading 'retail_analytics' toolset...")
            tools_result = self.toolbox.load_toolset('retail_analytics')
            
            # Handle different return formats from toolbox
            if isinstance(tools_result, dict):
                self.tools = tools_result
                logger.info(f"Loaded tools as dictionary: {list(self.tools.keys())}")
            elif isinstance(tools_result, list):
                logger.info(f"Converting tools list to dictionary. Found {len(tools_result)} tools")
                self.tools = {}
                
                # Simple conversion - assume tools have a callable interface
                for tool in tools_result:
                    if hasattr(tool, '__name__'):
                        self.tools[tool.__name__] = tool
                    elif hasattr(tool, 'name'):
                        self.tools[tool.name] = tool
                    else:
                        # Try to extract name from string representation
                        tool_str = str(tool)
                        if 'get_' in tool_str:
                            import re
                            match = re.search(r'(get_\w+)', tool_str)
                            if match:
                                self.tools[match.group(1)] = tool
                
                logger.info(f"Converted tools to dictionary: {list(self.tools.keys())}")
            else:
                logger.error(f"Unexpected tools format: {type(tools_result)}")
                raise RuntimeError(f"Invalid tools format from MCP Toolbox: {type(tools_result)}")
            
            # Only enable if we have tools
            if self.tools:
                self.toolbox_enabled = True
                logger.info(f"MCP Toolbox initialized successfully with {len(self.tools)} tools")
                logger.info(f"Available tools: {list(self.tools.keys())}")
            else:
                raise RuntimeError("No tools loaded from MCP Toolbox. Check your tools.yaml configuration.")
                
        except Exception as e:
            logger.error(f"Failed to initialize MCP Toolbox: {e}")
            self.toolbox_enabled = False
            self.tools = {}
            raise  # Re-raise so the caller can handle it

    def _map_query_to_tool(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """
        Map user queries to appropriate MCP tools and extract parameters.
        This replaces the complex intent extraction and SQL generation logic.
        """
        query_lower = query.lower()
        
        # Simple keyword-based mapping to tools
        tool_mappings = {
            # Top selling queries
            ('top', 'selling'): 'get_top_selling_items',
            ('best', 'sellers'): 'get_top_selling_items', 
            ('highest', 'revenue'): 'get_top_selling_items',
            ('top', 'sales'): 'get_top_selling_items',
            ('best', 'performing'): 'get_top_selling_items',
            
            # Inventory queries
            ('inventory', 'status'): 'get_inventory_status',
            ('current', 'stock'): 'get_inventory_status',
            ('inventory', 'levels'): 'get_inventory_status',
            ('stock', 'analysis'): 'get_inventory_status',
            
            # Out of stock queries
            ('out', 'stock'): 'get_out_of_stock_items',
            ('stockout',): 'get_out_of_stock_items',
            ('zero', 'inventory'): 'get_out_of_stock_items',
            ('no', 'inventory'): 'get_out_of_stock_items',
            
            # Overstock queries
            ('overstock',): 'get_overstock_items',
            ('excess', 'inventory'): 'get_overstock_items',
            ('slow', 'moving'): 'get_overstock_items',
            ('too', 'much'): 'get_overstock_items',
            
            # Trends queries
            ('trends',): 'get_sales_trends',
            ('over', 'time'): 'get_sales_trends',
            ('monthly', 'sales'): 'get_sales_trends',
            ('weekly', 'sales'): 'get_sales_trends',
            ('daily', 'sales'): 'get_sales_trends',
            
            # Margin queries
            ('margin',): 'get_top_margin_items',
            ('profit',): 'get_top_margin_items',
            ('profitable',): 'get_top_margin_items',
            ('markup',): 'get_top_margin_items',
            
            # Returns queries
            ('return',): 'get_return_analysis',
            ('returns',): 'get_return_analysis',
            ('defective',): 'get_return_analysis',
            ('exchange',): 'get_return_analysis',
            
            # Comparison queries
            ('compare',): 'get_comparison_analysis',
            ('versus',): 'get_comparison_analysis',
            ('vs',): 'get_comparison_analysis',
            ('comparison',): 'get_comparison_analysis',
        }
        
        # Find matching tool
        selected_tool = None
        for keywords, tool_name in tool_mappings.items():
            if all(keyword in query_lower for keyword in keywords):
                selected_tool = tool_name
                break
        
        # Default to top selling items if no specific match
        if not selected_tool:
            selected_tool = 'get_top_selling_items'
            logger.info(f"No specific tool mapping found for query '{query}', defaulting to {selected_tool}")
        
        # Extract parameters based on the query
        parameters = self._extract_parameters_from_query(query, selected_tool)
        
        logger.info(f"Mapped query '{query}' to tool '{selected_tool}' with parameters: {parameters}")
        return selected_tool, parameters

    def _extract_parameters_from_query(self, query: str, tool_name: str) -> Dict[str, Any]:
        """Extract parameters from user query - matching the actual tool parameters"""
        query_lower = query.lower()
        
        # Extract common parameters
        import re
        
        # Extract limit
        limit = 100  # Default limit
        limit_patterns = [
            r'top\s+(\d+)', r'(\d+)\s+top', r'first\s+(\d+)', 
            r'limit\s+(\d+)', r'show\s+(\d+)'
        ]
        for pattern in limit_patterns:
            match = re.search(pattern, query_lower)
            if match:
                limit = int(match.group(1))
                break
        
        # Extract store ID
        store_id = 0  # 0 means all stores
        if 'store 64' in query_lower or 'fargo' in query_lower:
            store_id = 64
        elif 'store 65' in query_lower or 'springfield' in query_lower:
            store_id = 65
        else:
            store_match = re.search(r'store\s+(\d+)', query_lower)
            if store_match:
                store_id = int(store_match.group(1))
        
        # Extract shop ID
        shop_id = 0  # 0 means all shops
        shop_match = re.search(r'shop\s+(\d+)', query_lower)
        if shop_match:
            shop_id = int(shop_match.group(1))
        
        # Extract year filter
        year_filter = 0  # 0 means no year filter
        year_match = re.search(r'(20\d{2})', query_lower)
        if year_match:
            year_filter = int(year_match.group(1))
        
        # Extract days back
        days_back = 30  # Default
        if 'last 7 days' in query_lower or 'last week' in query_lower or '7 day' in query_lower:
            days_back = 7
        elif 'last 30 days' in query_lower or '30 day' in query_lower:
            days_back = 30
        elif 'last 90 days' in query_lower or '90 day' in query_lower:
            days_back = 90
        elif 'last year' in query_lower or '365 day' in query_lower:
            days_back = 365
        elif year_filter > 0:  # If specific year mentioned
            days_back = 0  # Don't apply days_back filter when year is specified
        
        # Build parameters based on tool
        if tool_name == 'get_top_selling_items':
            return {
                'store_id': store_id,
                'shop_id': shop_id,
                'year_filter': year_filter,
                'days_back': days_back,
                'limit': limit
            }
        
        elif tool_name == 'get_inventory_status':
            return {
                'store_id': store_id,
                'min_on_hand': 0,
                'limit': limit
            }
        
        elif tool_name == 'get_out_of_stock_items':
            return {
                'store_id': store_id,
                'min_sales_30d': 1,
                'limit': limit
            }
        
        elif tool_name == 'get_overstock_items':
            return {
                'store_id': store_id,
                'days_supply_threshold': 90,
                'limit': limit
            }
        
        elif tool_name == 'get_sales_trends':
            return {
                'days_back': days_back,
                'store_id': store_id,
                'shop_id': shop_id
            }
        
        elif tool_name == 'get_top_margin_items':
            return {
                'limit': limit,
                'min_revenue': 1000,
                'days_back': days_back
            }
        
        elif tool_name == 'get_return_analysis':
            return {
                'store_id': store_id,
                'days_back': days_back,
                'limit': limit
            }
        
        elif tool_name == 'get_comparison_analysis':
            # Extract store IDs for comparison
            store1_id = 64  # default
            store2_id = 65  # default
            
            if 'store 64' in query_lower:
                store1_id = 64
            if 'store 65' in query_lower:
                store2_id = 65
            
            return {
                'store1_id': store1_id,
                'store2_id': store2_id,
                'days_back': days_back
            }
        
        # Fallback for unknown tools
        return {
            'store_id': store_id,
            'shop_id': shop_id,
            'limit': limit
        }

    def chat(self, user_query, model_name=None, user_id=None, session_id=None):
        """
        Process user query using ONLY MCP Toolbox tools with automatic summary generation.
        """
        if not self.toolbox_enabled:
            return {
                'success': False,
                'error': 'MCP Toolbox is not properly initialized. Check server configuration.',
                'toolbox_error': True
            }
        
        query_id = str(uuid.uuid4())
        self.current_query_id = query_id
        total_start_time = time.time()
        execution_times = {}

        logger.info(f"Processing query: {user_query}")

        # Map query to appropriate MCP tool
        tool_name, parameters = self._map_query_to_tool(user_query)
        
        if tool_name not in self.tools:
            available_tools = list(self.tools.keys())
            logger.error(f"Tool '{tool_name}' not available. Available: {available_tools}")
            return {
                'success': False,
                'error': f'Required tool "{tool_name}" not available in MCP Toolbox',
                'available_tools': available_tools,
                'suggestion': 'Check your tools.yaml configuration'
            }

        # Execute the MCP tool
        try:
            tool = self.tools[tool_name]
            start_time = time.time()
            
            logger.info(f"Executing MCP tool: {tool_name} with parameters: {parameters}")
            
            # Call the tool with extracted parameters
            result = tool(**parameters)
            execution_time = int((time.time() - start_time) * 1000)
            
            # Process the result into DataFrame with smart formatting
            df = self._process_mcp_result(result, tool_name)
            
            if df is None or df.empty:
                logger.warning(f"Tool {tool_name} returned no data")
                return {
                    'success': True,
                    'results': [],
                    'row_count': 0,
                    'has_data': False,
                    'message': 'Query executed successfully but returned no data',
                    'tool_name': tool_name,
                    'parameters': parameters,
                    'query_id': query_id
                }
            
            # Store results for other methods
            self.last_df = df.copy()
            self.last_query = user_query
            self.last_tool_used = tool_name
            self.last_results = df.to_dict('records')
            self.last_data = self.last_results
            
            execution_times['tool_execution_ms'] = execution_time

            # Add this debug logging in your chat() method
            logger.info(f"=== SUMMARY DEBUG ===")
            logger.info(f"model_name parameter: {model_name}")
            logger.info(f"config.model_name: {self.config.model_name}")
            logger.info(f"final model for summary: {model_name or self.config.model_name}")
            logger.info(f"available_models keys: {list(self.available_models.keys()) if self.available_models else 'None'}")
            logger.info(f"DataFrame shape: {df.shape}")
            logger.info(f"Query length: {len(user_query)}")
            
            # AUTO-GENERATE SUMMARY after successful MCP tool execution
            auto_summary = None
            summary_error = None
            summary_start_time = time.time()
            
            try:
                logger.info(f"Auto-generating summary with model: {model_name}")
                
                # Create toolbox context for enhanced summary
                toolbox_context = {
                    'tool_name': tool_name,
                    'toolbox_used': True,
                    'execution_method': 'MCP Toolbox',
                    'parameters': parameters,
                    'execution_time_ms': execution_time
                }
                
                # Generate summary using the specified model
                auto_summary = generate_summary(
                    df, 
                    user_query, 
                    model_name or self.config.model_name, 
                    self.available_models, 
                    self.api_clients, 
                    self.bigquery_utils,
                    toolbox_context=toolbox_context
                )
                
                summary_execution_time = int((time.time() - summary_start_time) * 1000)
                execution_times['summary_generation_ms'] = summary_execution_time
                
                logger.info(f"Auto-summary generated successfully in {summary_execution_time}ms")
                
            except Exception as e:
                summary_error = str(e)
                logger.error(f"Auto-summary generation failed: {e}")
                execution_times['summary_generation_ms'] = int((time.time() - summary_start_time) * 1000)
            
            execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)
            
            # Log to BigQuery
            try:
                self.bigquery_utils.log_query_to_bigquery(
                    query_id=query_id,
                    user_query=user_query,
                    sql_query=f"[MCP Tool: {tool_name}]",
                    model_name=f"mcp_{tool_name}",
                    success=True,
                    error_message=None,
                    row_count=len(df),
                    execution_times=execution_times,
                    user_id=user_id or "anonymous",
                    session_id=session_id or "default"
                )
                
                # Update with summary info if generated
                if auto_summary:
                    self.bigquery_utils.update_query_log(query_id, {'has_summary': True})
                    
            except Exception as e:
                logger.error(f"Failed to log to BigQuery: {e}")
            
            # Format results for return
            results = self._format_results(df)
            
            response = {
                'success': True,
                'error': None,
                'sql': f"[MCP Tool: {tool_name}]",
                'results': results,
                'results_data': results,  # Add this for table rendering
                'row_count': len(df),
                'has_data': True,
                'query_id': query_id,
                'execution_times': execution_times,
                'estimated_cost': 0.0,  # MCP tools don't have direct costs
                'total_session_cost': self.total_cost,
                'toolbox_used': True,
                'tool_name': tool_name,
                'parameters': parameters
            }
            
            # Add auto-summary to response if generated
            if auto_summary:
                response['auto_summary'] = auto_summary
            elif summary_error:
                response['summary_error'] = summary_error
            
            return response
            
        except Exception as e:
            logger.error(f"MCP tool execution failed: {str(e)}")
            execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)
            
            # Log failure to BigQuery
            try:
                self.bigquery_utils.log_query_to_bigquery(
                    query_id=query_id,
                    user_query=user_query,
                    sql_query=f"[MCP Tool: {tool_name}]",
                    model_name=f"mcp_{tool_name}",
                    success=False,
                    error_message=str(e),
                    row_count=None,
                    execution_times=execution_times,
                    user_id=user_id or "anonymous",
                    session_id=session_id or "default"
                )
            except Exception as log_error:
                logger.error(f"Failed to log error to BigQuery: {log_error}")
            
            return {
                'success': False,
                'error': f'MCP tool execution failed: {str(e)}',
                'tool_name': tool_name,
                'parameters': parameters,
                'query_id': query_id,
                'execution_times': execution_times,
                'suggestion': 'Try rephrasing your query or check if the MCP Toolbox server is running'
            }

    def _process_mcp_result(self, result: Any, tool_name: str) -> Optional[pd.DataFrame]:
        """Enhanced MCP result processing with smart auto-formatting"""
        try:
            logger.info(f"Processing result from tool {tool_name}: type={type(result)}")
            
            # First convert to DataFrame using existing logic
            df = self._convert_raw_result_to_dataframe(result, tool_name)
            
            if df is None or df.empty:
                return df
            
            # Apply smart auto-formatting
            formatted_df = self._apply_smart_formatting(df, tool_name)
            
            return formatted_df
            
        except Exception as e:
            logger.error(f"Failed to process MCP result: {str(e)}")
            return None

    def _convert_raw_result_to_dataframe(self, result: Any, tool_name: str) -> Optional[pd.DataFrame]:
        """Convert raw MCP result to DataFrame (existing logic)"""
        # Handle string results (JSON format)
        if isinstance(result, str):
            try:
                # Parse JSON string
                data = json.loads(result)
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                    logger.info(f"Created DataFrame from JSON string with shape: {df.shape}")
                    
                    # Basic type conversion for numeric fields
                    for col in df.columns:
                        if col in ['total_units', 'total_cost', 'transaction_count', 'unique_skus', 'unique_customers', 'store_id', 'shop_id']:
                            try:
                                df[col] = pd.to_numeric(df[col])
                            except:
                                pass
                        elif col in ['total_revenue', 'total_margin', 'margin_pct', 'avg_transaction_value', 'retail_value', 'current_on_hand']:
                            try:
                                # Handle fraction strings like "98833/25"
                                df[col] = df[col].apply(lambda x: eval(x) if isinstance(x, str) and '/' in x else float(x))
                            except:
                                pass
                        elif col in ['sale_date', 'snapshot_date']:
                            try:
                                df[col] = pd.to_datetime(df[col])
                            except:
                                pass
                    
                    return df
                else:
                    df = pd.DataFrame([data])
                    logger.info(f"Created single-row DataFrame from JSON object")
                    return df
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON string result")
                return None
        
        elif isinstance(result, pd.DataFrame):
            logger.info(f"Result is already a DataFrame with shape: {result.shape}")
            return result
        
        elif isinstance(result, dict):
            if 'data' in result:
                data = result['data']
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                    logger.info(f"Created DataFrame from data list with shape: {df.shape}")
                    return df
            elif 'rows' in result:
                df = pd.DataFrame(result['rows'])
                logger.info(f"Created DataFrame from rows with shape: {df.shape}")
                return df
            else:
                # Try to convert the entire dict to DataFrame
                if all(isinstance(v, list) for v in result.values()):
                    df = pd.DataFrame(result)
                    logger.info(f"Created DataFrame from columnar dict with shape: {df.shape}")
                    return df
                else:
                    df = pd.DataFrame([result])
                    logger.info(f"Created single-row DataFrame with shape: {df.shape}")
                    return df
        
        elif isinstance(result, list):
            logger.info(f"Result is a list with {len(result)} items")
            if result:
                if isinstance(result[0], dict):
                    df = pd.DataFrame(result)
                    logger.info(f"Created DataFrame from list of dicts with shape: {df.shape}")
                    return df
                else:
                    df = pd.DataFrame({'value': result})
                    logger.info(f"Created single-column DataFrame with shape: {df.shape}")
                    return df
            else:
                logger.warning("Empty list result")
                return pd.DataFrame()
        
        else:
            logger.error(f"Unsupported result type: {type(result)}")
            return None

    def _apply_smart_formatting(self, df: pd.DataFrame, tool_name: str) -> pd.DataFrame:
        """
        Apply intelligent auto-formatting based on data types and business rules.
        Optimized for both user display and LLM consumption.
        """
        
        formatted_df = df.copy()
        
        # 1. CURRENCY FIELDS - Auto-detect and format
        currency_fields = self._detect_currency_columns(formatted_df)
        for col in currency_fields:
            formatted_df[col] = self._format_currency_column(formatted_df[col])
        
        # 2. PERCENTAGE FIELDS - Auto-detect and format  
        percentage_fields = self._detect_percentage_columns(formatted_df)
        for col in percentage_fields:
            formatted_df[col] = self._format_percentage_column(formatted_df[col])
        
        # 3. INTEGER FIELDS - Auto-detect and format
        integer_fields = self._detect_integer_columns(formatted_df)
        for col in integer_fields:
            formatted_df[col] = self._format_integer_column(formatted_df[col])
        
        # 4. BUSINESS LOGIC FILTERING - Tool-specific intelligent filtering
        formatted_df = self._apply_business_rules(formatted_df, tool_name)
        
        # 5. INTELLIGENT SORTING - Sort by most relevant column
        formatted_df = self._apply_smart_sorting(formatted_df, tool_name)
        
        # 6. COLUMN OPTIMIZATION - Reorder for readability
        formatted_df = self._optimize_column_order(formatted_df)
        
        logger.info(f"Applied smart formatting: {len(formatted_df)} rows, {len(formatted_df.columns)} columns")
        return formatted_df

    def _detect_currency_columns(self, df: pd.DataFrame) -> List[str]:
        """Auto-detect currency columns based on name patterns and data"""
        currency_patterns = [
            'revenue', 'sales', 'cost', 'margin', 'price', 'value', 
            'total_revenue', 'total_sales', 'total_cost', 'total_margin',
            'avg_transaction_value', 'retail_value', 'unit_price'
        ]
        
        currency_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(pattern in col_lower for pattern in currency_patterns):
                # Verify it's actually numeric
                if pd.api.types.is_numeric_dtype(df[col]):
                    currency_cols.append(col)
        
        return currency_cols

    def _detect_percentage_columns(self, df: pd.DataFrame) -> List[str]:
        """Auto-detect percentage columns"""
        percentage_patterns = ['pct', 'percent', 'rate', 'margin_pct']
        
        percentage_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(pattern in col_lower for pattern in percentage_patterns):
                if pd.api.types.is_numeric_dtype(df[col]):
                    percentage_cols.append(col)
        
        return percentage_cols

    def _detect_integer_columns(self, df: pd.DataFrame) -> List[str]:
        """Auto-detect integer columns (units, counts, IDs)"""
        integer_patterns = [
            'units', 'quantity', 'count', 'on_hand', 'inventory',
            'total_units', 'current_on_hand', 'transaction_count',
            'unique_skus', 'unique_customers', 'days_supply'
        ]
        
        integer_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(pattern in col_lower for pattern in integer_patterns):
                if pd.api.types.is_numeric_dtype(df[col]):
                    integer_cols.append(col)
        
        return integer_cols

    def _format_currency_column(self, series: pd.Series) -> pd.Series:
        """Format currency column for optimal display and LLM readability"""
        # Convert to numeric, handle errors gracefully
        numeric_series = pd.to_numeric(series, errors='coerce')
        
        # Round to whole dollars (no cents for retail analytics)
        rounded_series = numeric_series.round(0)
        
        # Format with $ and commas, but keep as string for display
        # LLM can easily parse "$1,234" format
        formatted_series = rounded_series.apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) and x >= 0 else "$0"
        )
        
        return formatted_series

    def _format_percentage_column(self, series: pd.Series) -> pd.Series:
        """Format percentage column for optimal display and LLM readability"""
        numeric_series = pd.to_numeric(series, errors='coerce')
        
        # Determine if values are already in percentage form (0-100) or decimal form (0-1)
        max_val = numeric_series.max()
        if max_val <= 1.0:
            # Values are in decimal form, convert to percentage
            numeric_series = numeric_series * 100
        
        # Round to 1 decimal place for margins, whole numbers for rates
        rounded_series = numeric_series.round(1)
        
        # Format with % symbol - LLM understands "23.5%" format well
        formatted_series = rounded_series.apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "0.0%"
        )
        
        return formatted_series

    def _format_integer_column(self, series: pd.Series) -> pd.Series:
        """Format integer column for optimal display and LLM readability"""
        numeric_series = pd.to_numeric(series, errors='coerce')
        
        # Round to whole numbers
        integer_series = numeric_series.round(0)
        
        # Add thousand separators for large numbers
        # LLM handles "1,234" format very well
        formatted_series = integer_series.apply(
            lambda x: f"{int(x):,}" if pd.notna(x) and x >= 0 else "0"
        )
        
        return formatted_series

    def _apply_business_rules(self, df: pd.DataFrame, tool_name: str) -> pd.DataFrame:
        """Apply intelligent business rules based on tool type"""
        
        if 'top_margin' in tool_name and 'margin_pct' in df.columns:
            # Only show items with meaningful margins (>5%)
            margin_numeric = pd.to_numeric(df['margin_pct'].str.replace('%', ''), errors='coerce')
            df = df[margin_numeric > 5.0]
            logger.info(f"Filtered to items with margin > 5%: {len(df)} items")
        
        elif 'out_of_stock' in tool_name and 'total_revenue' in df.columns:
            # Focus on high-impact out of stock items (revenue > $100)
            revenue_numeric = pd.to_numeric(df['total_revenue'].str.replace('[$,]', '', regex=True), errors='coerce')
            df = df[revenue_numeric > 100]
            logger.info(f"Filtered to high-impact out of stock items: {len(df)} items")
        
        elif 'overstock' in tool_name and 'days_supply' in df.columns:
            # Focus on true overstock (>60 days supply)
            days_numeric = pd.to_numeric(df['days_supply'].str.replace(',', ''), errors='coerce')
            df = df[days_numeric > 60]
            logger.info(f"Filtered to true overstock items (>60 days): {len(df)} items")
        
        # General rule: Limit to top 50 results for LLM processing efficiency
        if len(df) > 50:
            df = df.head(50)
            logger.info(f"Limited to top 50 results for optimal LLM processing")
        
        return df

    def _apply_smart_sorting(self, df: pd.DataFrame, tool_name: str) -> pd.DataFrame:
        """Apply intelligent sorting based on tool purpose"""
        
        if 'top_selling' in tool_name or 'revenue' in tool_name:
            # Sort by revenue descending
            if 'total_revenue' in df.columns:
                revenue_numeric = pd.to_numeric(df['total_revenue'].str.replace('[$,]', '', regex=True), errors='coerce')
                df = df.iloc[revenue_numeric.argsort()[::-1]]
        
        elif 'margin' in tool_name:
            # Sort by margin percentage descending
            if 'margin_pct' in df.columns:
                margin_numeric = pd.to_numeric(df['margin_pct'].str.replace('%', ''), errors='coerce')
                df = df.iloc[margin_numeric.argsort()[::-1]]
        
        elif 'out_of_stock' in tool_name:
            # Sort by recent sales/revenue impact
            if 'total_revenue' in df.columns:
                revenue_numeric = pd.to_numeric(df['total_revenue'].str.replace('[$,]', '', regex=True), errors='coerce')
                df = df.iloc[revenue_numeric.argsort()[::-1]]
        
        elif 'overstock' in tool_name:
            # Sort by days supply descending (worst first)
            if 'days_supply' in df.columns:
                days_numeric = pd.to_numeric(df['days_supply'].str.replace(',', ''), errors='coerce')
                df = df.iloc[days_numeric.argsort()[::-1]]
        
        return df

    def _optimize_column_order(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reorder columns for optimal readability (user) and LLM processing"""
        
        # Define priority order for common retail analytics columns
        priority_columns = [
            'product_name', 'sku', 'description', 'product_description',
            'total_revenue', 'total_units', 'margin_pct', 'total_margin',
            'current_on_hand', 'days_supply', 'avg_transaction_value',
            'store_id', 'shop_id', 'sale_date', 'snapshot_date'
        ]
        
        # Get existing columns in priority order
        ordered_columns = []
        for col in priority_columns:
            if col in df.columns:
                ordered_columns.append(col)
        
        # Add remaining columns
        remaining_columns = [col for col in df.columns if col not in ordered_columns]
        final_order = ordered_columns + remaining_columns
        
        return df[final_order]

    def _format_results(self, df: pd.DataFrame, preview_rows: int = None) -> List[Dict[str, Any]]:
        """
        Enhanced results formatting that preserves formatted data for both display and LLM.
        No additional formatting needed since data is already optimally formatted.
        """
        if df is None or df.empty:
            return []
        
        preview_rows = preview_rows or self.config.preview_rows or 20
        
        if len(df) > preview_rows:
            logger.info(f"Retrieved {len(df)} rows, displaying first {preview_rows} for UI")
        
        # Convert to records - data is already perfectly formatted
        results = df.head(preview_rows).to_dict('records')
        
        # Only handle null values and timestamps
        for row in results:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
                elif isinstance(value, (pd.Timestamp, pd.Period)):
                    row[key] = str(value)
        
        return results

    def generate_chart(self, chart_type: str = None):
        """Generate chart from last query results"""
        if self.last_df is None or self.last_df.empty:  
            logger.error("No dataframe available for charting")
            return {'success': False, 'error': 'No data available to chart'}
            
        try:
            chart = create_visualization(self.last_df, self.last_query, chart_type)
            if chart:
                self.bigquery_utils.update_query_log(self.current_query_id, {'has_visualization': True})
                return {
                    'success': True,
                    'chart': chart
                }
            else:
                return {
                    'success': False,
                    'error': 'Unable to create chart from the data'
                }
        except Exception as e:
            logger.error(f"Chart generation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def generate_llm_summary(self, model_name: str = None):
        """Generate AI summary of last query results (manual generation)"""
        if self.last_df is None or self.last_df.empty:
            return {'success': False, 'error': 'No data available to summarize'}
            
        try:
            # Add toolbox context for enhanced summaries
            toolbox_context = {
                'tool_name': self.last_tool_used,
                'toolbox_used': True,
                'execution_method': 'MCP Toolbox'
            } if self.last_tool_used else None
            
            summary = generate_summary(
                self.last_df, 
                self.last_query, 
                model_name or self.config.model_name, 
                self.available_models, 
                self.api_clients, 
                self.bigquery_utils,
                toolbox_context=toolbox_context
            )
            
            if self.current_query_id:
                self.bigquery_utils.update_query_log(self.current_query_id, {
                    'has_summary': True,
                    'summary_method': 'manual_mcp_enhanced'
                })
            
            return {
                'success': True,
                'summary': summary
            }
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost summary - MCP tools don't have direct costs"""
        return {
            'total_session_cost': 0.0,  # MCP tools are typically free to use
            'queries_executed': len(self.query_costs),
            'query_costs': {},
            'average_cost_per_query': 0.0,
            'toolbox_enabled': self.toolbox_enabled,
            'cost_model': 'MCP Toolbox (infrastructure costs only)'
        }

    def reset_cost_tracking(self):
        """Reset cost tracking for a new session"""
        self.total_cost = 0.0
        self.query_costs = {}
        logger.info("Cost tracking reset for new session")

    def get_toolbox_status(self) -> Dict[str, Any]:
        """Get status information about MCP Toolbox integration"""
        return {
            'toolbox_available': TOOLBOX_AVAILABLE,
            'toolbox_enabled': self.toolbox_enabled,
            'tools_loaded': len(self.tools) if self.tools else 0,
            'available_tools': list(self.tools.keys()) if isinstance(self.tools, dict) else [],
            'toolbox_url': getattr(self.toolbox, 'url', 'Unknown') if self.toolbox else None,
            'system_mode': 'MCP-Only (No SQL Fallback)',
            'auth_enabled': getattr(self.toolbox, 'use_auth', False) if self.toolbox else False
        }
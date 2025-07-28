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

# MCP Toolbox Integration
try:
    from toolbox_core import ToolboxSyncClient
    TOOLBOX_AVAILABLE = True
except ImportError:
    TOOLBOX_AVAILABLE = False
    logging.error("MCP Toolbox not available. This system requires MCP Toolbox to function.")

logger = logging.getLogger(__name__)

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
        
        # MCP Toolbox initialization - REQUIRED
        self.toolbox = None
        self.tools = {}
        self.toolbox_enabled = False
        
        if not TOOLBOX_AVAILABLE:
            raise RuntimeError("MCP Toolbox is required but not available. Please install toolbox_core.")
        
        self._initialize_toolbox()

    def _initialize_toolbox(self):
        """Initialize MCP Toolbox client and load retail analytics tools"""
        try:
            # Your deployed Toolbox URL - update this to match your deployment
            toolbox_url = os.getenv("TOOLBOX_URL", "https://toolbox-41815171183.us-central1.run.app")
            logger.info(f"Connecting to MCP Toolbox at: {toolbox_url}")
            
            # Initialize the toolbox client
            self.toolbox = ToolboxSyncClient(toolbox_url)
            logger.info("MCP Toolbox client initialized successfully")
            
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
            logger.error("This system requires MCP Toolbox to function. Please ensure:")
            logger.error("1. MCP Toolbox server is running")
            logger.error("2. tools.yaml is properly configured")
            logger.error("3. toolbox_core package is installed")
            raise RuntimeError(f"MCP Toolbox initialization failed: {e}")

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
        Process user query using ONLY MCP Toolbox tools - no SQL generation fallback.
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
            
            # Debug: Try to inspect the tool
            try:
                if hasattr(tool, 'statement'):
                    logger.debug(f"Tool SQL template: {tool.statement[:200]}...")
                if hasattr(tool, '_statement'):
                    logger.debug(f"Tool SQL template (private): {tool._statement[:200]}...")
                if hasattr(tool, 'get_statement'):
                    logger.debug(f"Tool SQL via method: {tool.get_statement()[:200]}...")
            except Exception as e:
                logger.warning(f"Could not inspect tool SQL: {e}")
            
            # Call the tool with extracted parameters
            result = tool(**parameters)
            execution_time = int((time.time() - start_time) * 1000)
            
            # Process the result into DataFrame
            df = self._process_mcp_result(result, tool_name)
            
            if df is None or df.empty:
                logger.warning(f"Tool {tool_name} returned no data")
                return {
                    'success': True,
                    'results': "No data returned from query.",
                    'results_data': [],
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
            
            # AUTO-GENERATE SUMMARY HERE
            summary_text = None
            summary_error = None
            
            try:
                logger.info(f"Auto-generating summary for {len(df)} rows of data...")
                summary_start = time.time()
                
                # Add toolbox context for enhanced summaries
                toolbox_context = {
                    'tool_name': tool_name,
                    'toolbox_used': True,
                    'execution_method': 'MCP Toolbox',
                    'parameters': parameters
                }
                
                # Import here to avoid circular imports
                from .summarizer import generate_summary
                
                summary_text = generate_summary(
                    df, 
                    user_query, 
                    model_name or self.config.model_name, 
                    self.available_models, 
                    self.api_clients, 
                    self.bigquery_utils,
                    toolbox_context=toolbox_context
                )
                
                execution_times['summary_generation_ms'] = int((time.time() - summary_start) * 1000)
                logger.info("Summary generated successfully")
                
            except Exception as e:
                logger.error(f"Auto-summary generation failed: {e}")
                summary_error = str(e)
                # Don't fail the whole request if summary fails
            
            execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)
            
            # Log to BigQuery (but don't fail if this errors)
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
            except Exception as e:
                logger.warning(f"Failed to log to BigQuery (non-critical): {e}")
            
            # Format results for return - both string and structured
            results_string = self._format_results_as_string(df)
            results_structured = self._format_results_as_list(df)
            
            response = {
                'success': True,
                'error': None,
                'sql': f"[MCP Tool: {tool_name}]",
                'results': results_string,  # String for display
                'results_data': results_structured,  # Structured data for charts
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
            
            # Add summary if we got one
            if summary_text:
                response['auto_summary'] = summary_text
                response['summary_generated'] = True
            elif summary_error:
                response['summary_error'] = summary_error
                response['summary_generated'] = False
                
            return response
            
        except Exception as e:
            logger.error(f"MCP tool execution failed: {str(e)}")
            execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)
            
            # Log failure to BigQuery (but don't fail if this errors)
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
                logger.warning(f"Failed to log error to BigQuery (non-critical): {log_error}")
            
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
        """Process the result from an MCP tool call into a DataFrame"""
        try:
            logger.info(f"Processing result from tool {tool_name}: type={type(result)}")
            
            # Handle string results (JSON format)
            if isinstance(result, str):
                try:
                    # Parse JSON string
                    data = json.loads(result)
                    if isinstance(data, list):
                        df = pd.DataFrame(data)
                        logger.info(f"Created DataFrame from JSON string with shape: {df.shape}")
                        
                        # Convert numeric strings to proper types
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
                
        except Exception as e:
            logger.error(f"Failed to process MCP result: {str(e)}")
            return None

    def _format_results_as_string(self, df: pd.DataFrame, preview_rows: int = None) -> str:
        """Format DataFrame results as a formatted string table for display"""
        if df is None or df.empty:
            return "No data returned"
        
        # UI display limit
        preview_rows = preview_rows or self.config.preview_rows or 20
        
        # Log if we're truncating for display
        if len(df) > preview_rows:
            logger.info(f"Retrieved {len(df)} rows, displaying first {preview_rows} for UI")
        
        # Get the display DataFrame
        display_df = df.head(preview_rows).copy()
        
        # Clean up any NaN values
        display_df = display_df.fillna('')
        
        # Format numeric columns for better display
        for col in display_df.columns:
            if display_df[col].dtype in ['float64', 'float32']:
                # Round floats to 2 decimal places for currency/percentages
                if any(keyword in col.lower() for keyword in ['revenue', 'cost', 'margin', 'price', 'value']):
                    display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) and x != '' else '')
                elif 'pct' in col.lower() or 'percent' in col.lower():
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) and x != '' else '')
                else:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) and x != '' else '')
            elif display_df[col].dtype in ['int64', 'int32']:
                # Format integers with commas
                display_df[col] = display_df[col].apply(lambda x: f"{x:,}" if pd.notnull(x) and x != '' else '')
        
        # Convert to a nicely formatted string table
        return display_df.to_string(index=False, max_rows=preview_rows)

    def _format_results_as_list(self, df: pd.DataFrame, preview_rows: int = None) -> List[Dict[str, Any]]:
        """Format DataFrame results as list of dictionaries for structured use"""
        if df is None or df.empty:
            return []
        
        # UI display limit (not data retrieval limit)
        preview_rows = preview_rows or self.config.preview_rows or 20
        
        # Convert DataFrame to list of dictionaries - only first N rows for UI
        results = df.head(preview_rows).to_dict('records')
        
        # Clean up any NaN values
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
                if self.current_query_id:
                    try:
                        self.bigquery_utils.update_query_log(self.current_query_id, {'has_visualization': True})
                    except Exception as e:
                        logger.warning(f"Failed to update query log (non-critical): {e}")
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
        """Generate AI summary of last query results"""
        if self.last_df is None or self.last_df.empty:
            return {'success': False, 'error': 'No data available to summarize'}
            
        try:
            # Add toolbox context for enhanced summaries
            toolbox_context = {
                'tool_name': self.last_tool_used,
                'toolbox_used': True,
                'execution_method': 'MCP Toolbox'
            } if self.last_tool_used else None
            
            from .summarizer import generate_summary
            
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
                try:
                    self.bigquery_utils.update_query_log(self.current_query_id, {
                        'has_summary': True,
                        'summary_method': 'mcp_enhanced'
                    })
                except Exception as e:
                    logger.warning(f"Failed to update query log (non-critical): {e}")
            
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
            'system_mode': 'MCP-Only (No SQL Fallback)'
        }
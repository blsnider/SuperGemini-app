import uuid
import time
import logging
import pandas as pd
import os
import json
import re
from datetime import datetime
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

# Import asyncio for proper session management
import asyncio
import aiohttp

# Working Toolbox Client - No authentication needed
class AuthenticatedToolboxClient(ToolboxSyncClient):
    """Extended ToolboxSyncClient - no auth needed since Cloud Run allows unauthenticated access"""
    
    def __init__(self, base_url: str):
        self.toolbox_available = TOOLBOX_AVAILABLE
        self._session = None
        
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
    
    def __del__(self):
        """Cleanup any open sessions"""
        if hasattr(self, '_session') and self._session:
            try:
                asyncio.create_task(self._session.close())
            except RuntimeError:
                # If no event loop is running, we can't close it async
                pass

class SuperGeminiRetailChatbot:
    def __init__(self, config):
        # Local query history storage (fallback when BigQuery is unavailable)
        self.local_query_history = []
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
    
    def cleanup(self):
        """Cleanup resources, especially MCP toolbox connections"""
        if self.toolbox and hasattr(self.toolbox, '__del__'):
            try:
                self.toolbox.__del__()
            except Exception as e:
                logger.error(f"Error cleaning up toolbox: {e}")

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

    def _map_query_to_tool(self, query: str, snapshot_date: str = None) -> Tuple[str, Dict[str, Any]]:
        """
        Map user queries to appropriate MCP tools and extract parameters.
        This replaces the complex intent extraction and SQL generation logic.
        """
        query_lower = query.lower()
        
        # Check for direct tool execution request
        if 'execute mcp tool:' in query_lower:
            # Extract tool name from query like "Execute MCP tool: get_top_selling_items"
            import re
            match = re.search(r'execute mcp tool:\s*(\w+)', query_lower)
            if match:
                tool_name = match.group(1)
                if tool_name in self.tools:
                    logger.info(f"Direct tool execution requested: {tool_name}")
                    # Extract parameters based on the tool
                    parameters = self._extract_parameters_from_query(query, tool_name)
                    return tool_name, parameters
        
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
            
            # Inventory risk assessment queries
            ('inventory', 'risk'): 'get_inventory_risk_assessment',
            ('risk', 'assessment'): 'get_inventory_risk_assessment',
            ('inventory', 'assessment'): 'get_inventory_risk_assessment',
            ('stock', 'risk'): 'get_inventory_risk_assessment',
            ('inventory', 'priority'): 'get_inventory_risk_assessment',
            ('risk', 'analysis'): 'get_inventory_risk_assessment',
            ('at', 'risk'): 'get_inventory_risk_assessment',
            
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
            ('trend',): 'get_sales_trends',
            ('over', 'time'): 'get_sales_trends',
            ('monthly', 'sales'): 'get_sales_trends',
            ('weekly', 'sales'): 'get_sales_trends',
            ('daily', 'sales'): 'get_sales_trends',
            ('sales', 'trend'): 'get_sales_trends',
            ('sales', 'trends'): 'get_sales_trends',
            
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
            
            # Store comparison queries
            ('compare', 'top', 'items'): 'get_top_selling_item_comparison',
            ('compare', 'top', 'sellers'): 'get_top_selling_item_comparison',
            ('compare', 'best', 'sellers'): 'get_top_selling_item_comparison',
            ('store', 'comparison'): 'get_top_selling_item_comparison',
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
        
        # Extract parameters based on the query (pass snapshot_date if provided)
        parameters = self._extract_parameters_from_query(query, selected_tool, snapshot_date)
        
        logger.info(f"Mapped query '{query}' to tool '{selected_tool}' with parameters: {parameters}")
        return selected_tool, parameters
    
    def _normalize_date_format(self, date_str: str) -> str:
        """Convert various date formats to ISO format (YYYY-MM-DD) expected by BigQuery"""
        if not date_str:
            return date_str
        
        # If already in correct format, return as is
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # Try common date formats
        date_formats = [
            '%m/%d/%Y',      # US format: 7/31/2025
            '%d/%m/%Y',      # EU format: 31/07/2025
            '%Y/%m/%d',      # Alternative: 2025/07/31
            '%m-%d-%Y',      # With dashes: 07-31-2025
            '%d-%m-%Y',      # EU with dashes: 31-07-2025
            '%B %d, %Y',     # Text: July 31, 2025
            '%b %d, %Y',     # Short text: Jul 31, 2025
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                normalized = dt.strftime('%Y-%m-%d')
                logger.info(f"Normalized date from '{date_str}' to '{normalized}' using format '{fmt}'")
                return normalized
            except ValueError:
                continue
        
        logger.warning(f"Could not parse date '{date_str}', using as-is")
        return date_str

    def _get_tool_accepted_parameters(self, tool_name: str) -> list:
        """Get list of parameters that a specific tool accepts"""
        if not self.toolbox_enabled or tool_name not in self.tools:
            return []
        
        # Hardcoded parameter lists for tools based on tools.yaml
        tool_parameters = {
            'get_top_selling_items': ['store_id', 'shop_id', 'year_filter', 'days_back', 'limit'],
            'get_top_selling_item_comparison': ['store1_id', 'store2_id', 'shop_id', 'days_back', 'limit'],
            'get_units_vs_dollars_comparison': ['store_id', 'shop_id', 'days_back', 'limit'],
            'get_shop_performance': ['shop_id', 'store_id', 'days_back', 'limit'],
            'get_sell_through_rates': ['store_id', 'shop_id', 'days_period', 'min_beginning_inventory', 'snapshot_date'],
            'get_time_period_comparison': ['store_id', 'shop_id', 'current_days', 'compare_days', 'limit'],
            'get_inventory_status': ['store_id', 'shop_id', 'min_priority_score', 'include_overstocked', 'limit'],
            'get_1Y_out_of_stock_items': ['store_id', 'shop_id', 'min_sales_30d', 'limit'],
            'get_sales_trends': ['store_id', 'shop_id', 'days_back', 'granularity'],
            'get_top_margin_items': ['store_id', 'shop_id', 'days_back', 'min_revenue', 'limit'],
            'get_overstock_items': ['store_id', 'shop_id', 'days_supply_threshold', 'limit'],
            'get_comparison_analysis': ['store1_id', 'store2_id'],
            'get_advanced_inventory_turnover': ['store_id', 'shop_id', 'days_back', 'limit'],
            'get_advanced_stockout_analysis': ['store_id', 'shop_id', 'min_stockouts', 'days_back', 'limit'],
            'get_advanced_carrying_costs': ['store_id', 'carrying_pct', 'shop_id', 'days_back', 'limit'],
            'get_advanced_gmroi_performance': ['store_id', 'shop_id', 'days_back', 'limit'],
            'get_advanced_vendor_metrics': ['store_id', 'shop_id', 'vendor_name', 'days_back', 'limit'],
            'get_advanced_forecast_accuracy': ['store_id', 'shop_id', 'periods_back'],
            'get_otb_metrics': ['shop_id', 'store_id', 'metric_name', 'year'],
            'get_sales_variance_analysis': ['store_id', 'shop_id', 'period', 'days_back', 'limit'],
            'get_margin_variance_report': ['vendor_name', 'shop_id', 'period', 'min_margin_var', 'limit']
        }
        
        if tool_name in tool_parameters:
            return tool_parameters[tool_name]
        
        try:
            # Fallback - check if tool has __code__ attribute
            tool = self.tools[tool_name]
            if hasattr(tool, '__code__'):
                import inspect
                return list(inspect.signature(tool).parameters.keys())
        except Exception as e:
            logger.warning(f"Could not get parameters for tool {tool_name}: {e}")
        
        return []
    
    def _filter_parameters_for_tool(self, params: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
        """Filter parameters to only include those accepted by the tool"""
        accepted_params = self._get_tool_accepted_parameters(tool_name)
        
        if not accepted_params:
            # If we can't determine accepted parameters, return all
            logger.warning(f"Could not determine accepted parameters for {tool_name}, using all parameters")
            return params
        
        # Filter to only accepted parameters
        filtered = {k: v for k, v in params.items() if k in accepted_params}
        
        # Log if we're removing any parameters
        removed = set(params.keys()) - set(filtered.keys())
        if removed:
            logger.info(f"Removing parameters not accepted by {tool_name}: {removed}")
        
        return filtered

    def _extract_parameters_from_query(self, query: str, tool_name: str, snapshot_date: str = None) -> Dict[str, Any]:
        """Extract parameters from user query - only include explicitly mentioned parameters"""
        query_lower = query.lower()
        
        # Extract common parameters
        import re
        
        # Extract limit ONLY if explicitly mentioned
        limit = None  # No default - let MCP tool use its own
        limit_patterns = [
            r'top\s+(\d+)', r'(\d+)\s+top', r'first\s+(\d+)', 
            r'limit\s+(\d+)', r'show\s+(\d+)', r'best\s+(\d+)'
        ]
        for pattern in limit_patterns:
            match = re.search(pattern, query_lower)
            if match:
                limit = int(match.group(1))
                break
        
        # Extract store ID ONLY if mentioned
        store_id = None  # Let MCP use default
        if 'store 64' in query_lower or 'fargo' in query_lower:
            store_id = 64
        elif 'store 78' in query_lower or 'springfield' in query_lower:
            store_id = 78
        else:
            store_match = re.search(r'store\s+(\d+)', query_lower)
            if store_match:
                store_id = int(store_match.group(1))
        
        # Extract shop ID ONLY if mentioned
        shop_id = None  # Let MCP use default
        shop_match = re.search(r'shop\s+(\d+)', query_lower)
        if shop_match:
            shop_id = int(shop_match.group(1))
        
        # Extract year filter ONLY if mentioned
        year_filter = None  # Let MCP use default
        year_match = re.search(r'(20\d{2})', query_lower)
        if year_match:
            year_filter = int(year_match.group(1))
        
        # Extract days back ONLY if mentioned
        days_back = None  # Let MCP use default
        
        # Import datetime for potential date parsing
        from datetime import datetime, timedelta
        
        # Check for specific day counts
        day_pattern = r'last\s+(\d+)\s+days?|past\s+(\d+)\s+days?|(\d+)\s+days?\s+(?:back|ago)'
        day_match = re.search(day_pattern, query_lower)
        if day_match:
            days_back = int(next(g for g in day_match.groups() if g))
        
        # Check for week/month patterns
        elif 'last week' in query_lower or 'past week' in query_lower:
            days_back = 7
        elif 'last 2 weeks' in query_lower or 'past 2 weeks' in query_lower:
            days_back = 14
        elif 'last month' in query_lower or 'past month' in query_lower:
            days_back = 30
        elif 'last 3 months' in query_lower or 'past 3 months' in query_lower:
            days_back = 90
        elif 'last 6 months' in query_lower or 'past 6 months' in query_lower:
            days_back = 180
        elif 'last year' in query_lower or 'past year' in query_lower:
            days_back = 365
        
        # Check for specific date ranges (e.g., "from January 1 to January 31")
        date_range_pattern = r'from\s+(\w+\s+\d{1,2})\s+to\s+(\w+\s+\d{1,2})'
        date_range_match = re.search(date_range_pattern, query_lower)
        if date_range_match:
            # For now, estimate days back based on current date
            # This is a simplified version - could be enhanced further
            try:
                # Rough estimation - could be enhanced with proper date parsing
                days_back = 30  # Default for date ranges
            except:
                pass
        
        # Store year-over-year flag for later use
        year_over_year = False
        if 'year over year' in query_lower or 'yoy' in query_lower or 'versus last year' in query_lower:
            year_over_year = True
        elif 'last year' in query_lower or '365 day' in query_lower:
            days_back = 365
        elif year_filter is not None and year_filter > 0:  # If specific year mentioned
            days_back = 0  # Don't apply days_back filter when year is specified
        
        # Build parameters based on tool - only include explicitly set values
        if tool_name == 'get_top_selling_items':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if year_filter is not None:
                params['year_filter'] = year_filter
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            return params
        
        elif tool_name == 'get_inventory_status':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            # Only set risk_level if explicitly mentioned
            if 'critical' in query_lower:
                params['risk_level'] = 'critical'
            elif 'high' in query_lower and 'risk' in query_lower:
                params['risk_level'] = 'high'
            elif 'medium' in query_lower and 'risk' in query_lower:
                params['risk_level'] = 'medium'
            elif 'low' in query_lower and 'risk' in query_lower:
                params['risk_level'] = 'low'
            if limit is not None:
                params['limit'] = limit
            # Add snapshot_date for inventory tools
            if snapshot_date:
                params['snapshot_date'] = snapshot_date
            return params
        
        elif tool_name == 'get_out_of_stock_items':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if limit is not None:
                params['limit'] = limit
            # Let MCP use its own default for min_sales_30d
            return params
        
        elif tool_name == 'get_overstock_items':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if limit is not None:
                params['limit'] = limit
            # Let MCP use its own default for days_supply_threshold
            # Add snapshot_date for inventory tools
            if snapshot_date:
                params['snapshot_date'] = snapshot_date
            return params
        
        elif tool_name == 'get_sales_trends':
            params = {}
            if days_back is not None:
                params['days_back'] = days_back
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            # Only set granularity if mentioned
            if 'daily' in query_lower:
                params['granularity'] = 'daily'
            elif 'weekly' in query_lower:
                params['granularity'] = 'weekly'
            elif 'monthly' in query_lower:
                params['granularity'] = 'monthly'
            return params
        
        elif tool_name == 'get_top_margin_items':
            params = {}
            if limit is not None:
                params['limit'] = limit
            if days_back is not None:
                params['days_back'] = days_back
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            # Let MCP use its own default for min_revenue
            return params
        
        elif tool_name == 'get_return_analysis':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            return params
        
        elif tool_name == 'get_comparison_analysis':
            # Extract store IDs from query using regex
            import re
            store_pattern = r'store\s+(\d+)'
            store_matches = re.findall(store_pattern, query_lower)
            
            # No defaults - require explicit store IDs
            store1_id = 0
            store2_id = 0
            
            # Assign found store IDs
            if len(store_matches) >= 1:
                store1_id = int(store_matches[0])
            if len(store_matches) >= 2:
                store2_id = int(store_matches[1])
            
            # If only one store specified, don't do comparison
            if store1_id > 0 and store2_id == 0:
                # Switch to top selling items for single store - this should be handled at calling level
                logger.info(f"Only one store specified ({store1_id}), using comparison with store2_id=0")
                store2_id = 0  # Set to 0 to handle in the comparison logic
                
            logger.info(f"Extracted store IDs: store1={store1_id}, store2={store2_id} from query: {query_lower}")
            
            # Extract limit for comparison (default 25)
            comparison_limit = 25
            if 'top' in query_lower:
                limit_match = re.search(r'top\s+(\d+)', query_lower)
                if limit_match:
                    comparison_limit = int(limit_match.group(1))
            
            params = {
                'store1_id': store1_id,
                'store2_id': store2_id
            }
            if days_back is not None:
                params['days_back'] = days_back
            if comparison_limit != 25:  # Only include if different from assumed default
                params['limit'] = comparison_limit
            return params
        
        # Add new tools
        elif tool_name == 'get_units_vs_dollars_comparison':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            return params
        
        elif tool_name == 'get_shop_performance':
            params = {}
            if shop_id is not None:
                params['shop_id'] = shop_id
            if store_id is not None:
                params['store_id'] = store_id
            if days_back is not None:
                params['days_back'] = days_back
            # Only set metric_focus if explicitly mentioned
            if 'margin' in query_lower:
                params['metric_focus'] = 'margin'
            elif 'units' in query_lower or 'quantity' in query_lower:
                params['metric_focus'] = 'units'
            # Let MCP use its own default for metric_focus if not specified
            return params
        
        elif tool_name == 'get_sell_through_rates':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            # Only override days_period if explicitly mentioned
            if days_back is not None:
                params['days_period'] = days_back
            # Let MCP use its own defaults
            return params
        
        elif tool_name == 'get_time_period_comparison':
            params = {}
            # Only set comparison_type if explicitly mentioned
            if 'year over year' in query_lower or 'yoy' in query_lower:
                params['comparison_type'] = 'yoy'
            elif 'week over week' in query_lower or 'wow' in query_lower:
                params['comparison_type'] = 'wow'
            elif 'weekday' in query_lower or 'weekend' in query_lower:
                params['comparison_type'] = 'weekday_weekend'
            # Let MCP use its default if not specified
            
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            
            # Only set aggregation if mentioned
            if 'daily' in query_lower:
                params['aggregation_level'] = 'daily'
            elif 'weekly' in query_lower:
                params['aggregation_level'] = 'weekly'
            elif 'shop' in query_lower and 'by shop' in query_lower:
                params['aggregation_level'] = 'shop'
            
            return params
        
        elif tool_name == 'get_inventory_risk_assessment':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            # Note: This tool doesn't support shop_id filtering
            # Only set min_priority_score if mentioned
            if 'high priority' in query_lower or 'critical' in query_lower:
                params['min_priority_score'] = 60
            elif 'medium priority' in query_lower:
                params['min_priority_score'] = 30
            # Only set include_overstocked if explicitly mentioned
            if 'exclude overstock' in query_lower or 'no overstock' in query_lower:
                params['include_overstocked'] = False
            # Note: This tool doesn't have a limit parameter
            return params
        
        elif tool_name == 'get_top_selling_item_comparison':
            # Extract store IDs for comparison
            store_pattern = r'store\s+(\d+)'
            store_matches = re.findall(store_pattern, query_lower)
            
            # Initialize store IDs
            store1_id = None
            store2_id = None
            
            # Special handling for known store names
            if 'fargo' in query_lower:
                store1_id = 64 if store1_id is None else store1_id
                if store2_id is None and store1_id != 64:
                    store2_id = 64
            if 'springfield' in query_lower:
                if store1_id is None:
                    store1_id = 78
                elif store2_id is None and store1_id != 78:
                    store2_id = 78
            
            # Extract numeric store IDs
            if len(store_matches) >= 1 and store1_id is None:
                store1_id = int(store_matches[0])
            if len(store_matches) >= 2 and store2_id is None:
                store2_id = int(store_matches[1])
            
            # Build parameters
            params = {}
            if store1_id is not None:
                params['store1_id'] = store1_id
            if store2_id is not None:
                params['store2_id'] = store2_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            
            logger.info(f"Extracted parameters for top_selling_item_comparison: {params}")
            return params
        
        elif tool_name == 'get_1Y_out_of_stock_items':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if limit is not None:
                params['limit'] = limit
            return params
        
        # Handle advanced tools with specific parameter requirements
        elif tool_name == 'get_advanced_vendor_metrics':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            # Note: This tool doesn't support shop_id parameter
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            # Snapshot date will be filtered by _filter_parameters_for_tool if not accepted
            if snapshot_date:
                params['snapshot_date'] = snapshot_date
            return params
        
        elif tool_name == 'get_advanced_forecast_accuracy':
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            # Note: This tool doesn't support limit parameter
            # Snapshot date will be filtered by _filter_parameters_for_tool if not accepted
            if snapshot_date:
                params['snapshot_date'] = snapshot_date
            return params
        
        # Handle OTB metrics tool specifically
        elif tool_name == 'get_otb_metrics':
            params = {}
            
            # Always include shop_id (use empty string for "all")
            if shop_id is not None and shop_id > 0:
                params['shop_id'] = str(shop_id)
            else:
                params['shop_id'] = ''  # Empty string for all shops
            
            # Extract store_id - use actual store ID or empty for all
            if store_id is not None and store_id > 0:
                params['store_id'] = str(store_id)
            else:
                params['store_id'] = ''  # Empty string for all stores
            
            # Always include metric_name (use empty string for "all")
            if 'otb goal' in query_lower:
                params['metric_name'] = 'OTB Goal'
            elif 'otb ordered' in query_lower:
                params['metric_name'] = 'OTB Ordered'
            elif 'otb remaining' in query_lower:
                params['metric_name'] = 'OTB Remaining'
            else:
                params['metric_name'] = ''  # Empty string for all metrics
            
            # Extract year - if not specified, use current year
            if year_filter is not None:
                params['year'] = year_filter
            else:
                # Default to current year for OTB metrics
                from datetime import datetime
                params['year'] = datetime.now().year
            
            return params
        
        # Handle other advanced tools
        elif tool_name.startswith('get_advanced_'):
            params = {}
            if store_id is not None:
                params['store_id'] = store_id
            if shop_id is not None:
                params['shop_id'] = shop_id
            if days_back is not None:
                params['days_back'] = days_back
            if limit is not None:
                params['limit'] = limit
            # Snapshot date will be filtered by _filter_parameters_for_tool if not accepted
            if snapshot_date:
                params['snapshot_date'] = snapshot_date
            return params
        
        # Fallback for unknown tools - only include explicitly set parameters
        params = {}
        if store_id is not None:
            params['store_id'] = store_id
        if shop_id is not None:
            params['shop_id'] = shop_id
        if limit is not None:
            params['limit'] = limit
        return params

    def chat(self, user_query, model_name=None, user_id=None, session_id=None, mcp_tool=None, snapshot_date=None):
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

        logger.info(f"Processing query: {user_query} (Explicit tool: {mcp_tool})")
        if snapshot_date:
            # Normalize the date format to ISO (YYYY-MM-DD)
            original_date = snapshot_date
            snapshot_date = self._normalize_date_format(snapshot_date)
            if original_date != snapshot_date:
                logger.info(f"📅 Normalized snapshot date from '{original_date}' to '{snapshot_date}'")
            else:
                logger.info(f"📅 Snapshot date provided: {snapshot_date}")

        # Use explicit tool if provided, otherwise map query to appropriate MCP tool
        if mcp_tool and mcp_tool in self.tools:
            tool_name = mcp_tool
            parameters = self._extract_parameters_from_query(user_query, tool_name, snapshot_date)
            logger.info(f"Using explicitly selected tool: {tool_name}")
        else:
            # Map query to appropriate MCP tool
            tool_name, parameters = self._map_query_to_tool(user_query, snapshot_date)
        
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
            
            # Log parameters for debugging
            logger.info(f"Calling MCP tool '{tool_name}' with parameters: {json.dumps(parameters, indent=2)}")
            
            # Special logging for snapshot_date
            if 'snapshot_date' in parameters:
                logger.info(f"🗓️ SNAPSHOT DATE PASSED: {parameters['snapshot_date']}")
            else:
                logger.info(f"📅 NO SNAPSHOT DATE in parameters for tool: {tool_name}")
            
            # Filter parameters to only include those accepted by the tool
            parameters = self._filter_parameters_for_tool(parameters, tool_name)
            logger.info(f"Filtered parameters for {tool_name}: {json.dumps(parameters, indent=2)}")
            
            # Call the tool with extracted parameters with retry logic
            max_retries = 3
            retry_delay = 1  # seconds
            result = None
            
            for attempt in range(max_retries):
                try:
                    result = tool(**parameters)
                    break  # Success! Exit the retry loop
                except Exception as tool_error:
                    error_msg = str(tool_error)
                    
                    # Check for 503 Service Unavailable errors
                    if '503' in error_msg and 'text/plain' in error_msg:
                        logger.warning(f"MCP Toolbox server unavailable (503) - attempt {attempt + 1}/{max_retries}: {error_msg}")
                        
                        if attempt < max_retries - 1:
                            # Wait before retrying
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            # Final attempt failed
                            logger.error(f"MCP Toolbox server unavailable after {max_retries} attempts")
                            return {
                                'success': False,
                                'error': 'MCP Toolbox server is temporarily unavailable. Please try again later.',
                                'technical_error': error_msg,
                                'tool_name': tool_name,
                                'parameters': parameters,
                                'query_id': query_id,
                                'suggestion': 'The MCP Toolbox server appears to be down. Please contact support if this persists.'
                            }
                    
                    # Check for JSON decode errors
                    elif 'JSON' in error_msg and 'decode' in error_msg:
                        logger.error(f"MCP Toolbox response format error: {error_msg}")
                        # Don't retry JSON errors - they're likely not transient
                        return {
                            'success': False,
                            'error': 'Received unexpected response format from MCP Toolbox.',
                            'technical_error': error_msg,
                            'tool_name': tool_name,
                            'parameters': parameters,
                            'query_id': query_id,
                            'suggestion': 'The server returned an invalid response. Please contact support.'
                        }
                    
                    # For other errors, don't retry
                    else:
                        raise
            
            # Check if we got a result
            if result is None:
                logger.error("Failed to get result from MCP tool after all retries")
                return {
                    'success': False,
                    'error': 'Failed to execute MCP tool after multiple attempts',
                    'tool_name': tool_name,
                    'parameters': parameters,
                    'query_id': query_id
                }
            
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
            # Keep raw data for calculations
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
            
            # Skip auto-summary for lazy loading - will be done via separate endpoint
            auto_summary = None
            summary_error = None
            execution_times['summary_generation_ms'] = 0
            
            # Store query context for later summary generation
            self.last_query_context = {
                'query_id': query_id,
                'user_query': user_query,
                'tool_name': tool_name,
                'parameters': parameters,
                'execution_time': execution_time,
                'df': df,
                'model_name': model_name
            }
            
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
            
            # Add to local query history as fallback
            self._add_to_local_history({
                'query_id': query_id,
                'timestamp': pd.Timestamp.now().isoformat(),
                'user_query': user_query,
                'model_name': f"mcp_{tool_name}",
                'success': True,
                'error_message': None,
                'row_count': len(df),
                'execution_time_ms': execution_times.get('total_ms', 0),
                'tool_name': tool_name,
                'parameters': parameters,
                'user_id': user_id or "anonymous",
                'session_id': session_id or "default"
            })
            
            # Extract summary statistics before formatting
            summary_stats = self._extract_summary_statistics(df)
            
            # Format results for return
            # Format only for display
            formatted_results = self._format_results(df)
            
            # Keep raw data for calculations and LLM
            raw_data = df.to_dict('records')
            
            response = {
                'success': True,
                'error': None,
                'sql': f"[MCP Tool: {tool_name}]",
                'results': formatted_results,  # Formatted for display
                'results_data': raw_data,  # Raw data for calculations
                'row_count': len(df),
                'has_data': True,
                'query_id': query_id,
                'execution_times': execution_times,
                'estimated_cost': 0.0,  # MCP tools don't have direct costs
                'total_session_cost': self.total_cost,
                'toolbox_used': True,
                'tool_name': tool_name,
                'parameters': parameters,
                'summary_statistics': summary_stats  # Add summary stats separately
            }
            
            # Indicate summary is pending (will be loaded lazily)
            response['summary_pending'] = True
            response['auto_summary'] = None
            
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
            
            # Add to local query history as fallback
            self._add_to_local_history({
                'query_id': query_id,
                'timestamp': pd.Timestamp.now().isoformat(),
                'user_query': user_query,
                'model_name': f"mcp_{tool_name}",
                'success': False,
                'error_message': str(e),
                'row_count': None,
                'execution_time_ms': execution_times.get('total_ms', 0),
                'tool_name': tool_name,
                'parameters': parameters,
                'user_id': user_id or "anonymous",
                'session_id': session_id or "default"
            })
            
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
            
            # Don't apply formatting here - keep raw data for calculations
            # Formatting should only happen for display
            return df
            
        except Exception as e:
            logger.error(f"Failed to process MCP result: {str(e)}")
            return None

    def _convert_raw_result_to_dataframe(self, result: Any, tool_name: str) -> Optional[pd.DataFrame]:
        """Convert raw MCP result to DataFrame (existing logic)"""
        # Handle string results (JSON format)
        if isinstance(result, str):
            try:
                # Debug logging for OTB tool
                if tool_name == 'get_otb_metrics':
                    logger.info(f"OTB raw string result (first 500 chars): {result[:500]}")
                
                # Parse JSON string
                data = json.loads(result)
                if isinstance(data, list):
                    df = pd.DataFrame(data)
                    logger.info(f"Created DataFrame from JSON string with shape: {df.shape}")
                    
                    # Basic type conversion for numeric fields
                    for col in df.columns:
                        if col in ['total_units', 'total_cost', 'transaction_count', 'unique_skus', 'unique_customers', 
                                  'store_id', 'shop_id', 'current_oh_units', 'oh_units', 'ending_units', 'beginning_units',
                                  'units_sold', 'units_sold_30d', 'units_sold_90d', 'units_sold_7d', 'avg_on_hand', 
                                  'avg_inventory_units', 'current_units', 'total_units_on_hand']:
                            try:
                                df[col] = pd.to_numeric(df[col])
                            except:
                                pass
                        elif col in ['total_revenue', 'total_margin', 'margin_pct', 'avg_transaction_value', 'retail_value', 
                                    'current_on_hand', 'value', 'cost_value', 'retail_extension', 'cost_extension',
                                    'ending_retail', 'beginning_retail', 'inventory_cost', 'avg_inventory_value',
                                    'avg_inventory_cost', 'total_inventory_value']:
                            try:
                                # Handle fraction strings like "98833/25"
                                df[col] = df[col].apply(lambda x: eval(x) if isinstance(x, str) and '/' in x else float(x))
                            except:
                                pass
                        elif col in ['sale_date', 'snapshot_date', 'date_month']:
                            try:
                                df[col] = pd.to_datetime(df[col])
                            except:
                                pass
                    
                    return df
                else:
                    df = pd.DataFrame([data])
                    logger.info(f"Created single-row DataFrame from JSON object")
                    return df
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON string result: {e}")
                logger.error(f"Raw result type: {type(result)}, content: {str(result)[:200]}")
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
        
        # First, identify and remove summary statistics columns if they exist
        summary_columns_to_drop = []
        if len(formatted_df) > 1:
            summary_patterns = [
                'total_items', 'grand_total', 'avg_margin_pct_all',
                'total_qualifying', 'star_performers', 'critical_items',
                'total_oos', 'total_overstock', 'total_at_risk',
                'overall_avg', 'total_analyzed', 'total_units_on_hand',
                'total_retail_value', 'total_cost_value', 'value_at_risk',
                'dead_stock', 'severe_overstock', 'high_risk',
                'out_of_stock_count', 'overstock_count', 'avg_days_oos'
            ]
            
            for col in formatted_df.columns:
                col_lower = str(col).lower()
                if any(pattern in col_lower for pattern in summary_patterns):
                    # Check if all values are the same (indicating a summary stat)
                    unique_values = formatted_df[col].dropna().unique()
                    if len(unique_values) == 1:
                        summary_columns_to_drop.append(col)
            
            # Drop summary columns from the main results
            if summary_columns_to_drop:
                formatted_df = formatted_df.drop(columns=summary_columns_to_drop)
                logger.info(f"Removed {len(summary_columns_to_drop)} summary statistic columns from results")
        
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
            col_lower = str(col).lower()
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
            col_lower = str(col).lower()
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
            col_lower = str(col).lower()
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
        
        # Identify summary statistics columns (these have the same value for all rows)
        summary_columns = []
        if len(df) > 1:
            for col in df.columns:
                # Check if all non-null values in the column are the same
                unique_values = df[col].dropna().unique()
                if len(unique_values) == 1 and col not in priority_columns:
                    # Additional check for known summary column patterns
                    col_lower = str(col).lower()
                    if any(pattern in col_lower for pattern in [
                        'total_items', 'grand_total', 'avg_margin_pct_all',
                        'total_qualifying', 'star_performers', 'critical_items',
                        'total_oos', 'total_overstock', 'total_at_risk',
                        'overall_avg', 'total_analyzed', 'total_units_on_hand',
                        'total_retail_value', 'total_cost_value'
                    ]):
                        summary_columns.append(col)
        
        # Get existing columns in priority order
        ordered_columns = []
        for col in priority_columns:
            if col in df.columns:
                ordered_columns.append(col)
        
        # Add remaining columns (excluding summary columns)
        remaining_columns = [col for col in df.columns 
                           if col not in ordered_columns and col not in summary_columns]
        
        # Put summary columns at the end
        final_order = ordered_columns + remaining_columns + summary_columns
        
        return df[final_order]

    def _extract_summary_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract summary statistics that are repeated in every row"""
        summary_stats = {}
        
        if df is None or df.empty or len(df) < 2:
            return summary_stats
        
        # Known summary statistic column patterns
        summary_patterns = [
            'total_items', 'grand_total', 'avg_margin_pct_all',
            'total_qualifying', 'star_performers', 'critical_items',
            'total_oos', 'total_overstock', 'total_at_risk',
            'overall_avg', 'total_analyzed', 'total_units_on_hand',
            'total_retail_value', 'total_cost_value', 'value_at_risk',
            'dead_stock', 'severe_overstock', 'high_risk',
            'out_of_stock_count', 'overstock_count', 'avg_days_oos'
        ]
        
        for col in df.columns:
            col_lower = str(col).lower()
            # Check if column matches known summary patterns
            if any(pattern in col_lower for pattern in summary_patterns):
                # Verify all values are the same
                unique_values = df[col].dropna().unique()
                if len(unique_values) == 1:
                    value = unique_values[0]
                    # Format the value appropriately
                    if pd.api.types.is_numeric_dtype(df[col]):
                        if 'pct' in col_lower or 'percent' in col_lower:
                            summary_stats[col] = f"{value:.1f}%"
                        elif 'revenue' in col_lower or 'value' in col_lower or 'cost' in col_lower or 'margin' in col_lower:
                            summary_stats[col] = f"${value:,.2f}"
                        elif pd.api.types.is_integer_dtype(df[col]) or value == int(value):
                            summary_stats[col] = f"{int(value):,}"
                        else:
                            summary_stats[col] = f"{value:,.2f}"
                    else:
                        summary_stats[col] = str(value)
        
        return summary_stats

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
        
        # Apply smart formatting for display only
        display_df = self._apply_smart_formatting(df.head(preview_rows), self.last_tool_used)
        results = display_df.to_dict('records')
        
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

    def generate_summary_for_last_query(self, model_name: str = None) -> Dict[str, Any]:
        """Generate summary for the last query context (for lazy loading)"""
        try:
            if not hasattr(self, 'last_query_context') or not self.last_query_context:
                return {
                    'success': False,
                    'error': 'No query context available'
                }
            
            context = self.last_query_context
            df = context.get('df')
            user_query = context.get('user_query', '')
            tool_name = context.get('tool_name', '')
            execution_time = context.get('execution_time', 0)
            
            if df is None or len(df) == 0:
                return {
                    'success': False,
                    'error': 'No data available for summary'
                }
            
            # Use provided model or the one from context
            summary_model = model_name or context.get('model_name') or self.config.model_name
            
            # Create toolbox context for enhanced summary
            toolbox_context = {
                'tool_name': tool_name,
                'toolbox_used': True,
                'execution_method': 'MCP Toolbox',
                'parameters': context.get('parameters', {}),
                'execution_time_ms': execution_time
            }
            
            # Generate summary
            summary = generate_summary(
                df, 
                user_query, 
                summary_model, 
                self.available_models, 
                self.api_clients, 
                self.bigquery_utils,
                toolbox_context=toolbox_context
            )
            
            return {
                'success': True,
                'summary': summary,
                'model_used': summary_model,
                'query_id': context.get('query_id')
            }
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
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
    
    def _add_to_local_history(self, query_data: Dict[str, Any]):
        """Add query to local history (used as fallback when BigQuery is unavailable)"""
        try:
            # Keep only the last 100 queries in memory
            if len(self.local_query_history) >= 100:
                self.local_query_history.pop(0)
            
            self.local_query_history.append(query_data)
            logger.debug(f"Added query {query_data['query_id']} to local history")
        except Exception as e:
            logger.error(f"Failed to add query to local history: {e}")
    
    def get_local_query_history(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get query history from local storage (fallback for when BigQuery is unavailable)"""
        try:
            # First try to get from BigQuery
            try:
                bq_history = self.bigquery_utils.get_query_history(user_id, limit)
                if bq_history:
                    logger.info(f"Retrieved {len(bq_history)} queries from BigQuery")
                    return bq_history
            except Exception as e:
                logger.warning(f"Failed to get history from BigQuery, using local: {e}")
            
            # Fall back to local history
            history = self.local_query_history.copy()
            
            # Filter by user_id if provided
            if user_id:
                history = [q for q in history if q.get('user_id') == user_id]
            
            # Sort by timestamp descending (most recent first)
            history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            # Limit results
            return history[:limit]
        except Exception as e:
            logger.error(f"Failed to get local query history: {e}")
            return []
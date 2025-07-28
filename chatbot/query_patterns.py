import re
from .config import get_shop_mappings

def _init_query_patterns():
    """Initialize common query patterns and their SQL templates"""
    return {
        'top_selling': {
            'keywords': ['top', 'best', 'highest selling', 'most popular'],
            'template': 'SELECT {columns} FROM {tables} WHERE {conditions} GROUP BY {group_by} ORDER BY SUM(fs.quantity) DESC LIMIT {limit}',
            'tool_mapping': 'get_top_selling_items'
        },
        'comparison': {
            'keywords': ['compare', 'versus', 'vs', 'difference between'],
            'template': 'WITH period1 AS ({query1}), period2 AS ({query2}) SELECT * FROM period1 JOIN period2',
            'tool_mapping': 'get_comparison_analysis'
        },
        'trend': {
            'keywords': ['trend', 'over time', 'monthly', 'weekly', 'daily'],
            'template': 'SELECT {time_period}, {metrics} FROM {tables} WHERE {conditions} GROUP BY {time_period} ORDER BY {time_period}',
            'tool_mapping': 'get_sales_trends'
        },
        'margin_analysis': {
            'keywords': ['margin', 'profit', 'markup'],
            'template': 'SELECT {columns}, SAFE_DIVIDE(SUM(fs.price_extended) - SUM(fs.cogs_extended), SUM(fs.price_extended)) as margin_pct FROM {tables} WHERE {conditions} GROUP BY {group_by}',
            'tool_mapping': 'get_top_margin_items'
        },
        'inventory_analysis': {
            'keywords': ['inventory', 'on hand', 'stock', 'overstock', 'out of stock'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_inventory_snapshots` WHERE {conditions}',
            'tool_mapping': 'get_inventory_status'
        },
        'return_analysis': {
            'keywords': ['return', 'returns', 'returned', 'return rate', 'defective', 'exchange'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_sales_returns` WHERE {conditions}',
            'tool_mapping': 'get_return_analysis'
        },
        'out_of_stock': {
            'keywords': ['out of stock', 'oos', 'stockout', 'no inventory', 'zero inventory'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_inventory_snapshots` WHERE oh_units = 0',
            'tool_mapping': 'get_out_of_stock_items'
        },
        'overstock': {
            'keywords': ['overstock', 'excess inventory', 'too much stock', 'overstocked'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_inventory_snapshots` WHERE {conditions}',
            'tool_mapping': 'get_overstock_items'
        }
    }

def extract_intent(query: str) -> dict:
    """Extract intent and parameters from user query with MCP Toolbox tool mapping"""
    query_lower = query.lower()
    
    # Base intent structure - ensure all keys exist for backward compatibility
    intent = {
        'metrics': [],
        'dimensions': [],
        'filters': [],
        'time_period': None,
        'comparison': False,
        'ranking': None,
        'limit': 10,
        'chart_type': None,
        'time_series': False,
        'distribution': False,
        'inventory_focus': False,
        'return_focus': False,
        'tool_mapping': None,  # New field for MCP Toolbox integration
        'tool_parameters': {},  # New field for tool-specific parameters
        'toolbox_priority': False  # Whether to prefer toolbox over SQL generation
    }
    
    # Initialize query patterns for tool mapping
    patterns = _init_query_patterns()
    
    # Extract metrics
    metric_keywords = {
        'sales': ['sales', 'revenue', 'dollars'],
        'units': ['units', 'quantity', 'items sold', 'pieces'],
        'margin': ['margin', 'profit', 'markup'],
        'transactions': ['transactions', 'orders', 'receipts'],
        'inventory': ['inventory', 'on hand', 'oh', 'stock', 'in stock'],
        'days_supply': ['days of supply', 'dos', 'stock turn', 'turnover'],
        'out_of_stock': ['out of stock', 'oos', 'stockout', 'no inventory'],
        'overstock': ['overstock', 'excess', 'too much', 'overstocked'],
        'returns': ['return', 'returns', 'returned', 'return rate', 'defective', 'exchange'],
        'return_rate': ['return rate', 'return percentage', 'return ratio']
    }
    
    for metric, keywords in metric_keywords.items():
        if any(kw in query_lower for kw in keywords):
            intent['metrics'].append(metric)
            if metric in ['inventory', 'days_supply', 'out_of_stock', 'overstock']:
                intent['inventory_focus'] = True
            elif metric in ['returns', 'return_rate']:
                intent['return_focus'] = True
    
    # Extract dimensions
    if any(word in query_lower for word in ['style', 'styles']):
        intent['dimensions'].append('style')
    if any(word in query_lower for word in ['shop', 'division', 'department']):
        intent['dimensions'].append('shop')
    if any(word in query_lower for word in ['store', 'location']):
        intent['dimensions'].append('store')
    if any(word in query_lower for word in ['category', 'class', 'subclass']):
        intent['dimensions'].append('category')
    if any(word in query_lower for word in ['brand', 'vendor']):
        intent['dimensions'].append('brand')
    if any(word in query_lower for word in ['customer', 'customers']):
        intent['dimensions'].append('customer')
    if any(word in query_lower for word in ['return type', 'return reason']):
        intent['dimensions'].append('return_type')
    
    # Extract ranking
    if 'top' in query_lower or 'best' in query_lower:
        intent['ranking'] = 'top'
    elif 'bottom' in query_lower or 'worst' in query_lower:
        intent['ranking'] = 'bottom'
    
    # Extract limit
    limit_match = re.search(r'top (\d+)|bottom (\d+)|(\d+) best|(\d+) worst', query_lower)
    if limit_match:
        intent['limit'] = int(next(g for g in limit_match.groups() if g))
    
    # Detect comparison
    if any(word in query_lower for word in ['compare', 'versus', 'vs', 'difference']):
        intent['comparison'] = True
    
    # Detect time series
    if any(word in query_lower for word in ['trend', 'over time', 'by month', 'by week', 'by day', 'monthly', 'weekly', 'daily', 'timeline']):
        intent['time_series'] = True
    
    # Detect distribution
    if any(word in query_lower for word in ['distribution', 'breakdown', 'proportion', 'percentage of', 'share', 'composition']):
        intent['distribution'] = True
    
    # NEW: Map intent to MCP Toolbox tools
    intent['tool_mapping'], intent['tool_parameters'] = map_intent_to_tool(intent, query, patterns)
    
    # Determine if toolbox should be prioritized
    intent['toolbox_priority'] = should_use_toolbox(intent, query)
    
    # Determine chart type
    if intent['return_focus'] and intent['time_series']:
        intent['chart_type'] = 'line'
    elif intent['return_focus'] and 'store' in intent['dimensions']:
        intent['chart_type'] = 'bar'
    elif intent['inventory_focus'] and intent.get('comparison'):
        intent['chart_type'] = 'scatter'
    elif intent['inventory_focus'] and 'store' in intent['dimensions']:
        intent['chart_type'] = 'heatmap'
    elif intent['time_series']:
        intent['chart_type'] = 'line'
    elif intent['distribution'] and intent['limit'] <= 8:
        intent['chart_type'] = 'pie'
    elif intent['comparison'] and len(intent['metrics']) > 1:
        intent['chart_type'] = 'grouped_bar'
    elif 'scatter' in query_lower or 'correlation' in query_lower:
        intent['chart_type'] = 'scatter'
    elif intent['ranking']:
        intent['chart_type'] = 'bar'
    else:
        intent['chart_type'] = 'bar'
    
    return intent

def map_intent_to_tool(intent: dict, query: str, patterns: dict) -> tuple:
    """
    Map extracted intent to appropriate MCP Toolbox tool and extract parameters
    
    Args:
        intent: Intent dictionary from extract_intent()
        query: Original user query
        patterns: Query patterns with tool mappings
        
    Returns:
        Tuple of (tool_name, parameters)
    """
    query_lower = query.lower()
    tool_name = None
    parameters = {
        'limit': intent.get('limit', 10),
        'conditions': [],
        'time_period': intent.get('time_period'),
    }
    
    # Extract common parameters
    parameters.update(extract_query_conditions(query, intent))
    
    # Match patterns to determine tool
    if intent.get('inventory_focus'):
        if 'out_of_stock' in intent.get('metrics', []) or any(kw in query_lower for kw in ['out of stock', 'oos', 'stockout']):
            tool_name = 'get_out_of_stock_items'
        elif 'overstock' in intent.get('metrics', []) or any(kw in query_lower for kw in ['overstock', 'excess']):
            tool_name = 'get_overstock_items'
        elif any(kw in query_lower for kw in ['reorder', 'priority', 'risk']):
            tool_name = 'get_inventory_priority_analysis'
        else:
            tool_name = 'get_inventory_status'
            
    elif intent.get('return_focus'):
        if intent.get('time_series'):
            tool_name = 'get_return_trends'
        elif 'store' in intent.get('dimensions', []):
            tool_name = 'get_return_analysis_by_store'
        elif any(kw in query_lower for kw in ['customer', 'customers']):
            tool_name = 'get_customer_return_analysis'
        else:
            tool_name = 'get_return_analysis'
            
    elif intent.get('ranking') == 'top':
        if 'sales' in intent.get('metrics', []) or 'revenue' in intent.get('metrics', []):
            tool_name = 'get_top_selling_items'
        elif 'margin' in intent.get('metrics', []):
            tool_name = 'get_top_margin_items'
        elif 'units' in intent.get('metrics', []):
            tool_name = 'get_top_volume_items'
            
    elif intent.get('comparison'):
        tool_name = 'get_comparison_analysis'
        parameters['comparison_type'] = determine_comparison_type(query, intent)
        
    elif intent.get('time_series'):
        if intent.get('return_focus'):
            tool_name = 'get_return_trends'
        else:
            tool_name = 'get_sales_trends'
            
    # Fallback based on primary metrics
    elif not tool_name:
        if any(metric in intent.get('metrics', []) for metric in ['sales', 'revenue']):
            tool_name = 'get_sales_analysis'
        elif 'margin' in intent.get('metrics', []):
            tool_name = 'get_margin_analysis'
        elif 'transactions' in intent.get('metrics', []):
            tool_name = 'get_transaction_analysis'
    
    # Add tool-specific parameters
    if tool_name:
        parameters.update(get_tool_specific_parameters(tool_name, query, intent))
    
    return tool_name, parameters

def extract_query_conditions(query: str, intent: dict) -> dict:
    """
    Extract filtering conditions from the user query
    
    Args:
        query: Original user query
        intent: Extracted intent
        
    Returns:
        Dictionary of extracted conditions
    """
    conditions = {}
    query_lower = query.lower()
    
    # Store filters
    if 'fargo' in query_lower:
        conditions['store_filter'] = 'store_id = 64'
        conditions['store_name'] = 'Fargo'
    elif 'springfield' in query_lower:
        conditions['store_filter'] = 'store_id = 65'
        conditions['store_name'] = 'Springfield'
    
    # Shop/division filters  
    shop_mappings = get_shop_mappings()
    for shop_name, (div_num, desc) in shop_mappings.items():
        if shop_name in query_lower:
            conditions['shop_filter'] = f'division_number = "{div_num}"'
            conditions['shop_name'] = shop_name
            conditions['division_number'] = div_num
            break
    
    # Date range filters
    if 'last 30 days' in query_lower:
        conditions['date_filter'] = 'last_30_days'
        conditions['days_back'] = 30
    elif 'last week' in query_lower:
        conditions['date_filter'] = 'last_7_days'
        conditions['days_back'] = 7
    elif 'this month' in query_lower:
        conditions['date_filter'] = 'current_month'
    elif 'last month' in query_lower:
        conditions['date_filter'] = 'previous_month'
    elif 'ytd' in query_lower or 'year to date' in query_lower:
        conditions['date_filter'] = 'year_to_date'
    
    # Style/SKU filters
    style_match = re.search(r'style\s+([A-Za-z0-9\-_]+)', query_lower)
    if style_match:
        conditions['style_filter'] = style_match.group(1)
        conditions['style'] = style_match.group(1)
    
    # Brand/vendor filters
    brand_match = re.search(r'(?:brand|vendor)\s+([A-Za-z\s]+?)(?:\s|$)', query_lower)
    if brand_match:
        conditions['brand_filter'] = brand_match.group(1).strip()
        conditions['brand'] = brand_match.group(1).strip()
    
    # Category filters
    category_keywords = ['shoes', 'apparel', 'hunting', 'golf', 'camping', 'bikes']
    for category in category_keywords:
        if category in query_lower:
            conditions['category_filter'] = category
            conditions['category'] = category
            break
    
    # Minimum thresholds
    min_sales_match = re.search(r'minimum\s+\$?(\d+)', query_lower)
    if min_sales_match:
        conditions['min_sales'] = int(min_sales_match.group(1))
    
    return conditions

def get_tool_specific_parameters(tool_name: str, query: str, intent: dict) -> dict:
    """
    Get tool-specific parameters based on the tool being used
    
    Args:
        tool_name: Name of the MCP Toolbox tool
        query: Original user query
        intent: Extracted intent
        
    Returns:
        Dictionary of tool-specific parameters
    """
    params = {}
    query_lower = query.lower()
    
    if tool_name == 'get_inventory_status':
        params['include_zero_stock'] = 'zero' in query_lower or 'empty' in query_lower
        params['include_vendor_info'] = 'vendor' in query_lower or 'brand' in query_lower
        params['snapshot_type'] = 'latest'  # or 'historical' based on query
        
    elif tool_name == 'get_out_of_stock_items':
        params['include_recent_sales'] = True
        params['days_lookback'] = 30
        params['min_historical_sales'] = 1
        
    elif tool_name == 'get_overstock_items':
        # Extract days of supply threshold
        dos_match = re.search(r'(\d+)\s*days?\s*(?:of\s*)?supply', query_lower)
        if dos_match:
            params['min_days_supply'] = int(dos_match.group(1))
        else:
            params['min_days_supply'] = 90  # default threshold
            
    elif tool_name == 'get_top_selling_items':
        params['metric'] = 'revenue' if 'dollar' in query_lower or 'revenue' in query_lower else 'units'
        params['include_margin'] = 'margin' in query_lower or 'profit' in query_lower
        
    elif tool_name == 'get_sales_trends':
        if 'daily' in query_lower:
            params['time_grain'] = 'day'
        elif 'weekly' in query_lower:
            params['time_grain'] = 'week'
        elif 'monthly' in query_lower:
            params['time_grain'] = 'month'
        else:
            params['time_grain'] = 'week'  # default
            
    elif tool_name == 'get_return_analysis':
        params['include_return_reasons'] = 'reason' in query_lower or 'type' in query_lower
        params['include_customer_info'] = 'customer' in query_lower
        params['link_to_original_sales'] = True
        
    elif tool_name == 'get_comparison_analysis':
        params['comparison_periods'] = extract_comparison_periods(query)
        
    return params

def determine_comparison_type(query: str, intent: dict) -> str:
    """
    Determine the type of comparison being requested
    
    Args:
        query: Original user query
        intent: Extracted intent
        
    Returns:
        String indicating comparison type
    """
    query_lower = query.lower()
    
    if any(period in query_lower for period in ['month', 'year', 'quarter', 'week']):
        return 'time_period'
    elif any(location in query_lower for location in ['store', 'location', 'city']):
        return 'store'
    elif any(product in query_lower for product in ['style', 'brand', 'category', 'shop']):
        return 'product'
    else:
        return 'general'

def extract_comparison_periods(query: str) -> list:
    """
    Extract comparison periods from the query
    
    Args:
        query: Original user query
        
    Returns:
        List of time periods for comparison
    """
    periods = []
    query_lower = query.lower()
    
    # Look for specific month/year combinations
    month_year_matches = re.findall(r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})', query_lower)
    for month, year in month_year_matches:
        periods.append(f"{month}_{year}")
    
    # Look for relative periods
    if 'this month' in query_lower and 'last month' in query_lower:
        periods.extend(['current_month', 'previous_month'])
    elif 'this year' in query_lower and 'last year' in query_lower:
        periods.extend(['current_year', 'previous_year'])
    
    return periods if periods else ['current_month', 'previous_month']  # default

def should_use_toolbox(intent: dict, query: str) -> bool:
    """
    Determine if MCP Toolbox should be prioritized over SQL generation
    
    Args:
        intent: Extracted intent
        query: Original user query
        
    Returns:
        Boolean indicating whether to prefer toolbox
    """
    # Prioritize toolbox for these scenarios
    toolbox_priority_conditions = [
        # Standard retail analytics queries
        intent.get('inventory_focus') and intent.get('tool_mapping'),
        intent.get('return_focus') and intent.get('tool_mapping'),
        intent.get('ranking') and intent.get('tool_mapping'),
        
        # Complex analysis that benefits from pre-built tools
        'analysis' in query.lower(),
        'priority' in query.lower(),
        'risk' in query.lower(),
        
        # Performance-sensitive queries
        intent.get('limit', 0) <= 100,  # Small result sets
        len(intent.get('dimensions', [])) <= 2,  # Simple grouping
    ]
    
    # Don't use toolbox for these scenarios
    toolbox_avoid_conditions = [
        # Complex custom queries
        'custom' in query.lower(),
        'specific' in query.lower() and 'formula' in query.lower(),
        
        # Ad-hoc analysis
        len(query.split()) > 20,  # Very long, complex queries
        'calculate' in query.lower() and 'custom' in query.lower(),
    ]
    
    # Return decision
    if any(toolbox_avoid_conditions):
        return False
    
    return any(toolbox_priority_conditions)

def get_enhanced_schema_prompt():
    """Get the enhanced schema prompt with returns analysis capabilities and MCP Toolbox context"""
    shop_mappings = get_shop_mappings()
    division_mappings_str = ""
    example_shops = ['mens shoes', 'hunting', 'golf', 'womens fashion', 'tools']
    mappings = []
    for shop in example_shops:
        if shop in shop_mappings:
            div_num, desc = shop_mappings[shop]
            mappings.append(f"- '{shop}' → division_number = '{div_num}' ({desc})")
    division_mappings_str = "\n        ".join(mappings)
    
    store_mappings_str = ""
    mappings = []
    mappings.append("- Fargo: 64")
    mappings.append("- Springfield: 65")
    store_mappings_str = "\n        ".join(mappings)
    
    return f"""
    You are Super Gemini, an advanced retail analyst AI that converts natural language to BigQuery SQL.
    You understand complex retail queries and can handle various ways users might ask questions.
    
    NOTE: This system now includes MCP Toolbox integration for common retail analytics queries.
    If a query matches a standard pattern, it may be handled by pre-built tools instead of SQL generation.
    However, you should still be prepared to generate SQL for custom or complex queries.
    
    SCHEMA - EXACT FIELD PATHS (DO NOT DEVIATE):
    
    Main table: `sis-data-marts.warehouse.fct_sales` (fs)
    - transaction_datetime (TIMESTAMP) - for date filtering
    - price_extended (FLOAT) - retail dollars
    - cogs_extended (FLOAT) - cost of goods
    - quantity (FLOAT) - units sold
    - sku_id (STRING) - product ID
    - store_id (INTEGER) - store ID (joins to dim_stores.dim_store_id)
    
    SKU table: `sis-data-marts.warehouse.dim_skus` (skus)
    Join: fs.sku_id = skus.dim_sku_id
    - specialty_shop (NUMERIC) - shop number (e.g., 3 for Bikes, 17 for Camping, etc.)
    - as400_data.sku_description (STRING) - product name/description
    - as400_data.sku_description2 (STRING) - additional description
    - as400_data.class_subclass_description (STRING) - category (e.g., "Men's Shoes", "Women's Apparel")
    - as400_data.style (STRING) - style number/code
    - as400_data.vendor_name1 (STRING) - primary vendor/brand
    - as400_data.division_number (STRING) - division number (different from shop)
    - as400_data.specialty_shop_description (STRING) - shop name
    - as400_data.rate1_year (STRING) - year rating (1=2021, 2=2022, 3=2023, 4=2024, 5=2025)
    - as400_data.rate1_season (STRING) - season code
    - as400_data.team_description (STRING) - for sports merchandise
    - as400_data.color__size (STRING) - color and size info
    
    Store table: `sis-data-marts.warehouse.dim_stores` (st)
    Join: fs.store_id = st.dim_store_id
    - dim_store_id (INTEGER) - store ID
    - name (STRING) - full store name like "Springfield Scheels"
    - short_name (STRING) - abbreviated like "SP"
    - city (STRING) - city name
    - state (STRING) - state abbreviation (IA, ND, MN, etc.)
    
    *** CRITICAL: VENDOR FIELD HANDLING ***
    The product_details struct in mart_inventory_snapshots does NOT contain vendor_name.
    For vendor information in inventory queries, you must:
    
    OPTION 1 - Join with dim_skus for vendor info:
    SELECT 
        inv.sku_number,
        inv.product_details.sku_description,
        skus.as400_data.vendor_name1 as vendor_name,  -- Get vendor from dim_skus
        inv.oh_units
    FROM `sis-data-marts.data_marts.mart_inventory_snapshots` inv
    LEFT JOIN `sis-data-marts.warehouse.dim_skus` skus ON inv.sku_number = skus.dim_sku_id
    
    OPTION 2 - Exclude vendor from inventory-only queries:
    SELECT 
        inv.sku_number,
        inv.product_details.sku_description,
        -- DO NOT include vendor_name in inventory-only queries
        inv.oh_units
    FROM `sis-data-marts.data_marts.mart_inventory_snapshots` inv
    
    *** FIELD PATH CORRECTIONS ***:
    - ✅ CORRECT: inv.product_details.sku_description (exists)
    - ✅ CORRECT: inv.product_details.sku_description2 (exists)
    - ✅ CORRECT: inv.product_details.style (exists)
    - ❌ NEVER USE: inv.product_details.vendor_name (DOES NOT EXIST)
    - ❌ NEVER USE: inv.vendor1.vendor_name (DOES NOT EXIST)
    - ✅ FOR VENDOR: Join with dim_skus and use skus.as400_data.vendor_name1
    
    IMPORTANT RULES:
    - When user says "shop X", use skus.specialty_shop = X (numeric, no quotes)
    - When user says "division X", use skus.as400_data.division_number = 'X' (string, with quotes)
    - Always include margin calculations when showing sales metrics
    - Use table aliases consistently (fs, skus, st)
    - Handle NULL values with SAFE_DIVIDE, COALESCE, etc.
    - Group by all non-aggregate columns
    - Consider performance - limit results appropriately
    - For style queries, GROUP BY style to aggregate SKUs
    - Use LOWER() for case-insensitive text matching
    - Default to recent data (last 30-90 days) unless specified
    
    MCP TOOLBOX INTEGRATION NOTE:
    - Many common queries may be handled by pre-built MCP Toolbox tools
    - Only generate SQL for custom queries that don't match standard patterns
    - If generating SQL, ensure compatibility with existing toolbox result formats
    
    Return only the SQL query, no explanations.
    """
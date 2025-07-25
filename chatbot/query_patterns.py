import re
from chatbot.config import get_shop_mappings

def _init_query_patterns():
    """Initialize common query patterns and their SQL templates"""
    return {
        'top_selling': {
            'keywords': ['top', 'best', 'highest selling', 'most popular'],
            'template': 'SELECT {columns} FROM {tables} WHERE {conditions} GROUP BY {group_by} ORDER BY SUM(fs.quantity) DESC LIMIT {limit}'
        },
        'comparison': {
            'keywords': ['compare', 'versus', 'vs', 'difference between'],
            'template': 'WITH period1 AS ({query1}), period2 AS ({query2}) SELECT * FROM period1 JOIN period2'
        },
        'trend': {
            'keywords': ['trend', 'over time', 'monthly', 'weekly', 'daily'],
            'template': 'SELECT {time_period}, {metrics} FROM {tables} WHERE {conditions} GROUP BY {time_period} ORDER BY {time_period}'
        },
        'margin_analysis': {
            'keywords': ['margin', 'profit', 'markup'],
            'template': 'SELECT {columns}, SAFE_DIVIDE(SUM(fs.price_extended) - SUM(fs.cogs_extended), SUM(fs.price_extended)) as margin_pct FROM {tables} WHERE {conditions} GROUP BY {group_by}'
        },
        'inventory_analysis': {
            'keywords': ['inventory', 'on hand', 'stock', 'overstock', 'out of stock'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_inventory_snapshots` WHERE {conditions}'
        },
        'return_analysis': {
            'keywords': ['return', 'returns', 'returned', 'return rate', 'defective', 'exchange'],
            'template': 'SELECT {columns} FROM `sis-data-marts.data_marts.mart_sales_returns` WHERE {conditions}'
        }
    }

def extract_intent(query: str) -> dict:
    """Extract intent and parameters from user query with backward compatibility"""
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
        'return_focus': False  # Ensure this key always exists
    }
    
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

def get_enhanced_schema_prompt():
    """Get the enhanced schema prompt with returns analysis capabilities"""
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
    
    Return only the SQL query, no explanations.
    """

def get_store_filter_hint(query: str) -> str:
    """Get hints for store filtering optimization"""
    query_lower = query.lower()
    hints = []
    
    # This assumes access to BigQueryUtils.store_id_by_city; for standalone, use static
    store_id_by_city = {'fargo': [64], 'springfield': [65]}  # Example; replace with actual if needed
    
    for city, store_ids in store_id_by_city.items():
        if city in query_lower:
            if len(store_ids) == 1:
                hints.append(f"For better performance, use: st.dim_store_id = {store_ids[0]} instead of st.city = '{city.title()}'")
            else:
                hints.append(f"City '{city.title()}' has multiple stores: {store_ids}")
                
    return "\n".join(hints) if hints else ""

def get_weighting_enhanced_prompt():
    """Enhanced prompt that ensures weighting-compatible queries with correct field paths"""
    return """
    When generating queries for inventory analysis or weighting calculations, 
    ensure the following fields are included with CORRECT field paths:

    REQUIRED FIELDS FOR WEIGHTING (with correct schema paths):
    - oh_units (from inventory) as current_on_hand
    - units_on_order (from PO data if available, else 0) 
    - SUM(fs.quantity) over last 30 days as units_sold_30d (calculated in sales_metrics CTE)
    - SUM(fs.quantity) over last 7 days as units_sold_7d (calculated in sales_metrics CTE)
    - SUM(fs.quantity) from 14-7 days ago as units_sold_prev_7d (calculated in sales_metrics CTE)
    - SUM(fs.price_extended) as revenue_30d (calculated in sales_metrics CTE)
    - SUM(fs.cogs_extended) as cost_30d (calculated in sales_metrics CTE)
    - Calculated margin percentage (DERIVED in final SELECT only)
    - Calculated sell-through percentage (DERIVED in final SELECT only)
    - Daily/weekly velocity calculations
    - YoY growth calculations
    - Days with sales counts
    - MOQ extraction from inv.product_details.sku_description2 (NOT sku_description2 alone)

    CRITICAL FIELD PATH REMINDERS:
    - ✅ Use: inv.product_details.sku_description
    - ✅ Use: inv.product_details.sku_description2
    - ✅ Use: inv.product_details.style
    - ❌ Never use: inv.product_details.vendor_name (does not exist)
    - ✅ For vendor: JOIN with dim_skus and use skus.as400_data.vendor_name1
    - ✅ Calculate margin_pct in final SELECT: SAFE_DIVIDE(sm.revenue_30d - sm.cost_30d, sm.revenue_30d) * 100
    - ❌ Never calculate derived percentages inside intermediate CTEs

    Always follow the inventory analysis template provided in the main schema prompt.
    """

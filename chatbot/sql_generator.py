import time
import re
import logging
from chatbot.query_patterns import extract_intent, get_enhanced_schema_prompt, get_weighting_enhanced_prompt
from chatbot.config import get_available_models

logger = logging.getLogger(__name__)

# Known valid field paths for schema validation
VALID_FIELD_PATHS = {
    'fct_sales': [
        'fs.transaction_datetime', 'fs.price_extended', 'fs.cogs_extended', 
        'fs.quantity', 'fs.sku_id', 'fs.store_id'
    ],
    'dim_skus': [
        'skus.specialty_shop', 'skus.as400_data.sku_description', 
        'skus.as400_data.sku_description2', 'skus.as400_data.class_subclass_description',
        'skus.as400_data.style', 'skus.as400_data.vendor_name1', 
        'skus.as400_data.division_number', 'skus.as400_data.specialty_shop_description',
        'skus.as400_data.rate1_year', 'skus.as400_data.rate1_season',
        'skus.as400_data.team_description', 'skus.as400_data.color__size'
    ],
    'dim_stores': [
        'st.dim_store_id', 'st.name', 'st.short_name', 'st.city', 'st.state'
    ],
    'mart_inventory_snapshots': [
        'inv.snapshot_date', 'inv.oh_units', 'inv.retail_extension', 
        'inv.cost_extension', 'inv.sku_number', 'inv.store_number',
        'inv.product_details.sku_description', 'inv.product_details.sku_description2',
        'inv.product_details.style', 'inv.store_details.store_city',
        'inv.store_details.store_state'
    ],
    'mart_sales_returns': [
        'ret.store_number', 'ret.store_short_name', 'ret.register_number',
        'ret.transaction_ticket_number', 'ret.transaction_datetime', 'ret.transaction_date',
        'ret.transaction_time', 'ret.customer_type', 'ret.transaction_id',
        'ret.cashier_id', 'ret.cashier_first_name', 'ret.cashier_last_name',
        'ret.cashier_full_name', 'ret.customer_name', 'ret.customer_email_address',
        'ret.formatted_phone_number', 'ret.return_type', 'ret.link_store',
        'ret.link_store_short_name', 'ret.link_register', 'ret.link_ticket'
    ]
}

# Invalid field paths that commonly appear in generated SQL but don't exist
INVALID_FIELD_PATHS = [
    'inv.vendor1.vendor_name',  # Does not exist
    'inv.product_details.vendor_name',  # Does not exist in mart_inventory_snapshots
    'product_details.vendor_name',  # Does not exist
    'vendor1.vendor_name',  # Does not exist
]

def generate_sql(user_query: str, model_name: str, api_client, config):
    """Generate SQL query from user input using specified AI model with validation"""
    available_models = get_available_models()
    start_time = time.time()
    
    intent = extract_intent(user_query)
    logger.info(f"Extracted intent: {intent}")
    
    # Build the prompt with enhanced schema information
    prompt = get_enhanced_schema_prompt()
    
    # Add weighting-specific guidance if this is an inventory query
    if intent.get('inventory_focus') or should_apply_weighting_to_query(user_query):
        prompt += "\n\n" + get_weighting_enhanced_prompt()
        logger.info("Added weighting-compatible query guidance to prompt")
    
    # Add returns-specific guidance if this is a returns query
    if intent.get('return_focus', False):  # Add fallback to False
        prompt += "\n\n" + get_returns_enhanced_prompt()
        logger.info("Added returns analysis query guidance to prompt")
    
    # Add strict validation reminder
    prompt += """
    
    *** FINAL VALIDATION REMINDER ***:
    Before generating SQL, ensure:
    1. All field paths exactly match the schema above
    2. No use of invalid paths like vendor1.vendor_name or inv.product_details.vendor_name
    3. margin_pct, sell_through_pct, and return_rate_pct are only calculated in final SELECT
    4. All inventory fields use inv.product_details.* format (except vendor_name which doesn't exist)
    5. Returns queries use ret.* fields and proper linking via link_store/link_ticket
    6. For vendor info in inventory queries, JOIN with dim_skus
    """
    
    # Add the user query and intent analysis
    prompt += f"""
    
    User Query: "{user_query}"
    
    Query Intent Analysis:
    - Metrics requested: {intent['metrics']}
    - Dimensions to group by: {intent['dimensions']}
    - Ranking: {intent['ranking']}
    - Limit: {intent['limit']}
    - Is comparison: {intent['comparison']}
    - Inventory focus: {intent['inventory_focus']}
    - Return focus: {intent['return_focus']}
    - Time series: {intent['time_series']}
    
    Generate the SQL query based on this understanding, following the exact schema paths provided.
    """
    
    try:
        model_info = available_models.get(model_name, {})
        provider = model_info.get('provider', 'google')
        
        logger.info(f"Generating SQL using {model_name} ({provider})")
        
        # Use the unified APIClient.call_model method
        sql_text = api_client.call_model(provider, model_name, prompt)
        
        # Clean up the SQL response
        sql_query = sql_text.strip()
        sql_query = re.sub(r'^```sql\s*', '', sql_query)
        sql_query = re.sub(r'\s*```$', '', sql_query)
        sql_query = sql_query.strip()
        
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Validate the generated SQL
        validation_result = validate_generated_sql(sql_query, intent)
        if not validation_result['valid']:
            logger.warning(f"Generated SQL failed validation: {validation_result['errors']}")
            # Try to auto-fix common issues
            sql_query = auto_fix_common_sql_issues(sql_query)
            logger.info("Applied auto-fixes to SQL query")
        
        logger.info(f"Generated SQL using {model_name} in {generation_time_ms}ms")
        logger.debug(f"Generated SQL: {sql_query}")
        
        return sql_query, generation_time_ms
        
    except Exception as e:
        logger.error(f"SQL generation failed with {model_name}: {e}")
        generation_time_ms = int((time.time() - start_time) * 1000)
        
        # Return a basic error query that won't break the system
        error_query = "SELECT 'SQL generation failed' as error_message, 'Please try rephrasing your question' as suggestion"
        return error_query, generation_time_ms

def get_returns_enhanced_prompt():
    """Enhanced prompt for returns analysis queries"""
    return """
    RETURNS ANALYSIS GUIDANCE:
    
    For returns-focused queries, ensure proper linking and meaningful analysis:
    
    RETURNS LINKING PATTERNS:
    - Link returns to original sales: ret.link_ticket = fs.transaction_id AND ret.link_store = fs.store_id
    - For return rates: SAFE_DIVIDE(COUNT(DISTINCT ret.transaction_id), COUNT(DISTINCT fs.transaction_id)) * 100
    - For product-level analysis: JOIN through original sales transaction to get SKU details
    
    COMMON RETURNS QUERIES:
    1. Return rates by store/product/category
    2. Customer return patterns and frequency
    3. Return trends over time
    4. Return type analysis
    5. High-return items identification
    
    IMPORTANT RETURNS RULES:
    - Always include meaningful thresholds (e.g., minimum sales volume for return rate calculation)
    - Use proper date ranges for both sales and returns data
    - Consider return_type field for categorization
    - Link customer information when analyzing return patterns
    - Exclude returns data from sales analysis unless specifically combining
    """

def validate_generated_sql(sql_query: str, intent: dict) -> dict:
    """Validate generated SQL against known schema and common issues"""
    errors = []
    warnings = []
    
    # Check for invalid field paths
    for invalid_path in INVALID_FIELD_PATHS:
        if invalid_path in sql_query:
            errors.append(f"Invalid field path: {invalid_path}")
    
    # Check for margin_pct in wrong location (inside CTEs)
    lines = sql_query.split('\n')
    in_intermediate_cte = False
    cte_depth = 0
    
    for line in lines:
        line_stripped = line.strip().upper()
        
        # Track CTE depth
        if 'AS (' in line_stripped and ('_METRICS AS' in line_stripped or '_DATA AS' in line_stripped):
            in_intermediate_cte = True
            cte_depth += 1
        elif in_intermediate_cte and line_stripped.startswith('SELECT'):
            # Final SELECT - not in intermediate CTE
            if cte_depth <= 1:
                in_intermediate_cte = False
        elif in_intermediate_cte and 'FROM' in line_stripped:
            # Still in CTE
            pass
        elif in_intermediate_cte and line_stripped == ')':
            cte_depth -= 1
            if cte_depth == 0:
                in_intermediate_cte = False
        elif in_intermediate_cte and ('MARGIN_PCT' in line_stripped or 'RETURN_RATE_PCT' in line_stripped or 'SELL_THROUGH_PCT' in line_stripped):
            errors.append("Derived percentages (margin_pct, return_rate_pct, sell_through_pct) should not be calculated inside intermediate CTEs")
    
    # Check for required inventory snapshot_date filter
    if 'mart_inventory_snapshots' in sql_query and 'snapshot_date' not in sql_query:
        errors.append("Inventory queries must include snapshot_date filter")
    
    # Check for returns queries without proper linking
    if intent.get('return_focus') and 'mart_sales_returns' in sql_query:
        if 'link_ticket' not in sql_query and 'link_store' not in sql_query:
            warnings.append("Returns queries should typically link to original sales data")
    
    # Basic SQL syntax checks
    if not basic_sql_syntax_check(sql_query):
        errors.append("Basic SQL syntax validation failed")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }

def auto_fix_common_sql_issues(sql_query: str) -> str:
    """Automatically fix common SQL generation issues"""
    fixed_query = sql_query
    
    # Fix invalid vendor field paths
    replacements = {
        'inv.vendor1.vendor_name': 'skus.as400_data.vendor_name1',
        'inv.product_details.vendor_name': 'skus.as400_data.vendor_name1',
        'product_details.vendor_name': 'skus.as400_data.vendor_name1',
        'vendor1.vendor_name': 'skus.as400_data.vendor_name1',
    }
    
    for wrong, correct in replacements.items():
        if wrong in fixed_query:
            fixed_query = fixed_query.replace(wrong, correct)
            logger.info(f"Auto-fixed: {wrong} → {correct}")
            
            # If we're using skus fields, ensure dim_skus join exists
            if 'skus.as400_data' in correct and 'dim_skus' not in fixed_query:
                # Add the join if it's missing
                if 'FROM `sis-data-marts.data_marts.mart_inventory_snapshots` inv' in fixed_query:
                    fixed_query = fixed_query.replace(
                        'FROM `sis-data-marts.data_marts.mart_inventory_snapshots` inv',
                        'FROM `sis-data-marts.data_marts.mart_inventory_snapshots` inv\n    LEFT JOIN `sis-data-marts.warehouse.dim_skus` skus ON inv.sku_number = skus.dim_sku_id'
                    )
                    logger.info("Auto-added dim_skus join for vendor access")
    
    return fixed_query

def should_apply_weighting_to_query(query: str) -> bool:
    """Determine if a query should use weighting-compatible field generation"""
    weighting_keywords = [
        'inventory', 'stock', 'coverage', 'reorder', 'overstock', 'understock',
        'priority', 'risk', 'analysis', 'weighting', 'days of supply', 'velocity',
        'out of stock', 'on hand', 'turnover'
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in weighting_keywords)

def should_apply_returns_analysis(query: str) -> bool:
    """Determine if a query should include returns analysis"""
    returns_keywords = [
        'return', 'returns', 'returned', 'return rate', 'defective', 'exchange',
        'refund', 'customer returns', 'return analysis', 'return trends'
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in returns_keywords)

def enhance_sql_for_weighting(sql_query: str, intent: dict) -> str:
    """Enhance existing SQL query to include weighting-compatible fields"""
    
    # Only enhance if this looks like an inventory query
    if not intent.get('inventory_focus'):
        return sql_query
    
    # Check if the query already includes weighting fields
    weighting_fields = [
        'units_sold_30d', 'units_sold_7d', 'revenue_30d', 'cost_30d',
        'margin_pct', 'sell_through_pct', 'daily_velocity'
    ]
    
    has_weighting_fields = any(field in sql_query for field in weighting_fields)
    if has_weighting_fields:
        logger.info("SQL query already contains weighting-compatible fields")
        return sql_query
    
    # If it's a simple inventory query, we could add enhancements here
    # For now, just log and return the original query
    logger.info("SQL query could benefit from weighting field enhancements")
    return sql_query

def basic_sql_syntax_check(sql_query: str) -> bool:
    """Basic SQL syntax validation"""
    try:
        # Basic checks
        if not sql_query.strip():
            return False
        
        # Check for basic SQL structure
        sql_upper = sql_query.upper()
        if not any(keyword in sql_upper for keyword in ['SELECT', 'WITH']):
            return False
        
        # Check for balanced parentheses
        open_parens = sql_query.count('(')
        close_parens = sql_query.count(')')
        if open_parens != close_parens:
            logger.warning(f"Unbalanced parentheses in SQL: {open_parens} open, {close_parens} close")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"SQL validation error: {e}")
        return False

def get_sql_complexity_score(sql_query: str) -> int:
    """Calculate a complexity score for the SQL query"""
    score = 0
    
    # Count CTEs
    cte_count = sql_query.upper().count('WITH')
    score += cte_count * 10
    
    # Count JOINs
    join_count = len(re.findall(r'\bJOIN\b', sql_query.upper()))
    score += join_count * 5
    
    # Count subqueries
    subquery_count = len(re.findall(r'\bSELECT\b', sql_query.upper())) - 1
    score += subquery_count * 8
    
    # Count aggregate functions
    agg_functions = ['SUM', 'COUNT', 'AVG', 'MAX', 'MIN']
    for func in agg_functions:
        score += sql_query.upper().count(func) * 2
    
    return score

def validate_against_bigquery_schema(sql_query: str, bq_client) -> dict:
    """Optional: Validate SQL against actual BigQuery schema using dry run"""
    try:
        from google.cloud import bigquery
        
        # Create a dry run job configuration
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        
        # Execute dry run
        query_job = bq_client.query(sql_query, job_config=job_config)
        
        return {
            'valid': True,
            'bytes_processed': query_job.total_bytes_processed,
            'schema': [field.name for field in query_job.result().schema] if hasattr(query_job.result(), 'schema') else []
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error': str(e)
        }

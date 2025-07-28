import time
import logging
import json
from .query_patterns import extract_intent

logger = logging.getLogger(__name__)

def generate_summary(df, query, model_name, available_models, api_clients, bigquery_utils, toolbox_context=None):
    """
    Generate summary with enhanced MCP Toolbox context awareness
    
    Args:
        df: DataFrame with query results
        query: Original user query
        model_name: AI model to use for summary generation
        available_models: Available AI models configuration
        api_clients: API client instances
        bigquery_utils: BigQuery utilities for logging
        toolbox_context: Optional context from MCP Toolbox execution
    """
    if df is None or df.empty:
        return "No data available to summarize."
        
    start_time = time.time()
    
    # Enhanced analysis based on data content and toolbox context
    intent = extract_intent(query)
    is_inventory_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in ['oh_units', 'inventory', 'days_supply', 'stock_status']))
    is_return_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in ['return', 'defective', 'exchange']))
    
    # Build enhanced data summary with toolbox context
    data_summary = f"""
    Query: {query}
    
    Data Overview:
    - Total rows: {len(df)}
    - Columns: {', '.join(df.columns)}
    """
    
    # Add toolbox context if available
    if toolbox_context:
        data_summary += f"""
    
    MCP Toolbox Context:
    - Tool used: {toolbox_context.get('tool_name', 'Unknown')}
    - Parameters: {toolbox_context.get('parameters', {})}
    - Execution time: {toolbox_context.get('execution_time_ms', 0)}ms
    """
    
    data_summary += f"""
    
    Top 10 Results:
    {df.head(10).to_string()}
    
    Statistical Summary:
    {df.describe().to_string() if not df.empty else 'No numeric data'}
    """
    
    # Enhanced prompts based on query type and toolbox integration
    if is_return_query:
        prompt = generate_returns_summary_prompt(data_summary, toolbox_context)
    elif is_inventory_query:
        prompt = generate_inventory_summary_prompt(data_summary, toolbox_context)
    else:
        prompt = generate_general_summary_prompt(data_summary, toolbox_context)
    
    try:
        model_info = available_models.get(model_name, {})
        provider = model_info.get('provider', 'google')
        
        summary = api_clients.call_model(provider, model_name, prompt)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        data_preview = df.head(5).to_dict('records') if len(df) > 0 else None
        
        # Enhanced logging with toolbox context
        bigquery_utils.store_summary_bigquery(
            user_query=query,
            sql_query=getattr(bigquery_utils, 'last_sql', None),
            summary_text=summary,
            model_name=model_name,
            row_count=len(df),
            execution_time_ms=execution_time_ms,
            data_preview=data_preview,
            user_id=None,
            session_id=None
        )
        
        return summary
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return "Unable to generate summary at this time."

def generate_inventory_summary_prompt(data_summary: str, toolbox_context: dict = None) -> str:
    """Generate inventory-specific summary prompt with toolbox awareness"""
    
    base_prompt = f"""
    You are a retail inventory analyst. Analyze this inventory data and provide actionable insights.
    
    {data_summary}
    
    Please provide:
    1. A brief paragraph summarizing the inventory situation
    2. 2-3 specific inventory insights (overstocks, stockouts, slow movers)
    3. 1-2 inventory optimization recommendations (reorder suggestions, markdown candidates)
    
    Focus on:
    - Items that need immediate attention (very low or very high days of supply)
    - Inventory investment opportunities or risks
    - Specific SKUs or categories to take action on
    
    Keep the response under 200 words and focus on actionable insights.
    Format the response with clear sections using **bold** headers.
    """
    
    # Add toolbox-specific context
    if toolbox_context and toolbox_context.get('tool_name'):
        tool_name = toolbox_context['tool_name']
        
        if tool_name == 'get_out_of_stock_items':
            base_prompt += """
            
            **Tool Context**: This analysis used the out-of-stock detection tool. Focus on:
            - Immediate reorder priorities
            - Lost sales opportunities
            - Stock-out prevention strategies
            """
        elif tool_name == 'get_overstock_items':
            base_prompt += """
            
            **Tool Context**: This analysis used the overstock detection tool. Focus on:
            - Markdown and clearance opportunities
            - Inventory liquidation strategies
            - Future purchasing adjustments
            """
        elif tool_name == 'get_inventory_status':
            base_prompt += """
            
            **Tool Context**: This analysis used the general inventory status tool. Provide:
            - Balanced view of inventory health
            - Priority actions across stock levels
            - Overall inventory optimization opportunities
            """
    
    return base_prompt

def generate_returns_summary_prompt(data_summary: str, toolbox_context: dict = None) -> str:
    """Generate returns-specific summary prompt with toolbox awareness"""
    
    base_prompt = f"""
    You are a retail returns analyst. Analyze this returns data and provide actionable insights.
    
    {data_summary}
    
    Please provide:
    1. A brief paragraph summarizing the returns situation
    2. 2-3 specific returns insights (high-return items, patterns, customer behavior)
    3. 1-2 actionable recommendations (quality improvements, policy changes, customer service)
    
    Focus on:
    - Items or categories with concerning return rates
    - Return patterns that indicate quality or customer satisfaction issues
    - Opportunities to reduce returns while maintaining customer satisfaction
    
    Keep the response under 200 words and focus on actionable insights.
    Format the response with clear sections using **bold** headers.
    """
    
    # Add toolbox-specific context
    if toolbox_context and toolbox_context.get('tool_name'):
        tool_name = toolbox_context['tool_name']
        
        if tool_name == 'get_return_trends':
            base_prompt += """
            
            **Tool Context**: This analysis used the returns trend tool. Focus on:
            - Trend direction and seasonality
            - Time-based patterns requiring attention
            - Forecast implications for return rates
            """
        elif tool_name == 'get_return_analysis_by_store':
            base_prompt += """
            
            **Tool Context**: This analysis used the store-level returns tool. Focus on:
            - Store performance variations
            - Training or process improvement opportunities
            - Best practices from top-performing stores
            """
        elif tool_name == 'get_customer_return_analysis':
            base_prompt += """
            
            **Tool Context**: This analysis used the customer returns tool. Focus on:
            - Customer segmentation insights
            - Repeat return behavior patterns
            - Customer retention and satisfaction implications
            """
    
    return base_prompt

def generate_general_summary_prompt(data_summary: str, toolbox_context: dict = None) -> str:
    """Generate general summary prompt with toolbox awareness"""
    
    base_prompt = f"""
    You are a retail analytics expert. Analyze this data and provide a concise business summary.
    
    {data_summary}
    
    Please provide:
    1. A brief paragraph summarizing the key findings
    2. 2-3 specific insights from the data
    3. 1-2 business opportunities or recommendations
    
    Keep the response under 200 words and focus on actionable insights.
    Format the response with clear sections using **bold** headers.
    """
    
    # Add toolbox-specific context
    if toolbox_context and toolbox_context.get('tool_name'):
        tool_name = toolbox_context['tool_name']
        parameters = toolbox_context.get('parameters', {})
        
        base_prompt += f"""
        
        **Tool Context**: This analysis used the '{tool_name}' tool with parameters: {parameters}
        The results are optimized and pre-processed for this specific type of analysis.
        Consider this context when providing insights and recommendations.
        """
        
        # Add tool-specific guidance
        if 'top_selling' in tool_name:
            base_prompt += """
            Focus on sales performance leaders and what drives their success.
            """
        elif 'comparison' in tool_name:
            base_prompt += """
            Focus on the differences highlighted and their business implications.
            """
        elif 'trends' in tool_name:
            base_prompt += """
            Focus on trend direction, seasonality, and forecasting implications.
            """
        elif 'margin' in tool_name:
            base_prompt += """
            Focus on profitability insights and margin optimization opportunities.
            """
    
    return base_prompt

def generate_parallel_summary(df, query, models_list, api_clients, bigquery_utils, toolbox_context=None):
    """
    Generate summaries using multiple AI models in parallel for comparison
    
    Args:
        df: DataFrame with query results
        query: Original user query
        models_list: List of model configurations to use
        api_clients: API client instances
        bigquery_utils: BigQuery utilities for logging
        toolbox_context: Optional context from MCP Toolbox execution
        
    Returns:
        Dictionary with primary summary and alternatives
    """
    if df is None or df.empty:
        return {
            'primary_summary': "No data available to summarize.",
            'alternative_summaries': [],
            'models_used': [],
            'parallel_cost': 0.0
        }
    
    start_time = time.time()
    
    # Determine the appropriate prompt based on data type
    intent = extract_intent(query)
    is_inventory_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in ['oh_units', 'inventory', 'days_supply', 'stock_status']))
    is_return_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in ['return', 'defective', 'exchange']))
    
    # Build data summary
    data_summary = f"""
    Query: {query}
    Data Overview: {len(df)} rows, Columns: {', '.join(df.columns)}
    Top 5 Results: {df.head(5).to_string()}
    """
    
    # Select appropriate prompt
    if is_return_query:
        prompt = generate_returns_summary_prompt(data_summary, toolbox_context)
    elif is_inventory_query:
        prompt = generate_inventory_summary_prompt(data_summary, toolbox_context)
    else:
        prompt = generate_general_summary_prompt(data_summary, toolbox_context)
    
    summaries = []
    total_cost = 0.0
    
    # Generate summaries in parallel
    import concurrent.futures
    
    def generate_single_summary(model_info):
        try:
            provider = model_info.get('provider', 'google')
            model_name = model_info.get('name', 'gemini-1.5-flash')
            
            summary = api_clients.call_model(provider, model_name, prompt)
            
            # Estimate cost (simplified)
            cost = len(prompt) * 0.000001  # Rough estimate
            
            return {
                'model': model_name,
                'provider': provider,
                'summary': summary,
                'cost': cost,
                'success': True
            }
        except Exception as e:
            logger.error(f"Parallel summary generation failed for {model_info}: {e}")
            return {
                'model': model_info.get('name', 'unknown'),
                'provider': model_info.get('provider', 'unknown'),
                'summary': f"Summary generation failed: {str(e)}",
                'cost': 0.0,
                'success': False
            }
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(models_list), 3)) as executor:
        futures = [executor.submit(generate_single_summary, model) for model in models_list]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=30)
                summaries.append(result)
                total_cost += result.get('cost', 0)
            except concurrent.futures.TimeoutError:
                logger.error("Parallel summary generation timed out")
                summaries.append({
                    'model': 'timeout',
                    'provider': 'unknown',
                    'summary': 'Summary generation timed out',
                    'cost': 0.0,
                    'success': False
                })
            except Exception as e:
                logger.error(f"Parallel summary execution failed: {e}")
    
    execution_time_ms = int((time.time() - start_time) * 1000)
    
    # Process results
    successful_summaries = [s for s in summaries if s['success']]
    
    if successful_summaries:
        primary_summary = successful_summaries[0]['summary']
        alternative_summaries = [s['summary'] for s in successful_summaries[1:]]
        models_used = [s['model'] for s in successful_summaries]
    else:
        primary_summary = "All parallel summary generation attempts failed."
        alternative_summaries = []
        models_used = []
    
    # Log the primary summary
    if successful_summaries:
        data_preview = df.head(5).to_dict('records') if len(df) > 0 else None
        
        bigquery_utils.store_summary_bigquery(
            user_query=query,
            sql_query=getattr(bigquery_utils, 'last_sql', None),
            summary_text=primary_summary,
            model_name=f"parallel_{successful_summaries[0]['model']}",
            row_count=len(df),
            execution_time_ms=execution_time_ms,
            data_preview=data_preview,
            user_id=None,
            session_id=None
        )
    
    return {
        'primary_summary': primary_summary,
        'alternative_summaries': alternative_summaries,
        'models_used': models_used,
        'parallel_cost': total_cost,
        'execution_time_ms': execution_time_ms,
        'toolbox_context': toolbox_context
    }

def enhance_summary_with_toolbox_insights(summary: str, toolbox_context: dict) -> str:
    """
    Enhance a generated summary with additional insights from MCP Toolbox execution
    
    Args:
        summary: Generated summary text
        toolbox_context: Context from MCP Toolbox execution
        
    Returns:
        Enhanced summary with additional toolbox insights
    """
    if not toolbox_context:
        return summary
    
    tool_name = toolbox_context.get('tool_name')
    parameters = toolbox_context.get('parameters', {})
    execution_time = toolbox_context.get('execution_time_ms', 0)
    
    # Add performance context
    performance_note = f"\n\n**Performance**: Analysis completed using optimized {tool_name} tool in {execution_time}ms."
    
    # Add parameter context
    if parameters:
        param_summary = []
        for key, value in parameters.items():
            if key in ['limit', 'days_back', 'min_days_supply']:
                param_summary.append(f"{key}: {value}")
        
        if param_summary:
            performance_note += f" Parameters: {', '.join(param_summary)}."
    
    # Add tool-specific insights
    tool_insights = ""
    if tool_name == 'get_out_of_stock_items':
        tool_insights = "\n\n**Tool Insight**: This analysis used advanced out-of-stock detection algorithms that consider recent sales velocity and seasonal patterns."
    elif tool_name == 'get_overstock_items':
        tool_insights = "\n\n**Tool Insight**: This analysis used sophisticated overstock detection that factors in days of supply, sales velocity, and historical turnover rates."
    elif tool_name == 'get_inventory_status':
        tool_insights = "\n\n**Tool Insight**: This comprehensive inventory analysis includes real-time stock levels, sales velocity, and predictive indicators."
    
    return summary + performance_note + tool_insights
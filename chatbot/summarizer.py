import time
import logging
import json
from chatbot.query_patterns import extract_intent

logger = logging.getLogger(__name__)

def generate_summary(df, query, model_name, available_models, api_client, bigquery_utils):
    """
    Generate a comprehensive summary of the query results using AI.
    
    Args:
        df: Pandas DataFrame with query results
        query: Original user query
        model_name: AI model to use for summary generation
        available_models: Dictionary of available models
        api_client: APIClient instance
        bigquery_utils: BigQuery utilities instance
    
    Returns:
        Generated summary text
    """
    if df is None or df.empty:
        return "No data available to summarize."
        
    start_time = time.time()
    
    # Detect query type for specialized summary prompts
    is_inventory_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in [
        'oh_units', 'inventory', 'days_supply', 'stock_status', 'coverage', 'risk_level'
    ]))
    
    is_returns_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in [
        'return', 'returns', 'return_rate', 'return_count', 'defective'
    ]))
    
    is_sales_query = any(col for col in df.columns if any(keyword in col.lower() for keyword in [
        'sales', 'revenue', 'units_sold', 'quantity', 'price_extended'
    ]))
    
    # Prepare data summary for the AI prompt
    data_summary = f"""
    Query: {query}
    
    Data Overview:
    - Total rows: {len(df)}
    - Columns: {', '.join(df.columns)}
    
    Top 10 Results:
    {df.head(10).to_string()}
    
    Statistical Summary:
    {df.describe().to_string() if not df.empty else 'No numeric data'}
    """
    
    # Generate specialized prompts based on query type
    if is_inventory_query:
        prompt = get_inventory_summary_prompt(data_summary)
    elif is_returns_query:
        prompt = get_returns_summary_prompt(data_summary)
    elif is_sales_query:
        prompt = get_sales_summary_prompt(data_summary)
    else:
        prompt = get_general_summary_prompt(data_summary)
    
    try:
        model_info = available_models.get(model_name, {})
        provider = model_info.get('provider', 'google')
        
        logger.info(f"Generating summary using {model_name} ({provider})")
        
        # Use the unified APIClient.call_model method
        summary = api_client.call_model(provider, model_name, prompt)
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Prepare data preview for logging
        data_preview = df.head(5).to_dict('records') if len(df) > 0 else None
        
        # Store summary in BigQuery for analytics
        try:
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
        except Exception as e:
            logger.warning(f"Failed to store summary in BigQuery: {e}")
        
        logger.info(f"Summary generated successfully in {execution_time_ms}ms")
        return summary
        
    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        return "Unable to generate summary at this time. Please try again or use a different AI model."

def get_inventory_summary_prompt(data_summary: str) -> str:
    """Generate specialized prompt for inventory analysis summaries"""
    return f"""
    You are a retail inventory analyst with deep expertise in inventory management and optimization. 
    Analyze this inventory data and provide actionable business insights.
    
    {data_summary}
    
    Please provide a comprehensive analysis with:
    
    **📊 Inventory Situation Summary**
    - Brief overview of the current inventory state
    - Key metrics and patterns identified
    
    **⚠️ Critical Insights** (2-3 specific findings):
    - Items requiring immediate attention (stockouts, overstocks)
    - Risk patterns and coverage gaps
    - High-priority SKUs or categories
    
    **🎯 Actionable Recommendations** (1-2 specific actions):
    - Reorder priorities and quantities
    - Markdown or liquidation candidates
    - Inventory optimization opportunities
    
    **💡 Strategic Considerations**:
    - Investment implications
    - Operational efficiency opportunities
    - Risk mitigation strategies
    
    Focus on:
    - Items with critical risk levels or poor coverage
    - High-value inventory decisions
    - Specific SKUs, categories, or stores mentioned
    - Quantified impact where possible
    
    Keep response under 250 words, use clear business language, and format with **bold** headers.
    Prioritize actionable insights over general observations.
    """

def get_returns_summary_prompt(data_summary: str) -> str:
    """Generate specialized prompt for returns analysis summaries"""
    return f"""
    You are a retail quality and customer experience analyst specializing in returns analysis.
    Analyze this returns data to identify quality issues and improvement opportunities.
    
    {data_summary}
    
    Please provide a focused analysis with:
    
    **🔄 Returns Overview**
    - Current return patterns and rates
    - Key trends and seasonal patterns
    
    **🚨 Quality Concerns** (2-3 specific findings):
    - High-return items or categories
    - Return rate anomalies
    - Customer experience issues
    
    **🔧 Improvement Actions** (1-2 specific recommendations):
    - Product quality investigations needed
    - Process improvements
    - Supplier performance discussions
    
    **📈 Business Impact**:
    - Financial implications of return patterns
    - Customer satisfaction considerations
    - Operational efficiency opportunities
    
    Focus on:
    - Items with unusually high return rates
    - Return patterns that indicate quality issues
    - Specific products, vendors, or stores
    - Customer experience improvements
    
    Keep response under 250 words, use clear business language, and format with **bold** headers.
    Emphasize actionable quality improvements over descriptive statistics.
    """

def get_sales_summary_prompt(data_summary: str) -> str:
    """Generate specialized prompt for sales analysis summaries"""
    return f"""
    You are a retail sales analyst with expertise in performance optimization and market trends.
    Analyze this sales data to identify growth opportunities and performance insights.
    
    {data_summary}
    
    Please provide a strategic analysis with:
    
    **📈 Sales Performance Summary**
    - Overall performance trends
    - Key metrics and benchmarks
    
    **🎯 Growth Opportunities** (2-3 specific findings):
    - High-performing products or categories
    - Underperforming areas with potential
    - Market trends and customer preferences
    
    **🚀 Strategic Recommendations** (1-2 specific actions):
    - Sales optimization tactics
    - Product mix adjustments
    - Marketing or promotional opportunities
    
    **💰 Revenue Impact**:
    - High-value opportunities
    - Margin optimization potential
    - Resource allocation insights
    
    Focus on:
    - Top performers and their success factors
    - Underutilized opportunities
    - Seasonal patterns and trends
    - Specific products, categories, or locations
    
    Keep response under 250 words, use clear business language, and format with **bold** headers.
    Emphasize growth strategies over historical reporting.
    """

def get_general_summary_prompt(data_summary: str) -> str:
    """Generate general prompt for other types of analysis"""
    return f"""
    You are a retail analytics expert with comprehensive knowledge of retail operations.
    Analyze this data and provide concise, actionable business insights.
    
    {data_summary}
    
    Please provide a business-focused analysis with:
    
    **📊 Key Findings Summary**
    - Most important patterns and trends
    - Critical metrics and benchmarks
    
    **🔍 Business Insights** (2-3 specific findings):
    - Notable patterns or anomalies
    - Performance indicators
    - Operational efficiency observations
    
    **📋 Recommended Actions** (1-2 specific recommendations):
    - Immediate actions to consider
    - Strategic improvements
    - Further analysis needed
    
    **💡 Strategic Considerations**:
    - Business implications
    - Risk factors or opportunities
    - Resource allocation insights
    
    Focus on:
    - Actionable insights over descriptive statistics
    - Business impact and implications
    - Specific, measurable recommendations
    - Clear next steps
    
    Keep response under 250 words, use clear business language, and format with **bold** headers.
    Prioritize business value over technical details.
    """

def generate_executive_summary(df, query, model_name, available_models, api_client, include_charts=False):
    """
    Generate an executive-level summary with high-level insights and strategic recommendations.
    
    Args:
        df: Pandas DataFrame with query results
        query: Original user query
        model_name: AI model to use
        available_models: Dictionary of available models
        api_client: APIClient instance
        include_charts: Whether to suggest chart types for visualization
    
    Returns:
        Executive summary text
    """
    if df is None or df.empty:
        return "No data available for executive summary."
    
    # Identify key metrics and business KPIs
    revenue_cols = [col for col in df.columns if 'revenue' in col.lower() or 'sales' in col.lower()]
    unit_cols = [col for col in df.columns if 'unit' in col.lower() or 'quantity' in col.lower()]
    margin_cols = [col for col in df.columns if 'margin' in col.lower()]
    
    # Calculate high-level metrics
    total_revenue = df[revenue_cols[0]].sum() if revenue_cols else 0
    total_units = df[unit_cols[0]].sum() if unit_cols else 0
    avg_margin = df[margin_cols[0]].mean() if margin_cols else 0
    
    executive_prompt = f"""
    You are a senior retail executive consultant preparing a board-level summary.
    Create an executive summary focusing on strategic implications and business impact.
    
    Business Context:
    - Query: {query}
    - Data Points: {len(df)} records analyzed
    - Total Revenue: ${total_revenue:,.0f}
    - Total Units: {total_units:,.0f}
    - Average Margin: {avg_margin:.1f}%
    
    Top 5 Results:
    {df.head(5).to_string()}
    
    Provide an executive summary with:
    
    **🎯 Executive Summary** (2-3 sentences)
    - Bottom line business impact
    - Strategic significance
    
    **📊 Key Business Metrics**
    - Most critical performance indicators
    - Benchmark comparisons where relevant
    
    **⚡ Strategic Priorities** (Top 3)
    - Highest impact opportunities
    - Risk mitigation needs
    - Investment considerations
    
    **🚀 Next Steps** (1-2 actions)
    - Immediate decisions required
    - Further analysis needed
    
    Keep response under 200 words. Use executive language, focus on business impact, 
    and format with **bold** headers. Avoid technical jargon.
    """
    
    try:
        model_info = available_models.get(model_name, {})
        provider = model_info.get('provider', 'google')
        
        executive_summary = api_client.call_model(provider, model_name, executive_prompt)
        
        # Add chart recommendations if requested
        if include_charts:
            chart_suggestions = suggest_chart_types(df, query)
            if chart_suggestions:
                executive_summary += f"\n\n**📈 Recommended Visualizations**: {', '.join(chart_suggestions)}"
        
        return executive_summary
        
    except Exception as e:
        logger.error(f"Executive summary generation failed: {e}")
        return "Unable to generate executive summary at this time."

def suggest_chart_types(df, query):
    """Suggest appropriate chart types based on data structure and query intent"""
    suggestions = []
    
    # Analyze data structure
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
    text_cols = df.select_dtypes(include=['object']).columns
    date_cols = df.select_dtypes(include=['datetime64']).columns
    
    query_lower = query.lower()
    
    # Time series data
    if len(date_cols) > 0 and ('trend' in query_lower or 'over time' in query_lower):
        suggestions.append("Line Chart")
    
    # Comparison data
    if len(text_cols) > 0 and len(numeric_cols) > 0:
        if len(df) <= 10:
            suggestions.append("Bar Chart")
        elif 'top' in query_lower or 'bottom' in query_lower:
            suggestions.append("Horizontal Bar Chart")
    
    # Distribution analysis
    if 'distribution' in query_lower or 'breakdown' in query_lower:
        if len(df) <= 8:
            suggestions.append("Pie Chart")
        else:
            suggestions.append("Treemap")
    
    # Correlation analysis
    if len(numeric_cols) >= 2 and ('correlation' in query_lower or 'relationship' in query_lower):
        suggestions.append("Scatter Plot")
    
    # Geographic data
    if any('store' in col.lower() or 'location' in col.lower() or 'city' in col.lower() for col in text_cols):
        suggestions.append("Geographic Map")
    
    # Performance dashboard
    if 'performance' in query_lower or 'kpi' in query_lower:
        suggestions.append("Dashboard")
    
    return suggestions[:3]  # Return top 3 suggestions

def generate_insight_highlights(df, query, max_insights=5):
    """
    Generate key insight highlights from the data without using AI.
    This provides quick insights while AI summary is being generated.
    
    Args:
        df: Pandas DataFrame with results
        query: Original query
        max_insights: Maximum number of insights to generate
    
    Returns:
        List of insight strings
    """
    insights = []
    
    if df is None or df.empty:
        return ["No data available for analysis"]
    
    try:
        # Basic data insights
        insights.append(f"📊 Dataset contains {len(df):,} records across {len(df.columns)} metrics")
        
        # Identify top performers
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if len(numeric_cols) > 0:
            # Find the likely "value" column (revenue, sales, etc.)
            value_col = None
            for col in ['revenue', 'sales', 'total', 'amount', 'value']:
                matching_cols = [c for c in numeric_cols if col in c.lower()]
                if matching_cols:
                    value_col = matching_cols[0]
                    break
            
            if value_col:
                max_value = df[value_col].max()
                max_idx = df[value_col].idxmax()
                top_item = df.iloc[max_idx]
                
                # Get identifier column (first text column)
                text_cols = df.select_dtypes(include=['object']).columns
                if len(text_cols) > 0:
                    identifier = top_item[text_cols[0]]
                    insights.append(f"🏆 Top performer: {identifier} with {value_col.replace('_', ' ').title()}: ${max_value:,.0f}")
        
        # Identify data ranges and distributions
        if len(numeric_cols) > 0:
            for col in numeric_cols[:2]:  # Check first 2 numeric columns
                col_min = df[col].min()
                col_max = df[col].max()
                col_avg = df[col].mean()
                
                if col_max > col_min:  # Avoid division by zero
                    range_ratio = (col_max - col_min) / col_avg if col_avg != 0 else float('inf')
                    
                    if range_ratio > 3:  # High variability
                        insights.append(f"📈 High variability in {col.replace('_', ' ').title()}: Range ${col_min:,.0f} - ${col_max:,.0f}")
        
        # Check for zero values or missing data
        zero_counts = (df == 0).sum()
        significant_zeros = zero_counts[zero_counts > len(df) * 0.1]  # More than 10% zeros
        
        if len(significant_zeros) > 0:
            zero_col = significant_zeros.index[0]
            zero_pct = (significant_zeros.iloc[0] / len(df)) * 100
            insights.append(f"⚠️ {zero_pct:.0f}% of records have zero {zero_col.replace('_', ' ').title()}")
        
        # Geographic insights
        geo_cols = [col for col in df.columns if any(geo_term in col.lower() for geo_term in ['store', 'city', 'state', 'location'])]
        if geo_cols:
            geo_col = geo_cols[0]
            unique_locations = df[geo_col].nunique()
            insights.append(f"🗺️ Data spans {unique_locations} unique {geo_col.replace('_', ' ').title().lower()}s")
        
        # Time-based insights
        date_cols = df.select_dtypes(include=['datetime64']).columns
        if len(date_cols) > 0:
            date_col = date_cols[0]
            date_range = df[date_col].max() - df[date_col].min()
            insights.append(f"📅 Time period: {date_range.days} days of data")
        
    except Exception as e:
        logger.error(f"Error generating insights: {e}")
        insights.append("📊 Data analysis completed - detailed insights available in full summary")
    
    return insights[:max_insights]

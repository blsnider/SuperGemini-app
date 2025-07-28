import logging
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)

def create_visualization(df: pd.DataFrame, query: str, chart_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Create visualizations from query results - MCP-only version.
    Infers chart type from data structure and query content instead of using query_patterns.
    """
    if df is None or df.empty:
        logger.warning("Cannot create visualization from empty DataFrame")
        return None
    
    try:
        # Infer chart type from data and query if not specified
        if not chart_type:
            chart_type = _infer_chart_type(df, query)
        
        logger.info(f"Creating {chart_type} chart for query: '{query}' with {len(df)} rows")
        
        # Create chart based on type
        if chart_type == 'bar':
            return _create_bar_chart(df, query)
        elif chart_type == 'line':
            return _create_line_chart(df, query)
        elif chart_type == 'pie':
            return _create_pie_chart(df, query)
        elif chart_type == 'scatter':
            return _create_scatter_plot(df, query)
        elif chart_type == 'heatmap':
            return _create_heatmap(df, query)
        elif chart_type == 'grouped_bar':
            return _create_grouped_bar_chart(df, query)
        else:
            # Default to bar chart
            return _create_bar_chart(df, query)
            
    except Exception as e:
        logger.error(f"Visualization creation failed: {e}")
        return None

def _infer_chart_type(df: pd.DataFrame, query: str) -> str:
    """
    Infer the best chart type based on data structure and query content.
    Replaces the query_patterns.extract_intent() functionality.
    """
    query_lower = query.lower()
    columns = df.columns.tolist()
    
    # Analyze data structure
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
    
    # Time series detection
    if date_cols or any(keyword in query_lower for keyword in ['trend', 'over time', 'daily', 'weekly', 'monthly', 'timeline']):
        return 'line'
    
    # Pie chart detection
    if (len(df) <= 8 and 
        any(keyword in query_lower for keyword in ['distribution', 'breakdown', 'proportion', 'percentage', 'share']) and
        len(categorical_cols) >= 1 and len(numeric_cols) >= 1):
        return 'pie'
    
    # Scatter plot detection
    if (len(numeric_cols) >= 2 and 
        any(keyword in query_lower for keyword in ['correlation', 'relationship', 'scatter', 'vs', 'versus'])):
        return 'scatter'
    
    # Heatmap detection
    if (any(keyword in query_lower for keyword in ['heatmap', 'matrix', 'inventory by store']) and
        len(categorical_cols) >= 2):
        return 'heatmap'
    
    # Grouped bar chart detection
    if (len(categorical_cols) >= 2 and len(numeric_cols) >= 1 and
        any(keyword in query_lower for keyword in ['compare', 'comparison', 'by store', 'by shop'])):
        return 'grouped_bar'
    
    # Default to bar chart
    return 'bar'

def _create_bar_chart(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a bar chart from the data"""
    try:
        # Find appropriate columns
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        
        if not numeric_cols or not categorical_cols:
            logger.warning("Insufficient columns for bar chart")
            return None
        
        # Use first categorical column as x-axis
        x_col = categorical_cols[0]
        
        # Determine y-axis based on query content
        y_col = _select_metric_column(numeric_cols, query)
        
        # Limit to top items for readability
        df_plot = df.nlargest(min(20, len(df)), y_col)
        
        fig = px.bar(
            df_plot,
            x=x_col,
            y=y_col,
            title=_generate_chart_title(query, 'Bar Chart'),
            labels={x_col: x_col.replace('_', ' ').title(), y_col: y_col.replace('_', ' ').title()}
        )
        
        fig.update_layout(
            xaxis_tickangle=-45,
            height=500,
            showlegend=False
        )
        
        return {
            'type': 'bar',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Bar Chart')
        }
        
    except Exception as e:
        logger.error(f"Bar chart creation failed: {e}")
        return None

def _create_line_chart(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a line chart for time series data"""
    try:
        # Find date/time columns
        date_cols = [col for col in df.columns if any(keyword in col.lower() for keyword in ['date', 'time', 'period'])]
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if not date_cols or not numeric_cols:
            logger.warning("Insufficient columns for line chart")
            return None
        
        x_col = date_cols[0]
        y_col = _select_metric_column(numeric_cols, query)
        
        # Sort by date
        df_plot = df.sort_values(x_col)
        
        fig = px.line(
            df_plot,
            x=x_col,
            y=y_col,
            title=_generate_chart_title(query, 'Trend Analysis'),
            labels={x_col: x_col.replace('_', ' ').title(), y_col: y_col.replace('_', ' ').title()}
        )
        
        fig.update_layout(height=500)
        
        return {
            'type': 'line',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Trend Analysis')
        }
        
    except Exception as e:
        logger.error(f"Line chart creation failed: {e}")
        return None

def _create_pie_chart(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a pie chart for distribution data"""
    try:
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if not categorical_cols or not numeric_cols:
            logger.warning("Insufficient columns for pie chart")
            return None
        
        label_col = categorical_cols[0]
        value_col = _select_metric_column(numeric_cols, query)
        
        # Limit to top items and group others
        df_plot = df.nlargest(8, value_col).copy()
        
        fig = px.pie(
            df_plot,
            names=label_col,
            values=value_col,
            title=_generate_chart_title(query, 'Distribution')
        )
        
        fig.update_layout(height=500)
        
        return {
            'type': 'pie',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Distribution')
        }
        
    except Exception as e:
        logger.error(f"Pie chart creation failed: {e}")
        return None

def _create_scatter_plot(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a scatter plot for correlation analysis"""
    try:
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(numeric_cols) < 2:
            logger.warning("Insufficient numeric columns for scatter plot")
            return None
        
        x_col = numeric_cols[0]
        y_col = numeric_cols[1]
        
        fig = px.scatter(
            df,
            x=x_col,
            y=y_col,
            title=_generate_chart_title(query, 'Correlation Analysis'),
            labels={x_col: x_col.replace('_', ' ').title(), y_col: y_col.replace('_', ' ').title()}
        )
        
        fig.update_layout(height=500)
        
        return {
            'type': 'scatter',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Correlation Analysis')
        }
        
    except Exception as e:
        logger.error(f"Scatter plot creation failed: {e}")
        return None

def _create_heatmap(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a heatmap for matrix data"""
    try:
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(categorical_cols) < 2 or not numeric_cols:
            logger.warning("Insufficient columns for heatmap")
            return None
        
        # Create pivot table
        pivot_df = df.pivot_table(
            index=categorical_cols[0],
            columns=categorical_cols[1],
            values=numeric_cols[0],
            aggfunc='sum',
            fill_value=0
        )
        
        fig = px.imshow(
            pivot_df,
            title=_generate_chart_title(query, 'Heatmap'),
            aspect='auto'
        )
        
        fig.update_layout(height=500)
        
        return {
            'type': 'heatmap',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Heatmap')
        }
        
    except Exception as e:
        logger.error(f"Heatmap creation failed: {e}")
        return None

def _create_grouped_bar_chart(df: pd.DataFrame, query: str) -> Dict[str, Any]:
    """Create a grouped bar chart for comparison data"""
    try:
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(categorical_cols) < 2 or not numeric_cols:
            logger.warning("Insufficient columns for grouped bar chart")
            return None
        
        x_col = categorical_cols[0]
        color_col = categorical_cols[1]
        y_col = _select_metric_column(numeric_cols, query)
        
        fig = px.bar(
            df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=_generate_chart_title(query, 'Comparison'),
            labels={x_col: x_col.replace('_', ' ').title(), y_col: y_col.replace('_', ' ').title()}
        )
        
        fig.update_layout(
            xaxis_tickangle=-45,
            height=500
        )
        
        return {
            'type': 'grouped_bar',
            'data': fig.to_json(),
            'title': _generate_chart_title(query, 'Comparison')
        }
        
    except Exception as e:
        logger.error(f"Grouped bar chart creation failed: {e}")
        return None

def _select_metric_column(numeric_cols: List[str], query: str) -> str:
    """Select the most appropriate numeric column based on query content"""
    query_lower = query.lower()
    
    # Priority mapping based on query keywords
    priority_keywords = {
        'revenue': ['revenue', 'sales', 'dollar'],
        'units': ['units', 'quantity', 'count'],
        'margin': ['margin', 'profit'],
        'cost': ['cost', 'expense'],
        'inventory': ['inventory', 'stock', 'on_hand'],
        'days_supply': ['days_supply', 'supply'],
        'return': ['return', 'exchange']
    }
    
    # Check for keyword matches in column names and query
    for col in numeric_cols:
        col_lower = col.lower()
        for metric, keywords in priority_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                if any(keyword in col_lower for keyword in keywords):
                    return col
    
    # Common column name preferences
    preferred_order = [
        'total_revenue', 'revenue', 'total_sales', 'sales',
        'total_units', 'units', 'quantity',
        'total_margin', 'margin', 'profit',
        'current_on_hand', 'inventory', 'stock'
    ]
    
    for pref in preferred_order:
        matching_cols = [col for col in numeric_cols if pref.lower() in col.lower()]
        if matching_cols:
            return matching_cols[0]
    
    # Default to first numeric column
    return numeric_cols[0]

def _generate_chart_title(query: str, chart_type: str) -> str:
    """Generate an appropriate chart title"""
    # Clean up the query for use as title
    title_base = query.strip()
    if len(title_base) > 60:
        title_base = title_base[:57] + "..."
    
    return f"{chart_type}: {title_base}"

def get_chart_suggestions(df: pd.DataFrame, query: str) -> List[Dict[str, str]]:
    """Get suggested chart types for the given data"""
    suggestions = []
    
    if df is None or df.empty:
        return suggestions
    
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
    
    # Always suggest bar chart for basic data
    if categorical_cols and numeric_cols:
        suggestions.append({
            'type': 'bar',
            'name': 'Bar Chart',
            'description': 'Compare values across categories'
        })
    
    # Suggest line chart for time series
    if date_cols and numeric_cols:
        suggestions.append({
            'type': 'line',
            'name': 'Line Chart',
            'description': 'Show trends over time'
        })
    
    # Suggest pie chart for distributions
    if len(df) <= 10 and categorical_cols and numeric_cols:
        suggestions.append({
            'type': 'pie',
            'name': 'Pie Chart',
            'description': 'Show distribution breakdown'
        })
    
    # Suggest scatter plot for correlations
    if len(numeric_cols) >= 2:
        suggestions.append({
            'type': 'scatter',
            'name': 'Scatter Plot',
            'description': 'Explore relationships between metrics'
        })
    
    # Suggest heatmap for matrix data
    if len(categorical_cols) >= 2 and numeric_cols:
        suggestions.append({
            'type': 'heatmap',
            'name': 'Heatmap',
            'description': 'Visualize data as a matrix'
        })
    
    return suggestions
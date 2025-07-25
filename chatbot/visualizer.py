import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import plotly.io as pio
import time
import logging
from chatbot.query_patterns import extract_intent

logger = logging.getLogger(__name__)

pio.templates.default = "plotly_white"

def create_visualization(df: pd.DataFrame, query: str, chart_type: str = None) -> str:
    if df is None or df.empty:
        return None
        
    try:
        intent = extract_intent(query)
        
        chart_info = _analyze_dataframe_for_chart(df)
        
        if not chart_type:
            chart_type = _determine_best_chart_type(df, intent, chart_info)
            
        logger.info(f"Creating {chart_type} chart for query: {query[:50]}...")
        logger.info(f"Chart info: {chart_info}")
        
        df_vis = df.copy()
        
        for col in chart_info['numeric_cols']:
            df_vis[col] = pd.to_numeric(df_vis[col], errors='coerce')
        
        max_items = 20 if chart_type not in ['scatter', 'heatmap'] else 100
        if len(df_vis) > max_items and chart_type not in ['heatmap', 'scatter']:
            df_vis = df_vis.head(max_items)
        
        fig = _create_chart_by_type(df_vis, chart_type, chart_info, query)
        
        if fig:
            _apply_chart_styling(fig, chart_type)
            
            chart_json = fig.to_json()
            
            chart_id = f"plotly-chart-{int(time.time() * 1000)}"
            
            return _generate_chart_html(chart_id, chart_json)
        else:
            return None
            
    except Exception as e:
        logger.error(f"Visualization creation failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def _analyze_dataframe_for_chart(df: pd.DataFrame) -> dict:
    info = {
        'numeric_cols': [],
        'text_cols': [],
        'date_cols': [],
        'has_time_data': False,
        'row_count': len(df),
        'likely_measures': [],
        'likely_dimensions': [],
        'has_inventory_data': False
    }
    
    for col in df.columns:
        col_lower = col.lower()
        
        if any(keyword in col_lower for keyword in ['oh_units', 'on_hand', 'inventory', 'days_supply', 'stock_status']):
            info['has_inventory_data'] = True
        
        if df[col].dtype == 'datetime64[ns]' or 'date' in col_lower or 'time' in col_lower:
            info['date_cols'].append(col)
            info['has_time_data'] = True
        elif df[col].dtype in ['float64', 'int64', 'float32', 'int32']:
            info['numeric_cols'].append(col)
            if any(keyword in col_lower for keyword in ['revenue', 'sales', 'amount', 'quantity', 'units', 'margin', 'profit', 'cost', 'price', 'total', 'sum', 'avg', 'count', 'oh_units', 'days_supply', 'velocity']):
                info['likely_measures'].append(col)
        elif df[col].dtype == 'object' and len(df) > 0:
            try:
                pd.to_numeric(df[col], errors='raise')
                info['numeric_cols'].append(col)
            except:
                info['text_cols'].append(col)
                if any(keyword in col_lower for keyword in ['name', 'category', 'type', 'brand', 'style', 'store', 'shop', 'division', 'description', 'city', 'state', 'vendor', 'status']):
                    info['likely_dimensions'].append(col)
        else:
            info['text_cols'].append(col)
    
    if not info['likely_measures'] and info['numeric_cols']:
        info['likely_measures'] = info['numeric_cols']
        
    if not info['likely_dimensions'] and info['text_cols']:
        info['likely_dimensions'] = [info['text_cols'][0]]
        
    return info

def _determine_best_chart_type(df: pd.DataFrame, intent: dict, chart_info: dict) -> str:
    """Determine the best chart type based on data structure and query intent."""
    
    # Time series data
    if chart_info['has_time_data'] and intent.get('time_series', False):
        return 'line'
    
    # Inventory heatmap
    if chart_info['has_inventory_data'] and len(chart_info['text_cols']) >= 1:
        return 'heatmap'
    
    # Distribution analysis
    if intent.get('distribution', False):
        if len(df) <= 8:
            return 'pie'
        else:
            return 'bar'
    
    # Comparison charts
    if len(chart_info['text_cols']) >= 1 and len(chart_info['numeric_cols']) >= 1:
        if len(df) <= 15:
            return 'bar'
        else:
            return 'line'
    
    # Correlation analysis
    if len(chart_info['numeric_cols']) >= 2 and 'correlation' in intent.get('metrics', []):
        return 'scatter'
    
    # Default fallback
    if len(chart_info['text_cols']) >= 1 and len(chart_info['numeric_cols']) >= 1:
        return 'bar'
    elif len(chart_info['numeric_cols']) >= 2:
        return 'scatter'
    else:
        return 'bar'

def _create_chart_by_type(df: pd.DataFrame, chart_type: str, chart_info: dict, query: str) -> go.Figure:
    """Create a chart based on the specified type."""
    try:
        if chart_type == 'line':
            return _create_line_chart(df, chart_info)
        elif chart_type == 'bar':
            return _create_bar_chart(df, chart_info)
        elif chart_type == 'pie':
            return _create_pie_chart(df, chart_info)
        elif chart_type == 'scatter':
            return _create_scatter_chart(df, chart_info)
        elif chart_type == 'heatmap':
            return _create_heatmap_chart(df, chart_info)
        else:
            # Default to bar chart
            return _create_bar_chart(df, chart_info)
    except Exception as e:
        logger.error(f"Error creating {chart_type} chart: {e}")
        return None

def _create_bar_chart(df: pd.DataFrame, chart_info: dict) -> go.Figure:
    """Create a bar chart."""
    if not chart_info['likely_dimensions'] or not chart_info['likely_measures']:
        return None
    
    x_col = chart_info['likely_dimensions'][0]
    y_col = chart_info['likely_measures'][0]
    
    # Sort by y values for better visualization
    df_sorted = df.nlargest(min(20, len(df)), y_col)
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_sorted[x_col],
        y=df_sorted[y_col],
        text=[_format_bar_text(val, y_col) for val in df_sorted[y_col]],
        textposition='auto',
        marker_color='#667eea'
    ))
    
    fig.update_layout(
        title=f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}",
        xaxis_title=x_col.replace('_', ' ').title(),
        yaxis_title=y_col.replace('_', ' ').title()
    )
    
    return fig

def _create_line_chart(df: pd.DataFrame, chart_info: dict) -> go.Figure:
    """Create a line chart."""
    if not chart_info['likely_measures']:
        return None
    
    # Use date column if available, otherwise use index
    if chart_info['date_cols']:
        x_col = chart_info['date_cols'][0]
        df_sorted = df.sort_values(x_col)
    else:
        x_col = chart_info['likely_dimensions'][0] if chart_info['likely_dimensions'] else df.index.name or 'Index'
        df_sorted = df.sort_values(x_col) if x_col in df.columns else df
    
    y_col = chart_info['likely_measures'][0]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sorted[x_col] if x_col in df_sorted.columns else df_sorted.index,
        y=df_sorted[y_col],
        mode='lines+markers',
        name=y_col.replace('_', ' ').title(),
        line=dict(color='#667eea', width=3),
        marker=dict(size=6)
    ))
    
    fig.update_layout(
        title=f"{y_col.replace('_', ' ').title()} Trend",
        xaxis_title=x_col.replace('_', ' ').title() if x_col in df.columns else 'Index',
        yaxis_title=y_col.replace('_', ' ').title()
    )
    
    return fig

def _create_pie_chart(df: pd.DataFrame, chart_info: dict) -> go.Figure:
    """Create a pie chart."""
    if not chart_info['likely_dimensions'] or not chart_info['likely_measures']:
        return None
    
    labels_col = chart_info['likely_dimensions'][0]
    values_col = chart_info['likely_measures'][0]
    
    # Take top 8 items for readability
    df_top = df.nlargest(8, values_col)
    
    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=df_top[labels_col],
        values=df_top[values_col],
        hole=0.3,
        textinfo='label+percent'
    ))
    
    fig.update_layout(
        title=f"{values_col.replace('_', ' ').title()} Distribution"
    )
    
    return fig

def _create_scatter_chart(df: pd.DataFrame, chart_info: dict) -> go.Figure:
    """Create a scatter chart."""
    if len(chart_info['numeric_cols']) < 2:
        return None
    
    x_col = chart_info['numeric_cols'][0]
    y_col = chart_info['numeric_cols'][1]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col],
        y=df[y_col],
        mode='markers',
        marker=dict(
            size=8,
            color='#667eea',
            opacity=0.7
        ),
        text=df[chart_info['likely_dimensions'][0]] if chart_info['likely_dimensions'] else None,
        hovertemplate=f"{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>"
    ))
    
    fig.update_layout(
        title=f"{y_col.replace('_', ' ').title()} vs {x_col.replace('_', ' ').title()}",
        xaxis_title=x_col.replace('_', ' ').title(),
        yaxis_title=y_col.replace('_', ' ').title()
    )
    
    return fig

def _create_heatmap_chart(df: pd.DataFrame, chart_info: dict) -> go.Figure:
    """Create a heatmap chart."""
    if not chart_info['likely_dimensions'] or not chart_info['likely_measures']:
        return None
    
    # For heatmap, we need at least 2 categorical dimensions or 1 dimension + numeric measure
    if len(chart_info['likely_dimensions']) >= 2:
        x_col = chart_info['likely_dimensions'][0]
        y_col = chart_info['likely_dimensions'][1]
        z_col = chart_info['likely_measures'][0]
        
        # Pivot the data for heatmap
        pivot_df = df.pivot_table(values=z_col, index=y_col, columns=x_col, aggfunc='sum', fill_value=0)
        
        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            z=pivot_df.values,
            x=pivot_df.columns,
            y=pivot_df.index,
            colorscale='Blues'
        ))
        
        fig.update_layout(
            title=f"{z_col.replace('_', ' ').title()} Heatmap",
            xaxis_title=x_col.replace('_', ' ').title(),
            yaxis_title=y_col.replace('_', ' ').title()
        )
        
        return fig
    else:
        # Fallback to bar chart
        return _create_bar_chart(df, chart_info)

def _format_bar_text(value, column_name: str) -> str:
    """Format text for bar charts based on column type."""
    if pd.isna(value):
        return ""
    
    col_lower = column_name.lower()
    if 'revenue' in col_lower or 'sales' in col_lower or 'amount' in col_lower or 'price' in col_lower:
        return f"${value:,.0f}"
    elif 'pct' in col_lower or 'percent' in col_lower:
        return f"{value:.1f}%"
    elif isinstance(value, (int, float)):
        if value >= 1000:
            return f"{value:,.0f}"
        else:
            return f"{value:.1f}"
    else:
        return str(value)

def _apply_chart_styling(fig: go.Figure, chart_type: str):
    """Apply consistent styling to charts."""
    fig.update_layout(
        font_family="Segoe UI, Tahoma, Geneva, Verdana, sans-serif",
        title_font_size=16,
        title_font_color="#333",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=60, r=60, t=80, b=60),
        height=400
    )
    
    # Update axes styling
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(0,0,0,0.1)',
        showline=True,
        linewidth=1,
        linecolor='rgba(0,0,0,0.2)'
    )
    
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(0,0,0,0.1)',
        showline=True,
        linewidth=1,
        linecolor='rgba(0,0,0,0.2)'
    )

def _generate_chart_html(chart_id: str, chart_json: str) -> str:
    """Generate HTML for embedding the chart."""
    return f"""
    <div id="{chart_id}" style="width: 100%; height: 400px;"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.26.0/plotly.min.js"></script>
    <script>
        window.renderChart_{chart_id.replace('-', '_')} = function() {{
            try {{
                const chartData = {chart_json};
                Plotly.newPlot('{chart_id}', chartData.data, chartData.layout, {{
                    responsive: true,
                    displayModeBar: true,
                    modeBarButtonsToRemove: ['pan2d', 'lasso2d']
                }});
                console.log('Chart {chart_id} rendered successfully');
            }} catch (error) {{
                console.error('Error rendering chart {chart_id}:', error);
                document.getElementById('{chart_id}').innerHTML = '<div style="color: red; padding: 20px; text-align: center;">Error rendering chart: ' + error.message + '</div>';
            }}
        }};
        
        // Auto-execute when Plotly is available
        if (typeof Plotly !== 'undefined') {{
            window.renderChart_{chart_id.replace('-', '_')}();
        }} else {{
            // Wait for Plotly to load
            const checkPlotly = setInterval(() => {{
                if (typeof Plotly !== 'undefined') {{
                    clearInterval(checkPlotly);
                    window.renderChart_{chart_id.replace('-', '_')}();
                }}
            }}, 100);
            
            // Timeout after 10 seconds
            setTimeout(() => {{
                clearInterval(checkPlotly);
                if (typeof Plotly === 'undefined') {{
                    document.getElementById('{chart_id}').innerHTML = '<div style="color: red; padding: 20px; text-align: center;">Failed to load Plotly library</div>';
                }}
            }}, 10000);
        }}
    </script>
    """

# dashboard.py - Enhanced Plotly Dash Integration for Retail Analytics

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go
import plotly.express as px
from flask import Flask
import pandas as pd
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

def init_dash(flask_app: Flask):
    """Initialize Plotly Dash app with Flask integration."""
    
    dash_app = dash.Dash(
        __name__, 
        server=flask_app, 
        url_base_pathname='/dashboard/',
        external_stylesheets=[
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
        ]
    )
    
    # Define the dashboard layout
    dash_app.layout = html.Div([
        # Header
        html.Div([
            html.H1("📊 Super Gemini Analytics Dashboard", className="dashboard-title"),
            html.P("Interactive retail analytics with real-time insights", className="dashboard-subtitle"),
            html.Div([
                html.Button("🔄 Refresh Data", id="refresh-btn", className="control-btn"),
                html.Button("📈 Sales View", id="sales-view-btn", className="control-btn active"),
                html.Button("📦 Inventory View", id="inventory-view-btn", className="control-btn"),
                html.Button("🔄 Returns View", id="returns-view-btn", className="control-btn"),
            ], className="dashboard-controls")
        ], className="dashboard-header"),
        
        # Filters Row
        html.Div([
            html.Div([
                html.Label("📅 Date Range:", className="filter-label"),
                dcc.DatePickerRange(
                    id='date-range-picker',
                    start_date=datetime.now() - timedelta(days=30),
                    end_date=datetime.now(),
                    display_format='YYYY-MM-DD',
                    className="date-picker"
                )
            ], className="filter-item"),
            
            html.Div([
                html.Label("🏪 Store Filter:", className="filter-label"),
                dcc.Dropdown(
                    id='store-dropdown',
                    options=[
                        {'label': 'All Stores', 'value': 'all'},
                        {'label': 'Fargo (64)', 'value': '64'},
                        {'label': 'Springfield (65)', 'value': '65'},
                    ],
                    value='all',
                    className="dropdown"
                )
            ], className="filter-item"),
            
            html.Div([
                html.Label("🛍️ Category Filter:", className="filter-label"),
                dcc.Dropdown(
                    id='category-dropdown',
                    options=[
                        {'label': 'All Categories', 'value': 'all'},
                        {'label': "Men's Shoes", 'value': 'mens_shoes'},
                        {'label': 'Hunting', 'value': 'hunting'},
                        {'label': 'Golf', 'value': 'golf'},
                    ],
                    value='all',
                    className="dropdown"
                )
            ], className="filter-item"),
        ], className="filters-row"),
        
        # KPI Cards Row
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-dollar-sign kpi-icon"),
                    html.Div([
                        html.H3("$0", id="total-sales-kpi"),
                        html.P("Total Sales")
                    ])
                ], className="kpi-content")
            ], className="kpi-card sales"),
            
            html.Div([
                html.Div([
                    html.I(className="fas fa-chart-line kpi-icon"),
                    html.Div([
                        html.H3("0", id="total-units-kpi"),
                        html.P("Units Sold")
                    ])
                ], className="kpi-content")
            ], className="kpi-card units"),
            
            html.Div([
                html.Div([
                    html.I(className="fas fa-percentage kpi-icon"),
                    html.Div([
                        html.H3("0%", id="avg-margin-kpi"),
                        html.P("Avg Margin")
                    ])
                ], className="kpi-content")
            ], className="kpi-card margin"),
            
            html.Div([
                html.Div([
                    html.I(className="fas fa-boxes kpi-icon"),
                    html.Div([
                        html.H3("0", id="inventory-items-kpi"),
                        html.P("SKUs in Stock")
                    ])
                ], className="kpi-content")
            ], className="kpi-card inventory"),
        ], className="kpi-row"),
        
        # Charts Row 1
        html.Div([
            html.Div([
                html.H3("📈 Sales Trend", className="chart-title"),
                dcc.Graph(id='sales-trend-chart', className="dashboard-chart")
            ], className="chart-container half"),
            
            html.Div([
                html.H3("🏆 Top Products", className="chart-title"),
                dcc.Graph(id='top-products-chart', className="dashboard-chart")
            ], className="chart-container half"),
        ], className="charts-row"),
        
        # Charts Row 2
        html.Div([
            html.Div([
                html.H3("📊 Category Performance", className="chart-title"),
                dcc.Graph(id='category-performance-chart', className="dashboard-chart")
            ], className="chart-container half"),
            
            html.Div([
                html.H3("🗺️ Store Performance", className="chart-title"),
                dcc.Graph(id='store-performance-chart', className="dashboard-chart")
            ], className="chart-container half"),
        ], className="charts-row"),
        
        # Inventory Analysis Row (shown when inventory view active)
        html.Div([
            html.Div([
                html.H3("⚠️ Risk Analysis", className="chart-title"),
                dcc.Graph(id='risk-analysis-chart', className="dashboard-chart")
            ], className="chart-container half"),
            
            html.Div([
                html.H3("📦 Coverage Heatmap", className="chart-title"),
                dcc.Graph(id='coverage-heatmap-chart', className="dashboard-chart")
            ], className="chart-container half"),
        ], className="charts-row", id="inventory-row", style={'display': 'none'}),
        
        # Returns Analysis Row (shown when returns view active)
        html.Div([
            html.Div([
                html.H3("🔄 Return Trends", className="chart-title"),
                dcc.Graph(id='return-trends-chart', className="dashboard-chart")
            ], className="chart-container half"),
            
            html.Div([
                html.H3("📉 Return Rates by Category", className="chart-title"),
                dcc.Graph(id='return-rates-chart', className="dashboard-chart")
            ], className="chart-container half"),
        ], className="charts-row", id="returns-row", style={'display': 'none'}),
        
        # Data Table
        html.Div([
            html.H3("📋 Detailed Data", className="chart-title"),
            html.Div(id="data-table-container")
        ], className="table-container"),
        
        # Hidden div to store data
        html.Div(id='dashboard-data-store', style={'display': 'none'})
        
    ], className="dashboard-container")
    
    # Add custom CSS
    dash_app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                .dashboard-container {
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                
                .dashboard-header {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    padding: 30px;
                    margin-bottom: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                }
                
                .dashboard-title {
                    margin: 0 0 10px 0;
                    color: #333;
                    font-size: 2.5em;
                    font-weight: 700;
                }
                
                .dashboard-subtitle {
                    margin: 0 0 20px 0;
                    color: #666;
                    font-size: 1.2em;
                }
                
                .dashboard-controls {
                    display: flex;
                    gap: 15px;
                    flex-wrap: wrap;
                }
                
                .control-btn {
                    padding: 12px 24px;
                    border: none;
                    border-radius: 12px;
                    background: linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%);
                    color: #475569;
                    cursor: pointer;
                    font-weight: 600;
                    transition: all 0.3s ease;
                }
                
                .control-btn:hover, .control-btn.active {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
                }
                
                .filters-row {
                    display: flex;
                    gap: 20px;
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    padding: 20px;
                    border-radius: 15px;
                    margin-bottom: 20px;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    flex-wrap: wrap;
                }
                
                .filter-item {
                    flex: 1;
                    min-width: 200px;
                }
                
                .filter-label {
                    display: block;
                    margin-bottom: 8px;
                    font-weight: 600;
                    color: #333;
                }
                
                .kpi-row {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 20px;
                }
                
                .kpi-card {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 15px;
                    padding: 25px;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease;
                }
                
                .kpi-card:hover {
                    transform: translateY(-5px);
                }
                
                .kpi-content {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                }
                
                .kpi-icon {
                    font-size: 2.5em;
                    padding: 15px;
                    border-radius: 12px;
                    color: white;
                }
                
                .kpi-card.sales .kpi-icon { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
                .kpi-card.units .kpi-icon { background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); }
                .kpi-card.margin .kpi-icon { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); }
                .kpi-card.inventory .kpi-icon { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); }
                
                .kpi-content h3 {
                    margin: 0;
                    font-size: 2em;
                    font-weight: 700;
                    color: #333;
                }
                
                .kpi-content p {
                    margin: 5px 0 0 0;
                    color: #666;
                    font-weight: 500;
                }
                
                .charts-row {
                    display: flex;
                    gap: 20px;
                    margin-bottom: 20px;
                    flex-wrap: wrap;
                }
                
                .chart-container {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 15px;
                    padding: 20px;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                }
                
                .chart-container.half {
                    flex: 1;
                    min-width: 400px;
                }
                
                .chart-container.full {
                    width: 100%;
                }
                
                .chart-title {
                    margin: 0 0 15px 0;
                    color: #333;
                    font-size: 1.3em;
                    font-weight: 600;
                }
                
                .dashboard-chart {
                    height: 350px;
                }
                
                .table-container {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 15px;
                    padding: 20px;
                    box-shadow: 0 5px 20px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }
                
                @media (max-width: 768px) {
                    .dashboard-controls {
                        flex-direction: column;
                    }
                    
                    .filters-row {
                        flex-direction: column;
                    }
                    
                    .charts-row {
                        flex-direction: column;
                    }
                    
                    .chart-container.half {
                        min-width: auto;
                    }
                }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''
    
    # Register callbacks
    register_callbacks(dash_app)
    
    return dash_app

def register_callbacks(dash_app):
    """Register all dashboard callbacks."""
    
    @dash_app.callback(
        [Output('sales-view-btn', 'className'),
         Output('inventory-view-btn', 'className'),
         Output('returns-view-btn', 'className'),
         Output('inventory-row', 'style'),
         Output('returns-row', 'style')],
        [Input('sales-view-btn', 'n_clicks'),
         Input('inventory-view-btn', 'n_clicks'),
         Input('returns-view-btn', 'n_clicks')]
    )
    def update_view_mode(sales_clicks, inventory_clicks, returns_clicks):
        """Switch between different dashboard views."""
        ctx = callback_context
        if not ctx.triggered:
            # Default view
            return (
                'control-btn active', 'control-btn', 'control-btn',
                {'display': 'none'}, {'display': 'none'}
            )
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if button_id == 'inventory-view-btn':
            return (
                'control-btn', 'control-btn active', 'control-btn',
                {'display': 'flex'}, {'display': 'none'}
            )
        elif button_id == 'returns-view-btn':
            return (
                'control-btn', 'control-btn', 'control-btn active',
                {'display': 'none'}, {'display': 'flex'}
            )
        else:  # sales-view-btn
            return (
                'control-btn active', 'control-btn', 'control-btn',
                {'display': 'none'}, {'display': 'none'}
            )
    
    @dash_app.callback(
        [Output('total-sales-kpi', 'children'),
         Output('total-units-kpi', 'children'),
         Output('avg-margin-kpi', 'children'),
         Output('inventory-items-kpi', 'children')],
        [Input('refresh-btn', 'n_clicks'),
         Input('date-range-picker', 'start_date'),
         Input('date-range-picker', 'end_date'),
         Input('store-dropdown', 'value'),
         Input('category-dropdown', 'value')]
    )
    def update_kpis(refresh_clicks, start_date, end_date, store_filter, category_filter):
        """Update KPI cards with current data."""
        # This would normally fetch real data from BigQuery
        # For now, return sample data
        return "$125,450", "2,340", "24.5%", "1,234"
    
    @dash_app.callback(
        Output('sales-trend-chart', 'figure'),
        [Input('refresh-btn', 'n_clicks'),
         Input('date-range-picker', 'start_date'),
         Input('date-range-picker', 'end_date'),
         Input('store-dropdown', 'value')]
    )
    def update_sales_trend(refresh_clicks, start_date, end_date, store_filter):
        """Update sales trend chart."""
        # Generate sample data
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        sales = [1000 + i*50 + (i%7)*200 for i in range(len(dates))]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=sales,
            mode='lines+markers',
            name='Daily Sales',
            line=dict(color='#667eea', width=3),
            marker=dict(size=6)
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)'),
            yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)'),
            hovermode='x unified'
        )
        
        return fig
    
    @dash_app.callback(
        Output('top-products-chart', 'figure'),
        [Input('refresh-btn', 'n_clicks'),
         Input('category-dropdown', 'value')]
    )
    def update_top_products(refresh_clicks, category_filter):
        """Update top products chart."""
        # Sample data
        products = ['Product A', 'Product B', 'Product C', 'Product D', 'Product E']
        sales = [1500, 1200, 1000, 800, 600]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=products,
            y=sales,
            marker_color='#34d399',
            text=sales,
            textposition='auto'
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.1)')
        )
        
        return fig
    
    @dash_app.callback(
        Output('category-performance-chart', 'figure'),
        [Input('refresh-btn', 'n_clicks'),
         Input('store-dropdown', 'value')]
    )
    def update_category_performance(refresh_clicks, store_filter):
        """Update category performance chart."""
        # Sample data
        categories = ['Shoes', 'Apparel', 'Accessories', 'Equipment']
        revenue = [15000, 12000, 8000, 10000]
        
        fig = go.Figure()
        fig.add_trace(go.Pie(
            labels=categories,
            values=revenue,
            hole=0.4,
            marker_colors=['#667eea', '#34d399', '#f59e0b', '#ef4444']
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5)
        )
        
        return fig
    
    @dash_app.callback(
        Output('store-performance-chart', 'figure'),
        [Input('refresh-btn', 'n_clicks'),
         Input('date-range-picker', 'start_date'),
         Input('date-range-picker', 'end_date')]
    )
    def update_store_performance(refresh_clicks, start_date, end_date):
        """Update store performance chart."""
        # Sample data
        stores = ['Fargo', 'Springfield', 'Des Moines', 'Omaha']
        sales = [25000, 22000, 18000, 20000]
        units = [500, 450, 380, 420]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=stores,
            y=sales,
            name='Sales ($)',
            marker_color='#667eea',
            yaxis='y'
        ))
        fig.add_trace(go.Scatter(
            x=stores,
            y=units,
            mode='lines+markers',
            name='Units',
            marker_color='#f59e0b',
            yaxis='y2'
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            yaxis=dict(title='Sales ($)', side='left'),
            yaxis2=dict(title='Units', side='right', overlaying='y'),
            xaxis=dict(showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        
        return fig
    
    # Inventory analysis callbacks
    @dash_app.callback(
        Output('risk-analysis-chart', 'figure'),
        [Input('inventory-view-btn', 'n_clicks'),
         Input('refresh-btn', 'n_clicks')]
    )
    def update_risk_analysis(inventory_clicks, refresh_clicks):
        """Update inventory risk analysis chart."""
        # Sample risk data
        risk_levels = ['Critical', 'High', 'Medium', 'Low', 'Adequate']
        counts = [45, 120, 200, 150, 300]
        colors = ['#ef4444', '#f59e0b', '#fbbf24', '#34d399', '#10b981']
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=risk_levels,
            y=counts,
            marker_color=colors,
            text=counts,
            textposition='auto'
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            title="Inventory Risk Distribution"
        )
        
        return fig
    
    # Returns analysis callbacks
    @dash_app.callback(
        Output('return-trends-chart', 'figure'),
        [Input('returns-view-btn', 'n_clicks'),
         Input('refresh-btn', 'n_clicks')]
    )
    def update_return_trends(returns_clicks, refresh_clicks):
        """Update return trends chart."""
        # Sample return trend data
        dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='M')
        return_rates = [2.5, 3.1, 2.8, 3.5, 4.2, 3.8, 3.2, 2.9, 3.4, 3.7, 4.1, 3.6]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=return_rates,
            mode='lines+markers',
            name='Return Rate %',
            line=dict(color='#ef4444', width=3),
            marker=dict(size=8)
        ))
        
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color='#333',
            margin=dict(l=0, r=0, t=0, b=0),
            yaxis=dict(title='Return Rate (%)'),
            title="Monthly Return Rate Trends"
        )
        
        return fig

def get_sample_data():
    """Generate sample data for dashboard demo."""
    return {
        'sales_data': pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30, freq='D'),
            'sales': [1000 + i*50 + (i%7)*200 for i in range(30)]
        }),
        'inventory_data': pd.DataFrame({
            'sku': [f'SKU-{i:04d}' for i in range(100)],
            'risk_level': ['Critical']*10 + ['High']*20 + ['Medium']*30 + ['Low']*25 + ['Adequate']*15,
            'coverage_percentage': [25, 30, 45, 50, 55, 60, 65, 70, 75, 80] * 10
        })
    }

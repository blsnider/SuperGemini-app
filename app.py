# app.py - Updated for API separation (using your existing config pattern)
from flask import Flask, render_template, request, jsonify, session
import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
import traceback
import sys

# Load environment variables
load_dotenv()

# Configure logging
environment = os.getenv('ENVIRONMENT', 'production')
logging.basicConfig(
    level=logging.INFO if environment == 'production' else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info(f"=== Starting Super Gemini Application ({environment}) ===")

# Test Google Cloud setup for smart fallback
def test_google_cloud_setup():
    """Test Google Cloud libraries and authentication setup."""
    try:
        import google.auth
        import google.cloud.secretmanager
        credentials, project = google.auth.default()
        logger.info(f"✅ GCP authentication successful, project: {project}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ GCP authentication not available: {e}")
        return False

gcp_available = test_google_cloud_setup()

# Security and Rate Limiting Imports
try:
    from google.cloud import secretmanager
    SECURITY_FEATURES_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Security features not available due to missing dependencies: {e}")
    SECURITY_FEATURES_AVAILABLE = False

# Smart Secret Loading (from your original app.py)
def load_secret(secret_name: str, project_id: str = None) -> str:
    """Load secret from GCP Secret Manager with smart fallback."""
    # Check environment variable first
    env_var_name = secret_name.upper().replace('-', '_')
    env_value = os.getenv(env_var_name)
    
    if env_value:
        logger.info(f"✅ Using environment variable for {secret_name}")
        return env_value
    
    # Try Secret Manager only if available and in production-like environment
    if not SECURITY_FEATURES_AVAILABLE or not gcp_available:
        logger.warning(f"Secret Manager not available for {secret_name}")
        return ''
    
    try:
        # Use the correct project for secrets - sis-sandbox-463113 is where your secrets are!
        if not project_id:
            project_id = (
                os.getenv('SECRETS_PROJECT') or 
                'sis-sandbox-463113'  # Your actual secrets project
            )
            
        logger.info(f"Loading {secret_name} from project: {project_id}")
            
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        logger.info(f"✅ Successfully loaded {secret_name} from Secret Manager")
        return secret_value
        
    except Exception as e:
        logger.error(f"❌ Failed to load secret {secret_name}: {e}")
        return ''

def load_api_keys():
    """Load API keys with smart fallback logic."""
    try:
        logger.info("Loading API keys...")
        
        api_keys = {
            'GOOGLE_API_KEY': load_secret('GOOGLE_API_KEY'),
            'XAI_API_KEY': load_secret('XAI_API_KEY'),
            'ANTHROPIC_API_KEY': load_secret('ANTHROPIC_API_KEY'),
            'OPENAI_API_KEY': load_secret('OPENAI_API_KEY')
        }
        
        loaded_count = 0
        for key, value in api_keys.items():
            if value:
                os.environ[key] = value
                logger.info(f"✅ {key} loaded successfully")
                loaded_count += 1
            else:
                logger.warning(f"⚠️  {key} not found")
        
        logger.info(f"✅ {loaded_count}/{len(api_keys)} API keys loaded successfully")
        
    except Exception as e:
        logger.error(f"Error loading API keys: {e}")

# Load API keys at startup (skip if we're just building Docker image)
if os.getenv('SKIP_INIT') != 'true':
    load_api_keys()

# Import your existing modules
try:
    logger.info("Loading application modules...")
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from chatbot.config import get_available_models, get_store_mappings, get_shop_mappings
    from chatbot import SuperGeminiRetailChatbot
    from dashboard import DashboardManager
    logger.info("✅ All application modules loaded successfully")
    
except Exception as e:
    logger.error(f"❌ Import error: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    raise

# Use your existing configuration pattern
@dataclass
class AppConfig:
    bq_project: str = os.getenv('BQ_PROJECT', 'scheels-data-marts')
    model_name: str = os.getenv('DEFAULT_MODEL', 'gemini-2.5-pro')
    preview_rows: int = int(os.getenv('PREVIEW_ROWS', '20'))
    enable_weighting: bool = os.getenv('ENABLE_WEIGHTING', 'True').lower() == 'true'
    enable_auth: bool = os.getenv('ENABLE_AUTH', 'False').lower() == 'true'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Initialize config and services using your existing pattern
config = AppConfig()
logger.info(f"Configuration: {config}")

# Initialize services - using your existing chatbot initialization pattern
# Defer initialization to avoid issues during Docker build
chatbot = None
dashboard_manager = None

def get_chatbot():
    """Lazy initialization of chatbot"""
    global chatbot
    if chatbot is None:
        chatbot = SuperGeminiRetailChatbot(config)
    return chatbot

def get_dashboard_manager():
    """Lazy initialization of dashboard manager"""
    global dashboard_manager
    if dashboard_manager is None:
        dashboard_manager = DashboardManager()
    return dashboard_manager

# =============================================================================
# PAGE ROUTES (Serve HTML pages)
# =============================================================================

@app.route('/')
def index():
    """Main page - redirect to chat"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard_page():
    """Dashboard page"""
    return render_template('dashboard.html')

@app.route('/chat')
def chat_page():
    """Chat interface page"""
    return render_template('chat.html')

# Legacy endpoints (keep for backward compatibility)
@app.route('/chat_api', methods=['POST'])  # Changed from '/chat' to '/chat_api'
def legacy_chat():
    """Legacy chat endpoint - redirect to new API"""
    return api_chat_message()

@app.route('/models')
def legacy_models():
    """Legacy models endpoint - redirect to new API"""
    return api_get_models()

@app.route('/history')
def get_history():
    """Get query history"""
    try:
        bot = get_chatbot()
        # Get recent queries from session or database
        history = bot.get_recent_queries(limit=10) if hasattr(bot, 'get_recent_queries') else []
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/suggest')
def get_suggestions():
    """Get query suggestions based on partial input"""
    try:
        query = request.args.get('q', '').strip()
        if len(query) < 2:
            return jsonify({'success': True, 'suggestions': []})
        
        # Simple suggestions based on common queries
        suggestions = []
        
        # Common query patterns
        common_patterns = [
            "top selling items",
            "inventory status", 
            "out of stock items",
            "overstock analysis",
            "sales trends",
            "return analysis",
            "store performance",
            "margin analysis",
            "inventory at risk"
        ]
        
        # Filter patterns that match the query
        for pattern in common_patterns:
            if query.lower() in pattern.lower():
                suggestions.append({
                    'text': pattern,
                    'type': 'suggested'
                })
        
        return jsonify({'success': True, 'suggestions': suggestions[:5]})
    except Exception as e:
        logger.error(f"Error getting suggestions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/clear_history', methods=['POST'])
def clear_history():
    """Clear query history"""
    try:
        # Clear from session if implemented
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cost_summary')
def get_cost_summary():
    """Get current session cost summary"""
    try:
        bot = get_chatbot()
        # Get cost info from session or calculate
        cost_summary = {
            'total_session_cost': session.get('total_cost', 0.0),
            'queries_executed': session.get('query_count', 0),
            'average_cost_per_query': 0.0
        }
        
        if cost_summary['queries_executed'] > 0:
            cost_summary['average_cost_per_query'] = cost_summary['total_session_cost'] / cost_summary['queries_executed']
            
        return jsonify({'success': True, 'cost_summary': cost_summary})
    except Exception as e:
        logger.error(f"Error getting cost summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/export', methods=['POST'])
def export_data():
    """Export data in specified format"""
    try:
        data = request.get_json()
        format_type = data.get('format', 'csv')
        
        bot = get_chatbot()
        if not hasattr(bot, 'last_df') or bot.last_df is None:
            return jsonify({'success': False, 'error': 'No data available to export'}), 400
            
        if format_type == 'csv':
            csv_data = bot.last_df.to_csv(index=False)
            return jsonify({
                'success': True,
                'data': csv_data,
                'filename': 'export.csv',
                'mime_type': 'text/csv'
            })
        elif format_type == 'json':
            json_data = bot.last_df.to_json(orient='records')
            return jsonify({
                'success': True,
                'data': json_data,
                'filename': 'export.json',
                'mime_type': 'application/json'
            })
        else:
            return jsonify({'success': False, 'error': 'Unsupported format'}), 400
            
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate_chart', methods=['POST'])
def generate_chart():
    """Generate chart for the last query results"""
    try:
        bot = get_chatbot()
        if not hasattr(bot, 'last_df') or bot.last_df is None:
            return jsonify({'success': False, 'error': 'No data available for chart'}), 400
            
        # Simple chart generation - you can enhance this
        chart_html = "<div>Chart generation not yet implemented</div>"
        
        return jsonify({'success': True, 'chart': chart_html})
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate_summary', methods=['POST'])
def generate_summary():
    """Generate AI summary for the last query results"""
    try:
        data = request.get_json()
        model = data.get('model')
        
        bot = get_chatbot()
        # Check for last_df instead of df
        if not hasattr(bot, 'last_df') or bot.last_df is None:
            return jsonify({'success': False, 'error': 'No data available to summarize'}), 400
            
        # Use the summarizer module
        from chatbot.summarizer import generate_summary as gen_summary
        summary = gen_summary(
            df=bot.last_df,
            query=bot.last_query or '',
            model_name=model,
            available_models=get_available_models(),
            api_clients=bot.api_clients,
            bigquery_utils=bot.bigquery_utils
        )
        
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug/mcp_status')
def debug_mcp_status():
    """Debug endpoint to check MCP toolbox status"""
    try:
        bot = get_chatbot()
        diagnostic_info = {
            'chatbot_status': {
                'initialized': bot is not None,
                'toolbox_enabled': hasattr(bot, 'toolbox') and bot.toolbox is not None,
                'tools_count': len(bot.available_tools) if hasattr(bot, 'available_tools') else 0,
                'available_tools': list(bot.available_tools.keys()) if hasattr(bot, 'available_tools') else []
            },
            'connection_test': 'OK' if bot else 'Failed'
        }
        
        return jsonify({'success': True, 'diagnostic_info': diagnostic_info})
    except Exception as e:
        logger.error(f"Error in MCP status check: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =============================================================================
# API ROUTES (Return JSON data)
# =============================================================================

# Chat API endpoints
@app.route('/api/chat/message', methods=['POST'])
def api_chat_message():
    """Process chat message - API endpoint"""
    try:
        data = request.get_json()
        query = data.get('query')
        model = data.get('model')
        mcp_tool = data.get('mcp_tool')  # Get explicit MCP tool selection
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
            
        response = get_chatbot().chat(query, model, mcp_tool=mcp_tool)
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/models')
def api_get_models():
    """Get available models - API endpoint"""
    try:
        models = get_available_models()
        return jsonify({'success': True, 'models': models})
    except Exception as e:
        logger.error(f"Models API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mcp/tools')
def api_get_mcp_tools():
    """Get available MCP tools - API endpoint"""
    try:
        bot = get_chatbot()
        if not bot or not bot.toolbox_enabled:
            return jsonify({
                'success': False,
                'error': 'MCP toolbox not enabled',
                'tools': []
            })
        
        # Get available tools with descriptions
        tools_list = []
        if hasattr(bot, 'tools') and isinstance(bot.tools, dict):
            # Map tool names to user-friendly descriptions
            tool_descriptions = {
                'get_top_selling_items': 'Top Selling Items',
                'get_units_vs_dollars_comparison': 'Units vs Dollars Comparison',
                'get_shop_performance': 'Shop Performance Analysis',
                'get_sell_through_rates': 'Sell-Through Rate Analysis',
                'get_time_period_comparison': 'Time Period Comparison',
                'get_inventory_status': 'Inventory Status',
                'get_current_inventory_status': 'Current Inventory Status',
                'get_inventory_risk_assessment': 'Inventory Risk Assessment',
                'get_out_of_stock_items': 'Out of Stock Items',
                'get_sales_trends': 'Sales Trends',
                'get_top_margin_items': 'Top Margin Items',
                'get_overstock_items': 'Overstock Analysis',
                'get_comparison_analysis': 'Store/Shop Comparison',
                'get_return_analysis': 'Return Analysis'
            }
            
            for tool_name in sorted(bot.tools.keys()):
                tools_list.append({
                    'id': tool_name,
                    'name': tool_descriptions.get(tool_name, tool_name.replace('_', ' ').title()),
                    'description': f"Execute {tool_name} MCP tool"
                })
        
        return jsonify({
            'success': True,
            'tools': tools_list
        })
    except Exception as e:
        logger.error(f"MCP tools API error: {e}")
        return jsonify({'success': False, 'error': str(e), 'tools': []}), 500

@app.route('/api/chat/summary', methods=['POST'])
def api_generate_summary():
    """Generate summary for last query - lazy loading endpoint"""
    try:
        data = request.get_json()
        model = data.get('model')
        query_id = data.get('query_id')
        
        bot = get_chatbot()
        if not bot:
            return jsonify({'success': False, 'error': 'Chatbot not initialized'}), 500
        
        # Generate summary for the last query
        result = bot.generate_summary_for_last_query(model)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/mcp/test')
def test_mcp():
    """Test MCP toolbox connection and tools"""
    try:
        bot = get_chatbot()
        if not bot or not bot.toolbox_enabled:
            return jsonify({
                'success': False,
                'error': 'MCP toolbox not enabled',
                'toolbox_enabled': bot.toolbox_enabled if bot else False
            })
        
        # Get available tools
        tools_list = []
        if hasattr(bot, 'tools') and isinstance(bot.tools, dict):
            tools_list = list(bot.tools.keys())
        
        # Test a simple query
        test_result = None
        if 'get_sales_trends' in tools_list:
            try:
                tool = bot.tools['get_sales_trends']
                test_result = tool(days_back=7, store_id=0, shop_id=0)
                test_result = {'success': True, 'rows': len(test_result) if test_result else 0}
            except Exception as e:
                test_result = {'success': False, 'error': str(e)}
        
        return jsonify({
            'success': True,
            'toolbox_enabled': True,
            'available_tools': tools_list,
            'tools_count': len(tools_list),
            'test_query': test_result
        })
        
    except Exception as e:
        logger.error(f"MCP test error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Dashboard API endpoints
@app.route('/api/dashboard/kpis')
def api_dashboard_kpis():
    """Get executive KPIs - API endpoint"""
    try:
        kpis = get_dashboard_manager().get_executive_kpis()
        return jsonify({'success': True, 'data': kpis})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/sales-trends')
def api_sales_trends():
    """Get sales trends - API endpoint"""
    period = request.args.get('period', '30d')
    store_id = request.args.get('store_id', 0, type=int)
    
    try:
        trends = get_dashboard_manager().get_sales_trends(period, store_id)
        return jsonify({'success': True, 'data': trends})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/top-performers')
def api_top_performers():
    """Get top performing items - API endpoint"""
    limit = request.args.get('limit', 10, type=int)
    store_id = request.args.get('store_id', 0, type=int)
    
    try:
        performers = get_dashboard_manager().get_top_performers(limit, store_id)
        return jsonify({'success': True, 'data': performers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/stock-alerts')
def api_stock_alerts():
    """Get stock alerts - API endpoint"""
    try:
        alerts = get_dashboard_manager().get_stock_alerts()
        return jsonify({'success': True, 'data': alerts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/metrics')
def api_dashboard_metrics():
    """Get dashboard metrics - API endpoint"""
    try:
        # Get store and shop IDs from query parameters
        store_id = request.args.get('store_id', 0, type=int)
        shop_id = request.args.get('shop_id', 0, type=int)
        
        logger.info(f"Fetching dashboard metrics for store: {store_id}, shop: {shop_id}")
        
        # Build query for top selling items to get aggregate metrics
        query = f"show me top selling items"
        if store_id > 0:
            query += f" for store {store_id}"
        if shop_id > 0:
            query += f" in shop {shop_id}"
        query += " for last 42 days"
        
        # Get data from chatbot/MCP
        result = get_chatbot().chat(query, config.model_name)
        
        # Extract metrics from result
        metrics = {
            'total_revenue': 0,
            'margin_pct': 0,
            'total_units': 0,
            'total_profit': 0,
            'total_cogs': 0
        }
        
        if result.get('success') and result.get('has_data'):
            try:
                # Try to extract metrics from summary statistics first
                summary_stats = result.get('summary_statistics', {})
                
                if summary_stats:
                    # Use summary statistics for accurate totals
                    total_revenue = 0
                    total_units = 0
                    margin_pct = 0
                    
                    # Extract from summary stats
                    for key, value in summary_stats.items():
                        key_lower = key.lower()
                        # Clean numeric values (remove $, commas, %)
                        clean_value = str(value).replace('$', '').replace(',', '').replace('%', '')
                        
                        if 'grand_total_revenue' in key_lower or 'total_revenue' in key_lower:
                            try:
                                total_revenue = float(clean_value)
                            except:
                                pass
                        elif 'grand_total_units' in key_lower or 'total_units' in key_lower:
                            try:
                                total_units = int(float(clean_value))
                            except:
                                pass
                        elif 'avg_margin_pct' in key_lower or 'margin_pct' in key_lower:
                            try:
                                margin_pct = float(clean_value)
                            except:
                                pass
                    
                    # Calculate profit and COGS based on margin
                    total_profit = (total_revenue * margin_pct / 100) if margin_pct > 0 else 0
                    total_cogs = total_revenue - total_profit
                    
                    logger.info(f"Extracted from summary stats: revenue={total_revenue}, units={total_units}, margin={margin_pct}%")
                else:
                    # Fallback to calculating from raw data
                    results_data = result.get('results_data', [])
                    if results_data and len(results_data) > 0:
                        # Sum up the metrics from the data
                        total_revenue = 0
                        total_units = 0
                        total_profit = 0
                        
                        for row in results_data:
                            # Handle different possible column names
                            revenue = float(row.get('total_revenue', 0) or row.get('revenue', 0) or 0)
                            units = int(row.get('total_units', 0) or row.get('units_sold', 0) or row.get('units', 0) or 0)
                            margin = float(row.get('total_margin', 0) or row.get('margin', 0) or 0)
                            
                            total_revenue += revenue
                            total_units += units
                            total_profit += margin
                        
                        # Calculate COGS and margin
                        total_cogs = total_revenue - total_profit
                        margin_pct = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
                
                # Set metrics regardless of which path we took
                metrics['total_revenue'] = total_revenue
                metrics['margin_pct'] = margin_pct
                metrics['total_units'] = total_units
                metrics['total_profit'] = total_profit
                metrics['total_cogs'] = total_cogs
                
                logger.info(f"Calculated metrics: {metrics}")
            except Exception as calc_error:
                logger.error(f"Error calculating metrics: {calc_error}")
            # Check if results_data is defined
            if 'results_data' in locals():
                logger.error(f"Sample data: {results_data[0] if results_data else 'No data'}")
            else:
                logger.error("No results_data available")
        
        return jsonify({'success': True, 'metrics': metrics})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/chart/<chart_type>')
def api_dashboard_chart(chart_type):
    """Get dashboard chart HTML - API endpoint"""
    try:
        # Get store and shop IDs from query parameters
        store_id = request.args.get('store_id', 0, type=int)
        shop_id = request.args.get('shop_id', 0, type=int)
        
        logger.info(f"Generating {chart_type} chart for store: {store_id}, shop: {shop_id}")
        
        # Map chart types to appropriate queries
        chart_queries = {
            'salesTrend': 'show me sales trends',
            'topSellingItems': 'show me top 10 selling items',
            'topMarginItems': 'show me top 10 items by margin',
            'inventoryStatus': 'show inventory status',
            'outOfStock': 'show out of stock items',
            'overstockItems': 'show overstock items',
            'storeComparison': 'show store comparison analysis'
        }
        
        query = chart_queries.get(chart_type, 'show me sales data')
        if store_id > 0:
            query += f" for store {store_id}"
        if shop_id > 0:
            query += f" in shop {shop_id}"
        query += " for last 42 days"
        
        # Get data from chatbot/MCP
        result = get_chatbot().chat(query, config.model_name)
        
        if result.get('success') and result.get('has_data'):
            # Generate chart visualization from result
            try:
                # Get the visualization if available
                if result.get('visualization'):
                    chart_html = result['visualization']
                else:
                    # Create a simple table view of the data
                    results_data = result.get('results_data', [])
                    if results_data:
                        chart_html = '<div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">'
                        chart_html += '<table>'
                        
                        # Headers
                        if len(results_data) > 0:
                            chart_html += '<thead><tr>'
                            for key in results_data[0].keys():
                                # Format header names
                                display_header = key.replace('_', ' ').title()
                                display_header = display_header.replace('Pct', '%').replace('Id', 'ID')
                                chart_html += f'<th>{display_header}</th>'
                            chart_html += '</tr></thead>'
                        
                        # Data rows
                        chart_html += '<tbody>'
                        for i, row in enumerate(results_data[:20]):  # Limit to 20 rows
                            chart_html += '<tr>'
                            for key, value in row.items():
                                # Determine CSS class and format value
                                css_class = ''
                                if isinstance(value, (int, float)):
                                    key_lower = str(key).lower()
                                    # Check for margin/percentage columns first
                                    if 'margin' in key_lower or 'pct' in key_lower or 'percent' in key_lower or '%' in key_lower:
                                        display_value = f'{value:.1f}%'
                                        css_class = 'percentage'
                                    # Then check for units/count columns
                                    elif 'units' in key_lower or 'count' in key_lower or 'quantity' in key_lower:
                                        display_value = f'{int(value):,}'
                                        css_class = 'units'
                                    # Check for currency columns (but exclude margin!)
                                    elif ('revenue' in key_lower or 'cost' in key_lower or 'price' in key_lower or 
                                          'profit' in key_lower or 'cogs' in key_lower or 'sales' in key_lower) and 'margin' not in key_lower:
                                        if value > 1000:
                                            display_value = f'${value:,.0f}'
                                        else:
                                            display_value = f'${value:,.2f}'
                                        css_class = 'currency'
                                    # Default for other numbers
                                    else:
                                        if value > 1000:
                                            display_value = f'{value:,.0f}'
                                        else:
                                            display_value = f'{value:,.2f}'
                                else:
                                    display_value = str(value)
                                
                                chart_html += f'<td class="{css_class}">{display_value}</td>'
                            chart_html += '</tr>'
                        chart_html += '</tbody></table></div>'
                        
                        if len(results_data) > 20:
                            chart_html += f'<p style="text-align: center; color: #666; margin-top: 10px;">Showing first 20 of {len(results_data)} rows</p>'
                    else:
                        chart_html = '<div style="text-align: center; padding: 40px;">No data available</div>'
            except Exception as viz_error:
                logger.error(f"Error generating visualization: {viz_error}")
                chart_html = f'<div style="text-align: center; padding: 40px; color: #ef4444;">Error generating chart: {str(viz_error)}</div>'
        else:
            error_msg = result.get('error', 'No data available')
            chart_html = f'<div style="text-align: center; padding: 40px; color: #666;">{error_msg}</div>'
        
        return jsonify({'success': True, 'chart_html': chart_html})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test chatbot initialization
        bot = get_chatbot()
        status = bot.get_toolbox_status() if bot and hasattr(bot, 'get_toolbox_status') else {'status': 'unknown'}
        return jsonify({
            'status': 'healthy' if status.get('toolbox_enabled', False) else 'degraded',
            'chatbot': status
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/api/chat/queries')
def get_query_history():
    """Get query history from local storage or BigQuery"""
    try:
        bot = get_chatbot()
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 50))
        
        # Get query history from chatbot (will try BigQuery first, then local)
        history = bot.get_local_query_history(user_id=user_id, limit=limit)
        
        return jsonify({
            'success': True,
            'queries': history,
            'count': len(history)
        })
    except Exception as e:
        logger.error(f"Failed to get query history: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'queries': []
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
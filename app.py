# app.py - Updated for API separation (using your existing config pattern)
from flask import Flask, render_template, request, jsonify
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
    return render_template('chat.html')

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
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
            
        response = get_chatbot().chat(query, model)
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
        
        # Build query for sales trends to get detailed data
        query = f"show me sales trends"
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
            # Try to extract metrics from the data
            try:
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
                        profit = float(row.get('total_profit', 0) or row.get('profit', 0) or 0)
                        
                        total_revenue += revenue
                        total_units += units
                        total_profit += profit
                    
                    # Calculate COGS and margin
                    total_cogs = total_revenue - total_profit
                    margin_pct = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
                    
                    metrics['total_revenue'] = total_revenue
                    metrics['margin_pct'] = margin_pct
                    metrics['total_units'] = total_units
                    metrics['total_profit'] = total_profit
                    metrics['total_cogs'] = total_cogs
                    
                    logger.info(f"Calculated metrics: {metrics}")
            except Exception as calc_error:
                logger.error(f"Error calculating metrics: {calc_error}")
                logger.error(f"Sample data: {results_data[0] if results_data else 'No data'}")
        
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
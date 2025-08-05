# app.py - Updated for API separation (using your existing config pattern)
from flask import Flask, render_template, request, jsonify, session
import os
import logging
import json
from dataclasses import dataclass
from dotenv import load_dotenv
import traceback
import sys
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


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
        snapshot_date = data.get('snapshot_date')  # Get snapshot date for inventory tools
        
        # Debug logging
        logger.info(f"📥 Received request data: {json.dumps(data, indent=2)}")
        logger.info(f"📅 Snapshot date from request: {snapshot_date}")
        
        if not query:
            return jsonify({'success': False, 'error': 'Query is required'}), 400
            
        response = get_chatbot().chat(query, model, mcp_tool=mcp_tool, snapshot_date=snapshot_date)
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
                'get_top_selling_items': 'get_top_selling_items',
                'get_top_selling_item_comparison': 'get_top_selling_item_comparison',
                'get_units_vs_dollars_comparison': 'get_units_vs_dollars_comparison',
                'get_shop_performance': 'get_shop_performance',
                'get_1Y_out_of_stock_items': 'get_1Y_out_of_stock_items',
                'get_sales_trends': 'get_sales_trends',
                'get_sell_through_rates': 'get_sell_through_rates',
                'get_time_period_comparison': 'get_time_period_comparison',
                'get_inventory_status': 'get_inventory_status',
                'get_top_margin_items': 'get_top_margin_items',
                'get_overstock_items': 'get_overstock_items',
                'get_comparison_analysis': 'get_comparison_analysis',
                'get_advanced_inventory_turnover': 'get_advanced_inventory_turnover',
                'get_advanced_stockout_analysis': 'get_advanced_stockout_analysis',
                'get_advanced_carrying_costs': 'get_advanced_carrying_costs',
                'get_advanced_gmroi_performance': 'get_advanced_gmroi_performance',
                'get_advanced_vendor_metrics': 'get_advanced_vendor_metrics',
                'get_advanced_forecast_accuracy': 'get_advanced_forecast_accuracy',
                'get_otb_metrics': 'get_otb_metrics',
                'get_sales_variance_analysis': 'get_sales_variance_analysis',
                'get_margin_variance_report': 'get_margin_variance_report'
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

@app.route('/api/mcp/execute', methods=['POST'])
def api_execute_mcp_tool():
    """Execute MCP tool directly with parameters"""
    try:
        data = request.get_json()
        tool_name = data.get('tool')
        parameters = data.get('parameters', {})
        
        if not tool_name:
            return jsonify({'success': False, 'error': 'No tool specified'}), 400
        
        bot = get_chatbot()
        if not bot or not bot.toolbox_enabled:
            return jsonify({
                'success': False,
                'error': 'MCP toolbox not enabled'
            }), 500
        
        # Check if tool exists
        if tool_name not in bot.tools:
            return jsonify({
                'success': False,
                'error': f'Tool {tool_name} not found'
            }), 404
        
        # Execute the MCP tool directly
        tool = bot.tools[tool_name]
        
        try:
            # Call the tool with parameters
            logger.info(f"Executing MCP tool directly: {tool_name} with params: {parameters}")
            result = tool(**parameters)
            
            # Process the result into DataFrame
            df = bot._process_mcp_result(result, tool_name)
            
            if df is None or df.empty:
                return jsonify({
                    'success': True,
                    'results': [],
                    'row_count': 0,
                    'has_data': False,
                    'message': 'Query executed successfully but returned no data',
                    'tool_name': tool_name,
                    'parameters': parameters
                })
            
            # Store the last tool used for formatting
            bot.last_tool_used = tool_name
            
            # Format the results
            results = bot._format_results(df)
            
            # Calculate summary statistics
            summary_stats = bot._calculate_summary_statistics(df)
            
            return jsonify({
                'success': True,
                'results': results,
                'results_data': results,
                'row_count': len(df),
                'total_rows': len(df),
                'has_data': True,
                'tool_name': tool_name,
                'parameters': parameters,
                'summary_statistics': summary_stats,
                'columns': list(df.columns) if not df.empty else []
            })
            
        except Exception as tool_error:
            logger.error(f"Tool execution error: {tool_error}")
            return jsonify({
                'success': False,
                'error': f'Tool execution failed: {str(tool_error)}'
            }), 500
        
    except Exception as e:
        logger.error(f"MCP tool execution error: {e}")
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
    """Get dashboard metrics - API endpoint with foolproof YoY analysis"""
    try:
        store_id = request.args.get('store_id', 0, type=int)
        shop_id = request.args.get('shop_id', 0, type=int)
        
        logger.info(f"Fetching dashboard metrics for store: {store_id}, shop: {shop_id}")
        
        today = datetime.today().date()

        # Define exact date ranges
        end_current_period = today
        start_current_period = end_current_period - timedelta(days=41)  # 42 days inclusive

        end_prior_period = end_current_period - relativedelta(years=1)
        start_prior_period = start_current_period - relativedelta(years=1)

        current_period_str = f"from {start_current_period} to {end_current_period}"
        prior_period_str = f"from {start_prior_period} to {end_prior_period}"

        # Queries
        base_query = "show me top selling items"
        if store_id > 0:
            base_query += f" for store {store_id}"
        if shop_id > 0:
            base_query += f" in shop {shop_id}"

        current_query = f"{base_query} {current_period_str}"
        prior_query = f"{base_query} {prior_period_str}"

        # Get current year data
        current_result = get_chatbot().chat(current_query, config.model_name)

        # Get prior year data
        prior_result = get_chatbot().chat(prior_query, config.model_name)

        def extract_metrics(result):
            revenue, units, margin_pct, profit = 0, 0, 0, 0

            if result.get('success') and result.get('has_data'):
                summary = result.get('summary_statistics', {})

                if summary:
                    for key, val in summary.items():
                        val_clean = float(str(val).replace('$', '').replace(',', '').replace('%', ''))
                        if 'revenue' in key.lower():
                            revenue = val_clean
                        elif 'units' in key.lower():
                            units = int(val_clean)
                        elif 'margin' in key.lower():
                            margin_pct = val_clean
                    profit = revenue * margin_pct / 100 if margin_pct else 0
                else:
                    results_data = result.get('results_data', [])
                    for row in results_data:
                        revenue += float(row.get('total_revenue', 0) or row.get('revenue', 0) or 0)
                        units += int(row.get('total_units', 0) or row.get('units_sold', 0) or row.get('units', 0) or 0)
                        profit += float(row.get('total_margin', 0) or row.get('margin', 0) or 0)
                    margin_pct = (profit / revenue * 100) if revenue else 0

            return revenue, units, margin_pct, profit

        # Extract metrics
        current_revenue, current_units, current_margin_pct, current_profit = extract_metrics(current_result)
        prior_revenue, prior_units, prior_margin_pct, prior_profit = extract_metrics(prior_result)

        # Calculate YoY percentages
        metrics = {
            'total_revenue': current_revenue,
            'total_units': current_units,
            'margin_pct': current_margin_pct,
            'total_profit': current_profit,
            'revenue_yoy_pct': round(((current_revenue - prior_revenue) / prior_revenue) * 100, 1) if prior_revenue else 0,
            'units_yoy_pct': round(((current_units - prior_units) / prior_units) * 100, 1) if prior_units else 0,
            'margin_yoy_pct': round(current_margin_pct - prior_margin_pct, 1) if prior_margin_pct else 0
        }

        logger.info(f"Final metrics calculated: {metrics}")

        return jsonify({'success': True, 'metrics': metrics})

    except Exception as e:
        logger.error(f"Error in metrics endpoint: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/otb-metrics')
def api_dashboard_otb_metrics():
    """Get OTB (Open To Buy) metrics - API endpoint"""
    try:
        from datetime import datetime
        
        # Get store and shop IDs from query parameters
        store_id = request.args.get('store_id', 0, type=int)
        shop_id = request.args.get('shop_id', 0, type=int)
        
        # Get current month and next 2 months
        now = datetime.now()
        current_month = now.month
        current_year = now.year
        
        # Build query for OTB metrics based on filters
        query = f"Get OTB metrics for year {current_year}"
        if store_id > 0:
            query += f" store {store_id}"
        if shop_id > 0:
            query += f" shop {shop_id}"
        
        logger.info(f"Fetching OTB metrics with query: {query} (store_id={store_id}, shop_id={shop_id})")
        
        # For OTB metrics, let's query BigQuery directly due to MCP tool issues
        try:
            from google.cloud import bigquery
            client = bigquery.Client()
            
            # Build the query with proper parameters
            query_sql = f"""
            SELECT 
                CAST(shop_id AS STRING) AS shop_id,
                shop_name,
                CAST(store_id AS STRING) AS store_id,
                store_name,
                metric_name,
                date_month,
                value,
                last_updated_timestamp
            FROM `sis-sandbox-463113.OTB.OTB_at_a_glance`
            WHERE 1=1
                {f"AND shop_id = '{shop_id}'" if shop_id > 0 else ""}
                {f"AND store_id = '{store_id}'" if store_id > 0 else ""}
                AND EXTRACT(YEAR FROM date_month) = {current_year}
            ORDER BY date_month DESC, shop_id, store_id, metric_name
            """
            
            logger.info(f"Executing direct BigQuery: {query_sql}")
            
            # Execute the query
            query_job = client.query(query_sql)
            results = list(query_job)
            
            # Convert to list of dicts
            results_data = []
            for row in results:
                results_data.append(dict(row))
            
            logger.info(f"Direct BigQuery returned {len(results_data)} rows")
            
            # Create a result structure similar to chatbot response
            result = {
                'success': True,
                'has_data': len(results_data) > 0,
                'results_data': results_data
            }
            
        except Exception as bq_error:
            logger.error(f"BigQuery direct query failed: {bq_error}")
            # Fallback to MCP tool
            bot = get_chatbot()
            result = bot.chat(query, config.model_name, mcp_tool='get_otb_metrics')
        
        if result.get('success') and result.get('has_data'):
            try:
                # Try different possible data locations
                results_data = result.get('results_data', [])
                if not results_data and 'data' in result:
                    results_data = result['data']
                if not results_data and 'df' in result:
                    # Convert DataFrame to list of dicts
                    df = result['df']
                    if hasattr(df, 'to_dict'):
                        results_data = df.to_dict('records')
                
                logger.info(f"OTB query returned {len(results_data) if isinstance(results_data, list) else 'unknown'} rows")
                logger.info(f"Results data type: {type(results_data)}")
                
                # If results_data is a DataFrame, convert to list of dicts
                if hasattr(results_data, 'to_dict'):
                    results_data = results_data.to_dict('records')
                    logger.info(f"Converted DataFrame to {len(results_data)} records")
                
                # Log sample data for debugging
                if results_data and isinstance(results_data, list) and len(results_data) > 0:
                    logger.info(f"Sample OTB data: {results_data[0]}")
                else:
                    logger.warning(f"Unexpected results_data format: {results_data}")
                    # Try to extract data from the result
                    logger.info(f"Full result keys: {list(result.keys())}")
                    if 'visualization' in result:
                        logger.info(f"Has visualization: {len(result['visualization'])} chars")
                
                # Ensure results_data is a list
                if not isinstance(results_data, list):
                    logger.error(f"results_data is not a list: {type(results_data)}")
                    results_data = []
                
                # Process and format OTB data for display
                otb_data = {
                    'months': [],
                    'metrics': {},
                    'formatted_table': []
                }
                
                # Get current and next 2 months
                months = []
                month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                              'July', 'August', 'September', 'October', 'November', 'December']
                
                for i in range(3):
                    month_idx = (current_month - 1 + i) % 12
                    year = current_year if (current_month + i) <= 12 else current_year + 1
                    months.append({
                        'name': month_names[month_idx],
                        'date': f"{year}-{(month_idx + 1):02d}-01"
                    })
                
                otb_data['months'] = [m['name'] for m in months]
                
                # Filter data for current + next 2 months
                # If store_id or shop_id filters are applied, use them
                filtered_data = []
                for row in results_data:
                    # Log row for debugging
                    row_store = row.get('store_id', '')
                    row_shop = row.get('shop_id', '')
                    
                    # Check if row matches filters (if any)
                    # Note: store_id and shop_id from DB might be strings
                    if store_id > 0:
                        if str(row_store) != str(store_id):
                            continue
                    if shop_id > 0:
                        if str(row_shop) != str(shop_id):
                            continue
                    
                    # Check if date is in our target months
                    row_date = str(row.get('date_month', ''))
                    for month in months:
                        if row_date.startswith(month['date'][:7]):  # Compare YYYY-MM
                            filtered_data.append(row)
                            break
                
                logger.info(f"Filtered OTB data to {len(filtered_data)} rows for months: {[m['date'][:7] for m in months]}")
                
                # Check if we have any data after filtering
                if not filtered_data:
                    logger.warning(f"No OTB data found for store {store_id}, shop {shop_id} in months {[m['date'][:7] for m in months]}")
                    return jsonify({
                        'success': True,
                        'data': {
                            'months': [m['name'] for m in months],
                            'formatted_table': [],
                            'message': f'No OTB data available for the selected filters in {months[0]["name"]}-{months[-1]["name"]} {current_year}'
                        }
                    })
                
                # Organize data by metric and month
                metrics_by_name = {}
                for row in filtered_data:
                    metric_name = row.get('metric_name', '')
                    month_date = str(row.get('date_month', ''))
                    value = float(row.get('value', 0))
                    
                    if metric_name not in metrics_by_name:
                        metrics_by_name[metric_name] = {}
                    
                    # Find which month this belongs to
                    for month in months:
                        if month_date.startswith(month['date'][:7]):
                            metrics_by_name[metric_name][month['name']] = value
                            break
                
                # Format data for table display
                metric_order = ['OTB Goal', 'OTB Ordered', 'Monthly OTB Remaining', 
                               'Yearly OTB Remaining', 'OTB Received', '% Received YTD']
                
                for metric in metric_order:
                    if metric in metrics_by_name:
                        row = {'metric': metric}
                        for month_name in otb_data['months']:
                            value = metrics_by_name[metric].get(month_name, 0)
                            # Format value based on metric type
                            if metric == '% Received YTD':
                                row[month_name] = f"{value:.0f}%"
                            elif value < 0:
                                row[month_name] = f"(${abs(value):,.0f})"
                            else:
                                row[month_name] = f"${value:,.0f}"
                        otb_data['formatted_table'].append(row)
                
                return jsonify({
                    'success': True, 
                    'data': otb_data,
                    'raw_data': filtered_data
                })
                
            except Exception as process_error:
                logger.error(f"Error processing OTB data: {process_error}")
                return jsonify({'success': False, 'error': f'Failed to process OTB data: {str(process_error)}'}), 500
        else:
            error_msg = result.get('error', 'No OTB data available')
            logger.error(f"Failed to get OTB data: {error_msg}")
            logger.error(f"Full result: {result}")
            return jsonify({'success': False, 'error': error_msg}), 404
            
    except Exception as e:
        logger.error(f"Error fetching OTB metrics: {e}")
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
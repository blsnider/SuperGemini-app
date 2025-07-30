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

# Load API keys at startup
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
    bq_project: str = os.getenv('BQ_PROJECT', 'sis-data-marts')
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
chatbot = SuperGeminiRetailChatbot(config)
dashboard_manager = DashboardManager()

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
            
        response = chatbot.chat(query, model)
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

# Dashboard API endpoints
@app.route('/api/dashboard/kpis')
def api_dashboard_kpis():
    """Get executive KPIs - API endpoint"""
    try:
        kpis = dashboard_manager.get_executive_kpis()
        return jsonify({'success': True, 'data': kpis})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/sales-trends')
def api_sales_trends():
    """Get sales trends - API endpoint"""
    period = request.args.get('period', '30d')
    store_id = request.args.get('store_id', 0, type=int)
    
    try:
        trends = dashboard_manager.get_sales_trends(period, store_id)
        return jsonify({'success': True, 'data': trends})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/top-performers')
def api_top_performers():
    """Get top performing items - API endpoint"""
    limit = request.args.get('limit', 10, type=int)
    store_id = request.args.get('store_id', 0, type=int)
    
    try:
        performers = dashboard_manager.get_top_performers(limit, store_id)
        return jsonify({'success': True, 'data': performers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dashboard/stock-alerts')
def api_stock_alerts():
    """Get stock alerts - API endpoint"""
    try:
        alerts = dashboard_manager.get_stock_alerts()
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
        
        # For now, return sample metrics
        metrics = {
            'total_revenue': 1250000,
            'total_orders': 3456,
            'avg_order_value': 362,
            'return_rate': 3.5
        }
        
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
        
        # For now, return a placeholder chart
        chart_html = f"""
        <div style="text-align: center; padding: 40px; background: white; border-radius: 8px;">
            <h3>{chart_type.replace('_', ' ').title()} Chart</h3>
            <p>Chart visualization would appear here</p>
            <p style="color: #666; font-size: 0.9em;">Store: {store_id or 'All'} | Shop: {shop_id or 'All'}</p>
        </div>
        """
        
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
        status = chatbot.get_toolbox_status() if hasattr(chatbot, 'get_toolbox_status') else {'status': 'unknown'}
        return jsonify({
            'status': 'healthy' if status.get('toolbox_enabled', False) else 'degraded',
            'chatbot': status
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
# app.py - Production Ready Flask Application with Smart Environment Handling
import os
import logging
import traceback
import sys
from typing import Optional, Dict, Any, List
from functools import wraps
from flask_caching import Cache
from flask import Flask, render_template, request, jsonify, session, g
from dotenv import load_dotenv
from dataclasses import dataclass
import time

# Load environment variables first
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
    from firebase_admin import auth, initialize_app, credentials
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    import redis
    import json
    SECURITY_FEATURES_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Security features not available due to missing dependencies: {e}")
    SECURITY_FEATURES_AVAILABLE = False

# Smart Secret Loading
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
        if not project_id:
            project_id = os.getenv('GCP_PROJECT', os.getenv('GOOGLE_CLOUD_PROJECT'))
            
        if not project_id:
            logger.error(f"No project ID configured for Secret Manager")
            return ''
        
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8")
        logger.info(f"✅ Successfully loaded {secret_name} from Secret Manager")
        return secret_value
        
    except Exception as e:
        logger.error(f"❌ Failed to load secret {secret_name}: {e}")
        return ''

def initialize_security_features(app: Flask) -> tuple:
    """Initialize Firebase and Redis with environment-aware logic."""
    firebase_app = None
    limiter = None
    
    if not SECURITY_FEATURES_AVAILABLE:
        logger.warning("Security features disabled - missing dependencies")
        try:
            limiter = Limiter(
                key_func=get_remote_address,
                app=app,
                default_limits=["100 per minute", "500 per hour"]
            )
            logger.info("✅ Basic rate limiter initialized")
        except Exception as e:
            logger.error(f"Rate limiter failed: {e}")
        return firebase_app, limiter
    
    try:
        # Initialize Firebase only in production environment
        if environment == 'production' and gcp_available:
            logger.info("Production environment - initializing Firebase...")
            firebase_cred_json = load_secret('firebase-cred-json')
            if firebase_cred_json:
                try:
                    cred_dict = json.loads(firebase_cred_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_app = initialize_app(cred)
                    logger.info("✅ Firebase initialized successfully")
                except Exception as e:
                    logger.error(f"Firebase initialization failed: {e}")
            else:
                logger.info("No Firebase credentials found")
        else:
            logger.info(f"Environment: {environment} - skipping Firebase initialization")
        
        # Initialize Redis and Rate Limiter
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        redis_db = int(os.getenv('REDIS_DB', '0'))
        
        try:
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, socket_timeout=5)
            redis_client.ping()
            
            limiter = Limiter(
                key_func=get_remote_address,
                app=app,
                storage_uri=f"redis://{redis_host}:{redis_port}/{redis_db}",
                default_limits=["100 per minute", "500 per hour"]
            )
            logger.info("✅ Redis-backed rate limiter initialized")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            limiter = Limiter(
                key_func=get_remote_address,
                app=app,
                default_limits=["100 per minute", "500 per hour"]
            )
            logger.info("✅ In-memory rate limiter initialized")
            
    except Exception as e:
        logger.error(f"Security features initialization failed: {e}")
        try:
            limiter = Limiter(
                key_func=get_remote_address,
                app=app,
                default_limits=["100 per minute", "500 per hour"]
            )
            logger.info("✅ Fallback rate limiter initialized")
        except Exception as fallback_error:
            logger.error(f"Even fallback rate limiter failed: {fallback_error}")
    
    return firebase_app, limiter

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

# Import dashboard with safe import
try:
    from dashboard import init_dash
    DASHBOARD_AVAILABLE = True
    logger.info("✅ Dashboard module imported successfully")
except ImportError as e:
    logger.warning(f"❌ Dashboard module not available: {e}")
    DASHBOARD_AVAILABLE = False
    init_dash = None

# Test application imports
try:
    logger.info("Loading application modules...")
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from chatbot.config import get_available_models, get_store_mappings, get_shop_mappings
    from weighting_logic import WeightingCalculator, CoverageMetrics, apply_weighting_to_results
    from chatbot import SuperGeminiRetailChatbot
    logger.info("✅ All application modules loaded successfully")
    
except Exception as e:
    logger.error(f"❌ Import error: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    raise

# Configure caching
cache = Cache(config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 300})

# Configuration
@dataclass
class AppConfig:
    bq_project: str = os.getenv('BQ_PROJECT', 'sis-data-marts')
    model_name: str = os.getenv('DEFAULT_MODEL', 'gemini-2.5-pro')
    preview_rows: int = int(os.getenv('PREVIEW_ROWS', '20'))
    enable_weighting: bool = os.getenv('ENABLE_WEIGHTING', 'True').lower() == 'true'
    enable_auth: bool = os.getenv('ENABLE_AUTH', 'False').lower() == 'true'
    max_history_items: int = int(os.getenv('MAX_HISTORY_ITEMS', '50'))
    environment: str = environment

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())
app.config['SESSION_TYPE'] = 'filesystem'
cache.init_app(app)

# Initialize configuration
config = AppConfig()
logger.info(f"Configuration: {config}")

# Initialize security features
firebase_app, limiter = initialize_security_features(app)

# Initialize dashboard
dash_app = None
if DASHBOARD_AVAILABLE and init_dash:
    try:
        dash_app = init_dash(app)
        logger.info("✅ Dashboard initialized successfully")
    except Exception as e:
        logger.error(f"❌ Dashboard initialization failed: {e}")
        dash_app = None
else:
    logger.info("📊 Dashboard disabled - module not available")

# Authentication decorator
def firebase_auth_required(f):
    """Decorator for Firebase authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.enable_auth or not firebase_app:
            return f(*args, **kwargs)
        
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'No authorization token provided'}), 401
        
        try:
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Invalid authorization format'}), 401
            
            token = auth_header.split('Bearer ')[1]
            decoded_token = auth.verify_id_token(token)
            g.user = decoded_token
            logger.info(f"Authenticated user: {decoded_token.get('email', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        return f(*args, **kwargs)
    return decorated

def optional_auth(f):
    """Decorator that applies auth only if enabled."""
    if config.enable_auth:
        return firebase_auth_required(f)
    return f

# Query history functions
def add_to_history(query: str, results_count: int = 0):
    """Add query to session history."""
    try:
        if 'query_history' not in session:
            session['query_history'] = []
        
        history_entry = {
            'query': query,
            'timestamp': int(time.time()),
            'results_count': results_count
        }
        
        session['query_history'].insert(0, history_entry)
        
        if len(session['query_history']) > config.max_history_items:
            session['query_history'] = session['query_history'][:config.max_history_items]
        
        session.modified = True
        logger.debug(f"Added query to history: {query}")
        
    except Exception as e:
        logger.error(f"Error adding to history: {e}")

def get_query_history() -> List[Dict[str, Any]]:
    """Get query history from session."""
    return session.get('query_history', [])

# Sample queries
SAMPLE_QUERIES = [
    "Show me top 10 selling products by revenue",
    "Which products are overstocked?",
    "Products with low inventory that need reordering",
    "Top performing categories by margin",
    "Products with declining sales trends",
    "Inventory analysis for urgent reorders",
    "Show products with high coverage gaps",
    "Out of stock items with high demand",
    "Products requiring immediate attention",
    "Monthly sales performance summary"
]

# Initialize components
logger.info("Initializing application components...")

try:
    weighting_calculator = WeightingCalculator()
    logger.info("✅ WeightingCalculator initialized")
except Exception as e:
    logger.error(f"Failed to initialize WeightingCalculator: {e}")
    weighting_calculator = None

try:
    chatbot = SuperGeminiRetailChatbot(config)
    logger.info("✅ Chatbot initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize chatbot: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    chatbot = None

# Helper functions
def should_apply_weighting(query: str) -> bool:
    """Determine if weighting logic should be applied."""
    try:
        if not config.enable_weighting or not weighting_calculator:
            return False
        
        weighting_keywords = [
            'weighting', 'weight', 'priority', 'coverage', 'risk', 'reorder',
            'stock analysis', 'inventory analysis', 'order quantity', 'recommended',
            'overstocked', 'understocked', 'out of stock', 'review flag',
            'action group', 'urgent', 'monitoring', 'inventory', 'stock'
        ]
        
        query_lower = query.lower()
        result = any(keyword in query_lower for keyword in weighting_keywords)
        logger.debug(f"Weighting check for '{query}': {result}")
        return result
    except Exception as e:
        logger.error(f"Error in should_apply_weighting: {e}")
        return False

def enhance_results_with_weighting(results: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
    """Apply weighting logic to query results."""
    try:
        if not results or not should_apply_weighting(query):
            return {'results': results, 'weighting_applied': False}
        
        logger.info(f"Applying weighting logic to {len(results)} results")
        enhanced_results = apply_weighting_to_results(results)
        
        # Generate summary statistics
        summary_stats = {
            'total_skus': len(enhanced_results),
            'by_risk_level': {},
            'by_action_group': {},
            'avg_coverage_percentage': 0,
            'total_coverage_gap': 0,
            'total_recommended_qty': 0
        }
        
        coverage_percentages = []
        for result in enhanced_results:
            risk_level = result.get('risk_level', 'Unknown')
            summary_stats['by_risk_level'][risk_level] = summary_stats['by_risk_level'].get(risk_level, 0) + 1
            
            action_group = result.get('action_group', 'Unknown')
            summary_stats['by_action_group'][action_group] = summary_stats['by_action_group'].get(action_group, 0) + 1
            
            summary_stats['total_coverage_gap'] += result.get('coverage_gap', 0)
            summary_stats['total_recommended_qty'] += result.get('recommended_order_qty', 0)
            
            coverage_pct = result.get('coverage_percentage')
            if coverage_pct is not None and coverage_pct >= 0:
                coverage_percentages.append(coverage_pct)
        
        if coverage_percentages:
            summary_stats['avg_coverage_percentage'] = sum(coverage_percentages) / len(coverage_percentages)
        
        summary_stats['items_needing_attention'] = (
            summary_stats['by_risk_level'].get('Critical', 0) + 
            summary_stats['by_risk_level'].get('High', 0)
        )
        
        return {
            'results': enhanced_results,
            'weighting_applied': True,
            'summary_stats': summary_stats,
            'weighting_metadata': {
                'total_processed': len(results),
                'successfully_enhanced': len(enhanced_results),
                'failed_items': len(results) - len(enhanced_results)
            }
        }
        
    except Exception as e:
        logger.error(f"Error applying weighting logic: {e}")
        return {
            'results': results, 
            'weighting_applied': False, 
            'error': str(e)
        }

# Routes
@app.route('/')
def index() -> str:
    """Serve the main HTML page."""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return f"Error loading page: {str(e)}", 500

@app.route('/models', methods=['GET'])
def get_models() -> Dict[str, Any]:
    """Get available models configuration."""
    try:
        models = get_available_models()
        return jsonify({
            'success': True,
            'models': models,
            'default_model': config.model_name
        })
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat', methods=['POST'])
@limiter.limit("50 per minute") if limiter else lambda f: f
@optional_auth
def chat() -> Dict[str, Any]:
    """Handle chat requests."""
    if not chatbot:
        return jsonify({'success': False, 'error': 'Chatbot not initialized'}), 500

    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400

        data = request.json or {}
        query = data.get('query', '').strip()
        model = data.get('model', config.model_name).lower()
        apply_weighting = data.get('apply_weighting', True)
        
        user_id = getattr(g, 'user', {}).get('email') or 'anonymous'
        session_id = request.headers.get('X-Cloud-Trace-Context', 'default').split('/')[0]

        if not query:
            return jsonify({'success': False, 'error': 'No query provided'}), 400

        # Validate model
        if not chatbot.available_models or model not in chatbot.available_models:
            return jsonify({'success': False, 'error': f'Invalid model: {model}'}), 400

        # Call chatbot
        try:
            result = chatbot.chat(query, model, user_id, session_id)
        except Exception as e:
            logger.error(f"Chatbot error: {e}")
            return jsonify({
                'success': False,
                'error': f'Chatbot error: {str(e)}'
            }), 500
        
        # Apply weighting if applicable
        if result.get('success') and apply_weighting and result.get('results'):
            try:
                weighting_result = enhance_results_with_weighting(result['results'], query)
                result.update(weighting_result)
            except Exception as e:
                logger.error(f"Weighting error: {e}")
                result['weighting_error'] = str(e)
        
        # Add to history
        results_count = len(result.get('results', [])) if result.get('success') else 0
        add_to_history(query, results_count)
        
        return jsonify(result)

    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}'
        }), 500

@app.route('/health')
def health() -> Dict[str, Any]:
    """Comprehensive health check."""
    try:
        status = {
            'status': 'healthy',
            'environment': config.environment,
            'chatbot_initialized': chatbot is not None,
            'weighting_enabled': config.enable_weighting,
            'auth_enabled': config.enable_auth,
            'gcp_auth_available': gcp_available,
            'security_features_available': SECURITY_FEATURES_AVAILABLE,
            'rate_limiting_enabled': limiter is not None,
            'firebase_initialized': firebase_app is not None,
            'dashboard_available': dash_app is not None
        }
        
        # Test BigQuery connection
        if chatbot:
            try:
                if hasattr(chatbot, 'bigquery_utils') and hasattr(chatbot.bigquery_utils, 'bq_client'):
                    client = chatbot.bigquery_utils.bq_client
                    client.query('SELECT 1').result()
                    status['bq_connected'] = True
                else:
                    status['bq_connected'] = False
            except Exception as e:
                status['bq_connected'] = False
                status['bq_error'] = str(e)
            
            status['available_models'] = list(chatbot.available_models.keys()) if chatbot.available_models else []
        
        # Check API keys
        api_keys_status = {}
        for key in ['GOOGLE_API_KEY', 'XAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY']:
            api_keys_status[key] = bool(os.getenv(key))
        status['api_keys'] = api_keys_status
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    debug = config.environment != 'production'
    
    logger.info(f"Starting Super Gemini server on port {port}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Authentication: {'Enabled' if config.enable_auth else 'Disabled'}")
    logger.info(f"Weighting: {'Enabled' if config.enable_weighting else 'Disabled'}")
    logger.info(f"GCP Auth: {'Available' if gcp_available else 'Not available'}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)

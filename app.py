# app.py - MCP-Only Flask Application for Retail Analytics
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

logger.info(f"=== Starting MCP-Only Retail Analytics Application ({environment}) ===")

# Ensure GOOGLE_CLOUD_PROJECT is set for all GCP clients
if not os.getenv("GOOGLE_CLOUD_PROJECT"):
    fallback_project = os.getenv("GCP_PROJECT", "sis-sandbox-463113")
    os.environ["GOOGLE_CLOUD_PROJECT"] = fallback_project
    logger.info(f"🛠 Set GOOGLE_CLOUD_PROJECT to: {fallback_project}")

# Test Google Cloud setup for smart fallback
def test_google_cloud_setup():
    """Test Google Cloud libraries and authentication setup."""
    try:
        import google.auth
        credentials, project = google.auth.default()
        if not project:
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
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
    env_var_name = secret_name.upper().replace('-', '_')
    env_value = os.getenv(env_var_name)
    
    if env_value:
        logger.info(f"✅ Using environment variable for {secret_name}")
        return env_value
    
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
        # Initialize Firebase only in production environment and if enabled
        if environment == 'production' and gcp_available and os.getenv('ENABLE_FIREBASE', 'false').lower() == 'true':
            logger.info("Production environment - initializing Firebase...")
            firebase_cred_json = load_secret('firebase-cred-json')
            if firebase_cred_json:
                try:
                    cred_dict = json.loads(firebase_cred_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_app = initialize_app(cred)
                    logger.info("✅ Firebase initialized successfully")
                except Exception as e:
                    logger.warning(f"Firebase initialization failed: {e}")
            else:
                logger.info("No Firebase credentials found - skipping")
        else:
            logger.info(f"Environment: {environment} - skipping Firebase initialization")
        
        # Initialize Redis and Rate Limiter
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', '6379'))
        redis_db = int(os.getenv('REDIS_DB', '0'))
        
        try:
            redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, socket_timeout=2)
            redis_client.ping()
            
            limiter = Limiter(
                key_func=get_remote_address,
                app=app,
                storage_uri=f"redis://{redis_host}:{redis_port}/{redis_db}",
                default_limits=["100 per minute", "500 per hour"]
            )
            logger.info("✅ Redis-backed rate limiter initialized")
        except Exception as e:
            logger.info(f"Redis not available, using in-memory rate limiter: {e}")
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
    """Load API keys for LLM services (used for summaries)."""
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
                loaded_count += 1
        
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

# Load MCP-only application modules
try:
    logger.info("Loading MCP-only application modules...")
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from chatbot.config import get_available_models, get_store_mappings, get_shop_mappings
    from chatbot.core import SuperGeminiRetailChatbot
    logger.info("✅ All MCP-only application modules loaded successfully")
    
except Exception as e:
    logger.error(f"❌ Import error: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    raise

# Configure caching
cache = Cache(config={'CACHE_TYPE': 'simple', 'CACHE_DEFAULT_TIMEOUT': 300})

# Configuration
@dataclass
class AppConfig:
    bq_project: str = os.getenv('BQ_PROJECT', 'sis-sandbox-463113')
    model_name: str = os.getenv('DEFAULT_MODEL', 'gemini-2.5-pro')
    preview_rows: int = int(os.getenv('PREVIEW_ROWS', '20'))
    enable_auth: bool = os.getenv('ENABLE_AUTH', 'False').lower() == 'true'
    max_history_items: int = int(os.getenv('MAX_HISTORY_ITEMS', '50'))
    environment: str = environment
    toolbox_url: str = os.getenv('TOOLBOX_URL', 'https://toolbox-41815171183.us-central1.run.app')

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

# Sample queries for MCP tools
MCP_SAMPLE_QUERIES = [
    "Show me top 10 selling products by revenue",
    "Which products are out of stock with recent sales?",
    "Products with excess inventory over 90 days supply",
    "Top performing items by margin",
    "Sales trends over last 30 days",
    "Inventory status for store 64",
    "Compare sales between stores",
    "Return analysis by store",
    "Top selling items in shop 3",
    "Monthly sales performance for 2025"
]

# Initialize MCP-only chatbot
logger.info("Initializing MCP-only chatbot...")

try:
    chatbot = SuperGeminiRetailChatbot(config)
    app.chatbot = chatbot  # Store reference for other routes
    logger.info("✅ MCP-only chatbot initialized successfully")
    
    # Log MCP status
    if hasattr(chatbot, 'toolbox_enabled'):
        logger.info(f"MCP Toolbox enabled: {chatbot.toolbox_enabled}")
        if chatbot.toolbox_enabled and hasattr(chatbot, 'tools'):
            if isinstance(chatbot.tools, dict):
                logger.info(f"Available MCP tools: {list(chatbot.tools.keys())}")
            else:
                logger.info(f"Available MCP tools count: {len(chatbot.tools)}")
    
except Exception as e:
    logger.error(f"Failed to initialize MCP-only chatbot: {e}")
    logger.error(f"Full traceback: {traceback.format_exc()}")
    chatbot = None

# Routes
@app.route('/')
def index() -> str:
    """Serve the main HTML page."""
    try:
        # First try to use Flask's template system
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
            'default_model': config.model_name,
            'system_mode': 'MCP-Only'
        })
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/chat', methods=['POST'])
@limiter.limit("50 per minute") if limiter else lambda f: f
@optional_auth
def chat() -> Dict[str, Any]:
    """Handle chat requests using ONLY MCP tools."""
    if not chatbot:
        return jsonify({'success': False, 'error': 'MCP chatbot not initialized'}), 500

    if not chatbot.toolbox_enabled:
        return jsonify({
            'success': False, 
            'error': 'MCP Toolbox is not enabled. Please check server configuration.',
            'system_mode': 'MCP-Only',
            'suggestion': 'Ensure MCP Toolbox server is running and tools.yaml is configured'
        }), 500

    try:
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Content-Type must be application/json'}), 400

        data = request.json or {}
        query = data.get('query', '').strip()
        model = data.get('model', config.model_name).lower()
        
        user_id = getattr(g, 'user', {}).get('email') or 'anonymous'
        session_id = request.headers.get('X-Cloud-Trace-Context', 'default').split('/')[0]

        if not query:
            return jsonify({'success': False, 'error': 'No query provided'}), 400

        # Validate model (for summary generation)
        if not chatbot.available_models or model not in chatbot.available_models:
            return jsonify({'success': False, 'error': f'Invalid model: {model}'}), 400

        # Call MCP-only chatbot
        try:
            result = chatbot.chat(query, model, user_id, session_id)
        except Exception as e:
            logger.error(f"MCP chatbot error: {e}")
            return jsonify({
                'success': False,
                'error': f'MCP chatbot error: {str(e)}',
                'system_mode': 'MCP-Only'
            }), 500
        
        # Add to history
        results_count = result.get('row_count', 0) if result.get('success') else 0
        add_to_history(query, results_count)
        
        # Add system information to response
        result['system_mode'] = 'MCP-Only'
        result['sql_generation_disabled'] = True
        
        return jsonify(result)

    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal error: {str(e)}',
            'system_mode': 'MCP-Only'
        }), 500

@app.route('/generate_chart', methods=['POST'])
@optional_auth  
def generate_chart():
    """Generate chart from last query results."""
    if not chatbot:
        return jsonify({'success': False, 'error': 'MCP chatbot not initialized'}), 500
    
    try:
        data = request.json or {}
        chart_type = data.get('chart_type')
        
        result = chatbot.generate_chart(chart_type)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/generate_summary', methods=['POST'])
@optional_auth
def generate_summary():
    """Generate AI summary of last query results."""
    if not chatbot:
        return jsonify({'success': False, 'error': 'MCP chatbot not initialized'}), 500
    
    try:
        data = request.json or {}
        model = data.get('model', config.model_name)
        
        result = chatbot.generate_llm_summary(model)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/export', methods=['POST'])
@optional_auth
def export_data():
    """Export last query results"""
    if not chatbot or not chatbot.last_results:
        return jsonify({'success': False, 'error': 'No data available to export'}), 400
    
    try:
        data = request.json or {}
        export_format = data.get('format', 'csv').lower()
        
        if export_format == 'csv':
            import io
            import csv
            
            output = io.StringIO()
            if chatbot.last_results:
                writer = csv.DictWriter(output, fieldnames=chatbot.last_results[0].keys())
                writer.writeheader()
                writer.writerows(chatbot.last_results)
            
            return jsonify({
                'success': True,
                'data': output.getvalue(),
                'filename': f'query_results_{int(time.time())}.csv',
                'mime_type': 'text/csv'
            })
            
        elif export_format == 'json':
            import json
            return jsonify({
                'success': True,
                'data': json.dumps(chatbot.last_results, indent=2),
                'filename': f'query_results_{int(time.time())}.json',
                'mime_type': 'application/json'
            })
        else:
            return jsonify({'success': False, 'error': 'Unsupported format'}), 400
            
    except Exception as e:
        logger.error(f"Export error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/suggest', methods=['GET'])
def suggest():
    """Provide MCP-optimized query suggestions."""
    try:
        query = request.args.get('q', '').strip().lower()
        
        if not query:
            suggestions = [{'text': q, 'type': 'template'} for q in MCP_SAMPLE_QUERIES[:8]]
            return jsonify({'success': True, 'suggestions': suggestions})
        
        # Filter MCP sample queries based on input
        matching_suggestions = []
        for suggestion in MCP_SAMPLE_QUERIES:
            if query in suggestion.lower():
                matching_suggestions.append({'text': suggestion, 'type': 'template'})
        
        # If no direct matches, try partial word matching
        if not matching_suggestions:
            query_words = query.split()
            for suggestion in MCP_SAMPLE_QUERIES:
                suggestion_lower = suggestion.lower()
                if any(word in suggestion_lower for word in query_words):
                    matching_suggestions.append({'text': suggestion, 'type': 'template'})
        
        # Add history suggestions
        history = get_query_history()
        for item in history:
            if query in item['query'].lower():
                matching_suggestions.append({
                    'text': item['query'],
                    'type': 'history',
                    'results_count': item.get('results_count', 0)
                })
        
        # Limit to top 8 suggestions
        matching_suggestions = matching_suggestions[:8]
        
        return jsonify({
            'success': True,
            'suggestions': matching_suggestions,
            'query': query,
            'count': len(matching_suggestions),
            'system_mode': 'MCP-Only'
        })
        
    except Exception as e:
        logger.error(f"Suggestion endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'suggestions': [{'text': q, 'type': 'template'} for q in MCP_SAMPLE_QUERIES[:5]],
            'error': 'Failed to generate suggestions'
        }), 500

@app.route('/cost_summary', methods=['GET'])
def cost_summary():
    """Get cost summary (MCP tools are typically infrastructure-only costs)."""
    try:
        if not chatbot:
            return jsonify({
                'success': False,
                'error': 'MCP chatbot not initialized',
                'cost_summary': {
                    'total_session_cost': 0.0,
                    'queries_executed': 0,
                    'average_cost_per_query': 0.0
                }
            }), 500
        
        cost_data = chatbot.get_cost_summary()
        cost_data['system_mode'] = 'MCP-Only'
        
        return jsonify({
            'success': True,
            'cost_summary': cost_data,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Cost summary endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'cost_summary': {
                'total_session_cost': 0.0,
                'queries_executed': 0,
                'average_cost_per_query': 0.0
            }
        }), 500

@app.route('/reset_costs', methods=['POST'])
def reset_costs():
    """Reset cost tracking."""
    try:
        if not chatbot:
            return jsonify({
                'success': False,
                'error': 'MCP chatbot not initialized'
            }), 500
        
        chatbot.reset_cost_tracking()
        
        return jsonify({
            'success': True,
            'message': 'Cost tracking reset successfully',
            'system_mode': 'MCP-Only'
        })
        
    except Exception as e:
        logger.error(f"Reset costs endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/toolbox_status', methods=['GET'])
def toolbox_status():
    """Get MCP Toolbox status and available tools."""
    try:
        if not chatbot:
            return jsonify({
                'success': False,
                'error': 'MCP chatbot not initialized',
                'toolbox_status': {
                    'toolbox_available': False,
                    'toolbox_enabled': False,
                    'available_tools': []
                }
            }), 500
        
        status = chatbot.get_toolbox_status()
        status['system_mode'] = 'MCP-Only'
        
        return jsonify({
            'success': True,
            'toolbox_status': status,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"Toolbox status endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'toolbox_status': {
                'toolbox_available': False,
                'toolbox_enabled': False,
                'available_tools': []
            }
        }), 500

@app.route('/history', methods=['GET'])
def history():
    """Get query history with properly formatted response"""
    try:
        history_data = get_query_history()
        
        # Format the response to match what frontend expects
        formatted_history = []
        for item in history_data:
            formatted_history.append({
                'query': item['query'],
                'timestamp': item['timestamp'],
                'results_count': item.get('results_count', 0)
            })
        
        return jsonify({
            'success': True,
            'history': formatted_history
        })
        
    except Exception as e:
        logger.error(f"History endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'history': []
        }), 500

@app.route('/clear_history', methods=['POST'])
@optional_auth
def clear_history():
    """Clear query history"""
    try:
        session['query_history'] = []
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': 'History cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/system_info', methods=['GET'])
def system_info():
    """Get system information for MCP-only configuration."""
    try:
        info = {
            'chatbot_initialized': chatbot is not None,
            'toolbox_available': False,
            'toolbox_enabled': False,
            'available_tools': [],
            'models_available': [],
            'bigquery_connected': False,
            'auth_enabled': config.enable_auth,
            'dashboard_available': dash_app is not None,
            'firebase_initialized': firebase_app is not None,
            'environment': config.environment,
            'system_mode': 'MCP-Only',
            'sql_generation_disabled': True,
            'toolbox_url': config.toolbox_url
        }
        
        if chatbot:
            # Get toolbox status
            toolbox_status_data = chatbot.get_toolbox_status()
            info.update({
                'toolbox_available': toolbox_status_data.get('toolbox_available', False),
                'toolbox_enabled': toolbox_status_data.get('toolbox_enabled', False),
                'available_tools': toolbox_status_data.get('available_tools', [])
            })
            
            # Get available models
            info['models_available'] = list(chatbot.available_models.keys()) if chatbot.available_models else []
            
            # Test BigQuery connection
            try:
                chatbot.bigquery_utils.bq_client.query("SELECT 1").result()
                info['bigquery_connected'] = True
            except:
                info['bigquery_connected'] = False
        
        # Check API keys (used for summaries)
        api_keys_status = {}
        for key in ['GOOGLE_API_KEY', 'XAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY']:
            api_keys_status[key] = bool(os.getenv(key))
        info['api_keys'] = api_keys_status
        
        return jsonify({
            'success': True,
            'system_info': info,
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"System info endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health() -> Dict[str, Any]:
    """Comprehensive health check for MCP-only system."""
    try:
        status = {
            'status': 'healthy',
            'environment': config.environment,
            'system_mode': 'MCP-Only',
            'sql_generation_disabled': True,
            'chatbot_initialized': chatbot is not None,
            'auth_enabled': config.enable_auth,
            'gcp_auth_available': gcp_available,
            'security_features_available': SECURITY_FEATURES_AVAILABLE,
            'rate_limiting_enabled': limiter is not None,
            'firebase_initialized': firebase_app is not None,
            'dashboard_available': dash_app is not None,
            'toolbox_url': config.toolbox_url
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
            
            # MCP Toolbox status
            if hasattr(chatbot, 'toolbox_enabled'):
                status['mcp_toolbox_enabled'] = chatbot.toolbox_enabled
                if chatbot.toolbox_enabled and hasattr(chatbot, 'tools'):
                    if isinstance(chatbot.tools, dict):
                        status['mcp_tools_available'] = list(chatbot.tools.keys())
                    else:
                        status['mcp_tools_count'] = len(chatbot.tools) if chatbot.tools else 0
        
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
            'error': str(e),
            'system_mode': 'MCP-Only'
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    debug = config.environment != 'production'
    
    logger.info(f"Starting MCP-Only Retail Analytics server on port {port}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Authentication: {'Enabled' if config.enable_auth else 'Disabled'}")
    logger.info(f"GCP Auth: {'Available' if gcp_available else 'Not available'}")
    logger.info(f"Dashboard: {'Available' if dash_app else 'Not available'}")
    logger.info(f"Firebase: {'Initialized' if firebase_app else 'Not initialized'}")
    logger.info(f"MCP Toolbox URL: {config.toolbox_url}")
    logger.info("🚫 SQL Generation: DISABLED (MCP-Only Mode)")
    
    if chatbot:
        logger.info(f"MCP Toolbox: {'Enabled' if getattr(chatbot, 'toolbox_enabled', False) else 'Disabled'}")
        if hasattr(chatbot, 'toolbox_enabled') and chatbot.toolbox_enabled:
            if isinstance(chatbot.tools, dict):
                logger.info(f"Available MCP tools: {list(chatbot.tools.keys())}")
            else:
                logger.info(f"MCP tools count: {len(chatbot.tools) if chatbot.tools else 0}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
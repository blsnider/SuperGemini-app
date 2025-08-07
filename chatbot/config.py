# config.py - Enhanced Configuration with Fixed Store Mappings

import os
import logging
from dataclasses import dataclass
from typing import Dict, Any
from google.cloud import bigquery

# Set up logger
logger = logging.getLogger(__name__)

# Keep your existing Config dataclass structure
@dataclass
class Config:
    bq_project: str
    model_name: str
    preview_rows: int = 20

# FIXED: Load store mappings from BigQuery
def get_store_mappings():
    """Load store mappings from BigQuery."""
    try:
        client = bigquery.Client(project=os.getenv('BQ_PROJECT', 'scheels-data-marts'))
        
        query = """
        SELECT 
            store_number,
            store_name,
            store_short_name,
            store_city,
            store_state
        FROM `scheels-data-marts.utility_data.mart_stores`
        WHERE store_number IS NOT NULL
        """
        
        result = client.query(query).result()
        
        store_mappings = {}
        for row in result:
            try:
                # Convert BigQuery row to dict explicitly
                row_dict = dict(row)
                store_id = str(int(row_dict['store_number']))  # Convert to string ID
                
                store_mappings[store_id] = {
                    'store_number': row_dict['store_number'],
                    'store_name': row_dict['store_name'],
                    'store_short_name': row_dict['store_short_name'],
                    'store_city': row_dict['store_city'],
                    'store_state': row_dict['store_state']
                }
            except Exception as row_error:
                logger.error(f"Error processing store row: {row_error}")
                continue
        
        logger.info(f"✅ Loaded {len(store_mappings)} store mappings")
        return store_mappings
        
    except Exception as e:
        logger.error(f"❌ Failed to load store mappings: {e}")
        # Return empty dict instead of failing
        return {}

def get_shop_mappings():
    return {
        'archery': ('1', 'ARCHERY'),
        'shotguns': ('11', 'SHOTGUNS'),
        'rifles': ('18', 'RIFLES'),
        'hunting': ('19', 'HUNTING'),
        'scopes': ('20', 'SCOPES OPTICS'),
        'optics': ('20', 'SCOPES OPTICS'),
        'reloading': ('21', 'RELOADING'),
        'muzzleloading': ('22', 'MUZZLELOADING'),
        'fishing': ('23', 'FISHING'),
        'handguns': ('67', 'HANDGUNS'),
        'ammunition': ('70', 'AMMUNITION'),
        'ammo': ('70', 'AMMUNITION'),
        'hunting clothing': ('75', 'HUNTING CLOTHING'),
        'hunting footwear': ('89', 'HUNTING FOOTWEAR'),
        'fly fishing': ('45', 'FLY FISHING'),
        'ice fishing': ('24', 'ICE FISHING'),
        'suppressors': ('68', 'SUPPRESSORS'),
        'cutlery': ('80', 'CUTLERY'),
        'workwear': ('87', 'WORKWEAR'),
        'baseball': ('2', 'BASEBALL/SOFTBALL'),
        'softball': ('2', 'BASEBALL/SOFTBALL'),
        'bike': ('3', 'BIKE'),
        'bikes': ('3', 'BIKE'),
        'bicycle': ('3', 'BIKE'),
        'camping': ('7', 'CAMPING'),
        'ski': ('15', 'SKI-ALPINE'),
        'alpine': ('15', 'SKI-ALPINE'),
        'cross country': ('16', 'SKI-CROSS COUNTRY'),
        'watersports': ('28', 'WATERSPORTS'),
        'team sports': ('29', 'TEAM SPORTS'),
        'hockey': ('31', 'HOCKEY'),
        'exercise': ('33', 'EXERCISE'),
        'golf': ('34', 'GOLF'),
        'snowboards': ('6', 'SNOWBOARDS'),
        'paddlesports': ('27', 'PADDLESPORTS'),
        'toys': ('30', 'TOYS'),
        'boys clothing': ('10', 'BOYS CLOTHING'),
        'swimwear women': ('13', 'SWIMWEAR-WOMEN\'S'),
        'womens swimwear': ('13', 'SWIMWEAR-WOMEN\'S'),
        'athletic clothing women': ('38', 'ATHLETIC CLOTHING WOMEN\'S'),
        'athletic clothing': ('39', 'ADULT ATHLETIC CLOTHING'),
        'swimwear men': ('47', 'SWIMWEAR-MEN\'S'),
        'mens swimwear': ('47', 'SWIMWEAR-MEN\'S'),
        'mens sportswear': ('52', 'MENS SPORTSWEAR'),
        'womens sportswear': ('55', 'WMNS SPORTSWEAR'),
        'college clothing': ('77', 'COLLEGE CLOTHING MENS'),
        'licensed clothing': ('78', 'LICENSED CLOTHING'),
        'socks': ('79', 'SOCKS'),
        'mens fashion': ('94', 'MEN\'S FASHION CLOTHING'),
        'womens fashion': ('95', 'WOMEN\'S FASHION CLOTHING'),
        'girls clothing': ('8', 'GIRLS CLOTHING'),
        'mens outerwear': ('40', 'MENS OUTERWEAR'),
        'womens outerwear': ('37', 'WOMENS OUTERWEAR'),
        'casual footwear mens': ('25', 'CASUAL FOOTWEAR MENS'),
        'mens shoes': ('25', 'CASUAL FOOTWEAR MENS'),
        'casual footwear womens': ('26', 'CASUAL FOOTWEAR WOMENS'),
        'womens shoes': ('26', 'CASUAL FOOTWEAR WOMENS'),
        'sport shoes men': ('41', 'SPORT SHOES-MEN\'S'),
        'mens sport shoes': ('41', 'SPORT SHOES-MEN\'S'),
        'sport shoes women': ('42', 'SPORT SHOES-WMN\'S'),
        'womens sport shoes': ('42', 'SPORT SHOES-WMN\'S'),
        'girls footwear': ('43', 'GIRLS FOOTWEAR'),
        'boys footwear': ('53', 'BOYS FOOTWEAR'),
        'hardware': ('250', 'HARDWARE'),
        'tools': ('220', 'TOOLS'),
        'paint': ('214', 'PAINT'),
        'electrical': ('230', 'ELECTRICAL'),
        'plumbing': ('240', 'PLUMBING'),
        'lawn garden': ('270', 'LAWN & GARDEN'),
        'lawn and garden': ('270', 'LAWN & GARDEN'),
        'power equipment': ('273', 'POWER EQUIPMENT'),
    }

# Enhanced model configuration with cost tracking and capabilities
def get_available_models():
    """
    Enhanced model configuration with cost tracking, capabilities, and provider information.
    This is the single source of truth for all model information.
    """
    return {
        "gemini-2.5-pro": {
            "provider": "google",
            "description": "Most powerful, best for complex analysis",
            "context_window": 1048576,
            "capabilities": ["text", "code", "analysis", "reasoning"],
            "recommended_for": ["complex_queries", "detailed_analysis", "inventory_analysis"]
        },
        "gemini-2.5-flash": {
            "provider": "google", 
            "description": "Faster, good for most queries",
            "context_window": 1048576,
            "capabilities": ["text", "code", "fast_response"],
            "recommended_for": ["quick_queries", "standard_analysis", "real_time"]
        },
        "gemini-2.0-flash-exp": {
            "provider": "google",
            "description": "Experimental, very fast",
            "context_window": 32768,
            "capabilities": ["text", "experimental", "speed"],
            "recommended_for": ["testing", "rapid_prototyping", "simple_queries"]
        },
        "grok-4-0709": {
            "provider": "xai",
            "description": "Latest Grok 4 - Advanced reasoning (256K context)",
            "context_window": 262144,
            "capabilities": ["text", "reasoning", "real_time_data"],
            "recommended_for": ["complex_reasoning", "current_events", "creative_analysis"]
        },
        "grok-3": {
            "provider": "xai",
            "description": "Grok 3 - Balanced performance (131K context)",
            "context_window": 131072,
            "capabilities": ["text", "reasoning", "balanced"],
            "recommended_for": ["general_queries", "balanced_performance", "cost_effective"]
        },
        "grok-3-mini": {
            "provider": "xai",
            "description": "Grok 3 Mini - Cost-effective ($0.30/$0.50)",
            "context_window": 32768,
            "capabilities": ["text", "fast", "budget"],
            "recommended_for": ["simple_queries", "budget_conscious", "high_volume"]
        },
        "claude-sonnet-4-20250514": {
            "provider": "anthropic",
            "description": "Fast and capable for most tasks",
            "context_window": 200000,
            "capabilities": ["text", "code", "analysis", "fast"],
            "recommended_for": ["standard_analysis", "code_review", "data_processing"]
        },
        "claude-opus-4-20250514": {
            "provider": "anthropic",
            "description": "Most powerful Claude model",
            "context_window": 200000,
            "capabilities": ["text", "code", "advanced_reasoning", "creative"],
            "recommended_for": ["complex_analysis", "creative_tasks", "detailed_reasoning"]
        },
        "claude-3.5-sonnet-20241022": {
            "provider": "anthropic",
            "description": "Claude 3.5 Sonnet - efficient affordable Sonnet",
            "context_window": 200000,
            "capabilities": ["text", "code", "efficient"],
            "recommended_for": ["general_use", "cost_effective", "reliable"]
        },
        "claude-3.5-haiku-20241022": {
            "provider": "anthropic",
            "description": "Fastest Anthropic Model",
            "context_window": 200000,
            "capabilities": ["text", "speed", "lightweight"],
            "recommended_for": ["quick_responses", "high_throughput", "simple_tasks"]
        },
        "gpt-4o": {
            "provider": "openai",
            "description": "Flagship GPT model for complex tasks",
            "context_window": 128000,
            "capabilities": ["text", "code", "multimodal", "reasoning"],
            "recommended_for": ["complex_tasks", "multimodal_analysis", "premium_quality"]
        },
        "gpt-4o-mini": {
            "provider": "openai",
            "description": "Faster, more affordable GPT-4 model",
            "context_window": 128000,
            "capabilities": ["text", "code", "fast", "budget"],
            "recommended_for": ["quick_queries", "cost_effective", "high_volume"]
        },
        "gpt-5-2025-08-07": {
            "provider": "openai",
            "description": "Advanced reasoning model (preview)",
            "context_window": 400000,
            "capabilities": ["reasoning", "complex_logic", "preview"],
            "recommended_for": ["complex_reasoning", "mathematical_analysis", "research"]
        }
    }

def get_provider_info() -> Dict[str, Dict[str, str]]:
    """Get provider information for UI display."""
    return {
        'google': {
            'name': 'Google',
            'color': '#1a73e8',
            'background': '#e8f0fe'
        },
        'xai': {
            'name': 'X.AI',
            'color': '#1d1d1d',
            'background': '#f0f0f0'
        },
        'anthropic': {
            'name': 'Anthropic',
            'color': '#8b5a00',
            'background': '#f4e8d8'
        },
        'openai': {
            'name': 'OpenAI',
            'color': '#059669',
            'background': '#e8f5e8'
        }
    }

def get_model_recommendations(query_type: str = None, budget: str = 'medium') -> list:
    """
    Get recommended models based on query type and budget constraints.
    
    Args:
        query_type: 'simple', 'complex', 'reasoning', 'creative', 'code'
        budget: 'low', 'medium', 'high'
    
    Returns:
        List of recommended model IDs in order of preference
    """
    models = get_available_models()
    
    if query_type == 'simple':
        if budget == 'low':
            return ['gpt-4o-mini', 'claude-3.5-haiku-20241022', 'grok-3-mini']
        elif budget == 'medium':
            return ['gemini-2.5-flash', 'claude-3.5-sonnet-20241022', 'grok-3']
        else:  # high budget
            return ['gemini-2.5-pro', 'gpt-4o', 'claude-sonnet-4-20250514']
    
    elif query_type == 'complex':
        if budget == 'low':
            return ['claude-3.5-sonnet-20241022', 'gemini-2.5-flash', 'gpt-4o-mini']
        elif budget == 'medium':
            return ['gemini-2.5-pro', 'claude-sonnet-4-20250514', 'gpt-4o']
        else:  # high budget
            return ['claude-opus-4-20250514', 'gemini-2.5-pro', 'gpt-4o']
    
    elif query_type == 'reasoning':
        return ['o1-preview', 'claude-opus-4-20250514', 'grok-4-0709', 'gemini-2.5-pro']
    
    elif query_type == 'creative':
        return ['claude-opus-4-20250514', 'gpt-4o', 'grok-4-0709', 'gemini-2.5-pro']
    
    elif query_type == 'code':
        return ['claude-sonnet-4-20250514', 'gpt-4o', 'gemini-2.5-pro', 'claude-3.5-sonnet-20241022']
    
    else:  # default recommendations
        return ['gemini-2.5-pro', 'claude-sonnet-4-20250514', 'gpt-4o', 'grok-3']

# Cost estimation function removed

def validate_model_selection(model_id: str) -> tuple[bool, str]:
    """
    Validate if a model selection is valid and available.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    available_models = get_available_models()
    
    if not available_models:
        return False, "No AI models are available. Please configure API keys."
    
    if model_id not in available_models:
        available_list = list(available_models.keys())
        return False, f"Model '{model_id}' not available. Available models: {available_list}"
    
    return True, ""

# Application configuration with enhanced features
@dataclass
class AppConfig:
    """Enhanced application configuration."""
    bq_project: str = os.getenv('BQ_PROJECT', 'scheels-data-marts')
    default_model: str = os.getenv('DEFAULT_MODEL', 'gemini-2.5-pro')
    preview_rows: int = int(os.getenv('PREVIEW_ROWS', '20'))
    enable_weighting: bool = os.getenv('ENABLE_WEIGHTING', 'True').lower() == 'true'
    enable_auth: bool = os.getenv('ENABLE_AUTH', 'False').lower() == 'true'
    max_history_items: int = int(os.getenv('MAX_HISTORY_ITEMS', '50'))
    max_suggestions: int = int(os.getenv('MAX_SUGGESTIONS', '8'))
    enable_dashboard: bool = os.getenv('ENABLE_DASHBOARD', 'True').lower() == 'true'
    # Cost tracking removed
    
    # API Keys validation
    @property
    def available_providers(self) -> list:
        """Get list of providers with valid API keys."""
        providers = []
        if os.getenv('GOOGLE_API_KEY'):
            providers.append('google')
        if os.getenv('XAI_API_KEY'):  # Note: using XAI_API_KEY as per your api_clients.py
            providers.append('xai')
        if os.getenv('ANTHROPIC_API_KEY'):
            providers.append('anthropic')
        if os.getenv('OPENAI_API_KEY'):
            providers.append('openai')
        return providers
    
    def get_available_models_filtered(self) -> Dict[str, Dict[str, Any]]:
        """Get only models for which we have API keys."""
        all_models = get_available_models()
        available_providers = self.available_providers
        
        return {
            model_id: config
            for model_id, config in all_models.items()
            if config['provider'] in available_providers
        }

# Usage examples and testing
if __name__ == "__main__":
    # Test the configuration
    print("=== Model Configuration Test ===")
    
    models = get_available_models()
    print(f"Total models configured: {len(models)}")
    
    for provider in ['google', 'xai', 'anthropic', 'openai']:
        provider_models = [m for m in models.values() if m['provider'] == provider]
        print(f"{provider.title()}: {len(provider_models)} models")
    
    # Cost estimation test removed
    
    print("\n=== Recommendation Test ===")
    for query_type in ['simple', 'complex', 'reasoning']:
        recommendations = get_model_recommendations(query_type, 'medium')
        print(f"{query_type.title()} queries: {recommendations[:3]}")
    
    print("\n=== Configuration Test ===")
    app_config = AppConfig()
    print(f"Default model: {app_config.default_model}")
    print(f"Available providers: {app_config.available_providers}")
    print(f"Dashboard enabled: {app_config.enable_dashboard}")
    # Cost tracking removed

    print("\n=== Store Mappings Test ===")
    store_mappings = get_store_mappings()
    print(f"Loaded {len(store_mappings)} stores")
    if '64' in store_mappings:
        print(f"Store 64: {store_mappings['64']}")
    if '28' in store_mappings:
        print(f"Store 28: {store_mappings['28']}")

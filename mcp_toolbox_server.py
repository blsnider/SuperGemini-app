#!/usr/bin/env python3
"""
Custom MCP Toolbox Server
Builds directly from tools.yaml configuration
"""

import os
import sys
import yaml
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import bigquery
from typing import Dict, Any, List
import traceback
from datetime import datetime
from decimal import Decimal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types from BigQuery"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to float for JSON serialization
            return float(obj)
        elif isinstance(obj, datetime):
            # Handle datetime objects
            return obj.isoformat()
        return super().default(obj)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure Flask to use our custom JSON encoder
app.json_encoder = DecimalEncoder

class ToolboxServer:
    def __init__(self, config_path: str = '/app/tools.yaml'):
        """Initialize the toolbox server with tools configuration."""
        self.config_path = config_path
        self.tools = {}
        self.sources = {}
        self.bigquery_clients = {}
        self.load_configuration()
        
    def load_configuration(self):
        """Load tools configuration from YAML file."""
        try:
            # Try to load from file first
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
            else:
                # Fallback to environment variable
                config_content = os.getenv('TOOLS_YAML_CONTENT')
                if config_content:
                    config = yaml.safe_load(config_content)
                    logger.info("Loaded configuration from environment variable")
                else:
                    raise FileNotFoundError(f"No configuration found at {self.config_path} or in environment")
            
            # Parse sources
            self.sources = config.get('sources', {})
            logger.info(f"Loaded {len(self.sources)} data sources")
            
            # Parse tools
            tools_config = config.get('tools', {})
            for tool_name, tool_def in tools_config.items():
                self.tools[tool_name] = {
                    'name': tool_name,
                    'kind': tool_def.get('kind', 'bigquery-sql'),
                    'source': tool_def.get('source'),
                    'description': tool_def.get('description', ''),
                    'parameters': tool_def.get('parameters', []),
                    'statement': tool_def.get('statement', '')
                }
            
            logger.info(f"Loaded {len(self.tools)} tools: {list(self.tools.keys())}")
            
            # Initialize BigQuery clients for each source
            for source_name, source_config in self.sources.items():
                if source_config.get('kind') == 'bigquery':
                    project = source_config.get('project')
                    location = source_config.get('location', 'US')
                    client = bigquery.Client(project=project, location=location)
                    self.bigquery_clients[source_name] = client
                    logger.info(f"Initialized BigQuery client for {source_name} (project: {project})")
                    
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Execute a tool with given parameters."""
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        tool = self.tools[tool_name]
        
        if tool['kind'] == 'bigquery-sql':
            return self.execute_bigquery_tool(tool, parameters)
        else:
            raise ValueError(f"Unsupported tool kind: {tool['kind']}")
    
    def execute_bigquery_tool(self, tool: Dict, parameters: Dict[str, Any]) -> List[Dict]:
        """Execute a BigQuery SQL tool."""
        source_name = tool['source']
        if source_name not in self.bigquery_clients:
            raise ValueError(f"Source '{source_name}' not configured")
        
        client = self.bigquery_clients[source_name]
        statement = tool['statement']
        
        # Build query parameters
        query_params = []
        for param_def in tool['parameters']:
            param_name = param_def['name']
            param_type = param_def['type']
            
            # Get parameter value or use default
            if param_name in parameters:
                param_value = parameters[param_name]
            elif 'default' in param_def:
                param_value = param_def['default']
                logger.info(f"Using default value for {param_name}: {param_def['default']}")
            else:
                # No value provided and no default - this should be an error
                param_value = None
            
            # Skip None values - they'll use defaults in the SQL
            if param_value is None:
                continue
            
            # Convert parameter to appropriate BigQuery type
            if param_type == 'integer':
                query_params.append(
                    bigquery.ScalarQueryParameter(param_name, "INT64", int(param_value))
                )
            elif param_type == 'string':
                query_params.append(
                    bigquery.ScalarQueryParameter(param_name, "STRING", str(param_value))
                )
            elif param_type == 'float':
                query_params.append(
                    bigquery.ScalarQueryParameter(param_name, "FLOAT64", float(param_value))
                )
            elif param_type == 'date':
                query_params.append(
                    bigquery.ScalarQueryParameter(param_name, "DATE", str(param_value))
                )
            else:
                query_params.append(
                    bigquery.ScalarQueryParameter(param_name, "STRING", str(param_value))
                )
        
        # Configure and execute query
        job_config = bigquery.QueryJobConfig(
            query_parameters=query_params,
            use_query_cache=True,
            use_legacy_sql=False
        )
        
        logger.info(f"Executing query for tool '{tool['name']}' with {len(query_params)} parameters")
        query_job = client.query(statement, job_config=job_config)
        
        # Get results and convert special types
        results = query_job.result()
        rows = []
        for row in results:
            row_dict = {}
            for key, value in dict(row).items():
                # Convert Decimal to float for JSON serialization
                if isinstance(value, Decimal):
                    row_dict[key] = float(value)
                # Convert datetime to ISO format string
                elif isinstance(value, datetime):
                    row_dict[key] = value.isoformat()
                # Convert date to ISO format string
                elif hasattr(value, 'isoformat'):
                    row_dict[key] = value.isoformat()
                else:
                    row_dict[key] = value
            rows.append(row_dict)
        
        logger.info(f"Query returned {len(rows)} rows")
        return rows

# Initialize the server
toolbox = ToolboxServer()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'tools_loaded': len(toolbox.tools)})

@app.route('/tools', methods=['GET'])
def list_tools():
    """List all available tools."""
    tools_list = []
    for tool_name, tool in toolbox.tools.items():
        # Process parameters to mark those with defaults as optional
        processed_params = []
        for param in tool['parameters']:
            param_copy = param.copy()
            # If parameter has a default, mark it as not required
            if 'default' in param_copy:
                param_copy['required'] = False
            elif 'required' not in param_copy:
                # If no default and no explicit required field, assume required
                param_copy['required'] = True
            processed_params.append(param_copy)
            
        tools_list.append({
            'name': tool_name,
            'description': tool['description'],
            'parameters': processed_params
        })
    return jsonify(tools_list)

@app.route('/api/toolset/<toolset_name>', methods=['GET'])
def get_api_toolset(toolset_name: str):
    """Get toolset definition (API endpoint for ToolboxSyncClient.load_toolset)."""
    if toolset_name == 'retail_analytics':
        # Return toolset manifest with tools as a dictionary
        tools_dict = {}
        for tool_name, tool in toolbox.tools.items():
            # Process parameters to mark those with defaults as optional
            processed_params = []
            for param in tool['parameters']:
                param_copy = param.copy()
                # If parameter has a default, mark it as not required
                if 'default' in param_copy:
                    param_copy['required'] = False
                elif 'required' not in param_copy:
                    # If no default and no explicit required field, assume required
                    param_copy['required'] = True
                processed_params.append(param_copy)
            
            tools_dict[tool_name] = {
                'name': tool['name'],
                'description': tool['description'],
                'parameters': processed_params
            }
        
        # Return as a manifest object with required fields
        manifest = {
            'name': toolset_name,
            'description': 'Retail analytics tools for Super Gemini',
            'serverVersion': '1.0.0',  # Required field
            'tools': tools_dict  # Changed from list to dict
        }
        return jsonify(manifest)
    return jsonify({'error': f"Toolset '{toolset_name}' not found"}), 404

@app.route('/toolsets/<toolset_name>', methods=['GET'])
def get_toolset_root(toolset_name: str):
    """Get toolset definition (compatibility endpoint)."""
    if toolset_name == 'retail_analytics':
        # Return all tools for the retail_analytics toolset
        return list_tools()
    return jsonify({'error': f"Toolset '{toolset_name}' not found"}), 404

@app.route('/toolsets/<toolset_name>/tools', methods=['GET'])
def get_toolset(toolset_name: str):
    """Get tools for a specific toolset (compatibility with existing API)."""
    if toolset_name == 'retail_analytics':
        # Return all tools for compatibility
        return list_tools()
    return jsonify({'error': f"Toolset '{toolset_name}' not found"}), 404

@app.route('/tools/<tool_name>', methods=['POST'])
def execute_tool(tool_name: str):
    """Execute a specific tool."""
    try:
        parameters = request.get_json() or {}
        result = toolbox.execute_tool(tool_name, parameters)
        
        # Return in the format expected by toolbox_core: {"result": data}
        response_data = {"result": result}
        return json.dumps(response_data, cls=DecimalEncoder), 200, {'Content-Type': 'application/json'}
        
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/toolsets/<toolset_name>/tools/<tool_name>', methods=['POST'])
def execute_toolset_tool(toolset_name: str, tool_name: str):
    """Execute a tool from a toolset (compatibility endpoint)."""
    if toolset_name == 'retail_analytics':
        return execute_tool(tool_name)
    return jsonify({'error': f"Toolset '{toolset_name}' not found"}), 404

@app.route('/api/tool/<tool_name>/invoke', methods=['POST'])
def invoke_tool(tool_name: str):
    """Execute a tool via the /invoke endpoint (ToolboxSyncClient expected endpoint)."""
    try:
        parameters = request.get_json() or {}
        logger.info(f"Tool invocation via /api/tool/{tool_name}/invoke with params: {parameters}")
        result = toolbox.execute_tool(tool_name, parameters)
        
        # Return in the format expected by toolbox_core: {"result": data}
        response_data = {"result": result}
        return json.dumps(response_data, cls=DecimalEncoder), 200, {'Content-Type': 'application/json'}
        
    except Exception as e:
        logger.error(f"Error invoking tool '{tool_name}': {e}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/reload', methods=['POST'])
def reload_configuration():
    """Reload the tools configuration."""
    try:
        toolbox.load_configuration()
        return jsonify({'status': 'reloaded', 'tools_loaded': len(toolbox.tools)})
    except Exception as e:
        logger.error(f"Failed to reload configuration: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starting MCP Toolbox Server on port {port}")
    logger.info(f"Tools loaded: {list(toolbox.tools.keys())}")
    
    # Use threaded mode for better performance in production
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
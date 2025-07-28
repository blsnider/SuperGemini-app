#!/usr/bin/env python3
"""
Local MCP Toolbox test server
"""
import os
import logging
from toolbox_core import Toolbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Configuration
    config_path = os.getenv("TOOLBOX_CONFIG_PATH", "chatbot/tools.yaml")
    port = int(os.getenv("PORT", "8080"))
    
    logger.info(f"Starting MCP Toolbox locally...")
    logger.info(f"Config file: {config_path}")
    logger.info(f"Port: {port}")
    
    # Create and run toolbox
    toolbox = Toolbox.from_config(config_path)
    
    # Start the server
    logger.info(f"Server starting on http://localhost:{port}")
    toolbox.serve(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()

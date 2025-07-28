#!/usr/bin/env python3
"""
MCP Toolbox Troubleshooting Script
Run this to diagnose MCP tool configuration issues
"""

import os
import sys
import json
import requests
from toolbox_core import ToolboxSyncClient

def main():
    # Get toolbox URL from environment or use default
    toolbox_url = os.getenv("TOOLBOX_URL", "https://toolbox-41815171183.us-central1.run.app")
    
    print(f"=== MCP Toolbox Troubleshooting ===")
    print(f"Toolbox URL: {toolbox_url}")
    print()
    
    # Test 1: Check if server is accessible
    print("1. Testing server connectivity...")
    try:
        response = requests.get(f"{toolbox_url}/health", timeout=5)
        print(f"   ✓ Server is accessible (status: {response.status_code})")
    except Exception as e:
        print(f"   ✗ Server is not accessible: {e}")
        return
    
    # Test 2: Initialize client
    print("\n2. Initializing MCP Toolbox client...")
    try:
        client = ToolboxSyncClient(toolbox_url)
        print("   ✓ Client initialized successfully")
    except Exception as e:
        print(f"   ✗ Failed to initialize client: {e}")
        return
    
    # Test 3: List available toolsets
    print("\n3. Listing available toolsets...")
    try:
        # This might need adjustment based on your MCP Toolbox API
        toolsets = client.list_toolsets() if hasattr(client, 'list_toolsets') else ['retail_analytics']
        print(f"   Available toolsets: {toolsets}")
    except Exception as e:
        print(f"   Note: Could not list toolsets ({e}), continuing...")
    
    # Test 4: Load retail_analytics toolset
    print("\n4. Loading 'retail_analytics' toolset...")
    try:
        tools = client.load_toolset('retail_analytics')
        print(f"   ✓ Loaded {len(tools)} tools")
        
        # Convert to dict if needed
        if isinstance(tools, list):
            tools_dict = {}
            for tool in tools:
                if hasattr(tool, '__name__'):
                    tools_dict[tool.__name__] = tool
                elif hasattr(tool, 'name'):
                    tools_dict[tool.name] = tool
            tools = tools_dict
        
        print(f"   Tool names: {list(tools.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to load toolset: {e}")
        return
    
    # Test 5: Inspect get_top_selling_items tool
    print("\n5. Inspecting 'get_top_selling_items' tool...")
    if 'get_top_selling_items' in tools:
        tool = tools['get_top_selling_items']
        
        # Try to inspect tool properties
        print("   Tool inspection:")
        
        # Check for various attributes
        attrs_to_check = ['__dict__', 'parameters', 'params', 'arguments', 
                         'signature', '__signature__', 'schema', '_schema',
                         'statement', '_statement', 'sql', '_sql']
        
        for attr in attrs_to_check:
            if hasattr(tool, attr):
                value = getattr(tool, attr)
                if isinstance(value, str) and len(value) > 100:
                    print(f"   - {attr}: {value[:100]}...")
                else:
                    print(f"   - {attr}: {value}")
        
        # Try to get function signature
        try:
            import inspect
            sig = inspect.signature(tool)
            print(f"   - Function signature: {sig}")
            print(f"   - Parameters: {list(sig.parameters.keys())}")
        except Exception as e:
            print(f"   - Could not get signature: {e}")
        
        # Test calling with different parameter sets
        print("\n6. Testing tool calls...")
        
        # Test 1: With conditions parameter (old style)
        print("   Test 1: Calling with 'conditions' parameter...")
        try:
            result = tool(conditions="1=1", limit=10)
            print(f"   ✓ Success with 'conditions' parameter")
            print(f"   Result type: {type(result)}")
            if hasattr(result, '__len__'):
                print(f"   Result length: {len(result)}")
        except Exception as e:
            print(f"   ✗ Failed with 'conditions' parameter: {e}")
        
        # Test 2: With individual parameters (new style)
        print("\n   Test 2: Calling with individual parameters...")
        try:
            result = tool(store_id=64, shop_id=3, year_filter=2025, days_back=0, limit=10)
            print(f"   ✓ Success with individual parameters")
            print(f"   Result type: {type(result)}")
            if hasattr(result, '__len__'):
                print(f"   Result length: {len(result)}")
        except Exception as e:
            print(f"   ✗ Failed with individual parameters: {e}")
        
        # Test 3: Try to find what parameters it actually expects
        print("\n   Test 3: Testing parameter discovery...")
        try:
            # Try calling with no parameters to see error message
            result = tool()
        except TypeError as e:
            print(f"   Expected error message: {e}")
            # This error message should tell us what parameters are required
    
    else:
        print("   ✗ 'get_top_selling_items' tool not found!")
    
    # Test 7: Try raw API call to understand tool structure
    print("\n7. Making raw API call to understand tool structure...")
    try:
        # This is a guess - adjust based on your MCP Toolbox API
        response = requests.get(f"{toolbox_url}/api/toolsets/retail_analytics/tools", timeout=5)
        if response.status_code == 200:
            tools_data = response.json()
            print(f"   Raw API response (first 500 chars): {json.dumps(tools_data, indent=2)[:500]}...")
        else:
            print(f"   API call returned status {response.status_code}")
    except Exception as e:
        print(f"   Could not make raw API call: {e}")

if __name__ == "__main__":
    main()
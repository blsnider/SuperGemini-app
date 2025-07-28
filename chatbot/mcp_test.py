#!/usr/bin/env python3
"""
Test MCP tools using the same approach as core.py
"""
import os
import logging
from toolbox_core import ToolboxSyncClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_mcp_tools():
    """Test MCP tools locally"""
    
    # Test both local and remote
    print("=== MCP Toolbox Testing ===")
    print("1. Remote server (Cloud Run)")
    print("2. Local server (if running)")
    choice = input("Select (1/2): ")
    
    if choice == "2":
        toolbox_url = "http://localhost:8080"
    else:
        toolbox_url = "https://toolbox-41815171183.us-central1.run.app"
    
    print(f"\nConnecting to: {toolbox_url}")
    
    try:
        # Initialize client (same as in core.py)
        client = ToolboxSyncClient(toolbox_url)
        print("✓ Client initialized")
        
        # Load retail_analytics toolset
        print("\nLoading retail_analytics toolset...")
        tools = client.load_toolset('retail_analytics')
        
        # Handle different return formats (from core.py)
        if isinstance(tools, dict):
            tool_dict = tools
            print(f"✓ Loaded {len(tool_dict)} tools as dict")
        elif isinstance(tools, list):
            print(f"✓ Loaded {len(tools)} tools as list")
            # Convert to dict
            tool_dict = {}
            for tool in tools:
                if hasattr(tool, '__name__'):
                    tool_dict[tool.__name__] = tool
                elif hasattr(tool, 'name'):
                    tool_dict[tool.name] = tool
                else:
                    # Try to extract name
                    import re
                    tool_str = str(tool)
                    match = re.search(r'(get_\w+)', tool_str)
                    if match:
                        tool_dict[match.group(1)] = tool
        else:
            print(f"Unexpected format: {type(tools)}")
            return
        
        print(f"Available tools: {list(tool_dict.keys())}")
        
        # Test get_top_selling_items
        if 'get_top_selling_items' in tool_dict:
            print("\n=== Testing get_top_selling_items ===")
            tool = tool_dict['get_top_selling_items']
            
            # Check signature
            import inspect
            try:
                sig = inspect.signature(tool)
                print(f"Signature: {sig}")
            except:
                print("Could not get signature")
            
            # Test 1: Simple query
            print("\nTest 1: Top 5 items")
            try:
                result = tool(
                    store_id=0,
                    shop_id=0,
                    year_filter=0,
                    days_back=30,
                    limit=5
                )
                print(f"✓ Success!")
                process_result(result)
            except Exception as e:
                print(f"✗ Error: {e}")
            
            # Test 2: With filters
            print("\nTest 2: Store 64, Shop 3, Year 2025")
            try:
                result = tool(
                    store_id=64,
                    shop_id=3,
                    year_filter=2025,
                    days_back=0,
                    limit=10
                )
                print(f"✓ Success!")
                process_result(result)
            except Exception as e:
                print(f"✗ Error: {e}")
        
        # Test other tools if available
        for tool_name in ['get_inventory_status', 'get_sales_trends']:
            if tool_name in tool_dict:
                print(f"\n=== Testing {tool_name} ===")
                tool = tool_dict[tool_name]
                try:
                    # Call with minimal parameters
                    if tool_name == 'get_inventory_status':
                        result = tool(store_id=64, limit=5)
                    elif tool_name == 'get_sales_trends':
                        result = tool(days_back=7, store_id=64, shop_id=0)
                    print(f"✓ Success!")
                    process_result(result)
                except Exception as e:
                    print(f"✗ Error: {e}")
    
    except Exception as e:
        print(f"\nConnection error: {e}")
        import traceback
        traceback.print_exc()

def process_result(result):
    """Process and display tool results"""
    import pandas as pd
    
    if isinstance(result, pd.DataFrame):
        print(f"  DataFrame: {result.shape} rows x columns")
        if not result.empty:
            print(f"  Columns: {list(result.columns)}")
            print(f"  First row:")
            print(result.head(1).to_string())
    elif isinstance(result, list):
        print(f"  List with {len(result)} items")
        if result:
            print(f"  First item: {result[0]}")
    elif isinstance(result, dict):
        print(f"  Dict with keys: {list(result.keys())}")
    elif isinstance(result, str):
        print(f"  String result (first 200 chars): {result[:200]}...")
    else:
        print(f"  Result type: {type(result)}")

if __name__ == "__main__":
    test_mcp_tools()
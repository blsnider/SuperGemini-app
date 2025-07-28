#!/usr/bin/env python3
"""
Test the MCP Toolbox locally
"""
import os
from toolbox_core import ToolboxSyncClient

def main():
    # Connect to local or remote toolbox
    local_mode = input("Test locally? (y/n): ").lower() == 'y'
    
    if local_mode:
        toolbox_url = "http://localhost:8080"
        print(f"Connecting to local MCP Toolbox at {toolbox_url}")
    else:
        toolbox_url = "https://toolbox-41815171183.us-central1.run.app"
        print(f"Connecting to Cloud Run MCP Toolbox at {toolbox_url}")
    
    try:
        # Initialize client
        client = ToolboxSyncClient(toolbox_url)
        print("✓ Client connected")
        
        # List toolsets
        toolsets = client.list_toolsets()
        print(f"Available toolsets: {toolsets}")
        
        # Load retail_analytics
        tools = client.load_toolset('retail_analytics')
        if isinstance(tools, list):
            print(f"✓ Loaded {len(tools)} tools")
            tool_names = [t.__name__ if hasattr(t, '__name__') else str(t) for t in tools]
        else:
            print(f"✓ Loaded tools: {list(tools.keys())}")
            tool_names = list(tools.keys())
        
        print(f"Tools: {tool_names}")
        
        # Test get_top_selling_items
        if 'get_top_selling_items' in tool_names or any('get_top_selling_items' in str(t) for t in tool_names):
            print("\nTesting get_top_selling_items...")
            
            # Get the tool
            if isinstance(tools, dict):
                tool = tools['get_top_selling_items']
            else:
                tool = next(t for t in tools if 'get_top_selling_items' in str(t))
            
            # Test with parameters
            print("Calling with: store_id=64, shop_id=3, year_filter=2025, limit=10")
            try:
                result = tool(store_id=64, shop_id=3, year_filter=2025, days_back=0, limit=10)
                print(f"✓ Success! Result type: {type(result)}")
                if hasattr(result, '__len__'):
                    print(f"  Result length: {len(result)}")
                # Print first few results
                import pandas as pd
                if isinstance(result, str):
                    print(f"  First 200 chars: {result[:200]}...")
                elif isinstance(result, pd.DataFrame):
                    print(f"  DataFrame shape: {result.shape}")
                    print(f"  Columns: {list(result.columns)}")
                    print(f"  First row:\n{result.head(1)}")
                elif isinstance(result, list) and result:
                    print(f"  First item: {result[0]}")
            except Exception as e:
                print(f"✗ Error: {e}")
                
    except Exception as e:
        print(f"Connection error: {e}")

if __name__ == "__main__":
    main()

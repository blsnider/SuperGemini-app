"""
Custom wrapper for MCP Toolbox integration that handles response format issues.
This wrapper fixes the mismatch between what the MCP server returns and what toolbox_core expects.
"""

import json
import logging
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from toolbox_core import ToolboxSyncClient

logger = logging.getLogger(__name__)


class FixedToolboxSyncTool:
    """
    A wrapper around ToolboxSyncTool that fixes the response format issue.
    """
    
    def __init__(self, original_tool, name: str):
        self._original_tool = original_tool
        self._name = name
        
    @property
    def name(self) -> str:
        return self._name
    
    def __call__(self, **kwargs) -> str:
        """
        Call the original tool but fix the response format if needed.
        """
        try:
            # Call the original tool
            result = self._original_tool(**kwargs)
            
            # The result should be a JSON string
            if isinstance(result, str):
                try:
                    # Try to parse as JSON
                    parsed_result = json.loads(result)
                    
                    # If it's already wrapped with 'result' key, return as-is
                    if isinstance(parsed_result, dict) and 'result' in parsed_result:
                        return result
                    
                    # If it's a raw list or dict, wrap it
                    wrapped_result = {"result": parsed_result}
                    return json.dumps(wrapped_result)
                    
                except json.JSONDecodeError:
                    # If it's not JSON, return as-is
                    return result
            else:
                # If result is not a string, convert to JSON and wrap
                wrapped_result = {"result": result}
                return json.dumps(wrapped_result)
                
        except Exception as e:
            logger.error(f"Error calling tool {self._name}: {e}")
            raise


class FixedToolboxSyncClient:
    """
    A wrapper around ToolboxSyncClient that provides proper tool names and response handling.
    """
    
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = ToolboxSyncClient(base_url)
        
    def load_toolset(self, name: str = None) -> Dict[str, FixedToolboxSyncTool]:
        """
        Load a toolset and return a dictionary of tool_name -> FixedToolboxSyncTool
        """
        try:
            # Load tools using the original client
            original_tools = self._client.load_toolset(name)
            logger.info(f"Loaded {len(original_tools)} tools from toolset '{name}'")
            
            # Create a dictionary mapping tool names to wrapped tools
            fixed_tools = {}
            
            for i, tool in enumerate(original_tools):
                # Try to get tool name from various sources
                tool_name = None
                
                # Method 1: Check if tool has _name property
                if hasattr(tool, '_name'):
                    tool_name = tool._name
                # Method 2: Check if tool has __name__ property  
                elif hasattr(tool, '__name__'):
                    tool_name = tool.__name__
                # Method 3: Try to get name from the async tool
                elif hasattr(tool, '_ToolboxSyncTool__async_tool'):
                    async_tool = tool._ToolboxSyncTool__async_tool
                    if hasattr(async_tool, '_ToolboxTool__name__'):
                        tool_name = async_tool._ToolboxTool__name__
                    elif hasattr(async_tool, '__name__'):
                        tool_name = async_tool.__name__
                
                if tool_name:
                    wrapped_tool = FixedToolboxSyncTool(tool, tool_name)
                    fixed_tools[tool_name] = wrapped_tool
                    logger.info(f"Wrapped tool: {tool_name}")
                else:
                    # If we can't get the name, use an index-based name
                    tool_name = f"tool_{i}"
                    wrapped_tool = FixedToolboxSyncTool(tool, tool_name)
                    fixed_tools[tool_name] = wrapped_tool
                    logger.warning(f"Could not determine tool name, using: {tool_name}")
            
            logger.info(f"Successfully wrapped {len(fixed_tools)} tools: {list(fixed_tools.keys())}")
            return fixed_tools
            
        except Exception as e:
            logger.error(f"Failed to load toolset '{name}': {e}")
            raise
    
    def close(self):
        """Close the underlying client"""
        if hasattr(self._client, 'close'):
            self._client.close()


class DirectAPIClient:
    """
    A direct API client that bypasses toolbox_core issues by calling the MCP server directly.
    This is a fallback solution that provides the same interface but with direct HTTP calls.
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self._session = None
        self._tools_cache = {}
        
    async def _get_session(self):
        """Get or create an aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
        
    async def _close_session(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _fetch_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from the server"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/tools") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to fetch tools: {response.status}")
        except Exception as e:
            logger.error(f"Error fetching tools: {e}")
            raise
    
    async def _call_tool_async(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Call a tool asynchronously"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/tool/{tool_name}/invoke"
            
            async with session.post(url, json=parameters) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Tool call failed: {response.status} - {error_text}")
                    
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise
    
    def call_tool_sync(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Call a tool synchronously and return JSON string"""
        import requests
        
        try:
            # Use requests for synchronous HTTP calls instead of asyncio
            url = f"{self.base_url}/api/tool/{tool_name}/invoke"
            
            # Dynamic timeout based on expected result size
            limit = parameters.get('limit', 250)
            # Estimate: ~10ms per row + 5s base overhead
            timeout = min(120, max(30, 5 + (limit * 0.01)))
            
            response = requests.post(url, json=parameters, timeout=timeout)
            
            if response.status_code == 200:
                result = response.json()
                # Return the result as JSON string for compatibility
                return json.dumps(result)
            else:
                error_text = response.text
                raise Exception(f"Tool call failed: {response.status_code} - {error_text}")
                
        except Exception as e:
            logger.error(f"Sync tool call failed for {tool_name}: {e}")
            raise
    
    def load_toolset(self, name: str = None) -> Dict[str, 'DirectAPITool']:
        """Load tools and return a dictionary of tool objects"""
        import requests
        
        try:
            # Use requests for synchronous HTTP call
            response = requests.get(f"{self.base_url}/tools", timeout=10)
            
            if response.status_code == 200:
                tools_data = response.json()
            else:
                raise Exception(f"Failed to fetch tools: {response.status_code}")
            
            # Create tool objects
            tools = {}
            for tool_info in tools_data:
                tool_name = tool_info['name']
                tool = DirectAPITool(self, tool_name, tool_info)
                tools[tool_name] = tool
            
            logger.info(f"Loaded {len(tools)} tools via direct API: {list(tools.keys())}")
            return tools
                
        except Exception as e:
            logger.error(f"Failed to load toolset via direct API: {e}")
            raise
    
    def close(self):
        """Close the client"""
        # Session will be closed when tools are called
        pass


class DirectAPITool:
    """A tool object that calls the MCP server directly"""
    
    def __init__(self, client: DirectAPIClient, name: str, tool_info: Dict[str, Any]):
        self.client = client
        self.name = name
        self._tool_info = tool_info
        
    def __call__(self, **kwargs) -> str:
        """Call the tool with given parameters"""
        return self.client.call_tool_sync(self.name, kwargs)


# Factory function to create the best available client
def create_toolbox_client(base_url: str, prefer_direct: bool = False) -> object:
    """
    Create the best available toolbox client.
    
    Args:
        base_url: The MCP toolbox server URL
        prefer_direct: If True, use DirectAPIClient instead of trying toolbox_core first
    
    Returns:
        Either FixedToolboxSyncClient or DirectAPIClient
    """
    if prefer_direct:
        logger.info("Using DirectAPIClient as requested")
        return DirectAPIClient(base_url)
    
    try:
        # Try to use the fixed toolbox_core client first
        client = FixedToolboxSyncClient(base_url)
        logger.info("Using FixedToolboxSyncClient (toolbox_core based)")
        return client
        
    except Exception as e:
        logger.warning(f"Failed to create FixedToolboxSyncClient: {e}")
        logger.info("Falling back to DirectAPIClient")
        return DirectAPIClient(base_url)
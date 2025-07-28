import uuid
import time
import logging
import concurrent.futures
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from .config import Config, get_store_mappings, get_shop_mappings, get_available_models
from .api_clients import APIClient 
from .bigquery_utils import BigQueryUtils
from .query_patterns import extract_intent, get_enhanced_schema_prompt
from .sql_generator import generate_sql_or_tool
from .executor import execute_query, format_results
from .visualizer import create_visualization
from .summarizer import generate_summary

# MCP Toolbox Integration
try:
    from toolbox_core import ToolboxSyncClient
    TOOLBOX_AVAILABLE = True
except ImportError:
    TOOLBOX_AVAILABLE = False
    logging.warning("MCP Toolbox not available. Falling back to direct BigQuery queries.")

logger = logging.getLogger(__name__)

class SuperGeminiRetailChatbot:
    def __init__(self, config):
        self.config = config
        self.store_mappings = get_store_mappings()
        self.shop_mappings = get_shop_mappings()
        self.available_models = get_available_models()
        self.api_clients = APIClient()
        self.bigquery_utils = BigQueryUtils(config)
        self.last_df = None
        self.last_query = None
        self.last_sql = None
        self.current_query_id = None
        
        # Add these attributes for app.py compatibility
        self.last_results = None  # Raw results data as list of dicts
        self.last_data = None     # Alias for last_results for chart generation
        
        # Cost tracking
        self.total_cost = 0.0
        self.query_costs = {}
        
        # MCP Toolbox initialization
        self.toolbox = None
        self.tools = {}
        self.toolbox_enabled = False
        
        if TOOLBOX_AVAILABLE:
            self._initialize_toolbox()

    def _initialize_toolbox(self):
        """Initialize MCP Toolbox client and load retail analytics tools"""
        try:
            # Your deployed Toolbox URL
            toolbox_url = "https://toolbox-41815171183.us-central1.run.app"
            
            # Initialize the toolbox client
            self.toolbox = ToolboxSyncClient(toolbox_url)
            
            # Load the toolset defined in tools.yaml
            self.tools = self.toolbox.load_toolset('retail_analytics')
            self.toolbox_enabled = True
            
            logger.info(f"MCP Toolbox initialized with {len(self.tools)} tools")
            logger.info(f"Available tools: {list(self.tools.keys())}")
            
        except Exception as e:
            logger.warning(f"Failed to initialize MCP Toolbox: {e}")
            logger.info("Falling back to direct BigQuery queries")
            self.toolbox_enabled = False

    def parallel_model_call(self, models: List[Dict], prompt: str) -> Tuple[List[Any], float]:
        """
        Execute parallel calls to multiple AI models for efficiency and comparison.
        
        Args:
            models: List of model dictionaries with 'provider' and 'name' keys
            prompt: The prompt to send to all models
            
        Returns:
            Tuple of (results_list, total_cost)
        """
        def call_single_model(model_info):
            try:
                start_time = time.time()
                provider = model_info['provider']
                model_name = model_info['name']
                
                # Call appropriate API client based on provider
                if provider == 'google' or model_name.startswith('gemini'):
                    result = self.api_clients.google_client.generate_content(prompt)
                elif provider == 'xai' or model_name.startswith('grok'):
                    result = self.api_clients.xai_client.generate_content(prompt)
                elif provider == 'anthropic' or model_name.startswith('claude'):
                    result = self.api_clients.anthropic_client.generate_content(prompt)
                elif provider == 'openai' or model_name.startswith(('gpt', 'o1')):
                    result = self.api_clients.openai_client.generate_content(prompt)
                else:
                    raise ValueError(f"Unsupported provider/model: {provider}/{model_name}")
                
                execution_time = time.time() - start_time
                
                # Estimate cost based on model and token usage (simplified)
                estimated_cost = self._estimate_model_cost(model_name, prompt, result, execution_time)
                
                return {
                    'model': model_name,
                    'provider': provider,
                    'result': result,
                    'cost': estimated_cost,
                    'execution_time': execution_time,
                    'success': True
                }
            except Exception as e:
                logger.error(f"Model {model_info.get('name', 'unknown')} failed: {str(e)}")
                return {
                    'model': model_info.get('name', 'unknown'),
                    'provider': model_info.get('provider', 'unknown'),
                    'result': None,
                    'cost': 0.0,
                    'execution_time': 0.0,
                    'success': False,
                    'error': str(e)
                }

        # Execute parallel calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(models), 5)) as executor:
            futures = [executor.submit(call_single_model, model) for model in models]
            results = []
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=30)  # 30 second timeout per model
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    logger.error("Model call timed out")
                    results.append({
                        'model': 'unknown',
                        'provider': 'unknown',
                        'result': None,
                        'cost': 0.0,
                        'execution_time': 30.0,
                        'success': False,
                        'error': 'Timeout'
                    })
                except Exception as e:
                    logger.error(f"Future execution failed: {str(e)}")
                    results.append({
                        'model': 'unknown',
                        'provider': 'unknown',
                        'result': None,
                        'cost': 0.0,
                        'execution_time': 0.0,
                        'success': False,
                        'error': str(e)
                    })

        # Calculate total cost and update tracking
        total_cost = sum(r.get('cost', 0) for r in results)
        self.total_cost += total_cost
        
        # Log parallel execution metrics
        successful_calls = [r for r in results if r['success']]
        logger.info(f"Parallel execution: {len(successful_calls)}/{len(models)} models succeeded, total cost: ${total_cost:.4f}")
        
        return results, total_cost

    def _estimate_model_cost(self, model_name: str, prompt: str, result: Any, execution_time: float) -> float:
        """
        Estimate the cost of a model call based on token usage and model pricing.
        This is a simplified estimation - integrate with actual API billing when available.
        """
        # Rough token estimation (characters / 4)
        input_tokens = len(str(prompt)) // 4
        output_tokens = len(str(result)) // 4 if result else 0
        
        # Simplified pricing per 1k tokens (update with actual API pricing)
        pricing = {
            'gemini-1.5-pro': {'input': 0.00125, 'output': 0.005},
            'gemini-1.5-flash': {'input': 0.00075, 'output': 0.003},
            'gpt-4': {'input': 0.03, 'output': 0.06},
            'gpt-3.5-turbo': {'input': 0.0015, 'output': 0.002},
            'claude-3-opus': {'input': 0.015, 'output': 0.075},
            'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
            'grok-beta': {'input': 0.002, 'output': 0.01}  # Estimated
        }
        
        # Find matching pricing
        model_pricing = None
        for price_key in pricing:
            if price_key in model_name.lower():
                model_pricing = pricing[price_key]
                break
        
        if not model_pricing:
            # Default pricing for unknown models
            model_pricing = {'input': 0.001, 'output': 0.002}
        
        cost = (input_tokens / 1000 * model_pricing['input']) + (output_tokens / 1000 * model_pricing['output'])
        return cost

    def _execute_toolbox_query(self, query: str, intent: dict) -> Dict[str, Any]:
        """
        Execute query using MCP Toolbox instead of direct SQL generation
        
        Args:
            query: The user's natural language query
            intent: Extracted intent from query_patterns
            
        Returns:
            Dictionary with execution results
        """
        try:
            # Map intent to appropriate toolbox tool
            tool_name, params = self._map_intent_to_tool(intent, query)
            
            if not tool_name or tool_name not in self.tools:
                logger.warning(f"No matching tool found for intent: {intent}")
                return {'success': False, 'error': 'No matching tool available', 'fallback_needed': True}
            
            logger.info(f"Executing tool: {tool_name} with params: {params}")
            
            # Execute the tool
            tool = self.tools[tool_name]
            start_time = time.time()
            
            result = tool(**params)
            execution_time = int((time.time() - start_time) * 1000)
            
            # Convert result to DataFrame if it's not already
            if isinstance(result, dict) and 'data' in result:
                df = pd.DataFrame(result['data'])
            elif isinstance(result, list):
                df = pd.DataFrame(result)
            elif isinstance(result, pd.DataFrame):
                df = result
            else:
                logger.error(f"Unexpected result type from tool {tool_name}: {type(result)}")
                return {'success': False, 'error': 'Invalid tool response format', 'fallback_needed': True}
            
            return {
                'success': True,
                'dataframe': df,
                'tool_name': tool_name,
                'execution_time_ms': execution_time,
                'parameters': params,
                'fallback_needed': False
            }
            
        except Exception as e:
            logger.error(f"Toolbox execution failed: {str(e)}")
            return {'success': False, 'error': str(e), 'fallback_needed': True}

    def _map_intent_to_tool(self, intent: dict, query: str) -> Tuple[str, dict]:
        """
        Map extracted intent to appropriate MCP Toolbox tool and parameters
        
        Args:
            intent: Intent dictionary from extract_intent()
            query: Original user query for parameter extraction
            
        Returns:
            Tuple of (tool_name, parameters)
        """
        # Default parameters
        params = {
            'limit': intent.get('limit', 10),
            'conditions': '',
            'time_period': intent.get('time_period'),
        }
        
        # Extract additional parameters from query
        params.update(self._extract_query_parameters(query, intent))
        
        # Map based on intent characteristics
        if intent.get('inventory_focus'):
            if 'out_of_stock' in intent.get('metrics', []):
                return 'get_out_of_stock_items', params
            elif 'overstock' in intent.get('metrics', []):
                return 'get_overstock_items', params
            else:
                return 'get_inventory_status', params
                
        elif intent.get('return_focus'):
            if intent.get('time_series'):
                return 'get_return_trends', params
            elif 'store' in intent.get('dimensions', []):
                return 'get_return_analysis_by_store', params
            else:
                return 'get_return_analysis', params
                
        elif intent.get('ranking') == 'top':
            if 'sales' in intent.get('metrics', []):
                return 'get_top_selling_items', params
            elif 'margin' in intent.get('metrics', []):
                return 'get_top_margin_items', params
                
        elif intent.get('comparison'):
            return 'get_comparison_analysis', params
            
        elif intent.get('time_series'):
            return 'get_sales_trends', params
            
        # Default fallback
        if any(metric in intent.get('metrics', []) for metric in ['sales', 'revenue']):
            return 'get_sales_analysis', params
            
        return None, params

    def _extract_query_parameters(self, query: str, intent: dict) -> dict:
        """
        Extract specific parameters from the user query
        
        Args:
            query: Original user query
            intent: Extracted intent
            
        Returns:
            Dictionary of extracted parameters
        """
        params = {}
        query_lower = query.lower()
        
        # Extract store filters
        if 'fargo' in query_lower:
            params['store_filter'] = 'store_id = 64'
        elif 'springfield' in query_lower:
            params['store_filter'] = 'store_id = 65'
        
        # Extract shop/division filters
        for shop_name, (div_num, desc) in self.shop_mappings.items():
            if shop_name in query_lower:
                params['shop_filter'] = f'division_number = "{div_num}"'
                break
        
        # Extract date ranges
        if 'last 30 days' in query_lower:
            params['date_filter'] = 'transaction_datetime >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)'
        elif 'last week' in query_lower:
            params['date_filter'] = 'transaction_datetime >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)'
        elif 'this month' in query_lower:
            params['date_filter'] = 'EXTRACT(MONTH FROM transaction_datetime) = EXTRACT(MONTH FROM CURRENT_TIMESTAMP())'
        
        # Extract specific style or SKU
        import re
        style_match = re.search(r'style\s+(\w+)', query_lower)
        if style_match:
            params['style_filter'] = f'style = "{style_match.group(1)}"'
        
        # Combine conditions
        conditions = []
        for key in ['store_filter', 'shop_filter', 'date_filter', 'style_filter']:
            if key in params:
                conditions.append(params[key])
        
        if conditions:
            params['conditions'] = ' AND '.join(conditions)
        
        return params

    def advanced_query(self, query: str, enable_web_search: bool = False, enable_code_execution: bool = False) -> Dict[str, Any]:
        """
        Handle advanced queries with web search and code execution capabilities.
        Now enhanced with MCP Toolbox integration.
        
        Args:
            query: The user query
            enable_web_search: Whether to enable web search for external data
            enable_code_execution: Whether to enable code execution for analysis
            
        Returns:
            Dictionary with query results and metadata
        """
        try:
            query_lower = query.lower()
            advanced_results = {}
            
            # Try MCP Toolbox first if available
            if self.toolbox_enabled:
                intent = extract_intent(query)
                toolbox_result = self._execute_toolbox_query(query, intent)
                
                if toolbox_result['success']:
                    # Process successful toolbox result
                    df = toolbox_result['dataframe']
                    self.last_df = df
                    self.last_query = query
                    
                    if df is not None and not df.empty:
                        self.last_results = df.to_dict('records')
                        self.last_data = self.last_results
                    
                    results = format_results(df, self.config.preview_rows)
                    
                    return {
                        'success': True,
                        'error': None,
                        'sql': f"[MCP Toolbox Tool: {toolbox_result['tool_name']}]",
                        'results': results,
                        'row_count': len(df) if df is not None else 0,
                        'has_data': df is not None and not df.empty,
                        'execution_times': {'toolbox_execution_ms': toolbox_result['execution_time_ms']},
                        'toolbox_used': True,
                        'tool_name': toolbox_result['tool_name'],
                        'parameters': toolbox_result['parameters']
                    }
                elif not toolbox_result.get('fallback_needed', False):
                    # Toolbox failed but no fallback needed
                    return {
                        'success': False,
                        'error': toolbox_result.get('error', 'Toolbox execution failed'),
                        'toolbox_attempted': True
                    }
                else:
                    logger.info("Falling back to direct BigQuery after toolbox failure")
            
            # Check if query needs web search
            if enable_web_search and any(keyword in query_lower for keyword in [
                "industry benchmarks", "market trends", "competitor analysis", 
                "external data", "current prices", "news", "recent"
            ]):
                logger.info("Query requires web search - integrating external data")
                web_results = self._simulate_web_search(query)
                advanced_results['web_search'] = web_results
                
                # Convert web results to DataFrame for analysis
                if web_results:
                    web_df = pd.DataFrame(web_results)
                    advanced_results['web_dataframe'] = web_df
            
            # Check if query needs code execution for complex analysis
            if enable_code_execution and any(keyword in query_lower for keyword in [
                "calculate", "analyze", "correlation", "regression", "statistical",
                "machine learning", "prediction", "forecast", "complex analysis"
            ]):
                logger.info("Query requires code execution - performing advanced analysis")
                
                # Get base SQL results first
                base_results = self.chat(query)
                
                if base_results['success'] and self.last_df is not None:
                    # Perform advanced analysis via code execution
                    analysis_results = self._execute_pandas_analysis(self.last_df, query)
                    advanced_results['code_execution'] = analysis_results
                    
                    # Integrate analysis results with base results
                    base_results['advanced_analysis'] = analysis_results
                    return base_results
            
            # Standard query processing with potential enhancements
            base_results = self.chat(query)
            
            # Add advanced results if any were generated
            if advanced_results:
                base_results['advanced_features'] = advanced_results
            
            return base_results
            
        except Exception as e:
            logger.error(f"Advanced query processing failed: {str(e)}")
            return {
                'success': False,
                'error': f"Advanced query processing failed: {str(e)}",
                'fallback_available': True
            }

    def _simulate_web_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Simulate web search functionality. 
        In production, integrate with actual web search APIs (Google Custom Search, Bing, etc.)
        """
        # This is a placeholder - integrate with actual web search tool calls
        logger.info(f"Simulating web search for: {query}")
        
        # Mock data for demonstration
        mock_results = [
            {
                'title': 'Retail Industry Benchmarks 2025',
                'source': 'RetailInsights.com',
                'data': {
                    'average_conversion_rate': 2.86,
                    'average_aov': 128.50,
                    'customer_acquisition_cost': 45.20
                }
            },
            {
                'title': 'Market Trends Analysis',
                'source': 'MarketResearch.org',
                'data': {
                    'growth_rate': 5.2,
                    'seasonal_impact': 0.15,
                    'digital_transformation_score': 7.8
                }
            }
        ]
        
        return mock_results

    def _execute_pandas_analysis(self, df: pd.DataFrame, query: str) -> Dict[str, Any]:
        """
        Execute advanced Pandas analysis on the DataFrame.
        In production, integrate with actual code execution tools.
        """
        try:
            analysis_results = {}
            
            # Basic statistical analysis
            analysis_results['descriptive_stats'] = df.describe().to_dict()
            
            # Correlation analysis if multiple numeric columns
            numeric_cols = df.select_dtypes(include=[int, float]).columns
            if len(numeric_cols) > 1:
                correlation_matrix = df[numeric_cols].corr().to_dict()
                analysis_results['correlation_matrix'] = correlation_matrix
            
            # Detect trends if there's a date column
            date_cols = df.select_dtypes(include=['datetime64']).columns
            if len(date_cols) > 0 and len(numeric_cols) > 0:
                # Simple trend analysis
                df_sorted = df.sort_values(date_cols[0])
                for col in numeric_cols:
                    if col in df_sorted.columns:
                        trend = 'increasing' if df_sorted[col].iloc[-1] > df_sorted[col].iloc[0] else 'decreasing'
                        analysis_results[f'{col}_trend'] = trend
            
            # Query-specific analysis based on keywords
            query_lower = query.lower()
            if 'forecast' in query_lower or 'predict' in query_lower:
                analysis_results['forecast_note'] = 'Advanced forecasting requires time series models - integrate with ML libraries'
            
            if 'anomaly' in query_lower or 'outlier' in query_lower:
                # Simple outlier detection using IQR
                for col in numeric_cols:
                    Q1 = df[col].quantile(0.25)
                    Q3 = df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    outliers = df[(df[col] < (Q1 - 1.5 * IQR)) | (df[col] > (Q3 + 1.5 * IQR))]
                    analysis_results[f'{col}_outliers'] = len(outliers)
            
            return analysis_results
            
        except Exception as e:
            logger.error(f"Pandas analysis failed: {str(e)}")
            return {'error': str(e)}

    def chat(self, user_query, model_name=None, user_id=None, session_id=None, use_parallel=False, models_list=None):
        """
        Enhanced chat method with MCP Toolbox integration and optional parallel model execution.
        
        Args:
            user_query: The user's query
            model_name: Single model to use (if not using parallel)
            user_id: User identifier
            session_id: Session identifier
            use_parallel: Whether to use parallel model calls
            models_list: List of models for parallel execution
        """
        model_name = model_name or self.config.model_name
        query_id = str(uuid.uuid4())
        self.current_query_id = query_id
        total_start_time = time.time()
        execution_times = {}
        query_cost = 0.0

        # First try MCP Toolbox if available and appropriate
        if self.toolbox_enabled:
            intent = extract_intent(user_query)
            toolbox_result = self._execute_toolbox_query(user_query, intent)
            
            if toolbox_result['success']:
                # Process successful toolbox result
                df = toolbox_result['dataframe']
                self.last_df = df.copy() if df is not None else None
                self.last_query = user_query
                self.last_sql = f"[MCP Toolbox Tool: {toolbox_result['tool_name']}]"
                
                # Store results in multiple formats for compatibility
                if df is not None and not df.empty:
                    self.last_results = df.to_dict('records')
                    self.last_data = self.last_results
                else:
                    self.last_results = None
                    self.last_data = None
                
                execution_times['toolbox_execution_ms'] = toolbox_result['execution_time_ms']
                execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)
                
                # Log to BigQuery with toolbox metadata
                self.bigquery_utils.log_query_to_bigquery(
                    query_id=query_id,
                    user_query=user_query,
                    sql_query=self.last_sql,
                    model_name=f"toolbox_{toolbox_result['tool_name']}",
                    success=True,
                    error_message=None,
                    row_count=len(df) if df is not None else None,
                    execution_times=execution_times,
                    user_id=user_id or "anonymous",
                    session_id=session_id or "default"
                )
                
                results = format_results(df, self.config.preview_rows)
                return {
                    'success': True,
                    'error': None,
                    'sql': self.last_sql,
                    'results': results,
                    'row_count': len(df) if df is not None else 0,
                    'has_data': df is not None and not df.empty,
                    'query_id': query_id,
                    'execution_times': execution_times,
                    'estimated_cost': query_cost,
                    'total_session_cost': self.total_cost,
                    'toolbox_used': True,
                    'tool_name': toolbox_result['tool_name'],
                    'parameters': toolbox_result['parameters']
                }
            elif not toolbox_result.get('fallback_needed', False):
                # Toolbox failed but shouldn't fallback
                return {
                    'success': False,
                    'error': toolbox_result.get('error', 'Toolbox execution failed'),
                    'sql': None,
                    'results': None,
                    'chart': None,
                    'summary': None,
                    'query_id': query_id,
                    'execution_times': execution_times,
                    'estimated_cost': query_cost,
                    'toolbox_attempted': True
                }
            else:
                logger.info("Toolbox execution failed, falling back to SQL generation")

        # Fallback to SQL Generation with optional parallel processing
        if use_parallel and models_list:
            # Use parallel model calls for SQL generation
            parallel_results, parallel_cost = self.parallel_model_call(models_list, user_query)
            query_cost += parallel_cost
            
            # Select best SQL result (simplified - take first successful one)
            successful_results = [r for r in parallel_results if r['success']]
            if successful_results:
                sql_query = successful_results[0]['result']
                sql_gen_time = successful_results[0]['execution_time'] * 1000  # Convert to ms
                # Log all model performances
                execution_times['parallel_models'] = {
                    'total_models': len(models_list),
                    'successful_models': len(successful_results),
                    'model_results': parallel_results
                }
            else:
                # Fallback to single model
                sql_query, sql_gen_time = generate_sql_or_tool(user_query, model_name, self.api_clients, self.config)
        else:
            # Standard single model SQL generation
            sql_query, sql_gen_time = generate_sql_or_tool(user_query, model_name, self.api_clients, self.config)
        
        execution_times['sql_generation_ms'] = sql_gen_time
        self.last_sql = sql_query

        # Execute query
        df, error, query_exec_time = execute_query(sql_query, self.bigquery_utils.bq_client)
        execution_times['query_execution_ms'] = query_exec_time
        execution_times['total_ms'] = int((time.time() - total_start_time) * 1000)

        # Store cost information
        self.query_costs[query_id] = query_cost
        execution_times['estimated_cost'] = query_cost

        # Log to BigQuery with enhanced metadata
        self.bigquery_utils.log_query_to_bigquery(
            query_id=query_id,
            user_query=user_query,
            sql_query=sql_query,
            model_name=model_name,
            success=(error is None),
            error_message=error,
            row_count=len(df) if df is not None else None,
            execution_times=execution_times,
            user_id=user_id or "anonymous",
            session_id=session_id or "default"
        )

        if error:
            # Clear last results on error
            self.last_results = None
            self.last_data = None
            return {
                'success': False,
                'error': error,
                'sql': sql_query,
                'results': None,
                'chart': None,
                'summary': None,
                'query_id': query_id,
                'execution_times': execution_times,
                'estimated_cost': query_cost,
                'toolbox_fallback_used': self.toolbox_enabled
            }

        # Store results in multiple formats for compatibility
        self.last_df = df.copy() if df is not None else None
        self.last_query = user_query
        
        # Convert DataFrame to list of dictionaries for app.py compatibility
        if df is not None and not df.empty:
            self.last_results = df.to_dict('records')  # List of dicts
            self.last_data = self.last_results  # Alias for chart generation
        else:
            self.last_results = None
            self.last_data = None
        
        results = format_results(df, self.config.preview_rows)
        return {
            'success': True,
            'error': None,
            'sql': sql_query,
            'results': results,
            'row_count': len(df) if df is not None else 0,
            'has_data': df is not None and not df.empty,
            'query_id': query_id,
            'execution_times': execution_times,
            'estimated_cost': query_cost,
            'total_session_cost': self.total_cost,
            'toolbox_fallback_used': self.toolbox_enabled
        }

    def generate_chart(self, chart_type: str = None):
        if not self.last_df:  
            logger.error("No dataframe available for charting")
            return {'success': False, 'error': 'No data available to chart'}
            
        try:
            chart = create_visualization(self.last_df, self.last_query, chart_type)
            if chart:
                self.bigquery_utils.update_query_log(self.current_query_id, {'has_visualization': True})
                return {
                    'success': True,
                    'chart': chart
                }
            else:
                return {
                    'success': False,
                    'error': 'Unable to create chart from the data'
                }
        except Exception as e:
            logger.error(f"Chart generation failed: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'error': str(e)
            }

    def generate_llm_summary(self, model_name: str = None, use_parallel: bool = False):
        """
        Enhanced summary generation with optional parallel model execution.
        """
        if self.last_df is None or self.last_df.empty:
            return {'success': False, 'error': 'No data available to summarize'}
            
        try:
            if use_parallel:
                # Use multiple models for summary generation and comparison
                summary_models = [
                    {'provider': 'google', 'name': 'gemini-1.5-pro'},
                    {'provider': 'anthropic', 'name': 'claude-3-sonnet'},
                    {'provider': 'openai', 'name': 'gpt-4'}
                ]
                
                summary_prompt = f"Summarize the following data analysis results for query: {self.last_query}\n\nData: {self.last_df.head(10).to_string()}"
                parallel_results, cost = self.parallel_model_call(summary_models, summary_prompt)
                
                # Combine summaries or select best one
                successful_summaries = [r['result'] for r in parallel_results if r['success']]
                
                if successful_summaries:
                    summary = {
                        'primary_summary': successful_summaries[0],
                        'alternative_summaries': successful_summaries[1:] if len(successful_summaries) > 1 else [],
                        'parallel_cost': cost,
                        'models_used': [r['model'] for r in parallel_results if r['success']]
                    }
                else:
                    # Fallback to standard summary
                    summary = generate_summary(
                        self.last_df, 
                        self.last_query, 
                        model_name or self.config.model_name, 
                        self.available_models, 
                        self.api_clients, 
                        self.bigquery_utils
                    )
            else:
                # Standard summary generation
                summary = generate_summary(
                    self.last_df, 
                    self.last_query, 
                    model_name or self.config.model_name, 
                    self.available_models, 
                    self.api_clients, 
                    self.bigquery_utils
                )
            
            # Update query log to indicate summary was generated
            if self.current_query_id:
                self.bigquery_utils.update_query_log(self.current_query_id, {
                    'has_summary': True,
                    'summary_parallel': use_parallel
                })
            
            return {
                'success': True,
                'summary': summary
            }
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_ai_response(self, prompt: str, model_name: str):
        """
        Helper method to get AI response for any prompt.
        This method can be used by app.py for custom summaries.
        """
        try:
            # Track cost for this call
            start_time = time.time()
            
            # Use your existing API clients to get response
            if model_name.startswith('gemini'):
                result = self.api_clients.google_client.generate_content(prompt)
            elif model_name.startswith('grok'):
                result = self.api_clients.xai_client.generate_content(prompt)
            elif model_name.startswith('claude'):
                result = self.api_clients.anthropic_client.generate_content(prompt)
            elif model_name.startswith('gpt') or model_name.startswith('o1'):
                result = self.api_clients.openai_client.generate_content(prompt)
            else:
                raise ValueError(f"Unsupported model: {model_name}")
            
            # Track cost
            execution_time = time.time() - start_time
            cost = self._estimate_model_cost(model_name, prompt, result, execution_time)
            self.total_cost += cost
            
            return result
        except Exception as e:
            logger.error(f"AI response generation failed for model {model_name}: {e}")
            raise

    def get_cost_summary(self) -> Dict[str, Any]:
        """
        Get a summary of costs incurred during the session.
        """
        return {
            'total_session_cost': self.total_cost,
            'queries_executed': len(self.query_costs),
            'query_costs': self.query_costs,
            'average_cost_per_query': self.total_cost / len(self.query_costs) if self.query_costs else 0,
            'toolbox_enabled': self.toolbox_enabled
        }

    def reset_cost_tracking(self):
        """
        Reset cost tracking for a new session.
        """
        self.total_cost = 0.0
        self.query_costs = {}
        logger.info("Cost tracking reset for new session")

    def get_toolbox_status(self) -> Dict[str, Any]:
        """
        Get status information about MCP Toolbox integration
        """
        return {
            'toolbox_available': TOOLBOX_AVAILABLE,
            'toolbox_enabled': self.toolbox_enabled,
            'tools_loaded': len(self.tools) if self.tools else 0,
            'available_tools': list(self.tools.keys()) if self.tools else []
        }
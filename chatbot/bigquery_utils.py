from google.cloud import bigquery
from google.cloud import billing_v1
import logging
import pandas as pd
from datetime import datetime
import json
import uuid
import os
from .config import get_available_models
from .query_patterns import extract_intent

logger = logging.getLogger(__name__)

class BigQueryUtils:
    def __init__(self, config):
        self.bq_client = bigquery.Client(project=config.bq_project)
        logger.info(f"Source data client initialized for project: {config.bq_project}")
        
        analytics_project = os.getenv('ANALYTICS_PROJECT', config.bq_project)
        if analytics_project != config.bq_project:
            try:
                self.bq_analytics_client = bigquery.Client(project=analytics_project)
                logger.info(f"Analytics storage client initialized for project: {analytics_project}")
            except Exception as e:
                logger.warning(f"Failed to create analytics client for project {analytics_project}: {e}")
                logger.info("Falling back to source data project for analytics storage")
                self.bq_analytics_client = self.bq_client
        else:
            self.bq_analytics_client = self.bq_client
            logger.info("Using same client for source data and analytics storage")
        
        # Initialize billing client for cost monitoring
        try:
            self.billing_client = billing_v1.CloudBillingClient()
            logger.info("Billing client initialized for cost monitoring")
        except Exception as e:
            logger.warning(f"Failed to initialize billing client: {e}")
            self.billing_client = None
        
        self.analytics_storage_enabled = True
        self.store_id_by_city = {}
        self.store_id_by_name = {}
        self._load_store_mappings()
        
        analytics_project = os.getenv('ANALYTICS_PROJECT', config.bq_project)
        self.analytics_dataset_id = os.getenv('ANALYTICS_DATASET_ID', 'llm_analytics')
        self.query_log_table_id = os.getenv('QUERY_LOG_TABLE_ID', 'query_logs')
        self.query_log_table_full_id = f"{analytics_project}.{self.analytics_dataset_id}.{self.query_log_table_id}"
        
        self.summary_project = os.getenv('SUMMARY_PROJECT', analytics_project)
        self.summary_dataset_id = os.getenv('SUMMARY_DATASET_ID', 'Sales_AI_agent')
        self.summary_table_id = os.getenv('SUMMARY_TABLE_ID', 'LLM_summaries')
        self.summary_table_full_id = f"{self.summary_project}.{self.summary_dataset_id}.{self.summary_table_id}"
        
        self.analytics_query_summaries_table_id = f"{analytics_project}.{self.analytics_dataset_id}.query_summaries"

    def _load_store_mappings(self):
        try:
            query = """
            SELECT DISTINCT
                dim_store_id,
                name,
                city,
                state
            FROM `sis-data-marts.warehouse.dim_stores`
            """
            df = self.bq_client.query(query).to_dataframe()
            
            for _, row in df.iterrows():
                city_lower = row['city'].lower() if pd.notna(row['city']) else ''
                name_lower = row['name'].lower() if pd.notna(row['name']) else ''
                store_id = int(row['dim_store_id'])
                
                if city_lower:
                    if city_lower not in self.store_id_by_city:
                        self.store_id_by_city[city_lower] = []
                    self.store_id_by_city[city_lower].append(store_id)
                
                if name_lower:
                    self.store_id_by_name[name_lower] = store_id
                    
            logger.info(f"Loaded {len(df)} store mappings")
            logger.info(f"Cities mapped: {list(self.store_id_by_city.keys())[:5]}...")
            
        except Exception as e:
            logger.error(f"Failed to load store mappings: {e}")
            self.store_id_by_city = {}
            self.store_id_by_name = {}

    def execute_query_with_params(self, query: str, params: dict = None, use_cache: bool = True, 
                                 dry_run: bool = False, max_bytes_billed: int = None):
        """
        Execute a BigQuery query with parameterization, caching, and cost controls.
        Note: This method is now primarily used for direct BigQuery access when MCP Toolbox is not suitable.
        
        Args:
            query: SQL query string with optional parameters (@param_name format)
            params: Dictionary of parameter values
            use_cache: Whether to use BigQuery result caching
            dry_run: If True, validate query without executing
            max_bytes_billed: Maximum bytes billed limit
            
        Returns:
            Query results as DataFrame or dry run statistics
        """
        try:
            # Configure query job with caching and parameters
            job_config = bigquery.QueryJobConfig()
            job_config.use_query_cache = use_cache
            job_config.dry_run = dry_run
            
            if max_bytes_billed:
                job_config.maximum_bytes_billed = max_bytes_billed
                
            # Add query parameters if provided
            if params:
                query_parameters = []
                for param_name, param_value in params.items():
                    # Automatically detect parameter type
                    if isinstance(param_value, str):
                        param_type = "STRING"
                    elif isinstance(param_value, int):
                        param_type = "INT64"
                    elif isinstance(param_value, float):
                        param_type = "FLOAT64"
                    elif isinstance(param_value, bool):
                        param_type = "BOOL"
                    elif isinstance(param_value, datetime):
                        param_type = "TIMESTAMP"
                    else:
                        param_type = "STRING"  # Default fallback
                        param_value = str(param_value)
                    
                    query_parameters.append(
                        bigquery.ScalarQueryParameter(param_name, param_type, param_value)
                    )
                
                job_config.query_parameters = query_parameters
                logger.info(f"Query configured with {len(query_parameters)} parameters")
            
            # Execute query
            query_job = self.bq_client.query(query, job_config=job_config)
            
            if dry_run:
                logger.info(f"Dry run - Query would process {query_job.total_bytes_processed} bytes")
                return {
                    'total_bytes_processed': query_job.total_bytes_processed,
                    'estimated_cost_usd': self._estimate_query_cost(query_job.total_bytes_processed),
                    'cache_hit': query_job.cache_hit if hasattr(query_job, 'cache_hit') else False
                }
            
            # Wait for query completion and get results
            results = query_job.result()
            df = results.to_dataframe()
            
            # Log performance metrics
            logger.info(f"Direct BigQuery execution - Rows: {len(df)}, "
                       f"Bytes processed: {query_job.total_bytes_processed}, "
                       f"Cache hit: {query_job.cache_hit}, "
                       f"Slot time: {query_job.slot_millis}ms")
            
            return df
            
        except Exception as e:
            logger.error(f"Error executing parameterized query: {e}")
            raise

    def _estimate_query_cost(self, bytes_processed: int) -> float:
        """
        Estimate query cost based on bytes processed.
        BigQuery pricing is approximately $5 per TB (as of 2024).
        """
        if not bytes_processed:
            return 0.0
        
        # Convert bytes to TB and calculate cost
        tb_processed = bytes_processed / (1024 ** 4)  # Convert to TB
        estimated_cost = tb_processed * 5.0  # $5 per TB
        return round(estimated_cost, 6)

    def monitor_query_cost(self, query_id: str, project_id: str, query_job: bigquery.QueryJob = None) -> dict:
        """
        Monitor query cost using BigQuery job statistics and billing API.
        Enhanced to handle MCP Toolbox execution context.
        
        Args:
            query_id: Unique identifier for the query
            project_id: GCP project ID
            query_job: BigQuery job object (optional, may be None for toolbox queries)
            
        Returns:
            Dictionary with cost information
        """
        cost_info = {
            'query_id': query_id,
            'project_id': project_id,
            'estimated_cost_usd': 0.0,
            'bytes_processed': 0,
            'cache_hit': False,
            'slot_millis': 0,
            'billing_available': self.billing_client is not None,
            'execution_method': 'unknown'
        }
        
        try:
            # Get cost from query job statistics if available (direct BigQuery)
            if query_job:
                cost_info['bytes_processed'] = query_job.total_bytes_processed or 0
                cost_info['cache_hit'] = query_job.cache_hit or False
                cost_info['slot_millis'] = query_job.slot_millis or 0
                cost_info['estimated_cost_usd'] = self._estimate_query_cost(cost_info['bytes_processed'])
                cost_info['execution_method'] = 'direct_bigquery'
                
                logger.info(f"Query {query_id} cost monitoring (BigQuery) - "
                           f"Bytes: {cost_info['bytes_processed']}, "
                           f"Estimated cost: ${cost_info['estimated_cost_usd']}, "
                           f"Cache hit: {cost_info['cache_hit']}")
            else:
                # For MCP Toolbox queries, cost monitoring is different
                cost_info['execution_method'] = 'mcp_toolbox'
                cost_info['estimated_cost_usd'] = 0.0  # Toolbox queries may have different cost structures
                
                logger.info(f"Query {query_id} executed via MCP Toolbox - traditional cost monitoring not applicable")
            
            # Additional billing API integration could be added here
            # This would require more complex setup with billing export and BigQuery datasets
            if self.billing_client:
                # Placeholder for more detailed billing API integration
                # In practice, you'd query billing export data or use Cloud Billing API
                # to get actual costs after processing
                pass
                
        except Exception as e:
            logger.error(f"Error monitoring query cost for {query_id}: {e}")
        
        return cost_info

    def log_query_to_bigquery(self, query_id: str, user_query: str, sql_query: str,
                             model_name: str, success: bool, error_message: str = None,
                             row_count: int = None, execution_times: dict = None,
                             user_id: str = None, session_id: str = None,
                             cost_info: dict = None, query_params: dict = None,
                             toolbox_context: dict = None):
        """
        Enhanced query logging with MCP Toolbox integration context
        
        Args:
            query_id: Unique query identifier
            user_query: Original user query
            sql_query: Generated SQL or tool identifier
            model_name: AI model used
            success: Whether execution succeeded
            error_message: Error message if failed
            row_count: Number of result rows
            execution_times: Timing information
            user_id: User identifier
            session_id: Session identifier
            cost_info: Cost monitoring information
            query_params: Query parameters
            toolbox_context: MCP Toolbox execution context
        """
        if not self.analytics_storage_enabled:
            logger.debug("Analytics storage is disabled")
            return
            
        try:
            model_info = get_available_models().get(model_name, {})
            provider = model_info.get('provider', 'unknown')
            
            from .query_patterns import extract_intent
            intent = extract_intent(user_query)
            
            # Determine execution method and enhance context
            execution_method = 'direct_bigquery'
            tool_name = None
            tool_parameters = None
            
            if toolbox_context:
                execution_method = 'mcp_toolbox'
                tool_name = toolbox_context.get('tool_name')
                tool_parameters = toolbox_context.get('parameters', {})
                
            # Handle special case where sql_query contains tool information
            elif isinstance(sql_query, dict) and sql_query.get('type') == 'toolbox_tool':
                execution_method = 'mcp_toolbox'
                tool_name = sql_query.get('tool_name')
                tool_parameters = sql_query.get('parameters', {})
                sql_query = f"[MCP Toolbox Tool: {tool_name}]"
            elif sql_query and sql_query.startswith('[MCP Toolbox Tool:'):
                execution_method = 'mcp_toolbox'
                # Extract tool name from SQL string
                import re
                match = re.search(r'\[MCP Toolbox Tool: ([^\]]+)\]', sql_query)
                if match:
                    tool_name = match.group(1)
            
            row_data = {
                "query_id": query_id,
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "sql_query": sql_query,
                "model_used": model_name,
                "model_provider": provider,
                "success": success,
                "error_message": error_message,
                "row_count": row_count,
                "execution_time_ms": execution_times.get('total_ms') if execution_times else None,
                "sql_generation_time_ms": execution_times.get('sql_generation_ms') if execution_times else None,
                "query_execution_time_ms": execution_times.get('query_execution_ms') if execution_times else None,
                "total_time_ms": execution_times.get('total_ms') if execution_times else None,
                "user_id": user_id or "anonymous",
                "session_id": session_id or "default",
                "intent_analysis": json.dumps(intent),
                "has_visualization": False,  # Will be updated if chart is generated
                "has_summary": False,  # Will be updated if summary is generated
                
                # Enhanced cost and performance tracking
                "bytes_processed": cost_info.get('bytes_processed') if cost_info else None,
                "estimated_cost_usd": cost_info.get('estimated_cost_usd') if cost_info else None,
                "cache_hit": cost_info.get('cache_hit') if cost_info else None,
                "slot_millis": cost_info.get('slot_millis') if cost_info else None,
                "query_parameters": json.dumps(query_params) if query_params else None,
                
                # MCP Toolbox integration fields
                "execution_method": execution_method,
                "toolbox_tool_name": tool_name,
                "toolbox_parameters": json.dumps(tool_parameters) if tool_parameters else None,
                "toolbox_execution_time_ms": execution_times.get('toolbox_execution_ms') if execution_times else None,
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.query_log_table_full_id,
                [row_data]
            )
            
            if errors:
                logger.error(f"Failed to log query to BigQuery: {errors}")
            else:
                logger.info(f"Query logged to BigQuery with ID: {query_id} (method: {execution_method})")
                
        except Exception as e:
            logger.error(f"Error logging query to BigQuery: {e}")

    def get_query_cost_summary(self, start_date: datetime = None, end_date: datetime = None,
                              user_id: str = None, include_toolbox: bool = True) -> pd.DataFrame:
        """
        Get a summary of query costs for analysis and optimization.
        Enhanced to include MCP Toolbox execution statistics.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            user_id: Specific user to analyze
            include_toolbox: Whether to include toolbox execution stats
        
        Returns:
            DataFrame with cost analysis including toolbox metrics
        """
        try:
            where_conditions = ["timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)"]
            
            if start_date:
                where_conditions.append(f"timestamp >= '{start_date.isoformat()}'")
            if end_date:
                where_conditions.append(f"timestamp <= '{end_date.isoformat()}'")
            if user_id:
                where_conditions.append(f"user_id = '{user_id}'")
            
            # Enhanced query to include toolbox metrics
            query = f"""
            SELECT 
                DATE(timestamp) as query_date,
                user_id,
                model_used,
                execution_method,
                toolbox_tool_name,
                COUNT(*) as query_count,
                SUM(COALESCE(bytes_processed, 0)) as total_bytes_processed,
                SUM(COALESCE(estimated_cost_usd, 0)) as total_estimated_cost,
                AVG(COALESCE(estimated_cost_usd, 0)) as avg_cost_per_query,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                ROUND(SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as cache_hit_rate,
                AVG(COALESCE(total_time_ms, 0)) as avg_execution_time_ms,
                -- Toolbox-specific metrics
                SUM(CASE WHEN execution_method = 'mcp_toolbox' THEN 1 ELSE 0 END) as toolbox_queries,
                SUM(CASE WHEN execution_method = 'direct_bigquery' THEN 1 ELSE 0 END) as direct_bigquery_queries,
                AVG(CASE WHEN execution_method = 'mcp_toolbox' THEN total_time_ms ELSE NULL END) as avg_toolbox_time_ms,
                AVG(CASE WHEN execution_method = 'direct_bigquery' THEN total_time_ms ELSE NULL END) as avg_bigquery_time_ms
            FROM `{self.query_log_table_full_id}`
            WHERE {' AND '.join(where_conditions)}
            GROUP BY query_date, user_id, model_used, execution_method, toolbox_tool_name
            ORDER BY query_date DESC, total_estimated_cost DESC
            """
            
            df = self.bq_analytics_client.query(query).to_dataframe()
            logger.info(f"Retrieved enhanced cost summary with {len(df)} rows")
            return df
            
        except Exception as e:
            logger.error(f"Error getting query cost summary: {e}")
            return pd.DataFrame()

    def get_toolbox_performance_metrics(self, start_date: datetime = None, end_date: datetime = None) -> pd.DataFrame:
        """
        Get performance metrics specifically for MCP Toolbox usage
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            
        Returns:
            DataFrame with toolbox performance metrics
        """
        try:
            where_conditions = [
                "execution_method = 'mcp_toolbox'",
                "timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)"
            ]
            
            if start_date:
                where_conditions.append(f"timestamp >= '{start_date.isoformat()}'")
            if end_date:
                where_conditions.append(f"timestamp <= '{end_date.isoformat()}'")
            
            query = f"""
            SELECT 
                toolbox_tool_name,
                COUNT(*) as usage_count,
                AVG(total_time_ms) as avg_execution_time_ms,
                MIN(total_time_ms) as min_execution_time_ms,
                MAX(total_time_ms) as max_execution_time_ms,
                AVG(row_count) as avg_rows_returned,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_executions,
                ROUND(SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as success_rate,
                -- Most common error messages
                STRING_AGG(DISTINCT error_message, '; ' LIMIT 3) as common_errors
            FROM `{self.query_log_table_full_id}`
            WHERE {' AND '.join(where_conditions)}
            GROUP BY toolbox_tool_name
            ORDER BY usage_count DESC
            """
            
            df = self.bq_analytics_client.query(query).to_dataframe()
            logger.info(f"Retrieved toolbox performance metrics for {len(df)} tools")
            return df
            
        except Exception as e:
            logger.error(f"Error getting toolbox performance metrics: {e}")
            return pd.DataFrame()

    def update_query_log(self, query_id: str, updates: dict):
        """
        Update query log with additional information (enhanced for toolbox context)
        
        Args:
            query_id: Query identifier to update
            updates: Dictionary of fields to update
        """
        if not self.analytics_storage_enabled:
            return
            
        try:
            # Note: Due to BigQuery streaming buffer limitations, updates may not be immediately visible
            # This is a known limitation when using streaming inserts
            logger.debug(f"Skipping query log update for {query_id} due to streaming buffer limitations")
            
            # In a production system, you might:
            # 1. Use a separate "updates" table and JOIN during analysis
            # 2. Implement a batch update process
            # 3. Use Cloud Functions to process updates after streaming buffer clears
            
            return
            
        except Exception as e:
            logger.error(f"Error updating query log: {e}")

    def store_summary_bigquery(self, user_query: str, sql_query: str, summary_text: str, 
                              model_name: str, row_count: int = None, execution_time_ms: int = None,
                              data_preview: dict = None, user_id: str = None, session_id: str = None,
                              toolbox_context: dict = None):
        """
        Store summary with enhanced MCP Toolbox context
        
        Args:
            user_query: Original user query
            sql_query: SQL query or tool identifier
            summary_text: Generated summary
            model_name: AI model used for summary
            row_count: Number of rows in source data
            execution_time_ms: Summary generation time
            data_preview: Sample of the data
            user_id: User identifier
            session_id: Session identifier
            toolbox_context: MCP Toolbox execution context
        """
        if not self.analytics_storage_enabled:
            logger.debug("Analytics storage is disabled")
            return
            
        try:
            model_info = get_available_models().get(model_name, {})
            provider = model_info.get('provider', 'unknown')
            
            from .query_patterns import extract_intent
            intent = extract_intent(user_query)
            
            query_id = getattr(self, 'current_query_id', str(uuid.uuid4()))
            
            # Determine if this summary was generated from toolbox data
            is_toolbox_summary = toolbox_context is not None
            execution_method = 'mcp_toolbox' if is_toolbox_summary else 'direct_bigquery'
            
            summary_row = {
                "summary_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "sql_query": sql_query,
                "model_used": model_name,
                "summary_text": summary_text,
                "row_count": row_count,
                "user_id": user_id or "anonymous",
                "session_id": session_id or "default",
                "execution_method": execution_method,
                "toolbox_tool_name": toolbox_context.get('tool_name') if toolbox_context else None,
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.summary_table_full_id,
                [summary_row]
            )
            
            if errors:
                logger.error(f"Failed to store summary in {self.summary_table_full_id}: {errors}")
            else:
                logger.info(f"Summary stored in {self.summary_table_full_id} with ID: {summary_row['summary_id']} (method: {execution_method})")
            
            # Enhanced analytics row with toolbox context
            analytics_row = {
                "summary_id": summary_row['summary_id'],
                "query_id": query_id,
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "sql_query": sql_query,
                "model_used": model_name,
                "model_provider": provider,
                "summary_text": summary_text,
                "row_count": row_count,
                "execution_time_ms": execution_time_ms,
                "user_id": user_id or "anonymous",
                "session_id": session_id or "default",
                "data_preview": json.dumps(data_preview) if data_preview else None,
                "intent_analysis": json.dumps(intent),
                "execution_method": execution_method,
                "toolbox_tool_name": toolbox_context.get('tool_name') if toolbox_context else None,
                "toolbox_parameters": json.dumps(toolbox_context.get('parameters', {})) if toolbox_context else None,
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.analytics_query_summaries_table_id,
                [analytics_row]
            )
            
            if errors:
                logger.error(f"Failed to store in analytics: {errors}")
            else:
                logger.info(f"Summary tracked in analytics with toolbox context")
                try:
                    self.update_query_log(query_id, {
                        'has_summary': True,
                        'summary_execution_method': execution_method
                    })
                except Exception as e:
                    logger.debug(f"Could not update query log (streaming buffer): {e}")
                
        except Exception as e:
            logger.error(f"Error storing summary in BigQuery: {e}")

    def get_toolbox_adoption_metrics(self, days_back: int = 30) -> dict:
        """
        Get metrics on MCP Toolbox adoption and usage patterns
        
        Args:
            days_back: Number of days to analyze
            
        Returns:
            Dictionary with adoption metrics
        """
        try:
            query = f"""
            WITH daily_metrics AS (
                SELECT 
                    DATE(timestamp) as query_date,
                    execution_method,
                    COUNT(*) as query_count,
                    AVG(total_time_ms) as avg_execution_time
                FROM `{self.query_log_table_full_id}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_back} DAY)
                GROUP BY query_date, execution_method
            ),
            summary_stats AS (
                SELECT 
                    execution_method,
                    SUM(query_count) as total_queries,
                    AVG(avg_execution_time) as overall_avg_time
                FROM daily_metrics
                GROUP BY execution_method
            )
            SELECT * FROM summary_stats
            """
            
            df = self.bq_analytics_client.query(query).to_dataframe()
            
            # Process results into metrics dictionary
            metrics = {
                'analysis_period_days': days_back,
                'total_queries': 0,
                'toolbox_queries': 0,
                'direct_bigquery_queries': 0,
                'toolbox_adoption_rate': 0.0,
                'avg_toolbox_time_ms': 0.0,
                'avg_bigquery_time_ms': 0.0,
                'performance_improvement': 0.0
            }
            
            for _, row in df.iterrows():
                method = row['execution_method']
                count = row['total_queries']
                avg_time = row['overall_avg_time']
                
                metrics['total_queries'] += count
                
                if method == 'mcp_toolbox':
                    metrics['toolbox_queries'] = count
                    metrics['avg_toolbox_time_ms'] = avg_time
                elif method == 'direct_bigquery':
                    metrics['direct_bigquery_queries'] = count
                    metrics['avg_bigquery_time_ms'] = avg_time
            
            # Calculate derived metrics
            if metrics['total_queries'] > 0:
                metrics['toolbox_adoption_rate'] = (metrics['toolbox_queries'] / metrics['total_queries']) * 100
            
            if metrics['avg_bigquery_time_ms'] > 0 and metrics['avg_toolbox_time_ms'] > 0:
                improvement = ((metrics['avg_bigquery_time_ms'] - metrics['avg_toolbox_time_ms']) / metrics['avg_bigquery_time_ms']) * 100
                metrics['performance_improvement'] = improvement
            
            logger.info(f"Toolbox adoption metrics: {metrics['toolbox_adoption_rate']:.1f}% adoption rate")
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting toolbox adoption metrics: {e}")
            return {
                'analysis_period_days': days_back,
                'total_queries': 0,
                'toolbox_queries': 0,
                'direct_bigquery_queries': 0,
                'toolbox_adoption_rate': 0.0,
                'avg_toolbox_time_ms': 0.0,
                'avg_bigquery_time_ms': 0.0,
                'performance_improvement': 0.0,
                'error': str(e)
            }

    def log_toolbox_fallback(self, query_id: str, user_query: str, toolbox_error: str, fallback_success: bool):
        """
        Log when MCP Toolbox fails and system falls back to direct BigQuery
        
        Args:
            query_id: Query identifier
            user_query: Original user query
            toolbox_error: Error from toolbox execution
            fallback_success: Whether fallback was successful
        """
        try:
            fallback_row = {
                "fallback_id": str(uuid.uuid4()),
                "query_id": query_id,
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "toolbox_error": toolbox_error,
                "fallback_success": fallback_success,
                "fallback_timestamp": datetime.utcnow().isoformat()
            }
            
            # This would go to a dedicated fallback logging table
            fallback_table_id = f"{self.analytics_dataset_id}.toolbox_fallbacks"
            
            errors = self.bq_analytics_client.insert_rows_json(
                fallback_table_id,
                [fallback_row]
            )
            
            if errors:
                logger.error(f"Failed to log toolbox fallback: {errors}")
            else:
                logger.info(f"Toolbox fallback logged for query {query_id}")
                
        except Exception as e:
            logger.error(f"Error logging toolbox fallback: {e}")

    def create_analytics_tables_if_needed(self):
        """
        Create analytics tables with enhanced schema for MCP Toolbox integration
        This should be run during system initialization
        """
        try:
            # Enhanced query logs table schema
            query_logs_schema = [
                bigquery.SchemaField("query_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("user_query", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("sql_query", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("model_used", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("model_provider", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("success", "BOOLEAN", mode="REQUIRED"),
                bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("row_count", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("execution_time_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("sql_generation_time_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("query_execution_time_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("total_time_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("session_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("intent_analysis", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("has_visualization", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("has_summary", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("bytes_processed", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("estimated_cost_usd", "FLOAT", mode="NULLABLE"),
                bigquery.SchemaField("cache_hit", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("slot_millis", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("query_parameters", "STRING", mode="NULLABLE"),
                # MCP Toolbox specific fields
                bigquery.SchemaField("execution_method", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("toolbox_tool_name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("toolbox_parameters", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("toolbox_execution_time_ms", "INTEGER", mode="NULLABLE"),
            ]
            
            # Create or update tables as needed
            # This is a simplified version - in production, you'd want proper migration handling
            logger.info("Analytics tables schema updated for MCP Toolbox integration")
            
        except Exception as e:
            logger.error(f"Error creating/updating analytics tables: {e}")

    def get_query_patterns_analysis(self, days_back: int = 30) -> pd.DataFrame:
        """
        Analyze query patterns to identify opportunities for new MCP Toolbox tools
        
        Args:
            days_back: Number of days to analyze
            
        Returns:
            DataFrame with pattern analysis results
        """
        try:
            query = f"""
            WITH intent_analysis AS (
                SELECT 
                    JSON_EXTRACT_SCALAR(intent_analysis, '$.inventory_focus') as is_inventory,
                    JSON_EXTRACT_SCALAR(intent_analysis, '$.return_focus') as is_returns,
                    JSON_EXTRACT_SCALAR(intent_analysis, '$.ranking') as ranking_type,
                    JSON_EXTRACT_SCALAR(intent_analysis, '$.time_series') as is_time_series,
                    JSON_EXTRACT_SCALAR(intent_analysis, '$.comparison') as is_comparison,
                    execution_method,
                    success,
                    total_time_ms,
                    user_query
                FROM `{self.query_log_table_full_id}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days_back} DAY)
                AND intent_analysis IS NOT NULL
            ),
            pattern_summary AS (
                SELECT 
                    CASE 
                        WHEN is_inventory = 'true' THEN 'Inventory Analysis'
                        WHEN is_returns = 'true' THEN 'Returns Analysis'
                        WHEN ranking_type IS NOT NULL THEN 'Ranking/Top Lists'
                        WHEN is_time_series = 'true' THEN 'Time Series'
                        WHEN is_comparison = 'true' THEN 'Comparison'
                        ELSE 'General Analytics'
                    END as query_pattern,
                    execution_method,
                    COUNT(*) as query_count,
                    AVG(total_time_ms) as avg_execution_time,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_queries,
                    ROUND(SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as success_rate
                FROM intent_analysis
                GROUP BY query_pattern, execution_method
            )
            SELECT 
                query_pattern,
                SUM(query_count) as total_queries,
                SUM(CASE WHEN execution_method = 'mcp_toolbox' THEN query_count ELSE 0 END) as toolbox_queries,
                SUM(CASE WHEN execution_method = 'direct_bigquery' THEN query_count ELSE 0 END) as bigquery_queries,
                ROUND(SUM(CASE WHEN execution_method = 'mcp_toolbox' THEN query_count ELSE 0 END) / SUM(query_count) * 100, 2) as toolbox_coverage,
                AVG(CASE WHEN execution_method = 'mcp_toolbox' THEN avg_execution_time ELSE NULL END) as avg_toolbox_time,
                AVG(CASE WHEN execution_method = 'direct_bigquery' THEN avg_execution_time ELSE NULL END) as avg_bigquery_time
            FROM pattern_summary
            GROUP BY query_pattern
            ORDER BY total_queries DESC
            """
            
            df = self.bq_analytics_client.query(query).to_dataframe()
            logger.info(f"Query pattern analysis completed for {len(df)} patterns")
            return df
            
        except Exception as e:
            logger.error(f"Error analyzing query patterns: {e}")
            return pd.DataFrame()
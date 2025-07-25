from google.cloud import bigquery
from google.cloud import billing_v1
import logging
import pandas as pd
from datetime import datetime
import json
import uuid
import os
from chatbot.config import get_available_models
from chatbot.query_patterns import extract_intent


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
            logger.info(f"Query executed - Rows: {len(df)}, "
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
        
        Args:
            query_id: Unique identifier for the query
            project_id: GCP project ID
            query_job: BigQuery job object (optional)
            
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
            'billing_available': self.billing_client is not None
        }
        
        try:
            # Get cost from query job statistics if available
            if query_job:
                cost_info['bytes_processed'] = query_job.total_bytes_processed or 0
                cost_info['cache_hit'] = query_job.cache_hit or False
                cost_info['slot_millis'] = query_job.slot_millis or 0
                cost_info['estimated_cost_usd'] = self._estimate_query_cost(cost_info['bytes_processed'])
                
                logger.info(f"Query {query_id} cost monitoring - "
                           f"Bytes: {cost_info['bytes_processed']}, "
                           f"Estimated cost: ${cost_info['estimated_cost_usd']}, "
                           f"Cache hit: {cost_info['cache_hit']}")
            
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
                             cost_info: dict = None, query_params: dict = None):
        if not self.analytics_storage_enabled:
            logger.debug("Analytics storage is disabled")
            return
            
        try:
            model_info = get_available_models().get(model_name, {})
            provider = model_info.get('provider', 'unknown')
            
            intent = extract_intent(user_query)
            
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
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.query_log_table_full_id,
                [row_data]
            )
            
            if errors:
                logger.error(f"Failed to log query to BigQuery: {errors}")
            else:
                logger.info(f"Query logged to BigQuery with ID: {query_id}")
                
        except Exception as e:
            logger.error(f"Error logging query to BigQuery: {e}")

    def get_query_cost_summary(self, start_date: datetime = None, end_date: datetime = None,
                              user_id: str = None) -> pd.DataFrame:
        """
        Get a summary of query costs for analysis and optimization.
        
        Returns:
            DataFrame with cost analysis
        """
        try:
            where_conditions = ["timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)"]
            
            if start_date:
                where_conditions.append(f"timestamp >= '{start_date.isoformat()}'")
            if end_date:
                where_conditions.append(f"timestamp <= '{end_date.isoformat()}'")
            if user_id:
                where_conditions.append(f"user_id = '{user_id}'")
            
            query = f"""
            SELECT 
                DATE(timestamp) as query_date,
                user_id,
                model_used,
                COUNT(*) as query_count,
                SUM(COALESCE(bytes_processed, 0)) as total_bytes_processed,
                SUM(COALESCE(estimated_cost_usd, 0)) as total_estimated_cost,
                AVG(COALESCE(estimated_cost_usd, 0)) as avg_cost_per_query,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                ROUND(SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as cache_hit_rate
            FROM `{self.query_log_table_full_id}`
            WHERE {' AND '.join(where_conditions)}
            GROUP BY query_date, user_id, model_used
            ORDER BY query_date DESC, total_estimated_cost DESC
            """
            
            df = self.bq_analytics_client.query(query).to_dataframe()
            logger.info(f"Retrieved cost summary with {len(df)} rows")
            return df
            
        except Exception as e:
            logger.error(f"Error getting query cost summary: {e}")
            return pd.DataFrame()

    def update_query_log(self, query_id: str, updates: dict):
        if not self.analytics_storage_enabled:
            return
            
        try:
            logger.debug(f"Skipping query log update for {query_id} due to streaming buffer")
            return
            
        except Exception as e:
            logger.error(f"Error updating query log: {e}")

    def store_summary_bigquery(self, user_query: str, sql_query: str, summary_text: str, 
                              model_name: str, row_count: int = None, execution_time_ms: int = None,
                              data_preview: dict = None, user_id: str = None, session_id: str = None):
        if not self.analytics_storage_enabled:
            logger.debug("Analytics storage is disabled")
            return
            
        try:
            model_info = get_available_models().get(model_name, {})
            provider = model_info.get('provider', 'unknown')
            
            intent = extract_intent(user_query)
            
            query_id = getattr(self, 'current_query_id', str(uuid.uuid4()))
            
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
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.summary_table_full_id,
                [summary_row]
            )
            
            if errors:
                logger.error(f"Failed to store summary in {self.summary_table_full_id}: {errors}")
            else:
                logger.info(f"Summary stored in {self.summary_table_full_id} with ID: {summary_row['summary_id']}")
            
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
            }
            
            errors = self.bq_analytics_client.insert_rows_json(
                self.analytics_query_summaries_table_id,
                [analytics_row]
            )
            
            if errors:
                logger.error(f"Failed to store in analytics: {errors}")
            else:
                logger.info(f"Summary tracked in analytics")
                try:
                    self.update_query_log(query_id, {'has_summary': True})
                except Exception as e:
                    logger.debug(f"Could not update query log (streaming buffer): {e}")
                
        except Exception as e:
            logger.error(f"Error storing summary in BigQuery: {e}")

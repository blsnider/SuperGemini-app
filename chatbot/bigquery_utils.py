import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

class BigQueryUtils:
    """Utilities for BigQuery operations and logging - MCP-only version"""
    
    def __init__(self, config):
        self.config = config
        self.project_id = getattr(config, 'bq_project', 'sis-sandbox-463113')
        self.bq_client = self._init_bigquery_client()
        
        # Use existing llm_analytics dataset in sis-sandbox-463113 project
        # Note: The logging tables are always in sis-sandbox-463113, regardless of the main project
        self.logging_project_id = 'sis-sandbox-463113'
        self.query_log_table = f"{self.logging_project_id}.llm_analytics.query_logs"
        self.summary_log_table = f"{self.logging_project_id}.llm_analytics.LLM_summaries"
        
        # Ensure logging tables exist (but don't create dataset since it exists)
        self._ensure_logging_tables()

    def _init_bigquery_client(self):
        """Initialize BigQuery client with proper configuration"""
        try:
            client = bigquery.Client(project=self.project_id)
            # Test connection
            client.query("SELECT 1").result()
            logger.info(f"✅ BigQuery client initialized for project: {self.project_id}")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client: {e}")
            raise

    def _ensure_logging_tables(self):
        """Ensure logging tables exist in the existing llm_analytics dataset"""
        try:
            # The dataset already exists, so we just need to ensure tables exist
            # Check if tables exist and create them if they don't
            self._create_query_log_table()
            self._create_summary_log_table()
        except Exception as e:
            logger.warning(f"Could not ensure logging tables exist: {e}")

    def _create_query_log_table(self):
        """Create or verify query log table exists"""
        try:
            # Try to get the table first to see if it exists
            table_ref = self.bq_client.get_table(self.query_log_table)
            logger.info(f"✅ Query log table already exists: {self.query_log_table}")
        except Exception:
            # Table doesn't exist, create it
            schema = [
                bigquery.SchemaField("query_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("user_query", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("sql_query", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("tool_name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("model_name", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("success", "BOOLEAN", mode="REQUIRED"),
                bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("row_count", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("execution_times", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("session_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("has_visualization", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("has_summary", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("system_mode", "STRING", mode="NULLABLE"),
            ]
            
            self._create_table_if_not_exists(self.query_log_table, schema)

    def _create_summary_log_table(self):
        """Create or verify summary log table exists"""
        try:
            # Try to get the table first to see if it exists
            table_ref = self.bq_client.get_table(self.summary_log_table)
            logger.info(f"✅ Summary log table already exists: {self.summary_log_table}")
        except Exception:
            # Table doesn't exist, create it
            schema = [
                bigquery.SchemaField("summary_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("query_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("user_query", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("sql_query", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("summary_text", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("model_name", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("row_count", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("execution_time_ms", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("data_preview", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("user_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("session_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("summary_method", "STRING", mode="NULLABLE"),
            ]
            
            self._create_table_if_not_exists(self.summary_log_table, schema)

    def _create_table_if_not_exists(self, table_id: str, schema: List[bigquery.SchemaField]):
        """Create a BigQuery table if it doesn't exist"""
        try:
            table = bigquery.Table(table_id, schema=schema)
            
            # Set table to be partitioned by timestamp for better performance
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="timestamp"
            )
            
            table = self.bq_client.create_table(table, exists_ok=True)
            logger.info(f"✅ Ensured table exists: {table_id}")
            
        except Exception as e:
            logger.error(f"Failed to create table {table_id}: {e}")

    def log_query_to_bigquery(self, query_id: str, user_query: str, sql_query: str, 
                             model_name: str, success: bool, error_message: Optional[str] = None,
                             row_count: Optional[int] = None, execution_times: Optional[Dict] = None,
                             user_id: Optional[str] = None, session_id: Optional[str] = None):
        """Log query execution to BigQuery using exact schema match"""
        try:
            # Extract timing information from execution_times
            total_time_ms = execution_times.get('total_ms', 0) if execution_times else 0
            tool_execution_time = execution_times.get('tool_execution_ms', 0) if execution_times else 0
            sql_generation_time = execution_times.get('sql_generation_ms', 0) if execution_times else 0
            query_execution_time = execution_times.get('query_execution_ms', 0) if execution_times else 0
            
            # Determine model provider from model name
            model_provider = 'mcp_toolbox'
            if model_name.startswith('gemini'):
                model_provider = 'google'
            elif model_name.startswith('gpt') or model_name.startswith('o1'):
                model_provider = 'openai'
            elif model_name.startswith('claude'):
                model_provider = 'anthropic'
            elif model_name.startswith('grok'):
                model_provider = 'xai'
            elif model_name.startswith('mcp_'):
                model_provider = 'mcp_toolbox'
            
            # Build row matching your exact schema
            row = {
                "query_id": query_id,
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "sql_query": sql_query,
                "model_used": model_name,
                "model_provider": model_provider,
                "success": success,
                "error_message": error_message,
                "row_count": row_count,
                "execution_time_ms": tool_execution_time,  # Use tool execution time for main timing
                "sql_generation_time_ms": sql_generation_time,
                "query_execution_time_ms": query_execution_time,
                "total_time_ms": total_time_ms,
                "user_id": user_id or "anonymous",
                "session_id": session_id or "default",
                "intent_analysis": json.dumps({"system_mode": "MCP-Only", "tool_used": True}) if execution_times else None,
                "has_visualization": False,
                "has_summary": False
            }
            
            errors = self.bq_client.insert_rows_json(
                self.bq_client.get_table(self.query_log_table), 
                [row]
            )
            
            if errors:
                logger.error(f"BigQuery logging errors: {errors}")
            else:
                logger.debug(f"Successfully logged query {query_id} to BigQuery")
                
        except Exception as e:
            logger.error(f"Failed to log query to BigQuery: {e}")

    def update_query_log(self, query_id: str, updates: Dict[str, Any]):
        """Update an existing query log entry using exact field names"""
        try:
            # Build SET clause from updates using correct field names
            set_clauses = []
            field_mapping = {
                'has_visualization': 'has_visualization',
                'has_summary': 'has_summary',
                'success': 'success',
                'row_count': 'row_count',
                'error_message': 'error_message'
            }
            
            for key, value in updates.items():
                if key in field_mapping:
                    db_field = field_mapping[key]
                    if isinstance(value, bool):
                        set_clauses.append(f"{db_field} = {str(value).lower()}")
                    elif isinstance(value, str):
                        set_clauses.append(f"{db_field} = '{value}'")
                    elif value is None:
                        set_clauses.append(f"{db_field} = NULL")
                    else:
                        set_clauses.append(f"{db_field} = {value}")
            
            if not set_clauses:
                return
                
            update_query = f"""
                UPDATE `{self.query_log_table}`
                SET {', '.join(set_clauses)}
                WHERE query_id = '{query_id}'
            """
            
            job = self.bq_client.query(update_query)
            job.result()  # Wait for completion
            
            logger.debug(f"Successfully updated query log for {query_id}")
            
        except Exception as e:
            logger.error(f"Failed to update query log: {e}")

    def store_summary_bigquery(self, user_query: str, sql_query: Optional[str], 
                              summary_text: str, model_name: str, row_count: Optional[int] = None,
                              execution_time_ms: Optional[int] = None, data_preview: Optional[List] = None,
                              user_id: Optional[str] = None, session_id: Optional[str] = None,
                              query_id: Optional[str] = None, summary_method: Optional[str] = None):
        """Store AI-generated summary to BigQuery using exact schema match"""
        try:
            import uuid
            summary_id = str(uuid.uuid4())
            
            # Determine model provider from model name
            model_provider = 'google'
            if model_name.startswith('gemini'):
                model_provider = 'google'
            elif model_name.startswith('gpt') or model_name.startswith('o1'):
                model_provider = 'openai'
            elif model_name.startswith('claude'):
                model_provider = 'anthropic'
            elif model_name.startswith('grok'):
                model_provider = 'xai'
            elif 'parallel' in model_name:
                model_provider = 'parallel'
            
            row = {
                "summary_id": summary_id,
                "query_id": query_id or str(uuid.uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "user_query": user_query,
                "sql_query": sql_query,
                "model_used": model_name,
                "model_provider": model_provider,
                "summary_text": summary_text,
                "row_count": row_count,
                "execution_time_ms": execution_time_ms,
                "user_id": user_id or "anonymous",
                "session_id": session_id or "default",
                "data_preview": json.dumps(data_preview) if data_preview else None,
                "intent_analysis": json.dumps({"summary_method": summary_method}) if summary_method else None
            }
            
            errors = self.bq_client.insert_rows_json(
                self.bq_client.get_table(self.summary_log_table), 
                [row]
            )
            
            if errors:
                logger.error(f"BigQuery summary logging errors: {errors}")
            else:
                logger.debug(f"Successfully logged summary {summary_id} to BigQuery")
                
        except Exception as e:
            logger.error(f"Failed to log summary to BigQuery: {e}")

    def get_query_history(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get recent query history from BigQuery"""
        try:
            logger.info(f"Getting query history from BigQuery: user_id={user_id}, limit={limit}")
            logger.info(f"Query log table: {self.query_log_table}")
            
            where_clause = f"WHERE user_id = '{user_id}'" if user_id else ""
            
            query = f"""
                SELECT 
                    query_id,
                    timestamp,
                    user_query,
                    model_name,
                    success,
                    row_count,
                    tool_name,
                    system_mode
                FROM `{self.query_log_table}`
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """
            
            logger.debug(f"Running query: {query}")
            results = self.bq_client.query(query).result()
            
            history = []
            for row in results:
                history.append({
                    'query_id': row.query_id,
                    'timestamp': row.timestamp.isoformat() if row.timestamp else None,
                    'user_query': row.user_query,
                    'model_name': row.model_name,
                    'success': row.success,
                    'row_count': row.row_count,
                    'tool_name': row.tool_name,
                    'system_mode': row.system_mode
                })
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get query history: {e}")
            return []

    def get_usage_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get usage analytics for the last N days"""
        try:
            query = f"""
                SELECT 
                    COUNT(*) as total_queries,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    COUNTIF(success) as successful_queries,
                    COUNTIF(NOT success) as failed_queries,
                    COUNTIF(tool_name IS NOT NULL) as mcp_queries,
                    COUNTIF(has_visualization) as queries_with_charts,
                    COUNTIF(has_summary) as queries_with_summaries,
                    AVG(row_count) as avg_row_count,
                    DATE(timestamp) as query_date
                FROM `{self.query_log_table}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
                GROUP BY DATE(timestamp)
                ORDER BY query_date DESC
            """
            
            results = self.bq_client.query(query).result()
            
            analytics = {
                'daily_stats': [],
                'summary': {
                    'total_queries': 0,
                    'unique_users': 0,
                    'success_rate': 0.0,
                    'mcp_usage_rate': 0.0
                }
            }
            
            total_queries = 0
            successful_queries = 0
            mcp_queries = 0
            unique_users = set()
            
            for row in results:
                daily_stat = {
                    'date': row.query_date.isoformat() if row.query_date else None,
                    'total_queries': row.total_queries,
                    'unique_users': row.unique_users,
                    'success_rate': (row.successful_queries / row.total_queries * 100) if row.total_queries > 0 else 0,
                    'mcp_usage_rate': (row.mcp_queries / row.total_queries * 100) if row.total_queries > 0 else 0
                }
                analytics['daily_stats'].append(daily_stat)
                
                total_queries += row.total_queries
                successful_queries += row.successful_queries
                mcp_queries += row.mcp_queries
            
            # Calculate summary stats
            if total_queries > 0:
                analytics['summary'] = {
                    'total_queries': total_queries,
                    'success_rate': (successful_queries / total_queries * 100),
                    'mcp_usage_rate': (mcp_queries / total_queries * 100),
                    'period_days': days
                }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get usage analytics: {e}")
            return {'daily_stats': [], 'summary': {}}

    def get_popular_queries(self, limit: int = 10) -> List[Dict]:
        """Get most popular queries"""
        try:
            query = f"""
                SELECT 
                    user_query,
                    tool_name,
                    COUNT(*) as query_count,
                    COUNTIF(success) as success_count,
                    AVG(row_count) as avg_row_count
                FROM `{self.query_log_table}`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
                GROUP BY user_query, tool_name
                HAVING COUNT(*) > 1
                ORDER BY query_count DESC
                LIMIT {limit}
            """
            
            results = self.bq_client.query(query).result()
            
            popular_queries = []
            for row in results:
                popular_queries.append({
                    'query': row.user_query,
                    'tool_name': row.tool_name,
                    'count': row.query_count,
                    'success_rate': (row.success_count / row.query_count * 100) if row.query_count > 0 else 0,
                    'avg_row_count': float(row.avg_row_count) if row.avg_row_count else 0
                })
            
            return popular_queries
            
        except Exception as e:
            logger.error(f"Failed to get popular queries: {e}")
            return []

    def test_connection(self) -> bool:
        """Test BigQuery connection"""
        try:
            result = self.bq_client.query("SELECT 1 as test").result()
            for row in result:
                if row.test == 1:
                    logger.info("✅ BigQuery connection test successful")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ BigQuery connection test failed: {e}")
            return False
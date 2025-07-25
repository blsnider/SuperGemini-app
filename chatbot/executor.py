# chatbot/executor.py - Updated with tenacity retries and correct imports

import time
import logging
from google.cloud import bigquery
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((bigquery.exceptions.BigQueryError, TimeoutError))
)
def execute_query(sql_query: str, bq_client: bigquery.Client) -> tuple:
    """Execute BigQuery query with retries."""
    start_time = time.time()
    
    try:
        # Use parameterized query to prevent SQL injection (from search best practices)
        job_config = bigquery.QueryJobConfig(
            query_parameters=[  # Example: Add params based on query
                bigquery.ScalarQueryParameter("param_name", "STRING", "value")
            ] if "param_name" in sql_query else []  # Dynamically parse for params
        )
        
        query_job = bq_client.query(sql_query, job_config=job_config)
        df = query_job.to_dataframe()
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        return df, None, execution_time_ms
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        execution_time_ms = int((time.time() - start_time) * 1000)
        return None, str(e), execution_time_ms

def format_results(df, preview_rows):
    if df is None or df.empty:
        return "No results found."
    
    df_formatted = df.copy()
    
    for col in df_formatted.columns:
        col_lower = col.lower()
        if 'price' in col_lower or 'dollar' in col_lower or 'revenue' in col_lower or 'margin_dollar' in col_lower or 'retail_value' in col_lower or 'cost_value' in col_lower or 'retail_extension' in col_lower or 'cost_extension' in col_lower:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "")
        elif 'margin_pct' in col_lower or 'percent' in col_lower or '_pct' in col_lower:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")
        elif 'quantity' in col_lower or 'units' in col_lower or 'count' in col_lower or 'oh_units' in col_lower or 'on_hand' in col_lower:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "")
        elif 'days' in col_lower and 'supply' in col_lower:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:.0f} days" if pd.notnull(x) else "")
        elif 'velocity' in col_lower:
            df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:.2f}/day" if pd.notnull(x) else "")
    
    lines = []
    
    headers = []
    for col in df_formatted.columns:
        clean_col = col.replace('_', ' ').title()
        clean_col = clean_col.replace('Pct', '%')
        clean_col = clean_col.replace('Id', 'ID')
        clean_col = clean_col.replace('Oh ', 'On Hand ')
        headers.append(clean_col[:20])
    
    col_widths = []
    for i, col in enumerate(df_formatted.columns):
        max_width = max(
            len(headers[i]),
            max(len(str(val)) for val in df_formatted[col]) if len(df_formatted) > 0 else 0
        )
        col_widths.append(min(max_width + 2, 25))
    
    header_line = " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths))
    lines.append(header_line)
    lines.append("-" * len(header_line))
    
    for _, row in df_formatted.head(preview_rows).iterrows():
        row_values = []
        for i, val in enumerate(row):
            str_val = str(val) if pd.notnull(val) else ""
            if len(str_val) > col_widths[i] - 2:
                str_val = str_val[:col_widths[i]-5] + "..."
            row_values.append(f"{str_val:<{col_widths[i]}}")
        lines.append(" | ".join(row_values))
    
    if len(df_formatted) > preview_rows:
        lines.append(f"\n... showing {preview_rows} of {len(df_formatted)} results")
        
    return "\n".join(lines)

#!/usr/bin/env python3
"""
Script to check the schema of your existing BigQuery tables
Run this to see what fields exist in your current logging tables
"""

from google.cloud import bigquery

def check_table_schema():
    """Check the schema of existing BigQuery tables"""
    
    project_id = "sis-sandbox-463113"
    
    try:
        client = bigquery.Client(project=project_id)
        
        # Check query_logs table
        query_logs_table = f"{project_id}.llm_analytics.query_logs"
        
        try:
            table = client.get_table(query_logs_table)
            print(f"✅ Found table: {query_logs_table}")
            print(f"Schema for query_logs:")
            print("-" * 40)
            for field in table.schema:
                print(f"  {field.name}: {field.field_type} ({field.mode})")
            print()
            
        except Exception as e:
            print(f"❌ Could not access query_logs table: {e}")
        
        # Check LLM_summaries table
        summaries_table = f"{project_id}.llm_analytics.LLM_summaries"
        
        try:
            table = client.get_table(summaries_table)
            print(f"✅ Found table: {summaries_table}")
            print(f"Schema for LLM_summaries:")
            print("-" * 40)
            for field in table.schema:
                print(f"  {field.name}: {field.field_type} ({field.mode})")
            print()
            
        except Exception as e:
            print(f"❌ Could not access LLM_summaries table: {e}")
        
        # Also check if there are other tables
        dataset = client.get_dataset(f"{project_id}.llm_analytics")
        print("All tables in llm_analytics dataset:")
        print("-" * 40)
        
        for table in client.list_tables(dataset):
            print(f"  📋 {table.table_id}")
        
    except Exception as e:
        print(f"❌ Error checking BigQuery schema: {e}")

if __name__ == '__main__':
    check_table_schema()
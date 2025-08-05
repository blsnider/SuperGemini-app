#!/usr/bin/env python3
"""
Check what datasets are available in the scheels-data-marts project.
"""

from google.cloud import bigquery

def list_datasets():
    """List all datasets in the scheels-data-marts project."""
    
    client = bigquery.Client(project='scheels-data-marts')
    
    try:
        print("🔍 Listing datasets in scheels-data-marts project...")
        datasets = list(client.list_datasets())
        
        if datasets:
            print(f"Found {len(datasets)} dataset(s):")
            for dataset in datasets:
                dataset_id = dataset.dataset_id
                print(f"  📁 {dataset_id}")
                
                # List tables in each dataset
                try:
                    tables = list(client.list_tables(dataset_id))
                    if tables:
                        print(f"     Tables ({len(tables)}):")
                        for table in tables[:10]:  # Limit to first 10 tables
                            print(f"       📋 {table.table_id}")
                        if len(tables) > 10:
                            print(f"       ... and {len(tables) - 10} more tables")
                    else:
                        print("     No tables found")
                    print()
                except Exception as e:
                    print(f"     Error listing tables: {str(e)}")
                    print()
        else:
            print("No datasets found.")
            
    except Exception as e:
        print(f"❌ Error listing datasets: {str(e)}")

if __name__ == "__main__":
    list_datasets()
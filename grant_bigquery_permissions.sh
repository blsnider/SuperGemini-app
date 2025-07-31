#!/bin/bash

# Grant BigQuery permissions to MCP Toolbox service account
# This allows the service to query data in scheels-data-marts project

SERVICE_ACCOUNT="datamart-sandbox-warehouse@sis-sandbox-463113.iam.gserviceaccount.com"
DATA_PROJECT="scheels-data-marts"

echo "🔐 Granting BigQuery permissions to MCP Toolbox service account..."
echo "Service Account: $SERVICE_ACCOUNT"
echo "Target Project: $DATA_PROJECT"
echo ""

# Grant BigQuery Job User role (allows creating jobs)
echo "1️⃣ Granting BigQuery Job User role..."
gcloud projects add-iam-policy-binding $DATA_PROJECT \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/bigquery.jobUser"

# Grant BigQuery Data Viewer role (allows reading data)
echo "2️⃣ Granting BigQuery Data Viewer role..."
gcloud projects add-iam-policy-binding $DATA_PROJECT \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/bigquery.dataViewer"

echo ""
echo "✅ Permissions granted successfully!"
echo ""
echo "The service account now has:"
echo "  - bigquery.jobs.create (via BigQuery Job User role)"
echo "  - bigquery.tables.getData (via BigQuery Data Viewer role)"
echo "  - bigquery.tables.list (via BigQuery Data Viewer role)"
echo ""
echo "💡 Test the permissions by running a query through the Super Gemini dashboard"
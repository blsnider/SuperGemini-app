#!/bin/bash

# Diagnose MCP Toolbox BigQuery permissions issue

echo "🔍 Diagnosing MCP Toolbox BigQuery permissions..."
echo ""

# Service details
SERVICE_ACCOUNT="datamart-sandbox-warehouse@sis-sandbox-463113.iam.gserviceaccount.com"
TOOLBOX_PROJECT="sis-sandbox-463113"
DATA_PROJECT="scheels-data-marts"

echo "📋 Service Configuration:"
echo "  - Service Account: $SERVICE_ACCOUNT"
echo "  - Toolbox Project: $TOOLBOX_PROJECT"
echo "  - Data Project: $DATA_PROJECT"
echo ""

# Check if service account exists
echo "1️⃣ Checking if service account exists..."
if gcloud iam service-accounts describe $SERVICE_ACCOUNT --project=$TOOLBOX_PROJECT >/dev/null 2>&1; then
    echo "✅ Service account exists"
else
    echo "❌ Service account not found!"
fi
echo ""

# Check permissions in toolbox project
echo "2️⃣ Checking permissions in toolbox project ($TOOLBOX_PROJECT)..."
gcloud projects get-iam-policy $TOOLBOX_PROJECT \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:$SERVICE_ACCOUNT" \
    --format="table(bindings.role)" 2>/dev/null || echo "⚠️  Cannot check permissions (insufficient access)"
echo ""

# Test BigQuery access from local environment
echo "3️⃣ Testing BigQuery access with your credentials..."
bq query --project_id=$DATA_PROJECT --use_legacy_sql=false "SELECT 1 as test" 2>&1 | head -n 5
echo ""

# Check Cloud Run service configuration
echo "4️⃣ Checking Cloud Run service configuration..."
echo "Service Account in use:"
gcloud run services describe toolbox \
    --region=us-central1 \
    --project=$TOOLBOX_PROJECT \
    --format="value(spec.template.spec.serviceAccountName)"
echo ""

# Suggest next steps
echo "📝 Troubleshooting steps:"
echo ""
echo "1. The error suggests the service account doesn't have permissions in $DATA_PROJECT"
echo "   You need someone with IAM admin access to $DATA_PROJECT to run:"
echo ""
echo "   gcloud projects add-iam-policy-binding $DATA_PROJECT \\"
echo "       --member=\"serviceAccount:$SERVICE_ACCOUNT\" \\"
echo "       --role=\"roles/bigquery.jobUser\""
echo ""
echo "   gcloud projects add-iam-policy-binding $DATA_PROJECT \\"
echo "       --member=\"serviceAccount:$SERVICE_ACCOUNT\" \\"
echo "       --role=\"roles/bigquery.dataViewer\""
echo ""
echo "2. If permissions were just granted, wait 1-2 minutes for propagation"
echo ""
echo "3. Try redeploying the service to force a refresh:"
echo "   gcloud run services update toolbox --region=us-central1 --project=$TOOLBOX_PROJECT"
echo ""
echo "4. Contact the owner of project '$DATA_PROJECT' to grant the permissions"
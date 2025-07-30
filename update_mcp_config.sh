#\!/bin/bash

# Update MCP Toolbox Config on Cloud Run

echo "🚀 Updating MCP Toolbox Configuration..."

# 1. Create new version of the secret with updated tools.yaml
echo "📝 Creating new secret version..."
gcloud secrets versions add mcp-toolbox-config \
  --data-file=chatbot/tools.yaml \
  --project=sis-sandbox-463113

# 2. Force Cloud Run to redeploy with updated config
echo "🔄 Forcing Cloud Run service update..."
# Update the FORCE_RELOAD env var to current timestamp to force redeployment
gcloud run services update toolbox \
  --update-env-vars FORCE_RELOAD=$(date +%s) \
  --region=us-central1 \
  --project=sis-sandbox-463113

echo "✅ Update complete\! The service will take a minute to deploy."
echo "📊 You can check the status with:"
echo "   gcloud run services describe toolbox --region=us-central1 --project=sis-sandbox-463113"


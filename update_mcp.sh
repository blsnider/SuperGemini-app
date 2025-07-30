#!/bin/bash

# Update MCP Toolbox Configuration on Cloud Run
# Usage: ./update_mcp.sh

set -e

echo "🚀 Updating MCP Toolbox Configuration..."
echo "📁 Using tools.yaml from: chatbot/tools.yaml"

# Check if tools.yaml exists
if [ ! -f "chatbot/tools.yaml" ]; then
    echo "❌ Error: chatbot/tools.yaml not found!"
    exit 1
fi

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

echo ""
echo "✅ Update complete! The service will take 30-60 seconds to fully deploy."
echo ""
echo "📊 Check deployment status:"
echo "   gcloud run services describe toolbox --region=us-central1 --project=sis-sandbox-463113"
echo ""
echo "🧪 Test the service:"
echo "   curl http://localhost:5000/api/mcp/test | jq '.'"
echo ""
echo "📝 View Cloud Run logs:"
echo "   gcloud run services logs read toolbox --region=us-central1 --project=sis-sandbox-463113 --tail=50"
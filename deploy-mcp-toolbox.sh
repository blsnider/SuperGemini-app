#!/bin/bash

# Complete deployment script for MCP Toolbox Server
# This handles the full build and deployment process

set -e  # Exit on any error

# Configuration
PROJECT_ID="sis-sandbox-463113"
REGION="us-central1"
SERVICE_NAME="toolbox"
REPOSITORY="toolbox-repo"

echo "🚀 MCP Toolbox Server Deployment"
echo "================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Step 1: Validate required files
echo "📁 Step 1: Validating required files..."
echo "---------------------------------------"

MISSING_FILES=0

if [ ! -f "mcp_toolbox_server.py" ]; then
    echo "❌ mcp_toolbox_server.py not found"
    MISSING_FILES=1
else
    echo "✅ mcp_toolbox_server.py found"
fi

if [ ! -f "tools.yaml" ]; then
    if [ -f "chatbot/tools.yaml" ]; then
        echo "📋 Copying tools.yaml from chatbot/ directory..."
        cp chatbot/tools.yaml tools.yaml
        echo "✅ tools.yaml copied"
    else
        echo "❌ tools.yaml not found"
        MISSING_FILES=1
    fi
else
    echo "✅ tools.yaml found"
fi

if [ ! -f "Dockerfile.toolbox" ]; then
    echo "❌ Dockerfile.toolbox not found"
    MISSING_FILES=1
else
    echo "✅ Dockerfile.toolbox found"
fi

if [ ! -f "cloudbuild-toolbox.yaml" ]; then
    echo "❌ cloudbuild-toolbox.yaml not found"
    MISSING_FILES=1
else
    echo "✅ cloudbuild-toolbox.yaml found"
fi

if [ $MISSING_FILES -eq 1 ]; then
    echo ""
    echo "❌ Missing required files. Please ensure all files are present."
    exit 1
fi

echo ""
echo "✅ All required files present"
echo ""

# Step 2: Validate YAML syntax
echo "📝 Step 2: Validating configuration..."
echo "--------------------------------------"
python3 -c "
import yaml
try:
    with open('tools.yaml', 'r') as f:
        config = yaml.safe_load(f)
    print(f'✅ YAML valid - {len(config.get(\"tools\", {}))} tools configured')
except Exception as e:
    print(f'❌ YAML validation failed: {e}')
    exit(1)
"

# Step 3: Update the secret (optional)
echo ""
echo "🔐 Step 3: Update secret with tools.yaml?"
echo "-----------------------------------------"
echo "Do you want to update the secret 'mcp-tools-yaml' with the current tools.yaml? (y/n)"
read -p "> " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Updating secret..."
    gcloud secrets versions add mcp-tools-yaml \
        --data-file=tools.yaml \
        --project=$PROJECT_ID
    echo "✅ Secret updated"
else
    echo "⏭️  Skipping secret update"
fi

# Step 4: Build and push Docker image
echo ""
echo "🏗️  Step 4: Building and deploying..."
echo "------------------------------------"
echo "Starting Cloud Build process..."

# Generate a unique tag for this deployment
BUILD_TAG="deploy-$(date +%Y%m%d-%H%M%S)"

# Create a simple cloudbuild for this deployment
cat > cloudbuild-deploy-temp.yaml << EOF
steps:
  # Build the Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'build',
      '-f', 'Dockerfile.toolbox',
      '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox:$BUILD_TAG',
      '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox:latest',
      '.'
    ]

  # Push the image
  - name: 'gcr.io/cloud-builders/docker'
    args: [
      'push',
      '--all-tags',
      'us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox'
    ]

  # Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: bash
    args:
      - '-c'
      - |
        echo "Deploying to Cloud Run..."
        gcloud run deploy $SERVICE_NAME \
          --image=us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox:$BUILD_TAG \
          --region=$REGION \
          --project=$PROJECT_ID \
          --platform=managed \
          --allow-unauthenticated \
          --port=8080 \
          --memory=2Gi \
          --cpu=1 \
          --min-instances=0 \
          --max-instances=10 \
          --timeout=300 \
          --service-account=toolbox-sa@$PROJECT_ID.iam.gserviceaccount.com \
          --set-env-vars="TOOLBOX_CONFIG_PATH=/app/tools.yaml,BUILD_TAG=$BUILD_TAG"
        
        echo "Deployment complete!"

images:
  - 'us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox:$BUILD_TAG'
  - 'us-central1-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/custom-toolbox:latest'

timeout: 900s
EOF

# Submit the build
gcloud builds submit \
    --config=cloudbuild-deploy-temp.yaml \
    --project=$PROJECT_ID

# Clean up temp file
rm cloudbuild-deploy-temp.yaml

# Step 5: Verify deployment
echo ""
echo "✅ Step 5: Verifying deployment..."
echo "----------------------------------"
sleep 5

# Get service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(status.url)")

echo "Service URL: $SERVICE_URL"
echo ""

# Test the service
echo "Testing health endpoint..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/health")

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Health check passed (HTTP $HTTP_CODE)"
    echo ""
    echo "Testing tools list..."
    curl -s "$SERVICE_URL/tools" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'✅ Tools endpoint working - {len(data)} tools available')
    print('\\nAvailable tools:')
    for tool in data[:5]:
        print(f\"  - {tool.get('name', 'unknown')}: {tool.get('description', '')[:60]}...\")
    if len(data) > 5:
        print(f'  ... and {len(data)-5} more')
except:
    print('⚠️  Tools endpoint returned non-JSON response')
    "
else
    echo "⚠️  Health check returned HTTP $HTTP_CODE"
    echo "The service may still be starting up. Try again in a moment:"
    echo "curl $SERVICE_URL/health"
fi

echo ""
echo "🎉 Deployment Complete!"
echo "======================"
echo "Service URL: $SERVICE_URL"
echo "Health Check: $SERVICE_URL/health"
echo "List Tools: $SERVICE_URL/tools"
echo ""
echo "Example tool usage:"
echo "curl -X POST $SERVICE_URL/tools/get_top_selling_items \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"store_id\": 0, \"limit\": 10}'"
echo ""
echo "To view logs:"
echo "gcloud run services logs $SERVICE_NAME --region=$REGION --project=$PROJECT_ID"
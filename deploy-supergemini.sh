#!/bin/bash
# Deploy SuperGemini with UI/UX fixes
# This script builds and deploys directly without git push

echo "=== SuperGemini Direct Deployment Script ==="
echo "This will deploy the current local state directly to Cloud Run"
echo ""

# Variables
PROJECT_ID="sis-sandbox-463113"
SERVICE_NAME="supergemini-app"
REGION="us-central1"
IMAGE_NAME="super-gemini"
REPOSITORY="super-gemini-repo"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="ui-fix-${TIMESTAMP}"
FULL_IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo "📦 Building Docker image: ${IMAGE_TAG}"
docker build -t ${FULL_IMAGE} .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed"
    exit 1
fi

echo "📤 Pushing image to Artifact Registry..."
docker push ${FULL_IMAGE}

if [ $? -ne 0 ]; then
    echo "❌ Docker push failed"
    exit 1
fi

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image=${FULL_IMAGE} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --platform=managed \
    --allow-unauthenticated \
    --service-account=supergemini-client@${PROJECT_ID}.iam.gserviceaccount.com \
    --port=8080 \
    --memory=2Gi \
    --cpu=2 \
    --min-instances=0 \
    --max-instances=100 \
    --timeout=300

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo "🌐 Service URL: https://${SERVICE_NAME}-zchpgeskka-uc.a.run.app"
    echo ""
    echo "📝 Image deployed: ${FULL_IMAGE}"
    echo ""
    echo "To verify the UI changes:"
    echo "1. Open the URL in an incognito window"
    echo "2. Check for:"
    echo "   - Seasonality Config button in sidebar"
    echo "   - Tools Catalog button in sidebar"
    echo "   - Horizontal scrollbar on tables"
    echo "   - 'Generating insights...' text when loading"
else
    echo "❌ Deployment failed"
    exit 1
fi
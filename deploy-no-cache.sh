#!/bin/bash

# Deploy script that forces a fresh build without Docker cache
# This ensures all UI/UX changes are included

echo "==================================================="
echo "Deploying SuperGemini with fresh build (no cache)"
echo "==================================================="

PROJECT_ID="sis-sandbox-463113"
REGION="us-central1"
SERVICE_NAME="supergemini-app"
IMAGE_URL="us-central1-docker.pkg.dev/${PROJECT_ID}/super-gemini-repo/super-gemini"

# Add timestamp to force unique image tag
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="${IMAGE_URL}:${TIMESTAMP}"

echo ""
echo "Step 1: Building Docker image with --no-cache flag"
echo "Image tag: ${IMAGE_TAG}"
echo ""

# Build with no cache to ensure all files are fresh
docker build --no-cache -t ${IMAGE_TAG} .

if [ $? -ne 0 ]; then
    echo "Error: Docker build failed"
    exit 1
fi

echo ""
echo "Step 2: Pushing image to Artifact Registry"
echo ""

docker push ${IMAGE_TAG}

if [ $? -ne 0 ]; then
    echo "Error: Docker push failed"
    exit 1
fi

echo ""
echo "Step 3: Deploying to Cloud Run"
echo ""

gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE_TAG} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --platform=managed \
    --allow-unauthenticated \
    --service-account=supergemini-client@sis-sandbox-463113.iam.gserviceaccount.com \
    --port=8080

if [ $? -eq 0 ]; then
    echo ""
    echo "==================================================="
    echo "Deployment successful!"
    echo "Service URL: https://${SERVICE_NAME}-41815171183.${REGION}.run.app/"
    echo "Image: ${IMAGE_TAG}"
    echo ""
    echo "The soft red theme (v3.0.0) should now be visible."
    echo "Clear browser cache if needed: Ctrl+Shift+R"
    echo "==================================================="
else
    echo "Error: Cloud Run deployment failed"
    exit 1
fi
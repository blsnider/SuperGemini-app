#!/bin/bash

# rebuild_docker.sh - Rebuild and deploy Super Gemini to Cloud Run

set -e

echo "🔨 Rebuilding Super Gemini Docker container..."

# Set variables
PROJECT_ID="sis-sandbox-463113"
IMAGE_NAME="super-gemini"
REGION="us-central1"
SERVICE_NAME="super-gemini"

# Ensure we're in the right directory
cd "$(dirname "$0")"

echo "📦 Building Docker image..."
# Build with Cloud Build instead of locally to avoid authentication issues
gcloud builds submit --tag gcr.io/${PROJECT_ID}/${IMAGE_NAME} \
    --project=${PROJECT_ID} \
    --timeout=20m

echo "🚀 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
    --image gcr.io/${PROJECT_ID}/${IMAGE_NAME} \
    --platform managed \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 300 \
    --max-instances 10 \
    --set-env-vars="ENVIRONMENT=production,BQ_PROJECT=sis-data-marts,SECRETS_PROJECT=${PROJECT_ID}"

echo "✅ Deployment complete!"
echo ""
echo "🔗 Your app is available at:"
gcloud run services describe ${SERVICE_NAME} \
    --platform managed \
    --region ${REGION} \
    --project ${PROJECT_ID} \
    --format 'value(status.url)'
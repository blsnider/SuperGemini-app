#!/bin/bash

# Deploy Super Gemini App to Cloud Run via Cloud Build
# This script builds the Docker image and deploys to Cloud Run

set -e

echo "🚀 Deploying Super Gemini App to Cloud Run..."
echo "📦 Project: sis-sandbox-463113"
echo "🌍 Region: us-central1"
echo ""

# Check if gcloud is configured
if ! gcloud config get-value project &> /dev/null; then
    echo "❌ Error: gcloud is not configured. Please run 'gcloud init' first."
    exit 1
fi

# Confirm deployment
echo "This will:"
echo "  1. Build a new Docker image"
echo "  2. Push to Artifact Registry" 
echo "  3. Deploy to Cloud Run (supergemini-app)"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

# Submit build to Cloud Build
echo ""
echo "📨 Submitting to Cloud Build..."
gcloud builds submit \
    --config=cloudbuild.yaml \
    --project=sis-sandbox-463113 \
    --region=us-central1

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 View your app:"
echo "   https://supergemini-app-41815171183.us-central1.run.app"
echo ""
echo "📝 View Cloud Run service:"
echo "   gcloud run services describe supergemini-app --region=us-central1 --project=sis-sandbox-463113"
echo ""
echo "📋 View logs:"
echo "   gcloud run services logs read supergemini-app --region=us-central1 --project=sis-sandbox-463113 --tail=50"
echo ""
echo "🔄 To force a new deployment without code changes:"
echo "   gcloud run services update supergemini-app --region=us-central1 --project=sis-sandbox-463113 --update-env-vars=FORCE_DEPLOY=$(date +%s)"
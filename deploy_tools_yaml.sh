#!/bin/bash

# Deploy tools.yaml to MCP Toolbox Cloud Run Service
# This script updates the tools.yaml configuration for the MCP Toolbox service

set -e

# Configuration
PROJECT_ID="sis-sandbox-463113"
REGION="us-central1"
SECRET_NAME="mcp-tools-yaml"
TOOLS_YAML_PATH="./chatbot/tools.yaml"
TOOLBOX_SERVICE="toolbox"
SUPER_GEMINI_SERVICE="super-gemini"

echo "🚀 Starting tools.yaml deployment process..."

# Check if tools.yaml exists
if [ ! -f "$TOOLS_YAML_PATH" ]; then
    echo "❌ Error: tools.yaml not found at $TOOLS_YAML_PATH"
        exit 1
        fi

        echo "✅ Found tools.yaml at $TOOLS_YAML_PATH"

        # Check if secret exists, create or update
        echo "📦 Checking if secret $SECRET_NAME exists..."
        if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID >/dev/null 2>&1; then
            echo "🔄 Secret exists, creating new version..."
                gcloud secrets versions add $SECRET_NAME \
                        --project=$PROJECT_ID \
                                --data-file=$TOOLS_YAML_PATH
                                else
                                    echo "✨ Creating new secret..."
                                        gcloud secrets create $SECRET_NAME \
                                                --project=$PROJECT_ID \
                                                        --data-file=$TOOLS_YAML_PATH
                                                        fi

                                                        echo "✅ Secret $SECRET_NAME updated successfully"

                                                        # Deploy to MCP Toolbox service
                                                        echo "🔧 Updating MCP Toolbox service with new tools.yaml..."
                                                        gcloud run services update $TOOLBOX_SERVICE \
                                                            --region=$REGION \
                                                                --project=$PROJECT_ID \
                                                                    --update-secrets=/app/tools.yaml=$SECRET_NAME:latest

                                                                    echo "✅ MCP Toolbox service updated successfully"

                                                                    # Optional: Also update Super Gemini service if needed
                                                                    echo "🔧 Updating Super Gemini service with new tools.yaml..."
                                                                    gcloud run services update $SUPER_GEMINI_SERVICE \
                                                                        --region=$REGION \
                                                                            --project=$PROJECT_ID \
                                                                                --update-secrets=/app/chatbot/tools.yaml=$SECRET_NAME:latest

                                                                                echo "✅ Super Gemini service updated successfully"

                                                                                # Get service URLs
                                                                                TOOLBOX_URL=$(gcloud run services describe $TOOLBOX_SERVICE --region=$REGION --project=$PROJECT_ID --format="value(status.url)")
                                                                                SUPER_GEMINI_URL=$(gcloud run services describe $SUPER_GEMINI_SERVICE --region=$REGION --project=$PROJECT_ID --format="value(status.url)")

                                                                                echo ""
                                                                                echo "🎉 Deployment complete!"
                                                                                echo "📍 MCP Toolbox URL: $TOOLBOX_URL"
                                                                                echo "📍 Super Gemini URL: $SUPER_GEMINI_URL"
                                                                                echo ""
                                                                                echo "💡 Tip: Test your new tools by making a request to your Super Gemini application"
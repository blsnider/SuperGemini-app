# Super Gemini Deployment Guide

## Quick Deploy Commands

### 1. Deploy Super Gemini Application
```bash
# Make the script executable (first time only)
chmod +x deploy-supergemini.sh

# Run the deployment
./deploy-supergemini.sh
```

### 2. Deploy MCP Toolbox Server
```bash
# Make the script executable (first time only)
chmod +x deploy-mcp-toolbox.sh

# Run the deployment
./deploy-mcp-toolbox.sh
```

## Manual Deployment Commands

### Super Gemini App - Quick Deploy (Recommended)
```bash
gcloud run deploy supergemini-app \
    --source . \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --allow-unauthenticated \
    --service-account=supergemini-client@sis-sandbox-463113.iam.gserviceaccount.com \
    --port=8080 \
    --memory=2Gi \
    --cpu=2
```

### Super Gemini App - Cloud Build Deploy
```bash
gcloud builds submit --config=cloudbuild.yaml --project=sis-sandbox-463113
```

### MCP Toolbox - Cloud Build Deploy
```bash
gcloud builds submit --config=cloudbuild-toolbox.yaml --project=sis-sandbox-463113
```

## Service URLs

- **Super Gemini App**: https://supergemini-app-[hash]-uc.a.run.app
- **MCP Toolbox**: https://toolbox-[hash]-uc.a.run.app

## Monitoring & Logs

### View Logs
```bash
# Super Gemini logs
gcloud run services logs supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --tail=50

# MCP Toolbox logs
gcloud run services logs toolbox \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --tail=50
```

### Stream Logs (Real-time)
```bash
# Super Gemini
gcloud alpha run services logs tail supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113

# MCP Toolbox
gcloud alpha run services logs tail toolbox \
    --region=us-central1 \
    --project=sis-sandbox-463113
```

## Service Management

### Check Service Status
```bash
# List all services
gcloud run services list \
    --region=us-central1 \
    --project=sis-sandbox-463113

# Describe specific service
gcloud run services describe supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113
```

### Update Traffic Split
```bash
# Send all traffic to latest
gcloud run services update-traffic supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --to-latest

# Split traffic between revisions
gcloud run services update-traffic supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --to-revisions=REVISION1=50,REVISION2=50
```

### Rollback to Previous Version
```bash
# List revisions
gcloud run revisions list \
    --service=supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113

# Rollback to specific revision
gcloud run services update-traffic supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --to-revisions=REVISION_NAME=100
```

## Secrets Management

### Update Secrets
```bash
# Update Anthropic API Key
echo "your-api-key" | gcloud secrets versions add ANTHROPIC_API_KEY \
    --data-file=- \
    --project=sis-sandbox-463113

# Update BigQuery Service Account
gcloud secrets versions add BIGQUERY_KEY_JSON \
    --data-file=path/to/service-account.json \
    --project=sis-sandbox-463113

# Update MCP tools configuration
gcloud secrets versions add mcp-tools-yaml \
    --data-file=tools.yaml \
    --project=sis-sandbox-463113
```

### List Secret Versions
```bash
gcloud secrets versions list ANTHROPIC_API_KEY \
    --project=sis-sandbox-463113
```

## Docker Commands (Local Testing)

### Build Locally
```bash
# Super Gemini
docker build -t super-gemini:local .

# MCP Toolbox
docker build -f Dockerfile.toolbox -t mcp-toolbox:local .
```

### Run Locally
```bash
# Super Gemini (requires .env file)
docker run -p 8080:8080 --env-file .env super-gemini:local

# MCP Toolbox
docker run -p 8080:8080 -v $(pwd)/tools.yaml:/app/tools.yaml mcp-toolbox:local
```

## Troubleshooting

### Common Issues

1. **Service returns 503 or doesn't start**
   - Check logs for errors
   - Verify all required secrets are set
   - Ensure service account has necessary permissions

2. **BigQuery access denied**
   - Verify service account has BigQuery Data Viewer role
   - Check if BIGQUERY_KEY_JSON secret is properly formatted

3. **Anthropic API errors**
   - Verify ANTHROPIC_API_KEY secret is set correctly
   - Check API key validity and rate limits

4. **MCP tools not working**
   - Ensure tools.yaml is properly formatted
   - Check if mcp-tools-yaml secret is updated
   - Verify BigQuery permissions for the service account

### Debug Commands
```bash
# Test service health
curl https://[SERVICE_URL]/health

# Test MCP tools endpoint
curl https://[TOOLBOX_URL]/tools

# Check service account permissions
gcloud projects get-iam-policy sis-sandbox-463113 \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:*"
```

## Environment Variables

### Super Gemini App
- `ENVIRONMENT`: production/development
- `GCP_PROJECT`: sis-sandbox-463113
- `FLASK_APP`: app.py
- `PORT`: 8080

### MCP Toolbox
- `TOOLBOX_CONFIG_PATH`: /app/tools.yaml
- `PORT`: 8080
- `BUILD_TAG`: deployment version tag

## CI/CD Pipeline

The project uses Cloud Build for CI/CD:

1. **Trigger**: Manual via `gcloud builds submit` or deploy scripts
2. **Build**: Docker image built and pushed to Artifact Registry
3. **Deploy**: Cloud Run service updated with new image
4. **Verify**: Health checks ensure service is running

## Backup and Recovery

### Backup Current Configuration
```bash
# Export service configuration
gcloud run services export supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --format=export > supergemini-backup.yaml

# Backup secrets (metadata only)
gcloud secrets list --project=sis-sandbox-463113 --format=json > secrets-backup.json
```

### Restore from Backup
```bash
# Import service configuration
gcloud run services replace supergemini-backup.yaml \
    --region=us-central1 \
    --project=sis-sandbox-463113
```

## Performance Tuning

### Adjust Resources
```bash
gcloud run services update supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --memory=4Gi \
    --cpu=4 \
    --min-instances=1 \
    --max-instances=200 \
    --concurrency=100
```

### Set Autoscaling
```bash
gcloud run services update supergemini-app \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --min-instances=0 \
    --max-instances=100 \
    --cpu-throttling \
    --execution-environment=gen2
```

## Security Best Practices

1. **Never commit secrets to git**
   - Use `.gitignore` to exclude `.env` files
   - Store secrets in Google Secret Manager

2. **Use service accounts with minimal permissions**
   - Follow principle of least privilege
   - Regularly audit permissions

3. **Enable Cloud Armor for DDoS protection** (if needed)
```bash
gcloud compute security-policies create supergemini-policy \
    --description="Security policy for Super Gemini"
```

4. **Monitor for anomalies**
   - Set up alerting policies
   - Review logs regularly

## Contact & Support

For issues or questions:
- Check service logs first
- Review this documentation
- Contact the development team

Last Updated: 2025-08-07
# Custom MCP Toolbox Build & Deployment

This document explains how to build and deploy your own MCP Toolbox service from the `tools.yaml` configuration.

## Overview

Instead of relying on the pre-built MCP Toolbox from the `database-toolbox` project, you can now build and deploy your own custom toolbox that:
- Builds directly from your `tools.yaml` configuration
- Runs in your own project (`sis-sandbox-463113`)
- Can be modified and extended as needed
- Automatically connects to BigQuery based on your sources configuration

## Quick Start

### Option 1: Update Existing Toolbox Service (Recommended)
```bash
# This updates your existing 'toolbox' service with custom build
./deploy_custom_toolbox.sh
```

This will:
- Build your custom Docker image from tools.yaml
- **Update the existing `toolbox` service** (keeps same URL)
- No need to change any configuration in SuperGemini

### Option 2: Safe Migration with Backup
```bash
# This backs up current config before updating
./migrate_to_custom_toolbox.sh
```

This will:
- Create a backup of current service configuration
- Show you what will change
- Ask for confirmation before proceeding
- Test the service after deployment
- Provide rollback instructions if needed

### No Configuration Changes Needed!
Since we're updating the existing service, your SuperGemini app continues using:
- Same URL: `https://toolbox-41815171183.us-central1.run.app`
- No environment variable changes required

## File Structure

```
/home/user/SuperGemini/
├── mcp_toolbox_server.py      # Python server that reads tools.yaml
├── Dockerfile.toolbox          # Docker configuration for toolbox
├── cloudbuild-toolbox.yaml    # Cloud Build configuration
├── deploy_custom_toolbox.sh   # Deployment script
├── chatbot/tools.yaml         # Your tools configuration
└── test_local_toolbox.py      # Local testing script
```

## How It Works

### 1. **mcp_toolbox_server.py**
- Flask-based web server
- Reads `tools.yaml` at startup
- Executes BigQuery queries based on tool definitions
- Compatible with existing MCP Toolbox client API

### 2. **Tools Configuration (tools.yaml)**
```yaml
sources:
  bq-salesmart:
    kind: bigquery
    project: scheels-data-marts
    location: us

tools:
  get_top_selling_items:
    kind: bigquery-sql
    source: bq-salesmart
    description: Get top selling items
    parameters:
      - name: store_id
        type: integer
        default: 0
    statement: |
      SELECT * FROM `table` WHERE store_id = @store_id
```

### 3. **Deployment Process**
```bash
# Using Cloud Build (recommended)
gcloud builds submit --config cloudbuild-toolbox.yaml --project=sis-sandbox-463113

# Or using the deployment script
./deploy_custom_toolbox.sh
```

## Making Changes

### To Add/Modify Tools:
1. Edit `chatbot/tools.yaml`
2. Run deployment: `./deploy_custom_toolbox.sh`
3. The new tools are immediately available

### To Modify Server Code:
1. Edit `mcp_toolbox_server.py`
2. Test locally: `python test_local_toolbox.py`
3. Deploy: `./deploy_custom_toolbox.sh`

## Testing

### Local Testing:
```bash
# Test the server locally
python test_local_toolbox.py

# Run the server locally
python mcp_toolbox_server.py
# Then visit: http://localhost:8080/tools
```

### Production Testing:
```bash
# After deployment, test the endpoints
SERVICE_URL=https://custom-toolbox-xxx.run.app

# Health check
curl $SERVICE_URL/health

# List tools
curl $SERVICE_URL/tools

# Execute a tool
curl -X POST $SERVICE_URL/tools/get_top_selling_items \
  -H "Content-Type: application/json" \
  -d '{"store_id": 64, "shop_id": 29}'
```

## Comparison of Deployment Methods

| Method | What it Does | Service Name | URL Changes | Build Time | Use Case |
|--------|--------------|--------------|-------------|------------|----------|
| **`deploy_tools_yaml.sh`** (original) | Updates Secret Manager config only | `toolbox` | No change | ~30 seconds | Quick SQL/parameter changes only |
| **`deploy_custom_toolbox.sh`** (new) | Builds & deploys custom image | `toolbox` | No change | ~2-3 minutes | Full control, custom features |
| **`migrate_to_custom_toolbox.sh`** (safest) | Backs up, then builds & deploys | `toolbox` | No change | ~2-3 minutes | First-time migration with safety |

### Key Point: All methods update the SAME service
- Service name: `toolbox`
- URL: `https://toolbox-41815171183.us-central1.run.app`
- **No configuration changes needed in SuperGemini**

## Advantages of Custom Build

1. **Full Control**: Modify server behavior, add caching, custom authentication
2. **Single Project**: Everything runs in `sis-sandbox-463113`
3. **Extensibility**: Add new tool types beyond BigQuery SQL
4. **Debugging**: Full access to logs and source code
5. **Integration**: Can add custom endpoints for your specific needs

## Migration Path

To migrate from the existing toolbox to your custom one:

1. Deploy custom toolbox: `./deploy_custom_toolbox.sh`
2. Update environment variable: `MCP_TOOLBOX_URL=<new-url>`
3. Test thoroughly
4. Optional: Update `cloudbuild.yaml` to include toolbox in main build

## Troubleshooting

### Common Issues:

1. **Permission Denied**
   - Ensure service account has BigQuery access to all projects in tools.yaml
   - Run: `gcloud projects add-iam-policy-binding PROJECT --member=serviceAccount:toolbox-sa@sis-sandbox-463113.iam.gserviceaccount.com --role=roles/bigquery.user`

2. **Tools Not Loading**
   - Check Cloud Run logs: `gcloud run services logs read custom-toolbox --project=sis-sandbox-463113`
   - Verify tools.yaml syntax: `python -c "import yaml; yaml.safe_load(open('chatbot/tools.yaml'))"`

3. **Build Fails**
   - Ensure Artifact Registry API is enabled
   - Check Cloud Build logs in GCP Console

## Next Steps

1. Consider adding:
   - Response caching for frequently used queries
   - Request validation and rate limiting
   - Metrics and monitoring
   - Custom authentication if needed

2. For production:
   - Set up Cloud Build triggers for automatic deployment on git push
   - Configure alerts for service health
   - Implement proper secret management for any API keys
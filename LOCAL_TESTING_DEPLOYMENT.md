# Local Testing and Deployment Guide

## 1. Testing Locally

### Option A: Using Python Virtual Environment (Recommended)
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/Mac
# OR
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FLASK_ENV=development
export PORT=8080
export BQ_PROJECT=sis-sandbox-463113
export DEFAULT_MODEL=gemini-2.5-pro

# Run the application
python3 app.py
```

Then open your browser to: http://localhost:8080

### Option B: Using Docker Locally
```bash
# Build the Docker image locally
docker build -t super-gemini-local .

# Run the container
docker run -p 8080:8080 \
  -e BQ_PROJECT=sis-sandbox-463113 \
  -e DEFAULT_MODEL=gemini-2.5-pro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json \
  super-gemini-local
```

Then open your browser to: http://localhost:8080

## 2. Deploying from Local Files (NOT from Git)

Your `cloudbuild.yaml` is already configured to build from LOCAL files, not from git!

### Deploy Command:
```bash
# Make sure you're in the SuperGemini directory
cd /home/user/SuperGemini

# Deploy from LOCAL files
gcloud builds submit --config cloudbuild.yaml --project=sis-sandbox-463113
```

This command:
- Uses the `.` (current directory) as the build context
- Uploads your LOCAL files to Cloud Build
- Does NOT use git repository
- Builds the Docker image from your local files
- Deploys to Cloud Run

### What Happens:
1. `gcloud builds submit` packages your LOCAL directory
2. Uploads it to Google Cloud Storage
3. Cloud Build uses these uploaded files (NOT git)
4. Builds Docker image from your local changes
5. Pushes to Artifact Registry
6. Deploys to Cloud Run

## 3. Verify Your Changes

### Visual Confirmations:
After deployment, you should see:
1. **Soft red/pink theme** instead of purple
2. **Version badge showing v3.0.0**
3. **AG-Grid tables** with horizontal scrolling
4. **No 20-row limit** on data display

### Check Deployment Status:
```bash
# View Cloud Run service
gcloud run services describe supergemini-app \
  --region=us-central1 \
  --project=sis-sandbox-463113

# Get the service URL
gcloud run services list \
  --platform=managed \
  --region=us-central1 \
  --project=sis-sandbox-463113
```

## 4. Troubleshooting

### If you see old version after deployment:
1. Clear browser cache (Ctrl+Shift+R)
2. Check Cloud Build logs:
   ```bash
   gcloud builds list --limit=5 --project=sis-sandbox-463113
   gcloud builds log [BUILD_ID] --project=sis-sandbox-463113
   ```

3. Verify the deployed image:
   ```bash
   gcloud run services describe supergemini-app \
     --region=us-central1 \
     --format='value(spec.template.spec.containers[0].image)' \
     --project=sis-sandbox-463113
   ```

### If build fails:
1. Check `.gcloudignore` file isn't excluding needed files
2. Ensure all files are saved locally
3. Check Docker build works locally first:
   ```bash
   docker build -t test-build .
   ```

## 5. Quick Test Script

Create a file `test_local.sh`:
```bash
#!/bin/bash
echo "Testing local deployment readiness..."
echo "Current directory: $(pwd)"
echo "Files that will be deployed:"
ls -la
echo ""
echo "Checking for UI changes:"
grep -n "v3.0.0" templates/base.html
grep -n "#ff6b6b" static/css/main.css
echo ""
echo "Ready to deploy? Run:"
echo "gcloud builds submit --config cloudbuild.yaml --project=sis-sandbox-463113"
```

Make it executable: `chmod +x test_local.sh`
Run it: ./test_local.sh

## Important Notes

- **You ARE deploying from LOCAL files**, not git
- The `.` in the Dockerfile means current directory
- Cloud Build receives a tarball of your local directory
- Changes don't need to be committed to git
- The build context includes ALL files in current directory (except those in .gcloudignore)

## Version Tracking

Current version: **v3.0.0**
Changes in this version:
- ✅ AG-Grid implementation for data tables
- ✅ Removed 20-row display limit
- ✅ Fixed horizontal scrolling issues
- ✅ Soft red color theme throughout
- ✅ CSV export functionality
- ✅ Advanced filtering and search
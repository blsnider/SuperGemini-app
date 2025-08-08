#!/bin/bash

echo "==================================================="
echo "Verifying UI/UX Changes in SuperGemini"
echo "==================================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Track if all checks pass
ALL_PASS=true

# Function to check file content
check_content() {
    local file=$1
    local search=$2
    local description=$3
    
    if grep -q "$search" "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $description"
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        ALL_PASS=false
        return 1
    fi
}

echo "1. CSS Color Theme Checks:"
echo "--------------------------"
check_content "static/css/main.css" "#ff6b6b" "Soft red primary color (#ff6b6b) in main.css"
check_content "static/css/main.css" "#ee5a6f" "Soft red gradient color (#ee5a6f) in main.css"
check_content "templates/chat.html" "ff6b6b\|ee5a6f" "Soft red colors in chat.html"

echo ""
echo "2. Version Number Checks:"
echo "-------------------------"
check_content "templates/base.html" "v3.0.0" "Version 3.0.0 in base.html"
check_content "templates/base.html" "Version 3.0.0" "Version 3.0.0 in title attribute"

echo ""
echo "3. AG-Grid Integration:"
echo "----------------------"
check_content "templates/base.html" "ag-grid-community" "AG-Grid scripts in base.html"
check_content "templates/base.html" "ag-theme-quartz" "AG-Grid theme in base.html"
check_content "static/js/aggrid_tables.js" "initDataGrid" "AG-Grid initialization function"
check_content "static/js/chat.js" "AGGridUtils" "AG-Grid utils in chat.js"

echo ""
echo "4. File Timestamps:"
echo "------------------"
echo "Recent modifications (should show today's date):"
ls -la --time-style=long-iso static/css/main.css templates/base.html templates/chat.html | awk '{print $6, $7, $8, $9}'

echo ""
echo "5. Sample Content Preview:"
echo "-------------------------"
echo "First line with soft red color in CSS:"
grep -n "ff6b6b" static/css/main.css | head -1

echo ""
echo "Version badge line in base.html:"
grep -n "version-badge" templates/base.html | head -1

echo ""
echo "==================================================="
if [ "$ALL_PASS" = true ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED!${NC}"
    echo "Your files contain all the UI/UX updates."
    echo ""
    echo "If deployment still shows old version, the issue is:"
    echo "1. Docker build cache (use cloudbuild-nocache.yaml)"
    echo "2. Browser cache (hard refresh with Ctrl+Shift+R)"
    echo "3. CDN cache (may take a few minutes to update)"
else
    echo -e "${RED}✗ SOME CHECKS FAILED!${NC}"
    echo "Some UI changes are missing from your files."
fi
echo "==================================================="
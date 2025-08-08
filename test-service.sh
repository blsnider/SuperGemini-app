#!/bin/bash

# Test the MCP Toolbox service thoroughly

SERVICE_URL="https://toolbox-zchpgeskka-uc.a.run.app"

echo "🧪 Testing MCP Toolbox Service"
echo "================================"
echo ""

# Test 1: Raw health check
echo "1. Raw health check response:"
echo "------------------------------"
curl -s "$SERVICE_URL/health"
echo ""
echo ""

# Test 2: Health check with verbose
echo "2. Health check with headers:"
echo "------------------------------"
curl -sI "$SERVICE_URL/health"
echo ""

# Test 3: Tools endpoint raw
echo "3. Raw tools list response:"
echo "----------------------------"
curl -s "$SERVICE_URL/tools"
echo ""
echo ""

# Test 4: Test a specific tool
echo "4. Testing get_shop_performance tool:"
echo "--------------------------------------"
curl -s -X POST "$SERVICE_URL/tools/get_shop_performance" \
  -H "Content-Type: application/json" \
  -d '{
    "shop_id": 0,
    "store_id": 0,
    "days_back": 7,
    "metric_focus": "revenue"
  }' | head -100
echo ""
echo ""

# Test 5: Check if the old compatibility endpoint works
echo "5. Testing compatibility endpoint:"
echo "-----------------------------------"
curl -s "$SERVICE_URL/toolsets/retail_analytics/tools" | head -50
echo ""
echo ""

# Test 6: Check service logs for errors
echo "6. Recent service logs:"
echo "-----------------------"
gcloud run services logs toolbox \
    --region=us-central1 \
    --project=sis-sandbox-463113 \
    --limit=20 \
    --format="value(textPayload)"

echo ""
echo "🔍 Diagnostics Summary:"
echo "======================="
echo "Service URL: $SERVICE_URL"
echo "Service is responding but may have issues with JSON formatting."
echo ""

# Test 7: Simple connectivity test
echo "7. Simple connectivity test:"
echo "----------------------------"
if curl -s -o /dev/null -w "%{http_code}" "$SERVICE_URL/health" | grep -q "200"; then
    echo "✅ Service is returning HTTP 200 OK"
else
    echo "❌ Service is not returning HTTP 200"
fi

echo ""
echo "To manually test a tool, use:"
echo "curl -X POST $SERVICE_URL/tools/get_top_selling_items \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"store_id\": 0, \"limit\": 10}'"
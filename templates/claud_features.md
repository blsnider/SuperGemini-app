# Feature Updates: Bug Fixes and UI Enhancements

## Priority: High
**Date**: Current
**Status**: Multiple issues need addressing

---

## 1. Remove Session Cost Analysis
### Current State
- Session cost analysis is displayed in the UI
- Cost calculations are shown to users

### Required Changes
1. **Remove all cost-related UI components**
   - Hide/remove cost display widgets
   - Remove cost calculation functions from frontend
   - Keep backend logic intact (for potential future use)
   
2. **Files to modify**:
   - Frontend components displaying cost
   - Any cost-related state management
   - Dashboard/chat pages showing cost metrics

### Acceptance Criteria
- [ ] No cost information visible in UI
- [ ] No console errors from removed components
- [ ] Backend cost logic remains functional but disconnected from UI

---

## 2. Hide Inventory Snapshot Date UI
### Current State
- Date picker/selector for inventory snapshot is visible
- Users can currently select dates

### Required Changes
1. **Hide UI elements** (do not remove code):
   ```css
   /* Add display: none or visibility: hidden to date picker components */
   .inventory-snapshot-date-picker {
     display: none;
   }
   ```

2. **Maintain backend functionality**:
   - Keep date logic in place
   - Use system-determined date or default value
   - Preserve data flow, just hide UI

### Acceptance Criteria
- [ ] Date selection UI not visible to users
- [ ] System continues to function with default/automatic dates
- [ ] Easy to re-enable in future (just remove hiding CSS/prop)

---

## 3. Fix Query History Endpoint - BigQuery Access Issue
### Current State
- Query history endpoint not displaying executed queries in sidecar UI
- Suspected BigQuery data access permission issue

### Diagnostic Steps
1. **Verify BigQuery permissions**:
   - Check service account has `bigquery.jobs.list` permission
   - Verify project ID is correct
   - Ensure dataset/table access is granted

2. **Debug the endpoint**:
   ```javascript
   // Add logging to query history endpoint
   console.log('Fetching query history...');
   console.log('Project ID:', projectId);
   console.log('Dataset:', datasetId);
   // Log any BigQuery errors in detail
   ```

3. **Common fixes**:
   - Ensure correct scope: `https://www.googleapis.com/auth/bigquery.readonly`
   - Check if queries are being written to expected location
   - Verify timestamp filtering isn't excluding recent queries

### Files to check:
- Query history API endpoint
- BigQuery client configuration
- Sidecar UI component fetching history

### Acceptance Criteria
- [ ] Query history displays in sidecar
- [ ] Recent queries appear immediately
- [ ] No permission errors in logs

---

## 4. Fix Chat Page Scrollable DataFrame
### Current State
- Chat page DataFrame not scrollable
- Table display issues

### Required Changes
1. **Option A: Copy working implementation from dashboard**:
   ```javascript
   // Import the same table component used in dashboard
   import { DataTable } from '../dashboard/components/DataTable';
   
   // Use identical configuration that works in dashboard
   ```

2. **Option B: Fix current implementation**:
   ```css
   .dataframe-container {
     max-height: 400px;
     overflow-y: auto;
     overflow-x: auto;
   }
   
   .dataframe-table {
     width: 100%;
     table-layout: fixed;
   }
   ```

### Recommendation
- Use Option A (copy from dashboard) for consistency and proven functionality

### Acceptance Criteria
- [ ] DataFrame scrolls vertically for long data
- [ ] DataFrame scrolls horizontally for wide tables
- [ ] Headers remain visible during scroll (sticky headers)
- [ ] Performance remains good with large datasets

---

## 5. Fix OTB Metrics Dashboard Error
### Current State
- Error: "Failed to load OTB metrics - MCP tool execution failed: missing a required argument: 'metric_name'"
- Broke after adding "get otb aware" MCP tool

### Root Cause Analysis
- New MCP tool likely changed the expected parameters
- Metric name not being passed correctly to the tool

### Required Changes
1. **Check MCP tool calls**:
   ```javascript
   // Ensure metric_name is passed
   const otbMetrics = await mcpTool.execute('get_otb_metrics', {
     metric_name: 'required_metric_name', // This is missing
     // other parameters
   });
   ```

2. **Verify tool registration**:
   - Check if "get otb aware" tool conflicts with existing tools
   - Ensure proper parameter mapping

### Acceptance Criteria
- [ ] OTB metrics load successfully
- [ ] No parameter errors
- [ ] Both old and new MCP tools coexist without conflicts

---

## 6. Fix YOY Calculations on Dashboard
### Current State
- YOY (Year-over-Year) calculations showing incorrect values
- Calculation logic error

### Debugging Steps
1. **Verify calculation formula**:
   ```javascript
   // Correct YOY formula
   const yoyChange = ((currentYear - previousYear) / previousYear) * 100;
   ```

2. **Check data alignment**:
   - Ensure comparing same periods (e.g., Jan 2024 vs Jan 2023)
   - Verify timezone handling
   - Check for null/zero division

3. **Common issues**:
   - Date range misalignment
   - Incorrect aggregation before calculation
   - Missing data handling

### Acceptance Criteria
- [ ] YOY percentages calculate correctly
- [ ] Handle edge cases (division by zero, missing data)
- [ ] Results match manual calculations

---

## 7. Add MCP Tool Configuration in Sidecar
### New Feature Requirements
1. **Configuration UI in sidecar**:
   ```javascript
   // Settings structure
   {
     "mcpTools": {
       "enabledTools": {
         "get_inventory_metrics": true,
         "get_otb_metrics": true,
         "get_otb_aware": true,
         // ... other tools
       }
     }
   }
   ```

2. **Implementation**:
   - Add settings panel in sidecar
   - Checkbox list of all available MCP tools
   - Save preferences to local storage or user profile

3. **Apply configuration**:
   - Filter dropdown options on chat page
   - Hide/show dashboard icons based on selection
   - Maintain state across sessions

### UI Components Needed:
- Settings modal/panel in sidecar
- Checkbox group for tool selection
- Save/Cancel buttons
- Real-time preview of changes

### Acceptance Criteria
- [ ] Users can enable/disable individual MCP tools
- [ ] Chat dropdown reflects selected tools only
- [ ] Dashboard icons show/hide based on selection
- [ ] Settings persist between sessions

---

## 8. MCP Tools Performance - CAUTION
### Current State
- MCP tools have slowed down
- All tools working correctly with BigQuery
- **DO NOT break existing functionality**

### Performance Investigation Only
1. **Add performance monitoring**:
   ```javascript
   const startTime = performance.now();
   // ... tool execution ...
   const endTime = performance.now();
   console.log(`Tool ${toolName} took ${endTime - startTime}ms`);
   ```

2. **Optimization opportunities** (implement carefully):
   - Query result caching
   - Connection pooling for BigQuery
   - Batch operations where possible
   - Index optimization in BigQuery

3. **DO NOT CHANGE**:
   - Core query logic
   - BigQuery connection setup
   - Data transformation logic
   - Any working authentication

### Safe improvements:
- [ ] Add caching layer (with TTL)
- [ ] Implement request debouncing
- [ ] Add loading states for better UX
- [ ] Consider pagination for large results

---

## Testing Requirements
1. **Regression testing**:
   - All MCP tools continue to work
   - BigQuery connections remain stable
   - No new errors introduced

2. **Feature testing**:
   - Hidden UI elements don't break functionality
   - New configuration options work as expected
   - Performance monitoring doesn't impact functionality

## Implementation Order
1. Fix critical errors first (OTB metrics, Query History)
2. Hide UI elements (cost analysis, inventory date)
3. Fix display issues (scrollable DataFrame, YOY calculations)
4. Add new features (MCP tool configuration)
5. Monitor performance (carefully, without breaking changes)

## Notes
- Keep all changes reversible where possible
- Maintain backward compatibility
- Document any workarounds for future reference
- Test thoroughly in development before deploying
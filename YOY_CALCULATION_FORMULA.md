# Year-over-Year (YoY) Calculation Formula Documentation

## Overview
The dashboard calculates YoY percentages by comparing current period metrics with the same period from the previous year.

## Data Periods
- **Current Period**: Last 42 days from today
- **Prior Period**: Same 42-day period from last year

## Formulas

### 1. Revenue YoY %
```
revenue_yoy_pct = ((current_revenue - prior_revenue) / prior_revenue) * 100
```
Example: 
- Current Revenue: $100,000
- Prior Revenue: $80,000  
- YoY % = ((100,000 - 80,000) / 80,000) * 100 = 25.0%

### 2. Units YoY %
```
units_yoy_pct = ((current_units - prior_units) / prior_units) * 100
```
Example:
- Current Units: 5,000
- Prior Units: 4,500
- YoY % = ((5,000 - 4,500) / 4,500) * 100 = 11.1%

### 3. Margin YoY %
```
margin_yoy_pct = current_margin_pct - prior_margin_pct
```
**Note**: Margin is calculated as absolute percentage point change, not relative change.

Example:
- Current Margin: 35.5%
- Prior Margin: 32.3%
- YoY Change = 35.5 - 32.3 = 3.2 percentage points

## Implementation Details

### Data Extraction Process
1. **Current Period Query**: 
   - Fetches top selling items for last 42 days
   - Extracts total revenue, units, and margin from summary statistics

2. **Prior Period Query**:
   - Fetches data from same 42 day period last year
   - Uses same extraction logic as current period

### Error Handling
- If prior period data is unavailable, YoY shows as 0%
- If prior values are 0, YoY calculation is skipped (prevents division by zero)
- Default margin of 30% used if margin data is missing

### Display Rules
- **Positive YoY**: Displayed in green (growth)
- **Negative YoY**: Displayed in red (decline)
- **Zero YoY**: Displayed in default color (no change)

## Code Location
The YoY calculation logic is implemented in:
- **Backend**: `/app.py` in the `api_dashboard_metrics()` function 
- **Frontend**: `/templates/dashboard.html` in the `updateYoYMetric()` function
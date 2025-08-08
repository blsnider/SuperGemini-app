# URGENT FIX: Add Horizontal Scrollbar to Data Table

## Problem
The data table is cutting off columns on the right side (Priority column and beyond) with no way to scroll horizontally to see them. The table needs a horizontal scrollbar to access all columns.

## Current Broken State
- Table width exceeds container width
- No horizontal scrollbar appears
- Columns are cut off and inaccessible
- Pagination controls are partially hidden

## Required Solution

### Step 1: Identify the Table Container
Look for the component that renders this table. It likely has a structure like:
```jsx
<div className="table-container">
  <table>
    <!-- table content -->
  </table>
</div>
```

### Step 2: Apply These EXACT CSS Changes

**Option A - Add to the table container's CSS file:**
```css
.table-container {
  width: 100%;
  overflow-x: auto;
  overflow-y: visible;
  -webkit-overflow-scrolling: touch; /* For smooth scrolling on iOS */
}

.table-container table {
  min-width: max-content;
  width: 100%;
  table-layout: auto; /* Important: DO NOT use 'fixed' */
}

/* Ensure the container has a max-width */
.table-wrapper {
  max-width: 100%;
  overflow: hidden;
}
```

**Option B - If using inline styles or styled-components:**
```jsx
<div style={{
  width: '100%',
  overflowX: 'auto',
  overflowY: 'visible',
  WebkitOverflowScrolling: 'touch'
}}>
  <table style={{
    minWidth: 'max-content',
    width: '100%',
    tableLayout: 'auto'
  }}>
    {/* table content */}
  </table>
</div>
```

**Option C - If using Tailwind CSS:**
```jsx
<div className="w-full overflow-x-auto overflow-y-visible">
  <table className="w-full min-w-max table-auto">
    {/* table content */}
  </table>
</div>
```

### Step 3: Fix the Pagination Controls
The pagination controls also need to be within a scrollable container or positioned differently:

```css
.pagination-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: white;
  border-top: 1px solid #e0e0e0;
  position: sticky;
  bottom: 0;
  z-index: 10;
}
```

### Step 4: Common Mistakes to AVOID
1. **DO NOT use `overflow: hidden`** on any parent containers
2. **DO NOT use `table-layout: fixed`** - this prevents proper column sizing
3. **DO NOT set a fixed width** on the table
4. **DO NOT use `white-space: nowrap`** on all cells - only on specific cells if needed

### Step 5: Debug Checklist
If the scrollbar still doesn't appear, check:

```javascript
// Add this debug code temporarily
const tableContainer = document.querySelector('.table-container');
console.log('Container width:', tableContainer.offsetWidth);
console.log('Table width:', tableContainer.querySelector('table').offsetWidth);
console.log('Overflow-x:', window.getComputedStyle(tableContainer).overflowX);
console.log('Parent overflow:', window.getComputedStyle(tableContainer.parentElement).overflow);
```

### Step 6: Nuclear Option - Force Scrollbar
If nothing else works, add this CSS to force the scrollbar:

```css
.table-container {
  width: 100% !important;
  max-width: 100% !important;
  overflow-x: scroll !important; /* Force scrollbar always visible */
  overflow-y: visible !important;
}

/* Remove overflow hidden from ALL parent elements */
.parent-container,
.main-content,
.page-wrapper {
  overflow: visible !important;
}
```

## Testing Instructions
1. The horizontal scrollbar should appear when table width exceeds container
2. All columns should be accessible by scrolling
3. The scrollbar should be at the bottom of the table data (not below pagination)
4. Scrolling should be smooth
5. The table headers should scroll with the content

## Expected Result
- ✅ Horizontal scrollbar visible when needed
- ✅ Can scroll to see "Priority" column and any columns to the right
- ✅ Pagination controls fully visible and accessible
- ✅ No content is cut off

## File Locations to Check
- Look for files like: `DataTable.jsx`, `Table.tsx`, `table.css`, or similar
- Check parent components that might have `overflow: hidden`
- Look for any global styles affecting table containers

## IMPORTANT NOTE FOR CLAUDE CODE
This is a CSS issue. The solution is to add `overflow-x: auto` to the table's container div and ensure no parent elements have `overflow: hidden`. Do not modify the table data structure or React logic - only modify the CSS/styling.
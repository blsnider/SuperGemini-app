// AG-Grid Table Implementation for Super Gemini Analytics
// This replaces the problematic custom table implementation with a professional data grid

// Global variable to store grid instances
window.agGridInstances = {};

/**
 * Initialize AG-Grid for displaying query results
 * @param {string} containerId - The HTML element ID where grid should be rendered
 * @param {Array} data - The data rows to display
 * @param {Array} columns - The column definitions
 * @param {Object} options - Additional grid options
 */
function initDataGrid(containerId, data, columns = null, options = {}) {
    console.log('Initializing AG-Grid for container:', containerId);
    console.log('Data rows:', data ? data.length : 0);
    
    // Auto-generate columns if not provided
    if (!columns && data && data.length > 0) {
        columns = Object.keys(data[0]).map(key => ({
            field: key,
            headerName: formatColumnHeader(key),
            sortable: true,
            filter: true,
            resizable: true,
            minWidth: 100,
            // Auto-size based on content
            autoHeight: true,
            wrapText: true,
            // Format numbers and currency
            valueFormatter: params => formatCellValue(params.value, key)
        }));
    }
    
    // Default grid options with horizontal scrolling enabled
    const defaultOptions = {
        columnDefs: columns,
        rowData: data,
        
        // Enable horizontal scrolling
        suppressHorizontalScroll: false,
        alwaysShowHorizontalScroll: true,
        
        // Column defaults
        defaultColDef: {
            sortable: true,
            filter: true,
            resizable: true,
            floatingFilter: true, // Show filter inputs under headers
            minWidth: 100,
            wrapText: true,
            autoHeight: true
        },
        
        // Pagination for large datasets
        pagination: true,
        paginationPageSize: 100,
        paginationPageSizeSelector: [20, 50, 100, 200, 500],
        
        // Selection and interaction
        rowSelection: 'multiple',
        enableCellTextSelection: true,
        ensureDomOrder: true,
        
        // Excel-like features
        enableRangeSelection: true,
        enableRangeHandle: true,
        fillOperation: true,
        copyHeadersToClipboard: true,
        
        // Performance
        animateRows: true,
        rowBuffer: 10,
        
        // Styling
        rowHeight: 35,
        headerHeight: 40,
        
        // Export options
        defaultCsvExportParams: {
            allColumns: true,
            fileName: 'export.csv'
        },
        
        // Status bar
        statusBar: {
            statusPanels: [
                { statusPanel: 'agTotalAndFilteredRowCountComponent', align: 'left' },
                { statusPanel: 'agTotalRowCountComponent', align: 'center' },
                { statusPanel: 'agSelectedRowCountComponent', align: 'right' }
            ]
        },
        
        // Loading overlay
        overlayLoadingTemplate: '<span class="ag-overlay-loading-center">Loading data...</span>',
        overlayNoRowsTemplate: '<span class="ag-overlay-no-rows-center">No data to display</span>'
    };
    
    // Merge with custom options
    const gridOptions = { ...defaultOptions, ...options };
    
    // Get the container element
    const container = document.getElementById(containerId);
    if (!container) {
        console.error('Container not found:', containerId);
        return null;
    }
    
    // Clear any existing content
    container.innerHTML = '';
    
    // Add AG-Grid theme class
    container.className = 'ag-theme-quartz';
    container.style.height = '600px'; // Set a fixed height for scrolling
    container.style.width = '100%';
    
    // Create the grid
    const gridInstance = new agGrid.Grid(container, gridOptions);
    
    // Store instance for later reference
    window.agGridInstances[containerId] = gridInstance;
    
    // Auto-size columns to fit content (with max width)
    setTimeout(() => {
        if (gridOptions.api) {
            gridOptions.api.sizeColumnsToFit();
        }
    }, 100);
    
    return gridInstance;
}

/**
 * Format column headers for display
 */
function formatColumnHeader(key) {
    // Convert snake_case to Title Case
    return key
        .replace(/_/g, ' ')
        .replace(/\b\w/g, char => char.toUpperCase());
}

/**
 * Format cell values based on data type
 */
function formatCellValue(value, columnKey) {
    if (value === null || value === undefined) {
        return '';
    }
    
    // Currency formatting
    if (columnKey.toLowerCase().includes('price') || 
        columnKey.toLowerCase().includes('cost') ||
        columnKey.toLowerCase().includes('revenue') ||
        columnKey.toLowerCase().includes('sales')) {
        if (typeof value === 'number') {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        }
    }
    
    // Percentage formatting
    if (columnKey.toLowerCase().includes('percent') || 
        columnKey.toLowerCase().includes('rate')) {
        if (typeof value === 'number') {
            return (value * 100).toFixed(2) + '%';
        }
    }
    
    // Number formatting
    if (typeof value === 'number') {
        return new Intl.NumberFormat('en-US').format(value);
    }
    
    // Date formatting
    if (value instanceof Date || 
        (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value))) {
        try {
            const date = new Date(value);
            return date.toLocaleDateString('en-US');
        } catch (e) {
            return value;
        }
    }
    
    return value;
}

/**
 * Update existing grid with new data
 */
function updateGrid(containerId, newData) {
    const gridInstance = window.agGridInstances[containerId];
    if (gridInstance && gridInstance.gridOptions && gridInstance.gridOptions.api) {
        gridInstance.gridOptions.api.setRowData(newData);
    } else {
        console.error('Grid instance not found for:', containerId);
    }
}

/**
 * Export grid data to CSV
 */
function exportGridToCSV(containerId, fileName = 'export.csv') {
    const gridInstance = window.agGridInstances[containerId];
    if (gridInstance && gridInstance.gridOptions && gridInstance.gridOptions.api) {
        gridInstance.gridOptions.api.exportDataAsCsv({
            fileName: fileName,
            allColumns: true
        });
    }
}

/**
 * Add search functionality to grid
 */
function addGlobalSearch(containerId, searchInputId) {
    const searchInput = document.getElementById(searchInputId);
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const gridInstance = window.agGridInstances[containerId];
            if (gridInstance && gridInstance.gridOptions && gridInstance.gridOptions.api) {
                gridInstance.gridOptions.api.setQuickFilter(e.target.value);
            }
        });
    }
}

/**
 * Refresh grid data from endpoint
 */
async function refreshGridFromEndpoint(containerId, endpoint) {
    try {
        const response = await fetch(endpoint);
        const data = await response.json();
        
        if (data.rows && data.columns) {
            updateGrid(containerId, data.rows);
        } else if (Array.isArray(data)) {
            updateGrid(containerId, data);
        }
    } catch (error) {
        console.error('Error refreshing grid:', error);
    }
}

/**
 * Initialize grid with loading state
 */
function initGridWithLoading(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.innerHTML = '<div class="text-center p-4">Loading data...</div>';
    }
}

// Export functions for use in other scripts
window.AGGridUtils = {
    initDataGrid,
    updateGrid,
    exportGridToCSV,
    addGlobalSearch,
    refreshGridFromEndpoint,
    initGridWithLoading,
    formatColumnHeader,
    formatCellValue
};
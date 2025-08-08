// static/js/chat.js - Chat functionality

class ChatManager {
    constructor() {
        this.currentMessageId = null;
        this.availableModels = {};
        this.init();
    }
    
    async init() {
        try {
            await this.loadModels();
            this.setupEventListeners();
            this.initializeSnapshotDate();
        } catch (error) {
            console.error('Chat initialization failed:', error);
            this.showError('Failed to initialize chat');
        }
    }
    
    initializeSnapshotDate() {
        // Set default snapshot date to yesterday
        const snapshotDateInput = document.getElementById('snapshotDate');
        if (snapshotDateInput) {
            const yesterday = new Date();
            yesterday.setDate(yesterday.getDate() - 1);
            // Format as YYYY-MM-DD
            const formattedDate = yesterday.toISOString().split('T')[0];
            snapshotDateInput.value = formattedDate;
            console.log('Default snapshot date set to:', formattedDate);
        }
    }
    
    async loadModels() {
        try {
            const response = await fetch('/api/chat/models');
            const data = await response.json();
            
            if (data.success) {
                this.availableModels = data.models;
                this.populateModelSelect(data.models);
                console.log('Models loaded successfully:', Object.keys(data.models));
            } else {
                console.error('Failed to load models:', data.error);
                const select = document.getElementById('modelSelect');
                select.innerHTML = '<option value="">Error loading models</option>';
            }
        } catch (error) {
            console.error('Error loading models:', error);
            const select = document.getElementById('modelSelect');
            select.innerHTML = '<option value="">Connection error</option>';
        }
    }
    
    populateModelSelect(models) {
        const select = document.getElementById('modelSelect');
        select.innerHTML = '';
        
        // Get enabled models from localStorage
        const enabledModels = this.getEnabledModels();
        const hasEnabledFilter = enabledModels.length > 0;
        
        const providers = {};
        
        Object.entries(models).forEach(([modelId, config]) => {
            // Skip if model is not enabled
            if (hasEnabledFilter && !enabledModels.includes(modelId)) {
                return;
            }
            
            const provider = config.provider || 'unknown';
            if (!providers[provider]) {
                providers[provider] = [];
            }
            providers[provider].push({ id: modelId, config });
        });
        
        Object.entries(providers).forEach(([provider, modelList]) => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = this.getProviderDisplayName(provider);
            
            modelList.forEach(({ id, config }) => {
                const option = document.createElement('option');
                option.value = id;
                option.textContent = config.name || config.description || id;
                option.setAttribute('data-provider', provider);
                option.title = config.description || '';
                optgroup.appendChild(option);
            });
            
            select.appendChild(optgroup);
        });
        
        // Set default model
        const defaultModel = 'gemini-2.5-pro'; // Match your config
        if (models[defaultModel]) {
            select.value = defaultModel;
        } else if (select.options.length > 0) {
            select.value = Object.keys(models)[0];
        }
    }
    
    getProviderDisplayName(provider) {
        const names = {
            'google': '🔵 Google Gemini',
            'xai': '🚀 X.AI (Grok)',
            'anthropic': '🟠 Anthropic Claude',
            'openai': '🟢 OpenAI GPT'
        };
        return names[provider] || `🔘 ${provider}`;
    }
    
    getEnabledModels() {
        const stored = localStorage.getItem('enabledModels');
        return stored ? JSON.parse(stored) : [];
    }
    
    setupEventListeners() {
        // Submit button
        const submitBtn = document.getElementById('submitButton');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => this.submitQuery());
        }
        
        // Enter key support
        const queryInput = document.getElementById('queryInput');
        if (queryInput) {
            queryInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.submitQuery();
                }
            });
        }
        
        // Export button
        const exportBtn = document.getElementById('exportButton');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.showExportDialog());
        }
        
        // Make updateModelDropdown available globally for config dialog
        window.updateModelDropdown = () => {
            this.loadModels();
        };
    }
    
    async submitQuery() {
        const input = document.getElementById('queryInput');
        const submitBtn = document.getElementById('submitButton');
        const query = input.value.trim();
        
        if (!query) return;
        
        const selectedModel = document.getElementById('modelSelect').value;
        
        if (!selectedModel) {
            this.addMessage('error', 'Please select an AI model from the dropdown.');
            return;
        }
        
        submitBtn.disabled = true;
        
        this.addMessage('user', query);
        input.value = '';
        
        document.getElementById('loadingModel').textContent = selectedModel;
        document.getElementById('loading').style.display = 'block';
        
        try {
            const requestBody = {
                query: query,
                model: selectedModel
            };
            
            // Add snapshot date if available
            const snapshotDateInput = document.getElementById('snapshotDate');
            console.log('Snapshot date input element:', snapshotDateInput);
            console.log('Snapshot date value:', snapshotDateInput ? snapshotDateInput.value : 'input not found');
            
            if (snapshotDateInput && snapshotDateInput.value) {
                requestBody.snapshot_date = snapshotDateInput.value;
                console.log('Adding snapshot_date to request:', snapshotDateInput.value);
            } else {
                console.log('No snapshot date provided');
            }
            
            const response = await fetch('/api/chat/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            document.getElementById('loading').style.display = 'none';
            submitBtn.disabled = false;
            
            if (data.success) {
                this.currentMessageId = Date.now();
                let responseContent = this.buildResponseContent(data, selectedModel);
                this.addMessage('assistant', responseContent, this.currentMessageId);
                
                document.getElementById('exportButton').disabled = !data.has_data;
            } else {
                let errorContent = this.buildErrorContent(data, selectedModel);
                this.addMessage('error', errorContent);
            }
            
        } catch (error) {
            console.error('Query execution failed:', error);
            
            document.getElementById('loading').style.display = 'none';
            submitBtn.disabled = false;
            
            let errorMessage = 'Connection error: ' + error.message;
            this.addMessage('error', errorMessage);
        }
    }
    
    buildResponseContent(data, modelName) {
        let content = '';
        
        if (data.has_data && data.row_count > 0) {
            content += `<div class="results-header">
                <span><strong>Query Results</strong></span>
                <span style="background: rgba(255, 255, 255, 0.7); padding: 4px 12px; border-radius: 20px; font-size: 0.9em;">${data.row_count.toLocaleString()} total rows</span>
            </div>`;
        }
        
        content += '<strong>Results:</strong><br/>';
        content += `<small style="color: #666;">Generated by ${modelName}</small>`;
        
        if (data.execution_times) {
            content += `<small style="color: #666; margin-left: 10px;">Total time: ${data.execution_times.total_ms}ms</small>`;
        }
        
        // Cost display removed
        
        content += '<br/>';
        
        if (data.toolbox_used && data.tool_name) {
            content += '<div style="background: rgba(139, 92, 246, 0.1); padding: 15px; border-radius: 8px; margin: 10px 0; font-size: 0.9em;">';
            content += '<strong>🔧 MCP Tool Used:</strong><br/>';
            content += `• Tool: ${data.tool_name}<br/>`;
            if (data.parameters) {
                content += `• Parameters: ${JSON.stringify(data.parameters, null, 1).replace(/\n/g, ' ')}<br/>`;
            }
            content += '</div>';
        }
        
        // Handle summary - either show it or show loading placeholder
        if (data.auto_summary) {
            content += '<div class="summary-box" style="margin: 10px 0;">';
            content += '<h4>🤖 AI Insights</h4>';
            content += data.auto_summary.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>');
            content += '</div>';
        } else if (data.summary_pending) {
            // Add placeholder for lazy loading
            content += `<div class="summary-box" id="summary-${data.query_id}" style="margin: 10px 0;">`;
            content += '<h4>🤖 AI Insights</h4>';
            content += '<div class="summary-loading">';
            content += '<div class="spinner" style="width: 10px; height: 10px; margin: 0 auto 10px;"></div>';
            content += '<p style="color: #667eea; margin: 0;">Generating insights...</p>';
            content += '</div>';
            content += '</div>';
            
            // Trigger lazy loading of summary
            setTimeout(() => {
                this.loadSummary(data.query_id, modelName);
            }, 100);
        }
        
        // Display results
        let resultsToDisplay = '';
        if (data.results_data && Array.isArray(data.results_data) && data.results_data.length > 0) {
            content += '<div class="results-table">' + this.createSortableTable(data.results_data) + '</div>';
        } else if (data.results) {
            content += '<div class="results-table">' + this.escapeHtml(data.results) + '</div>';
        }
        
        // AG-Grid handles all rows efficiently, no need for limiting message
        
        return content;
    }
    
    buildErrorContent(data, modelName) {
        let content = `<strong>Query failed:</strong> ${this.escapeHtml(data.error)}<br/><br/>`;
        content += `<strong>Model used:</strong> ${modelName}<br/>`;
        
        if (data.tool_name) {
            content += `<strong>MCP Tool:</strong> ${data.tool_name}<br/>`;
        }
        
        content += '<br/><strong>💡 Troubleshooting Tips:</strong><ul>';
        content += '<li>Try rephrasing your question</li>';
        content += '<li>Check if store/city names are spelled correctly</li>';
        content += '<li>Specify time periods clearly</li>';
        content += '<li>Try a different AI model</li>';
        content += '</ul>';
        
        return content;
    }
    
    createSortableTable(data) {
        if (!data || data.length === 0) return '<div class="no-data">No data available</div>';
        
        // Create a unique container ID for this AG-Grid instance
        const gridId = 'aggrid-' + Date.now();
        
        // Create container HTML with search box
        let html = '<div class="aggrid-wrapper">';
        html += '<div class="table-search-wrapper" style="margin-bottom: 10px;">';
        html += `<input type="text" class="form-control" id="search-${gridId}" placeholder="Search in table..." style="max-width: 300px; display: inline-block;">`;
        html += `<span class="ms-3">Total rows: ${data.length.toLocaleString()}</span>`;
        html += `<button class="btn btn-sm btn-outline-primary ms-3" onclick="window.AGGridUtils.exportGridToCSV('${gridId}', 'export.csv')">Export CSV</button>`;
        html += '</div>';
        html += `<div id="${gridId}" style="height: 600px; width: 100%;"></div>`;
        html += '</div>';
        
        // Initialize AG-Grid after a short delay to ensure DOM is ready
        setTimeout(() => {
            if (window.AGGridUtils && window.AGGridUtils.initDataGrid) {
                // Initialize the grid with all data (AG-Grid handles large datasets efficiently)
                window.AGGridUtils.initDataGrid(gridId, data);
                
                // Add global search functionality
                window.AGGridUtils.addGlobalSearch(gridId, `search-${gridId}`);
                
                console.log(`AG-Grid initialized for ${gridId} with ${data.length} rows`);
            } else {
                console.error('AG-Grid utilities not loaded');
                // Fallback to simple table if AG-Grid fails
                document.getElementById(gridId).innerHTML = this.createFallbackTable(data);
            }
        }, 100);
        
        return html;
    }
    
    // Fallback table creation method in case AG-Grid fails to load
    createFallbackTable(data) {
        if (!data || data.length === 0) return '<div class="no-data">No data available</div>';
        
        const headers = Object.keys(data[0]);
        const displayData = data.slice(0, 100); // Show more rows in fallback
        
        let html = '<div style="overflow-x: auto;">';
        html += '<table class="table table-striped table-hover">';
        html += '<thead><tr>';
        headers.forEach(header => {
            html += `<th>${this.formatHeaderName(header)}</th>`;
        });
        html += '</tr></thead>';
        html += '<tbody>';
        displayData.forEach(row => {
            html += '<tr>';
            headers.forEach(header => {
                html += `<td>${this.formatCellValue(row[header], header)}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody>';
        html += '</table>';
        if (data.length > displayData.length) {
            html += `<div class="text-center text-muted mt-2">Showing ${displayData.length} of ${data.length} rows</div>`;
        }
        html += '</div>';
        return html;
    }
    
    // New method for determining cell classes
    getNewCellClass(header, value) {
        const columnLower = header.toLowerCase();
        
        // Currency columns
        if ((columnLower.includes('cost') || columnLower.includes('revenue') || 
             columnLower.includes('price') || columnLower.includes('sales') ||
             columnLower.includes('profit')) && !columnLower.includes('margin')) {
            return 'value-currency';
        }
        
        // Percentage columns
        if (columnLower.includes('margin') || columnLower.includes('percent') || 
            columnLower.includes('pct') || columnLower.includes('%')) {
            return 'value-percentage';
        }
        
        // Numeric columns
        if (columnLower.includes('units') || columnLower.includes('count') || 
            columnLower.includes('quantity') || columnLower.includes('qty')) {
            return 'value-number';
        }
        
        return '';
    }
    
    formatHeaderName(header) {
        return header.replace(/_/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase())
                    .replace(/Pct/g, '%')
                    .replace(/Id/g, 'ID');
    }
    
    formatCellValue(value, column) {
        if (value === null || value === undefined) return '';
        
        const columnLower = column.toLowerCase();
        
        // Check for margin or percentage columns
        if (columnLower.includes('margin') || columnLower.includes('pct') || 
            columnLower.includes('percent') || columnLower.includes('%')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return `${num.toFixed(1)}%`;
            }
        }
        
        // Check for currency columns (but not margin!)
        if ((columnLower.includes('cost') || columnLower.includes('revenue') || 
             columnLower.includes('price') || columnLower.includes('profit') || 
             columnLower.includes('cogs')) && !columnLower.includes('margin')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return `$${num.toLocaleString()}`;
            }
        }
        
        // Check for unit/quantity columns
        if (columnLower.includes('units') || columnLower.includes('count') || 
            columnLower.includes('quantity')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return num.toLocaleString();
            }
        }
        
        return String(value);
    }
    
    getCellClass(column) {
        const columnLower = column.toLowerCase();
        
        // Check for margin or percentage columns
        if (columnLower.includes('margin') || columnLower.includes('pct') || 
            columnLower.includes('percent') || columnLower.includes('%')) {
            return 'percentage';
        }
        
        // Check for currency columns (but not margin!)
        if ((columnLower.includes('cost') || columnLower.includes('revenue') || 
             columnLower.includes('price') || columnLower.includes('profit') || 
             columnLower.includes('cogs')) && !columnLower.includes('margin')) {
            return 'currency';
        }
        
        // Check for unit columns
        if (columnLower.includes('units') || columnLower.includes('count') || 
            columnLower.includes('quantity')) {
            return 'units';
        }
        
        return '';
    }
    
    addMessage(type, content, messageId) {
        const chatHistory = document.getElementById('chatHistory');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-box ' + (type === 'user' ? 'user-query' : type === 'error' ? 'error' : 'assistant-response');
        if (messageId) {
            messageDiv.id = 'message-' + messageId;
        }
        
        if (type === 'user') {
            messageDiv.innerHTML = '<strong>You:</strong> ' + this.escapeHtml(content);
        } else {
            messageDiv.innerHTML = content;
        }
        
        messageDiv.style.opacity = '0';
        chatHistory.insertBefore(messageDiv, chatHistory.firstChild);
        setTimeout(() => {
            messageDiv.style.opacity = '1';
        }, 10);
        
        chatHistory.scrollTop = 0;
    }
    
    escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') {
            return String(unsafe);
        }
        
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    
    async loadSummary(queryId, modelName) {
        try {
            const response = await fetch('/api/chat/summary', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query_id: queryId,
                    model: modelName
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            const summaryDiv = document.getElementById(`summary-${queryId}`);
            
            if (!summaryDiv) return;
            
            if (data.success && data.summary) {
                // Replace loading with actual summary
                summaryDiv.innerHTML = `
                    <h4>🤖 AI Insights</h4>
                    ${data.summary.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>')}
                `;
            } else {
                // Show error state
                summaryDiv.innerHTML = `
                    <h4>🤖 AI Insights</h4>
                    <p style="color: #666; font-style: italic;">Unable to generate insights: ${data.error || 'Unknown error'}</p>
                `;
            }
        } catch (error) {
            console.error('Failed to load summary:', error);
            const summaryDiv = document.getElementById(`summary-${queryId}`);
            if (summaryDiv) {
                summaryDiv.innerHTML = `
                    <h4>🤖 AI Insights</h4>
                    <p style="color: #666; font-style: italic;">Failed to load insights</p>
                `;
            }
        }
    }
    
    showExportDialog() {
        document.getElementById('exportDialog').style.display = 'flex';
    }
    
    showError(message) {
        this.addMessage('error', message);
    }
    
    // Enhanced table search functionality
    searchTable(tableId, searchValue) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const tbody = table.querySelector('tbody');
        const rows = tbody.querySelectorAll('tr');
        const searchLower = searchValue.toLowerCase().trim();
        let visibleCount = 0;
        const totalRows = rows.length;
        
        rows.forEach(row => {
            let rowMatches = false;
            const cells = row.querySelectorAll('td');
            
            cells.forEach(td => {
                const cellText = td.textContent.toLowerCase();
                td.classList.remove('highlight');
                
                if (searchLower && cellText.includes(searchLower)) {
                    rowMatches = true;
                    td.classList.add('highlight');
                }
            });
            
            if (!searchLower || rowMatches) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });
        
        // Update the row count display
        const countElement = document.getElementById('count-' + tableId);
        if (countElement) {
            const tableInfo = this.tableData[tableId];
            const totalDataRows = tableInfo ? tableInfo.fullData.length : totalRows;
            
            if (searchLower) {
                countElement.textContent = `Found ${visibleCount} of ${totalRows} displayed rows (${totalDataRows} total)`;
            } else {
                countElement.textContent = `Showing ${totalRows} of ${totalDataRows} rows`;
            }
        }
    }
    
    // Enhanced table sorting functionality
    sortTable(tableId, column) {
        const table = document.getElementById(tableId);
        const tableInfo = this.tableData[tableId];
        if (!table || !tableInfo) return;
        
        // Find the header element
        const headers = table.querySelectorAll('thead th');
        let columnIndex = -1;
        let targetHeader = null;
        
        headers.forEach((header, index) => {
            if (header.dataset.column === column || header.textContent.toLowerCase().replace(/ /g, '_') === column.toLowerCase()) {
                columnIndex = index;
                targetHeader = header;
            }
            // Reset all headers
            header.classList.remove('sort-active', 'sort-asc', 'sort-desc');
        });
        
        if (columnIndex === -1 || !targetHeader) return;
        
        // Determine sort direction
        let sortDirection = 'asc';
        if (tableInfo.currentSort.column === column) {
            sortDirection = tableInfo.currentSort.direction === 'asc' ? 'desc' : 'asc';
        }
        
        // Update sort state
        tableInfo.currentSort = { column, direction: sortDirection };
        targetHeader.classList.add('sort-active', `sort-${sortDirection}`);
        
        // Sort the display data
        const sortedData = [...tableInfo.displayData].sort((a, b) => {
            let aVal = a[column];
            let bVal = b[column];
            
            // Handle null/undefined values
            if (aVal === null || aVal === undefined) aVal = '';
            if (bVal === null || bVal === undefined) bVal = '';
            
            // Try to parse as numbers
            const aNum = parseFloat(String(aVal).replace(/[$,%]/g, ''));
            const bNum = parseFloat(String(bVal).replace(/[$,%]/g, ''));
            
            if (!isNaN(aNum) && !isNaN(bNum)) {
                return sortDirection === 'asc' ? aNum - bNum : bNum - aNum;
            }
            
            // Fall back to string comparison
            const aStr = String(aVal).toLowerCase();
            const bStr = String(bVal).toLowerCase();
            
            if (sortDirection === 'asc') {
                return aStr.localeCompare(bStr);
            } else {
                return bStr.localeCompare(aStr);
            }
        });
        
        // Update the table body
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        
        sortedData.forEach((row, rowIndex) => {
            const tr = document.createElement('tr');
            tr.dataset.rowIndex = rowIndex;
            
            tableInfo.headers.forEach(header => {
                const td = document.createElement('td');
                const value = row[header];
                td.className = this.getNewCellClass(header, value);
                td.dataset.column = header;
                td.dataset.value = this.escapeHtml(String(value));
                td.innerHTML = this.formatCellValue(value, header);
                tr.appendChild(td);
            });
            
            tbody.appendChild(tr);
        });
        
        // Reapply search if active
        const searchInput = document.getElementById('search-' + tableId);
        if (searchInput && searchInput.value) {
            this.searchTable(tableId, searchInput.value);
        }
    }
    
    getColumnIndex(table, columnName) {
        const headers = table.querySelectorAll('th');
        for (let i = 0; i < headers.length; i++) {
            const headerText = headers[i].textContent.toLowerCase().replace(/ /g, '_');
            if (headerText === columnName.toLowerCase()) {
                return i;
            }
        }
        return 0;
    }
    
    // Detect if table needs horizontal scrolling
    detectTableScroll(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const wrapper = table.closest('.table-responsive-wrapper');
        const scrollContainer = table.closest('.table-scroll-container');
        
        if (!wrapper || !scrollContainer) return;
        
        // Check if table is wider than container
        const needsScroll = table.scrollWidth > scrollContainer.clientWidth;
        
        if (needsScroll) {
            // Add a visual indicator that the table can be scrolled
            if (!wrapper.querySelector('.scroll-indicator')) {
                const indicator = document.createElement('div');
                indicator.className = 'scroll-indicator active';
                indicator.innerHTML = '← Scroll to see more →';
                wrapper.style.position = 'relative';
                wrapper.appendChild(indicator);
                
                // Hide indicator after first scroll
                scrollContainer.addEventListener('scroll', function() {
                    if (this.scrollLeft > 10) {
                        indicator.classList.remove('active');
                    }
                }, { once: true });
            }
        }
        
        console.log(`Table ${tableId} scroll detection:`, {
            tableWidth: table.scrollWidth,
            containerWidth: scrollContainer.clientWidth,
            needsScroll: needsScroll
        });
    }
}

// Initialize chat when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatManager = new ChatManager();
});

// Global functions for template compatibility
function submitQuery() {
    if (window.chatManager) {
        window.chatManager.submitQuery();
    }
}

function showExportDialog() {
    if (window.chatManager) {
        window.chatManager.showExportDialog();
    }
}

function closeExportDialog() {
    document.getElementById('exportDialog').style.display = 'none';
}

function exportData(format) {
    // Implement export functionality
    console.log('Export format:', format);
    closeExportDialog();
}

// Query History Functions Removed
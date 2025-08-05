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
        
        if (data.estimated_cost !== undefined) {
            content += `<small style="color: #666; margin-left: 10px;">Cost: ${data.estimated_cost.toFixed(4)}</small>`;
        }
        
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
        
        if (data.has_data && data.row_count > 20) {
            content += `<div style="color: #666; font-style: italic; margin-top: 10px; text-align: center;">`;
            content += `Showing first 20 rows of ${data.row_count.toLocaleString()} total results`;
            content += `</div>`;
        }
        
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
        if (!data || data.length === 0) return 'No data available';
        
        const headers = Object.keys(data[0]);
        const tableId = 'table-' + Date.now();
        
        // Create wrapper with search box
        let html = '<div class="table-wrapper">';
        
        // Add search box on the left
        html += '<div class="table-search-container">';
        html += '<div class="table-search-box">';
        html += `<input type="text" id="search-${tableId}" placeholder="Search table..." onkeyup="window.chatManager.searchTable('${tableId}', this.value)">`;
        html += '<span class="search-icon">🔍</span>';
        html += '</div>';
        html += '<span class="search-results-count" id="search-count-${tableId}" style="color: #6b7280; font-size: 14px;"></span>';
        html += '</div>';
        
        // Start table container
        html += '<div class="table-container" id="container-' + tableId + '">';
        html += `<table class="sortable-table" id="${tableId}">`;
        
        // Create header
        html += '<thead><tr>';
        headers.forEach(header => {
            const displayName = this.formatHeaderName(header);
            html += `<th class="sortable" onclick="window.chatManager.sortTable('${tableId}', '${header}')">${displayName}</th>`;
        });
        html += '</tr></thead>';
        
        // Create body
        html += '<tbody>';
        data.slice(0, 20).forEach((row, index) => {
            html += `<tr data-row-index="${index}">`;
            headers.forEach(header => {
                const value = row[header];
                const formattedValue = this.formatCellValue(value, header);
                const cellClass = this.getCellClass(header);
                html += `<td class="${cellClass}" data-column="${header}">${formattedValue}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        html += '</div>'; // Close table-container
        html += '</div>'; // Close table-wrapper
        
        // Store data for sorting
        if (!this.tableData) this.tableData = {};
        this.tableData[tableId] = data.slice(0, 20);
        
        // Check for scroll after render
        setTimeout(() => this.checkTableScroll(tableId), 100);
        
        return html;
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
    
    // Table search functionality
    searchTable(tableId, searchValue) {
        const table = document.getElementById(tableId);
        if (!table) return;
        
        const rows = table.querySelectorAll('tbody tr');
        const searchLower = searchValue.toLowerCase();
        let visibleCount = 0;
        
        rows.forEach(row => {
            let rowText = '';
            row.querySelectorAll('td').forEach(td => {
                rowText += td.textContent.toLowerCase() + ' ';
            });
            
            if (rowText.includes(searchLower)) {
                row.style.display = '';
                visibleCount++;
                
                // Highlight matching cells
                row.querySelectorAll('td').forEach(td => {
                    const cellText = td.textContent.toLowerCase();
                    if (searchValue && cellText.includes(searchLower)) {
                        td.classList.add('highlight');
                    } else {
                        td.classList.remove('highlight');
                    }
                });
            } else {
                row.style.display = 'none';
            }
        });
        
        // Update count
        const countElement = document.getElementById('search-count-' + tableId);
        if (countElement) {
            if (searchValue) {
                countElement.textContent = `${visibleCount} of ${rows.length} rows`;
            } else {
                countElement.textContent = '';
            }
        }
    }
    
    // Table sorting functionality
    sortTable(tableId, column) {
        const table = document.getElementById(tableId);
        if (!table || !this.tableData || !this.tableData[tableId]) return;
        
        // Get current sort state
        const th = table.querySelector(`th:nth-child(${this.getColumnIndex(table, column) + 1})`);
        const currentSort = th.dataset.sort || 'none';
        let newSort = currentSort === 'asc' ? 'desc' : 'asc';
        
        // Reset all headers
        table.querySelectorAll('th').forEach(header => {
            header.dataset.sort = 'none';
            header.classList.remove('sort-asc', 'sort-desc');
        });
        
        // Sort data
        const sortedData = [...this.tableData[tableId]].sort((a, b) => {
            let aVal = a[column];
            let bVal = b[column];
            
            // Handle numeric values
            if (!isNaN(aVal) && !isNaN(bVal)) {
                aVal = parseFloat(aVal);
                bVal = parseFloat(bVal);
            }
            
            if (newSort === 'asc') {
                return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
            } else {
                return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
            }
        });
        
        // Update header
        th.dataset.sort = newSort;
        th.classList.add(newSort === 'asc' ? 'sort-asc' : 'sort-desc');
        
        // Re-render table body
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        
        sortedData.forEach((row, index) => {
            const tr = document.createElement('tr');
            tr.dataset.rowIndex = index;
            
            Object.keys(row).forEach(header => {
                const td = document.createElement('td');
                td.className = this.getCellClass(header);
                td.dataset.column = header;
                const formattedValue = this.formatCellValue(row[header], header);
                td.textContent = typeof formattedValue === 'string' ? formattedValue : String(formattedValue);
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
    
    // Check if table needs scroll indicators
    checkTableScroll(tableId) {
        const container = document.getElementById('container-' + tableId);
        if (!container) return;
        
        const hasHorizontalScroll = container.scrollWidth > container.clientWidth;
        const hasVerticalScroll = container.scrollHeight > container.clientHeight;
        
        if (hasHorizontalScroll || hasVerticalScroll) {
            container.classList.add('has-scroll');
        } else {
            container.classList.remove('has-scroll');
        }
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

// Query History Functions
let queryHistoryOpen = false;

function toggleQueryHistory() {
    queryHistoryOpen = !queryHistoryOpen;
    const tray = document.getElementById('queryHistoryTray');
    
    if (queryHistoryOpen) {
        tray.classList.add('open');
        loadQueryHistory();
    } else {
        tray.classList.remove('open');
    }
}

function closeQueryHistory() {
    queryHistoryOpen = false;
    document.getElementById('queryHistoryTray').classList.remove('open');
}

async function loadQueryHistory() {
    const historyList = document.getElementById('queryHistoryList');
    historyList.innerHTML = '<div style="text-align: center; padding: 20px;">Loading...</div>';
    
    try {
        const response = await fetch('/api/chat/queries?limit=50');
        const data = await response.json();
        
        if (data.success && data.queries) {
            displayQueryHistory(data.queries);
        } else {
            historyList.innerHTML = '<div style="text-align: center; padding: 20px; color: #6c757d;">No query history available</div>';
        }
    } catch (error) {
        console.error('Failed to load query history:', error);
        historyList.innerHTML = '<div style="text-align: center; padding: 20px; color: #dc3545;">Failed to load history</div>';
    }
}

function displayQueryHistory(queries) {
    const historyList = document.getElementById('queryHistoryList');
    
    if (queries.length === 0) {
        historyList.innerHTML = '<div style="text-align: center; padding: 20px; color: #6c757d;">No queries yet</div>';
        return;
    }
    
    historyList.innerHTML = queries.map(query => {
        const time = new Date(query.timestamp).toLocaleString();
        const status = query.success ? '✅' : '❌';
        const rowCount = query.row_count !== null ? `${query.row_count} rows` : 'No data';
        
        return `
            <div class="query-history-item" onclick="rerunQuery('${encodeURIComponent(query.user_query)}')">
                <div class="query-history-time">${time}</div>
                <div class="query-history-text">${query.user_query}</div>
                <div class="query-history-meta">
                    <span>${status} ${rowCount}</span>
                    <span>${query.tool_name || query.model_name || 'Unknown'}</span>
                </div>
            </div>
        `;
    }).join('');
}

function rerunQuery(encodedQuery) {
    const query = decodeURIComponent(encodedQuery);
    document.getElementById('queryInput').value = query;
    closeQueryHistory();
    submitQuery();
}

// Auto-refresh query history when a new query is submitted
const originalSubmitQuery = window.submitQuery;
window.submitQuery = async function() {
    const result = await originalSubmitQuery.apply(this, arguments);
    
    // Refresh query history if the tray is open
    if (queryHistoryOpen) {
        setTimeout(() => loadQueryHistory(), 1000);
    }
    
    return result;
}
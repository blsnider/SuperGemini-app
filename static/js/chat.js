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
        } catch (error) {
            console.error('Chat initialization failed:', error);
            this.showError('Failed to initialize chat');
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
        
        const providers = {};
        
        Object.entries(models).forEach(([modelId, config]) => {
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
        
        if (data.auto_summary) {
            content += '<div class="summary-box" style="margin: 20px 0;">';
            content += '<h4>🤖 AI Insights (Auto-Generated)</h4>';
            content += data.auto_summary.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br/>');
            content += '</div>';
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
        let html = '<table class="sortable-table">';
        
        // Create header
        html += '<thead><tr>';
        headers.forEach(header => {
            const displayName = this.formatHeaderName(header);
            html += `<th class="sortable">${displayName}</th>`;
        });
        html += '</tr></thead>';
        
        // Create body
        html += '<tbody>';
        data.slice(0, 20).forEach(row => {
            html += '<tr>';
            headers.forEach(header => {
                const value = row[header];
                const formattedValue = this.formatCellValue(value, header);
                const cellClass = this.getCellClass(header);
                html += `<td class="${cellClass}">${formattedValue}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        
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
        
        if (column.includes('pct') || column.includes('percent')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return `${num.toFixed(1)}%`;
            }
        }
        
        if (column.includes('cost') || column.includes('revenue') || column.includes('price')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return `$${num.toLocaleString()}`;
            }
        }
        
        if (column.includes('units') || column.includes('count')) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return num.toLocaleString();
            }
        }
        
        return String(value);
    }
    
    getCellClass(column) {
        if (column.includes('pct') || column.includes('percent')) return 'percentage';
        if (column.includes('cost') || column.includes('revenue') || column.includes('price')) return 'currency';
        if (column.includes('units') || column.includes('count')) return 'units';
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
    
    showExportDialog() {
        document.getElementById('exportDialog').style.display = 'flex';
    }
    
    showError(message) {
        this.addMessage('error', message);
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
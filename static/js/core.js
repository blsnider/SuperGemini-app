// static/js/core.js - Core functionality

// Sidebar functionality
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');
    const overlay = document.getElementById('sidebarOverlay');
    const healthIndicator = document.getElementById('healthIndicator');
    
    sidebar.classList.toggle('open');
    toggle.classList.toggle('open');
    overlay.classList.toggle('open');
    healthIndicator.classList.toggle('sidebar-open');
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.getElementById('sidebarToggle');
    const overlay = document.getElementById('sidebarOverlay');
    const healthIndicator = document.getElementById('healthIndicator');
    
    sidebar.classList.remove('open');
    toggle.classList.remove('open');
    overlay.classList.remove('open');
    healthIndicator.classList.remove('sidebar-open');
}

// Health check functionality
async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        
        const indicator = document.getElementById('healthIndicator');
        const status = document.getElementById('healthStatus');
        
        if (data.status === 'healthy') {
            indicator.className = 'health-indicator healthy';
            status.textContent = '✅ System Healthy';
        } else {
            indicator.className = 'health-indicator unhealthy';
            status.textContent = '❌ System Issues';
        }
    } catch (error) {
        const indicator = document.getElementById('healthIndicator');
        const status = document.getElementById('healthStatus');
        indicator.className = 'health-indicator unhealthy';
        status.textContent = '⚠️ Connection Error';
    }
}

// History management
async function clearHistory() {
    try {
        const response = await fetch('/clear_history', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            loadHistory();
        }
    } catch (error) {
        console.error('Error clearing history:', error);
    }
}

async function loadHistory() {
    const historyPanel = document.getElementById('historyPanel');
    if (!historyPanel) return;
    
    historyPanel.innerHTML = '<div style="text-align: center; color: #666; font-size: 0.9em;">Loading...</div>';
    
    try {
        const response = await fetch('/api/chat/queries?limit=20');
        const data = await response.json();
        
        if (data.success && data.queries && data.queries.length > 0) {
            let historyHtml = '<div class="history-list">';
            
            data.queries.forEach((query, index) => {
                const timestamp = new Date(query.timestamp).toLocaleString();
                const truncatedQuery = query.query.length > 50 ? 
                    query.query.substring(0, 50) + '...' : query.query;
                
                historyHtml += `
                    <div class="history-item" style="padding: 8px; margin-bottom: 5px; border-radius: 4px; background: #f8f9fa; cursor: pointer; font-size: 0.85em;" 
                         onclick="loadHistoryQuery('${encodeURIComponent(query.query)}')">
                        <div style="font-weight: 500; color: #333;">${truncatedQuery}</div>
                        <div style="font-size: 0.8em; color: #666; margin-top: 2px;">${timestamp}</div>
                    </div>
                `;
            });
            
            historyHtml += '</div>';
            historyPanel.innerHTML = historyHtml;
        } else {
            historyPanel.innerHTML = '<div style="text-align: center; color: #666; font-size: 0.9em;">No queries yet</div>';
        }
    } catch (error) {
        console.error('Failed to load query history:', error);
        historyPanel.innerHTML = '<div style="text-align: center; color: #dc3545; font-size: 0.9em;">Failed to load history</div>';
    }
}

// Load a query from history
function loadHistoryQuery(encodedQuery) {
    const query = decodeURIComponent(encodedQuery);
    // Check if we're on the chat page
    const queryInput = document.getElementById('queryInput');
    if (queryInput) {
        queryInput.value = query;
        // Focus the input
        queryInput.focus();
    } else {
        // Navigate to chat page with query
        window.location.href = '/chat?q=' + encodeURIComponent(query);
    }
}

// Global function to refresh query history (can be called from other scripts)
window.refreshQueryHistory = function() {
    loadHistory();
}

// Initialize core functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Core functionality initialized');
    checkHealth();
    loadHistory();
    
    // Check health every 30 seconds
    setInterval(checkHealth, 30000);
    
    // Refresh history every 10 seconds if sidebar is open
    setInterval(() => {
        const sidebar = document.getElementById('sidebar');
        if (sidebar && sidebar.classList.contains('open')) {
            loadHistory();
        }
    }, 10000);
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeSidebar();
    }
});
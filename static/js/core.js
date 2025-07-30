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
    // Placeholder for history loading
    console.log('History loading not implemented yet');
}

// Initialize core functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Core functionality initialized');
    checkHealth();
    
    // Check health every 30 seconds
    setInterval(checkHealth, 30000);
});

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeSidebar();
    }
});
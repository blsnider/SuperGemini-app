// static/js/core.js - Core functionality

// Loading State Management
class LoadingManager {
    static show() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.add('active');
        }
    }
    
    static hide() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
}

// Toast Notification System
class ToastManager {
    static show(message, type = 'info', duration = 3000) {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const closeBtn = document.createElement('button');
        closeBtn.className = 'toast-close';
        closeBtn.textContent = '×';
        closeBtn.onclick = () => toast.remove();
        
        const msgText = document.createElement('div');
        msgText.textContent = message;
        
        toast.appendChild(closeBtn);
        toast.appendChild(msgText);
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
    
    static success(message) {
        this.show(message, 'success');
    }
    
    static error(message) {
        this.show(message, 'error', 5000);
    }
    
    static warning(message) {
        this.show(message, 'warning', 4000);
    }
}

// Safe Fetch with Loading and Error Handling
async function safeFetch(url, options = {}) {
    LoadingManager.show();
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();
        LoadingManager.hide();
        return data;
    } catch (error) {
        LoadingManager.hide();
        console.error('Fetch error:', error);
        ToastManager.error(`Request failed: ${error.message}`);
        throw error;
    }
}

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

// Query history functionality removed

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
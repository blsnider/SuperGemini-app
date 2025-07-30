// static/js/navigation.js - Navigation between pages

class NavigationManager {
    constructor() {
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.updateActiveNavigation();
    }
    
    setupEventListeners() {
        // Handle navigation button clicks
        document.addEventListener('click', (e) => {
            // Chat navigation
            if (e.target.matches('[data-nav="chat"]') || e.target.closest('[data-nav="chat"]')) {
                e.preventDefault();
                this.navigateToChat();
            }
            
            // Dashboard navigation
            if (e.target.matches('[data-nav="dashboard"]') || e.target.closest('[data-nav="dashboard"]')) {
                e.preventDefault();
                this.navigateToDashboard();
            }
            
            // Handle legacy function calls
            if (e.target.matches('.nav-button') || e.target.closest('.nav-button')) {
                const button = e.target.closest('.nav-button') || e.target;
                const text = button.textContent.toLowerCase();
                
                if (text.includes('chat')) {
                    e.preventDefault();
                    this.navigateToChat();
                } else if (text.includes('dashboard') || text.includes('analytics')) {
                    e.preventDefault();
                    this.navigateToDashboard();
                }
            }
        });
        
        // Handle keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
                e.preventDefault();
                this.navigateToDashboard();
            }
            
            if ((e.ctrlKey || e.metaKey) && e.key === 'h') {
                e.preventDefault();
                this.navigateToChat();
            }
        });
    }
    
    navigateToChat() {
        console.log('Navigating to chat...');
        window.location.href = '/chat';
    }
    
    navigateToDashboard() {
        console.log('Navigating to dashboard...');
        window.location.href = '/dashboard';
    }
    
    updateActiveNavigation() {
        // Update active state based on current page
        const currentPath = window.location.pathname;
        const navButtons = document.querySelectorAll('.nav-button');
        
        navButtons.forEach(button => {
            button.classList.remove('active');
            
            const text = button.textContent.toLowerCase();
            if (currentPath.includes('/chat') && text.includes('chat')) {
                button.classList.add('active');
            } else if ((currentPath === '/' || currentPath.includes('/dashboard')) && 
                       (text.includes('dashboard') || text.includes('analytics'))) {
                button.classList.add('active');
            }
        });
    }
}

// Global navigation functions for template compatibility
function showChatView() {
    console.log('showChatView called - redirecting to chat page');
    window.location.href = '/chat';
}

function showDashboard() {
    console.log('showDashboard called - redirecting to dashboard page');
    window.location.href = '/dashboard';
}

// Legacy functions that might be called from templates
function navigateToChat() {
    window.location.href = '/chat';
}

function navigateToDashboard() {
    window.location.href = '/dashboard';
}

// Initialize navigation when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.navigationManager = new NavigationManager();
    console.log('Navigation manager initialized');
});

// Debug function to check what buttons exist
function debugNavigation() {
    console.log('=== Navigation Debug ===');
    console.log('Current path:', window.location.pathname);
    
    const navButtons = document.querySelectorAll('.nav-button');
    console.log('Found nav buttons:', navButtons.length);
    
    navButtons.forEach((button, index) => {
        console.log(`Button ${index}:`, {
            text: button.textContent.trim(),
            classes: button.className,
            onclick: button.onclick ? 'has onclick' : 'no onclick'
        });
    });
    
    const sidebarButtons = document.querySelectorAll('button');
    console.log('All buttons:', sidebarButtons.length);
}
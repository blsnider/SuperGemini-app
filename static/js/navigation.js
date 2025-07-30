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

// Model Configuration Functions
let allModels = {};

function showModelConfig() {
    // Load all available models first
    fetch('/api/chat/models')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.models) {
                allModels = data.models;
                populateModelConfig();
                document.getElementById('modelConfigDialog').style.display = 'flex';
            }
        })
        .catch(error => console.error('Error loading models:', error));
}

function populateModelConfig() {
    const modelConfigList = document.getElementById('modelConfigList');
    const enabledModels = getEnabledModels();
    
    modelConfigList.innerHTML = '';
    
    Object.entries(allModels).forEach(([modelId, modelInfo]) => {
        const isEnabled = enabledModels.length === 0 || enabledModels.includes(modelId);
        
        const modelItem = document.createElement('div');
        modelItem.style.cssText = 'padding: 10px; border-bottom: 1px solid #e0e7ff; display: flex; align-items: center;';
        
        modelItem.innerHTML = `
            <label style="display: flex; align-items: center; width: 100%; cursor: pointer;">
                <input type="checkbox" id="model_${modelId}" value="${modelId}" 
                       ${isEnabled ? 'checked' : ''} 
                       style="margin-right: 10px;">
                <div style="flex: 1;">
                    <strong>${modelId}</strong>
                    <div style="font-size: 0.85em; color: #666; margin-top: 2px;">
                        ${modelInfo.description || 'No description available'}
                    </div>
                </div>
            </label>
        `;
        
        modelConfigList.appendChild(modelItem);
    });
}

function saveModelConfig() {
    const checkboxes = document.querySelectorAll('#modelConfigList input[type="checkbox"]');
    const enabledModels = [];
    
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            enabledModels.push(checkbox.value);
        }
    });
    
    // Save to localStorage
    localStorage.setItem('enabledModels', JSON.stringify(enabledModels));
    
    // Update the model dropdown if on chat page
    if (window.updateModelDropdown) {
        window.updateModelDropdown();
    }
    
    closeModelConfig();
}

function closeModelConfig() {
    document.getElementById('modelConfigDialog').style.display = 'none';
}

function getEnabledModels() {
    const stored = localStorage.getItem('enabledModels');
    return stored ? JSON.parse(stored) : [];
}
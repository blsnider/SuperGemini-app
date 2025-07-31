SuperGemini Project Overview

  Based on my analysis, here's a comprehensive overview of your project:

  🎯 Project Purpose

  SuperGemini is an AI-powered retail analytics platform specifically built for Scheels sporting goods. It
   transforms natural language business questions into actionable insights by intelligently querying
  BigQuery data warehouses and presenting results through an intuitive interface.

  🏗️ Architecture Highlights

  Three-Tier Architecture:
  1. Frontend: Modern web interface with chat and dashboard views
  2. Backend: Flask API server with MCP integration
  3. Data Layer: BigQuery warehouse with retail data marts

  Key Design Patterns:
  - API-first architecture (/api/* endpoints)
  - Microservices approach (MCP Toolbox as separate service)
  - Multi-provider AI strategy for reliability
  - Lazy loading for performance optimization

  💡 Core Features

  1. Natural Language Analytics
    - Convert questions like "What are my top selling items?" into SQL
    - 13 specialized MCP tools for different analytics needs
    - Smart parameter extraction from queries
  2. Multi-Model AI Support
    - 11 AI models across 4 providers (Google, X.AI, Anthropic, OpenAI)
    - Cost tracking and optimization
    - Model recommendation based on query type
  3. Executive Dashboard
    - Real-time KPI metrics
    - Interactive tool grid with lazy-loaded data
    - Store/shop filtering capabilities
    - Summary statistics separation (v2.4.0 update)
  4. Advanced Data Visualization
    - Smart table formatting with currency/percentage detection
    - Interactive charts via Plotly
    - Export capabilities (CSV, Excel)

  🔧 Technical Stack

  Backend Technologies:
  - Flask 3.1.1 with Gunicorn
  - Google Cloud Platform (BigQuery, Secret Manager, Cloud Run)
  - MCP Toolbox 0.1.7 for analytics
  - Pandas/PyArrow for data processing

  Frontend Technologies:
  - Vanilla JavaScript (no framework dependencies)
  - Modern CSS with responsive design
  - Chart.js for visualizations
  - Real-time features (WebSocket-ready)

  📊 Data Integration

  BigQuery Structure:
  scheels-data-marts/
  ├── facts_sales.fct_sales (transactions)
  ├── dim_scheels.dim_skus (products)
  ├── dim_inventory.mart_inventory_snapshots (stock levels)
  └── utility_data.mart_stores (locations)

  MCP Tools Coverage:
  - Sales analysis (top sellers, trends, margins)
  - Inventory management (stock levels, out-of-stock, overstock)
  - Performance comparisons (stores, time periods, shops)
  - Risk assessment (inventory at risk, sell-through rates)

  🚀 Recent Updates (v2.4.1)

  1. Summary Statistics Fix: Separated aggregate stats from row data
  2. Dashboard Metrics: Fixed Apply button functionality
  3. Version Badge: Added version indicator across all pages
  4. MCP Default Parameters: Tools now use their own defaults

  📁 Project Structure

  SuperGemini/
  ├── app.py                 # Main Flask application
  ├── chatbot/
  │   ├── core.py           # Core analytics engine
  │   ├── tools.yaml        # MCP tool definitions
  │   └── config.py         # Configuration management
  ├── templates/
  │   ├── base.html         # Base template with navigation
  │   ├── index.html        # Main chat interface
  │   ├── chat.html         # Legacy chat page
  │   └── dashboard.html    # Analytics dashboard
  ├── static/
  │   ├── css/              # Styling
  │   └── js/               # Frontend logic
  └── deployment/
      ├── Dockerfile        # Container configuration
      └── deploy scripts    # GCP deployment automation

  🔐 Security & Access

  - Service account authentication for GCP resources
  - Unauthenticated MCP Toolbox access (internal only)
  - API key management via environment variables
  - Future: User authentication planned

  🎨 UI/UX Features

  - Responsive Design: Works on all devices
  - Real-time Status: Health indicators and loading states
  - Smart Suggestions: Query history and auto-complete
  - Cost Tracking: Monitor API usage costs
  - Keyboard Shortcuts: Power user features

  🚧 Areas for Enhancement

  1. Performance: Add Redis caching, connection pooling
  2. Security: Implement user auth, query auditing
  3. Features: Scheduled reports, ML forecasting
  4. Operations: Better monitoring, automated testing

  This is a sophisticated, production-ready platform that effectively bridges the gap between complex data
   infrastructure and business user needs. The recent updates have significantly improved the user
  experience and data presentation.
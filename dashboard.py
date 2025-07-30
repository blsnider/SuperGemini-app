# dashboard.py - Dashboard Backend Logic
from typing import Dict, List, Any
import time
import logging

logger = logging.getLogger(__name__)

class DashboardManager:
    """Manages dashboard data and API responses"""
    
    def __init__(self, config=None):
        # Use the same config pattern as your existing app
        if config is None:
            from dataclasses import dataclass
            import os
            
            @dataclass
            class AppConfig:
                bq_project: str = os.getenv('BQ_PROJECT', 'sis-data-marts')
                model_name: str = os.getenv('DEFAULT_MODEL', 'gemini-2.5-pro')
                preview_rows: int = int(os.getenv('PREVIEW_ROWS', '20'))
            
            config = AppConfig()
        
        self.config = config
        # Initialize chatbot for MCP tool access
        from chatbot import SuperGeminiRetailChatbot
        self.chatbot = SuperGeminiRetailChatbot(config)
    
    def get_executive_kpis(self) -> Dict[str, Any]:
        """Get high-level KPIs for executive dashboard using MCP tools"""
        try:
            logger.info("Fetching executive KPIs...")
            
            # Get today's sales
            sales_result = self._get_mcp_data('get_sales_trends', {
                'period': 'daily',
                'limit': 1
            })
            
            # Get margin items for average margin calculation
            margin_result = self._get_mcp_data('get_top_margin_items', {
                'limit': 50
            })
            
            # Get inventory status
            inventory_result = self._get_mcp_data('get_inventory_status', {
                'limit': 100
            })
            
            # Get out of stock items
            out_of_stock_result = self._get_mcp_data('get_out_of_stock_items', {
                'limit': 20
            })
            
            # Calculate KPIs
            kpis = {
                'today_revenue': self._calculate_today_revenue(sales_result),
                'average_margin': self._calculate_average_margin(margin_result),
                'inventory_health': self._calculate_inventory_health(inventory_result, out_of_stock_result),
                'alerts_count': self._count_alerts(out_of_stock_result, inventory_result)
            }
            
            logger.info(f"Executive KPIs fetched successfully: {kpis}")
            return kpis
            
        except Exception as e:
            logger.error(f"Error fetching executive KPIs: {e}")
            # Return default values
            return {
                'today_revenue': {'value': 0, 'unit': '$', 'trend': 0},
                'average_margin': {'value': 0, 'unit': '%', 'trend': 0},
                'inventory_health': {'value': 0, 'unit': '%', 'status': 'unknown'},
                'alerts_count': {'value': 0, 'unit': 'alerts', 'critical': 0}
            }
    
    def get_sales_trends(self, period: str, store_id: int = 0) -> List[Dict]:
        """Get sales trends data for visualization"""
        try:
            logger.info(f"Fetching sales trends for period: {period}, store: {store_id}")
            
            # Use MCP tool to get sales trends
            trends_data = self._get_mcp_data('get_sales_trends', {
                'period': period,
                'store_id': store_id if store_id > 0 else None,
                'limit': 30
            })
            
            # Format for chart
            formatted_trends = self._format_trends_for_chart(trends_data)
            return formatted_trends
            
        except Exception as e:
            logger.error(f"Error fetching sales trends: {e}")
            return []
    
    def get_top_performers(self, limit: int = 10, store_id: int = 0) -> List[Dict]:
        """Get top performing items"""
        try:
            logger.info(f"Fetching top performers, limit: {limit}, store: {store_id}")
            
            # Use MCP tool to get top selling items
            performers_data = self._get_mcp_data('get_top_selling_items', {
                'store_id': store_id if store_id > 0 else None,
                'limit': limit
            })
            
            # Format for UI
            formatted_performers = self._format_performers_for_ui(performers_data)
            return formatted_performers
            
        except Exception as e:
            logger.error(f"Error fetching top performers: {e}")
            return []
    
    def get_stock_alerts(self) -> Dict[str, List]:
        """Get stock alerts for out of stock and overstock items"""
        try:
            logger.info("Fetching stock alerts...")
            
            # Get out of stock items
            out_of_stock = self._get_mcp_data('get_out_of_stock_items', {'limit': 20})
            
            # Get overstock items
            overstock = self._get_mcp_data('get_overstock_items', {'limit': 20})
            
            # Format alerts
            alerts = {
                'out_of_stock': self._format_stock_alerts(out_of_stock, 'out_of_stock'),
                'overstock': self._format_stock_alerts(overstock, 'overstock')
            }
            
            logger.info(f"Stock alerts fetched: {len(alerts['out_of_stock'])} OOS, {len(alerts['overstock'])} overstock")
            return alerts
            
        except Exception as e:
            logger.error(f"Error fetching stock alerts: {e}")
            return {'out_of_stock': [], 'overstock': []}
    
    def get_regional_performance(self) -> List[Dict]:
        """Get regional/store performance comparison"""
        try:
            logger.info("Fetching regional performance...")
            
            # Use comparison analysis tool
            comparison_data = self._get_mcp_data('get_comparison_analysis', {
                'compare_by': 'store',
                'limit': 10
            })
            
            # Format for UI
            formatted_performance = self._format_regional_performance(comparison_data)
            return formatted_performance
            
        except Exception as e:
            logger.error(f"Error fetching regional performance: {e}")
            return []
    
    # Helper Methods
    def _get_mcp_data(self, tool_name: str, params: Dict) -> List[Dict]:
        """Execute MCP tool and get results"""
        try:
            # Map tool parameters to query
            query = self._build_query_from_tool(tool_name, params)
            
            # Use chatbot to execute query
            result = self.chatbot.chat(query, model_name=self.config.model_name)
            
            if result.get('success') and result.get('has_data'):
                return result.get('results', [])
            else:
                logger.warning(f"MCP tool {tool_name} returned no data")
                return []
                
        except Exception as e:
            logger.error(f"Error executing MCP tool {tool_name}: {e}")
            return []
    
    def _build_query_from_tool(self, tool_name: str, params: Dict) -> str:
        """Build natural language query from tool name and parameters"""
        queries = {
            'get_sales_trends': lambda p: f"Show me sales trends for {p.get('period', 'daily')} period",
            'get_top_margin_items': lambda p: f"Get top {p.get('limit', 50)} items by margin",
            'get_inventory_status': lambda p: f"Show inventory status for top {p.get('limit', 100)} items",
            'get_out_of_stock_items': lambda p: f"Show {p.get('limit', 20)} out of stock items",
            'get_overstock_items': lambda p: f"Show {p.get('limit', 20)} overstock items",
            'get_top_selling_items': lambda p: f"Get top {p.get('limit', 10)} selling items",
            'get_comparison_analysis': lambda p: "Compare performance by store"
        }
        
        if tool_name in queries:
            return queries[tool_name](params)
        else:
            return f"Execute {tool_name} with parameters {params}"
    
    def _calculate_today_revenue(self, sales_data: List[Dict]) -> Dict:
        """Calculate today's revenue from sales data"""
        if not sales_data:
            return {'value': 0, 'unit': '$', 'trend': 0}
        
        # Get most recent day's revenue
        today_revenue = sales_data[0].get('total_revenue', 0) if sales_data else 0
        
        # Calculate trend if we have previous day
        trend = 0
        if len(sales_data) > 1:
            yesterday_revenue = sales_data[1].get('total_revenue', 0)
            if yesterday_revenue > 0:
                trend = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
        
        return {
            'value': round(today_revenue, 2),
            'unit': '$',
            'trend': round(trend, 1)
        }
    
    def _calculate_average_margin(self, margin_data: List[Dict]) -> Dict:
        """Calculate average margin from margin data"""
        if not margin_data:
            return {'value': 0, 'unit': '%', 'trend': 0}
        
        # Calculate average margin
        total_margin = sum(item.get('margin_pct', 0) for item in margin_data)
        avg_margin = total_margin / len(margin_data) if margin_data else 0
        
        return {
            'value': round(avg_margin, 1),
            'unit': '%',
            'trend': 0  # TODO: Calculate trend from historical data
        }
    
    def _calculate_inventory_health(self, inventory: List[Dict], out_of_stock: List[Dict]) -> Dict:
        """Calculate inventory health percentage"""
        total_items = len(inventory) if inventory else 100
        oos_items = len(out_of_stock) if out_of_stock else 0
        
        health_pct = ((total_items - oos_items) / total_items * 100) if total_items > 0 else 0
        
        status = 'good' if health_pct >= 95 else 'warning' if health_pct >= 90 else 'critical'
        
        return {
            'value': round(health_pct, 1),
            'unit': '%',
            'status': status
        }
    
    def _count_alerts(self, out_of_stock: List[Dict], inventory: List[Dict]) -> Dict:
        """Count total alerts and critical alerts"""
        oos_count = len(out_of_stock) if out_of_stock else 0
        
        # Count critical items (high velocity or high margin out of stock)
        critical_count = sum(1 for item in out_of_stock 
                           if item.get('units_sold_l30d', 0) > 100 
                           or item.get('margin_pct', 0) > 40) if out_of_stock else 0
        
        return {
            'value': oos_count,
            'unit': 'alerts',
            'critical': critical_count
        }
    
    def _format_trends_for_chart(self, trends_data: List[Dict]) -> List[Dict]:
        """Format trends data for chart display"""
        if not trends_data:
            return []
        
        formatted = []
        for item in trends_data:
            formatted.append({
                'date': item.get('date', item.get('period', '')),
                'revenue': round(item.get('total_revenue', 0), 2),
                'units': item.get('total_units', 0),
                'transactions': item.get('transaction_count', 0)
            })
        
        return formatted
    
    def _format_regional_performance(self, comparison_data: List[Dict]) -> List[Dict]:
        """Format regional/store performance data"""
        if not comparison_data:
            return []
        
        formatted = []
        for item in comparison_data:
            formatted.append({
                'id': item.get('store_id', item.get('region_id', 0)),
                'name': item.get('store_name', item.get('region_name', 'Unknown')),
                'revenue': round(item.get('total_revenue', 0), 2),
                'growth': round(item.get('growth_pct', 0), 1),
                'units': item.get('total_units', 0)
            })
        
        return formatted
    
    def _format_performers_for_ui(self, performers: List[Dict]) -> List[Dict]:
        """Format top performers for UI display"""
        if not performers:
            return []
        
        formatted = []
        for idx, item in enumerate(performers[:10]):  # Top 10 only
            formatted.append({
                'rank': idx + 1,
                'sku': item.get('sku', ''),
                'description': item.get('description', 'Unknown Item'),
                'revenue': round(item.get('total_revenue', 0), 2),
                'units': item.get('units_sold', 0),
                'margin': round(item.get('margin_pct', 0), 1)
            })
        
        return formatted
    
    def _format_stock_alerts(self, alerts_data: List[Dict], alert_type: str) -> List[Dict]:
        """Format stock alerts for UI display"""
        if not alerts_data:
            return []
        
        formatted = []
        for item in alerts_data[:10]:  # Limit to 10 alerts
            alert = {
                'sku': item.get('sku', ''),
                'description': item.get('description', 'Unknown Item'),
                'store': item.get('store_name', 'All Stores'),
                'severity': 'high' if item.get('units_sold_l30d', 0) > 100 else 'medium'
            }
            
            if alert_type == 'out_of_stock':
                alert['days_out'] = item.get('days_out_of_stock', 0)
                alert['lost_sales'] = round(item.get('lost_sales_estimate', 0), 2)
            else:  # overstock
                alert['excess_units'] = item.get('excess_units', 0)
                alert['excess_value'] = round(item.get('excess_value', 0), 2)
            
            formatted.append(alert)
        
        return formatted
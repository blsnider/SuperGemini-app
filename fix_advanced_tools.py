#!/usr/bin/env python3
"""
Fix advanced tools by removing unused snapshot_date parameters
"""

import yaml
import re

def fix_tools_yaml():
    """Remove unused snapshot_date from advanced tools"""
    
    # Tools that don't actually use @snapshot_date in their SQL
    tools_to_fix = [
        'get_advanced_inventory_turnover',
        'get_advanced_stockout_analysis', 
        'get_advanced_carrying_costs',
        'get_advanced_gmroi_performance',
        'get_advanced_vendor_metrics',
        'get_advanced_forecast_accuracy'
    ]
    
    with open('chatbot/tools.yaml', 'r') as f:
        content = f.read()
    
    # Load as YAML to process
    tools_config = yaml.safe_load(content)
    
    fixed_count = 0
    for tool_name in tools_to_fix:
        if tool_name in tools_config['tools']:
            tool = tools_config['tools'][tool_name]
            
            # Check if SQL actually uses @snapshot_date
            sql = tool.get('statement', '')
            if '@snapshot_date' not in sql:
                # Remove snapshot_date from parameters
                original_params = tool.get('parameters', [])
                new_params = [p for p in original_params if p.get('name') != 'snapshot_date']
                
                if len(new_params) < len(original_params):
                    tool['parameters'] = new_params
                    fixed_count += 1
                    print(f"✅ Fixed {tool_name} - removed unused snapshot_date parameter")
    
    # Write back
    with open('chatbot/tools.yaml', 'w') as f:
        yaml.dump(tools_config, f, default_flow_style=False, sort_keys=False, width=1000)
    
    print(f"\n✅ Fixed {fixed_count} tools")
    
    # Also check for other potential issues
    print("\n🔍 Checking for other potential issues...")
    
    # Check if any tools have both string defaults "" and null
    for tool_name, tool in tools_config['tools'].items():
        params = tool.get('parameters', [])
        for param in params:
            if param.get('type') == 'string' and param.get('default') == "":
                sql = tool.get('statement', '')
                param_name = param.get('name')
                # Check if SQL uses IS NULL check
                if f'@{param_name} IS NULL' in sql:
                    print(f"⚠️  {tool_name}: parameter '{param_name}' has default \"\" but SQL checks for IS NULL")

if __name__ == "__main__":
    fix_tools_yaml()
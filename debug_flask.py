#!/usr/bin/env python3
"""Debug Flask's template loading"""

import sys
import os
sys.path.insert(0, '/home/user/SuperGemini')

# Set up minimal environment
os.environ['FLASK_APP'] = 'app.py'

try:
    from flask import Flask
    
    # Create a minimal Flask app to test template loading
    test_app = Flask(__name__, 
                     template_folder='/home/user/SuperGemini/templates',
                     static_folder='/home/user/SuperGemini/static')
    
    print("Flask configuration:")
    print(f"  Template folder: {test_app.template_folder}")
    print(f"  Static folder: {test_app.static_folder}")
    print(f"  Root path: {test_app.root_path}")
    
    # Check if Flask can find the templates
    from jinja2 import Environment, FileSystemLoader
    loader = FileSystemLoader(test_app.template_folder)
    env = Environment(loader=loader)
    
    print("\nTemplates Flask can see:")
    for template in loader.list_templates():
        print(f"  - {template}")
    
    # Try to load base.html
    print("\nLoading base.html template...")
    source, filename, uptodate = loader.get_source(env, 'base.html')
    
    if 'v3.0.0' in source:
        print("✓ Version 3.0.0 found in template loaded by Flask")
    else:
        print("✗ Version 3.0.0 NOT found in template loaded by Flask")
    
    if 'ff6b6b' in source:
        print("✓ Red color found in template loaded by Flask")
    else:
        print("✗ Red color NOT found in template loaded by Flask")
        
    print(f"\nTemplate file path Flask is using: {filename}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
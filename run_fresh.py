#!/usr/bin/env python3
"""Run Flask app with fresh environment to ensure latest files are served"""

import os
import sys
import subprocess
import time

print("=" * 60)
print("FRESH FLASK STARTUP SCRIPT")
print("=" * 60)

# Kill any existing Flask processes
print("\n1. Killing any existing Flask/Python app processes...")
os.system("pkill -f 'python.*app.py' 2>/dev/null")
os.system("pkill -f 'flask run' 2>/dev/null")
os.system("pkill -f 'gunicorn' 2>/dev/null")
time.sleep(2)

# Clear all Python cache
print("\n2. Clearing Python cache...")
os.system("find /home/user/SuperGemini -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null")
os.system("find /home/user/SuperGemini -name '*.pyc' -delete 2>/dev/null")

# Set environment to prevent caching
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = '1'
os.environ['FLASK_APP'] = '/home/user/SuperGemini/app.py'

# Verify files have changes
print("\n3. Verifying file changes are present...")
with open('/home/user/SuperGemini/static/css/main.css', 'r') as f:
    css_content = f.read()
    if '#ff6b6b' in css_content:
        print("   ✓ Soft red colors confirmed in CSS")
    else:
        print("   ✗ WARNING: Soft red colors NOT found in CSS!")

with open('/home/user/SuperGemini/templates/base.html', 'r') as f:
    html_content = f.read()
    if 'v3.0.0' in html_content:
        print("   ✓ Version 3.0.0 confirmed in HTML")
    else:
        print("   ✗ WARNING: Version 3.0.0 NOT found in HTML!")

print("\n4. Starting Flask with explicit paths...")
print("   Working directory:", os.getcwd())
print("   Flask app path:", os.environ['FLASK_APP'])
print("   Python path:", sys.executable)

# Change to app directory
os.chdir('/home/user/SuperGemini')

print("\n" + "=" * 60)
print("Starting Flask server...")
print("Access at: http://localhost:8080")
print("You should see: Soft red theme + v3.0.0 badge")
print("Press Ctrl+C to stop")
print("=" * 60 + "\n")

# Run Flask with no bytecode compilation
subprocess.run([sys.executable, '-B', 'app.py'])
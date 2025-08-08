#!/usr/bin/env python3
"""Run on a different port to bypass Cloud Workstations caching"""

import os
import sys
import time
import random

# Use a random port to bypass caching
port = random.randint(8100, 8200)

print("=" * 60)
print("BYPASSING CLOUD WORKSTATIONS CACHE")
print("=" * 60)
print(f"\nUsing port {port} to bypass proxy cache")

# Kill existing processes
os.system("pkill -9 -f 'python.*app.py' 2>/dev/null")
time.sleep(1)

# Set up environment
os.environ['FLASK_APP'] = 'app.py'
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = '1'
os.environ['PORT'] = str(port)

print("\nFile verification:")
with open('static/css/main.css', 'r') as f:
    if '#ff6b6b' in f.read():
        print("✓ Red theme confirmed in CSS")

with open('templates/base.html', 'r') as f:
    if 'v3.0.0' in f.read():
        print("✓ Version 3.0.0 confirmed")

print("\n" + "=" * 60)
print(f"Starting Flask on port {port}")
print(f"Access at: http://localhost:{port}/static/test.html")
print(f"CloudWS URL: https://{port}-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/")
print("=" * 60)

# Modify app.py temporarily to use the new port
with open('app.py', 'r') as f:
    app_content = f.read()

# Run with the new port
import subprocess
subprocess.run([sys.executable, '-c', f"""
import os
os.environ['PORT'] = '{port}'
{app_content}
"""])
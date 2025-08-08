#!/usr/bin/env python3
"""Debug script to understand Cloud Workstations serving issue"""

import os
import sys
import subprocess
import hashlib

print("=" * 60)
print("CLOUD WORKSTATIONS DEBUG")
print("=" * 60)

# Check environments
print("\n1. Environment Variables:")
print(f"   PWD: {os.getcwd()}")
print(f"   HOME: {os.environ.get('HOME', 'not set')}")
print(f"   VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', 'not set')}")
print(f"   Python executable: {sys.executable}")

# Check for multiple Python environments
print("\n2. Python Environments Found:")
subprocess.run("find /home/user/SuperGemini -type d -name 'venv' -o -name '.venv' -o -name 'env' -o -name '.env' | head -10", shell=True)

# Check actual file content with checksums
print("\n3. File Checksums (to verify content):")
files_to_check = [
    '/home/user/SuperGemini/static/css/main.css',
    '/home/user/SuperGemini/templates/base.html',
    '/home/user/SuperGemini/static/test.html'
]

for filepath in files_to_check:
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
            checksum = hashlib.md5(content).hexdigest()
            
        # Check for specific content
        text_content = content.decode('utf-8', errors='ignore')
        has_red = '#ff6b6b' in text_content
        has_v3 = 'v3.0.0' in text_content
        has_purple = '#667eea' in text_content or '#764ba2' in text_content
        
        print(f"\n   {filepath}:")
        print(f"     MD5: {checksum}")
        print(f"     Has red theme: {has_red}")
        print(f"     Has v3.0.0: {has_v3}")
        print(f"     Has old purple: {has_purple}")
        print(f"     File size: {len(content)} bytes")
        print(f"     Modified: {subprocess.check_output(['stat', '-c', '%y', filepath]).decode().strip()}")

# Check if there are any symlinks or mounts
print("\n4. Checking for symlinks or special mounts:")
subprocess.run("ls -la /home/user/SuperGemini/ | grep '^l'", shell=True)
subprocess.run("mount | grep SuperGemini", shell=True)

# Check Cloud Workstations specific paths
print("\n5. Cloud Workstations paths:")
print(f"   /home/user/.cloudworkstations exists: {os.path.exists('/home/user/.cloudworkstations')}")
print(f"   /home/user/.codeoss-cloudworkstations exists: {os.path.exists('/home/user/.codeoss-cloudworkstations')}")

# Check for any proxy or redirect configs
print("\n6. Checking for proxy configs:")
subprocess.run("env | grep -i proxy", shell=True)
subprocess.run("env | grep -i workstation", shell=True)

print("\n" + "=" * 60)
print("DIAGNOSIS:")
print("=" * 60)
print("\nPossible issues:")
print("1. Cloud Workstations might be caching at the proxy level")
print("2. Multiple Python environments might be conflicting")
print("3. There might be a symlink or mount redirecting files")
print("\nSolution to try:")
print("1. Stop all Python processes: pkill -f python")
print("2. Remove ALL virtual environments: rm -rf venv .venv")
print("3. Run directly with system Python: /usr/bin/python3 app.py")
print("4. Access via direct IP if possible instead of CloudWorkstations URL")
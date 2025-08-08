#!/usr/bin/env python3
"""Serve actual SuperGemini files directly without Flask"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import mimetypes

class DirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Map URLs to actual files
        if self.path == '/':
            file_path = 'templates/base.html'
        elif self.path.startswith('/static/'):
            file_path = self.path[1:]  # Remove leading /
        else:
            file_path = 'templates' + self.path
        
        # Security check
        file_path = os.path.join('/home/user/SuperGemini', file_path)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            # Read and serve the file
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # If it's HTML, inject a verification banner
            if file_path.endswith('.html'):
                verification = b'''
                <div style="position:fixed; top:0; left:0; right:0; background:#ff6b6b; color:white; padding:10px; text-align:center; z-index:9999;">
                    DIRECT SERVE TEST - You should see RED theme below! Time: <script>document.write(new Date().toLocaleTimeString());</script>
                </div>
                '''
                content = content.replace(b'<body>', b'<body>' + verification)
            
            self.send_response(200)
            mime_type, _ = mimetypes.guess_type(file_path)
            self.send_header('Content-Type', mime_type or 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, f"File not found: {self.path}")
    
    def log_message(self, format, *args):
        pass  # Suppress logs

print("=" * 60)
print("DIRECT FILE SERVER (No Flask)")
print("=" * 60)
print("\nThis serves your actual files directly, bypassing Flask entirely.")

# Verify files
print("\nFile verification:")
with open('static/css/main.css', 'r') as f:
    css = f.read()
    if '#ff6b6b' in css:
        print("✓ Red color #ff6b6b found in main.css")
    else:
        print("✗ Red color NOT found in main.css")

with open('templates/base.html', 'r') as f:
    html = f.read()
    if 'v3.0.0' in html:
        print("✓ Version 3.0.0 found in base.html")
    else:
        print("✗ Version NOT found in base.html")

print("\n" + "=" * 60)
print("Server running on port 9090")
print("\nTest these URLs:")
print("https://9090-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/")
print("https://9090-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/static/css/main.css")
print("=" * 60)

server = HTTPServer(('0.0.0.0', 9090), DirectHandler)
server.serve_forever()
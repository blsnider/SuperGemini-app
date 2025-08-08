#!/usr/bin/env python3
"""Ultra-simple test to verify if ANY changes work"""

HTML_CONTENT = '''<!DOCTYPE html>
<html>
<head>
    <title>SIMPLE TEST</title>
    <style>
        body {
            background: #ff6b6b;
            color: white;
            font-size: 48px;
            text-align: center;
            padding: 100px;
            font-family: Arial;
        }
    </style>
</head>
<body>
    <h1>🔴 RED = WORKING 🔴</h1>
    <p>If this is RED, changes are working!</p>
    <p>If this is BLUE/PURPLE, something is cached!</p>
    <hr>
    <p style="font-size: 24px;">Direct test - No Flask, No templates</p>
</body>
</html>'''

# Simple HTTP server
from http.server import HTTPServer, BaseHTTPRequestHandler

class TestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs

print("Starting SIMPLE test server on port 7777")
print("Access at: https://7777-w-blsnider-mdk8d0vt.cluster-rg4hlmqyybggwv6jmu3tg6wun6.cloudworkstations.dev/")
print("This serves a RED page directly. If you see BLUE, Cloud Workstations is caching.")

server = HTTPServer(('0.0.0.0', 7777), TestHandler)
server.serve_forever()
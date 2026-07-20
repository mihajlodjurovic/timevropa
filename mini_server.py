"""Minimal HTTP file server on port 8090."""
import http.server, socketserver, os, socket, sys

PORT = 8090
DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

httpd = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
print(f"http://0.0.0.0:{PORT}", flush=True)
httpd.serve_forever()

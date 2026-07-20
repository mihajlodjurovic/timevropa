"""
seeze_europe server
===================
Serves the reasoning engine HTML + handles binary data compilation from MongoDB.
Usage:  python server.py
Open:   http://localhost:8080
"""

import http.server
import json
import os
import socket
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs

PORT = 8090
DIR = os.path.dirname(os.path.abspath(__file__))
META_FILE = os.path.join(DIR, "europe_lakehouse_meta.json")
DATA_FILE = os.path.join(DIR, "europe_lakehouse_data.bin")
BUILD_SCRIPT = os.path.join(os.path.dirname(DIR), "europe", "bitno", "build_europe_lakehouse.py")

# Compilation state
_build_state = {"status": "idle", "progress": "", "started_at": None, "error": None}
_build_lock = threading.Lock()


def run_build():
    """Run the build script in a subprocess, capture output for progress."""
    global _build_state
    import subprocess

    with _build_lock:
        if _build_state["status"] == "running":
            return
        _build_state = {"status": "running", "progress": "Starting build...", "started_at": time.time(), "error": None}

    try:
        python_exe = os.path.join(os.path.expanduser("~/miniconda3"), "envs", "djura", "bin", "python")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(os.path.expanduser("~/miniconda3"), "bin", "python")

        proc = subprocess.Popen(
            [python_exe, BUILD_SCRIPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=DIR,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        output_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            # Keep last 10 lines for progress display
            recent = output_lines[-10:]
            with _build_lock:
                _build_state["progress"] = "\n".join(recent)

        try:
            proc.wait(timeout=600)  # 10 minute timeout
        except subprocess.TimeoutExpired:
            proc.kill()
            with _build_lock:
                _build_state["status"] = "error"
                _build_state["error"] = "Build timed out after 10 minutes"
                _build_state["progress"] = _build_state["error"]
            return

        if proc.returncode == 0 and os.path.exists(META_FILE) and os.path.exists(DATA_FILE):
            with _build_lock:
                _build_state["status"] = "done"
                _build_state["progress"] = "Build complete. Data files ready."
        else:
            with _build_lock:
                _build_state["status"] = "error"
                _build_state["error"] = f"Build failed (exit {proc.returncode}):\n" + "\n".join(output_lines[-20:])
                _build_state["progress"] = _build_state["error"]
    except Exception as e:
        with _build_lock:
            _build_state["status"] = "error"
            _build_state["error"] = str(e)
            _build_state["progress"] = str(e)


def get_build_status():
    with _build_lock:
        return dict(_build_state)


class ReuseHTTPServer(http.server.HTTPServer):
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: build status
        if path == "/api/status":
            self._json(get_build_status())
            return

        # Check if data files exist, serve info
        if path == "/api/data-info":
            info = {
                "meta_exists": os.path.exists(META_FILE),
                "data_exists": os.path.exists(DATA_FILE),
                "meta_size": os.path.getsize(META_FILE) if os.path.exists(META_FILE) else 0,
                "data_size": os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 0,
            }
            if info["meta_exists"]:
                try:
                    with open(META_FILE) as f:
                        meta = json.load(f)
                    info["listing_count"] = meta.get("listing_count", 0)
                    info["segment_count"] = meta.get("segment_count", 0)
                    info["country_count"] = meta.get("country_count", 0)
                except Exception:
                    pass
            self._json(info)
            return

        # Serve static files
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/compile":
            status = get_build_status()
            if status["status"] == "running":
                self._json({"status": "already_running", "message": "Build is already in progress"})
                return

            # Start build in background thread
            t = threading.Thread(target=run_build, daemon=True)
            t.start()
            self._json({"status": "started", "message": "Build started"})
            return

        self.send_error(404)

    def _json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter logging
        if "/api/" not in (args[0] if args else ""):
            super().log_message(format, *args)


def main():
    # Ensure we're in the right directory
    os.chdir(DIR)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║               seeze.eu · Deal Discovery Engine               ║
╠══════════════════════════════════════════════════════════════╣
║  Server:  http://localhost:{PORT}                            ║
║  API:     http://localhost:{PORT}/api/compile   (POST)       ║
║           http://localhost:{PORT}/api/status    (GET)        ║
║           http://localhost:{PORT}/api/data-info (GET)        ║
╠══════════════════════════════════════════════════════════════╣
║  Step 1:  Open the URL in your browser                      ║
║  Step 2:  Click "Compile & Load" to build the index         ║
║  Step 3:  Explore 1M European listings                      ║
╚══════════════════════════════════════════════════════════════╝
""")

    server = ReuseHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()

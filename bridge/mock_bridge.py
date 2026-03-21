#!/usr/bin/env python3
"""
Mock bridge server: runs on the HOST for development/testing.
Same HTTP interface as bridge_server.py but prints to console instead of ROS2.

Usage:
    python3 mock_bridge.py [--port 8765]
"""

import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

MAX_LINEAR_VEL = 0.5
MAX_ANGULAR_VEL = 0.5

last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length))


def _respond(handler: BaseHTTPRequestHandler, code: int, body: dict):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.end_headers()
    handler.wfile.write(json.dumps(body).encode())


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global last_cmd
        try:
            data = _read_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _respond(self, 400, {"error": f"Bad JSON: {e}"})
            return

        if self.path == "/move":
            vx = max(-MAX_LINEAR_VEL, min(MAX_LINEAR_VEL, float(data.get("vx", 0.0))))
            vy = max(-MAX_LINEAR_VEL, min(MAX_LINEAR_VEL, float(data.get("vy", 0.0))))
            vyaw = max(-MAX_ANGULAR_VEL, min(MAX_ANGULAR_VEL, float(data.get("vyaw", 0.0))))
            last_cmd = {"vx": vx, "vy": vy, "vyaw": vyaw}
            print(f"[MOCK] MOVE  vx={vx:.2f}  vy={vy:.2f}  vyaw={vyaw:.2f}")
            _respond(self, 200, {"ok": True, "vx": vx, "vy": vy, "vyaw": vyaw})

        elif self.path == "/stop":
            last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            print("[MOCK] STOP")
            _respond(self, 200, {"ok": True, "stopped": True})

        elif self.path == "/key":
            key = data.get("key", "")
            if not key:
                _respond(self, 400, {"error": "Missing 'key' field"})
                return
            print(f"[MOCK] KEY   '{key}'")
            _respond(self, 200, {"ok": True, "key": key})

        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def do_GET(self):
        if self.path == "/status":
            _respond(self, 200, {
                "ok": True,
                "last_cmd": last_cmd,
                "mock": True,
                "max_linear_vel": MAX_LINEAR_VEL,
                "max_angular_vel": MAX_ANGULAR_VEL,
            })
        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format, *args):
        pass  # suppress default HTTP logging


def main():
    parser = argparse.ArgumentParser(description="Mock bridge server (no ROS2)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", args.port), MockHandler)
    print(f"[MOCK] Bridge server listening on http://127.0.0.1:{args.port}")
    print("[MOCK] Endpoints: POST /move, /stop, /key  |  GET /status")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MOCK] Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

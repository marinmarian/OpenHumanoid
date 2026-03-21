#!/usr/bin/env python3
"""
Bridge server: runs INSIDE the WBC Docker container.
Receives HTTP commands from the host, publishes to ROS2 topics.

Dependencies: Python stdlib + rclpy (already in the Docker image).
Zero pip installs needed.

Usage:
    python3 bridge_server.py [--port 8765]
"""

import json
import sys
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String, Float32MultiArray
except ImportError:
    print("\n[bridge_server] ERROR: rclpy not found. Source ROS2 first:")
    print('  docker exec <container> bash -c "source /opt/ros/humble/setup.bash && python3 /tmp/bridge_server.py"')
    sys.exit(1)

KEYBOARD_INPUT_TOPIC = "/keyboard_input"
NAV_CMD_TOPIC = "/nav_cmd"

MAX_LINEAR_VEL = 0.5
MAX_ANGULAR_VEL = 0.5


class BridgeNode(Node):
    def __init__(self):
        super().__init__("bridge_server")
        self.key_pub = self.create_publisher(String, KEYBOARD_INPUT_TOPIC, 10)
        self.nav_pub = self.create_publisher(Float32MultiArray, NAV_CMD_TOPIC, 10)
        self.last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
        self.get_logger().info(
            f"Bridge server ROS2 node ready. "
            f"Publishing to {KEYBOARD_INPUT_TOPIC} and {NAV_CMD_TOPIC}"
        )

    def publish_key(self, key: str):
        msg = String()
        msg.data = key
        self.key_pub.publish(msg)
        self.get_logger().info(f"Published key: {key}")

    def publish_nav(self, vx: float, vy: float, vyaw: float):
        vx = max(-MAX_LINEAR_VEL, min(MAX_LINEAR_VEL, vx))
        vy = max(-MAX_LINEAR_VEL, min(MAX_LINEAR_VEL, vy))
        vyaw = max(-MAX_ANGULAR_VEL, min(MAX_ANGULAR_VEL, vyaw))

        msg = Float32MultiArray()
        msg.data = [float(vx), float(vy), float(vyaw)]
        self.nav_pub.publish(msg)
        self.last_cmd = {"vx": vx, "vy": vy, "vyaw": vyaw}
        self.get_logger().info(f"Published nav: vx={vx:.2f} vy={vy:.2f} vyaw={vyaw:.2f}")

    def publish_stop(self):
        self.publish_nav(0.0, 0.0, 0.0)
        self.get_logger().info("STOP command issued")


bridge_node: BridgeNode = None


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


class BridgeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            data = _read_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _respond(self, 400, {"error": f"Bad JSON: {e}"})
            return

        if self.path == "/move":
            vx = float(data.get("vx", 0.0))
            vy = float(data.get("vy", 0.0))
            vyaw = float(data.get("vyaw", 0.0))
            bridge_node.publish_nav(vx, vy, vyaw)
            _respond(self, 200, {"ok": True, "vx": vx, "vy": vy, "vyaw": vyaw})

        elif self.path == "/stop":
            bridge_node.publish_stop()
            _respond(self, 200, {"ok": True, "stopped": True})

        elif self.path == "/key":
            key = data.get("key", "")
            if not key:
                _respond(self, 400, {"error": "Missing 'key' field"})
                return
            bridge_node.publish_key(key)
            _respond(self, 200, {"ok": True, "key": key})

        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def do_GET(self):
        if self.path == "/status":
            _respond(self, 200, {
                "ok": True,
                "last_cmd": bridge_node.last_cmd,
                "max_linear_vel": MAX_LINEAR_VEL,
                "max_angular_vel": MAX_ANGULAR_VEL,
            })
        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format, *args):
        bridge_node.get_logger().debug(f"HTTP: {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Bridge HTTP→ROS2 server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    rclpy.init()
    global bridge_node
    bridge_node = BridgeNode()

    spin_thread = threading.Thread(target=rclpy.spin, args=(bridge_node,), daemon=True)
    spin_thread.start()

    server = HTTPServer(("0.0.0.0", args.port), BridgeHandler)
    bridge_node.get_logger().info(f"Bridge HTTP server listening on 0.0.0.0:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge_node.get_logger().info("Shutting down bridge server")
        server.server_close()
        bridge_node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

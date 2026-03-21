#!/usr/bin/env python3
"""
Bridge server: runs INSIDE the WBC Docker container.
Receives HTTP commands from the host, translates them into keyboard events
published on the /keyboard_input ROS2 topic.

The G1GearWbcPolicy processes these keys:
  ]  = activate policy    o  = deactivate policy
  w/s = forward/backward (+/-0.2 per press)
  a/d = strafe left/right (+/-0.2 per press)
  q/e = rotate left/right (+/-0.2 per press)
  z   = reset all velocities to zero

Dependencies: Python stdlib + rclpy (already in the Docker image).
Zero pip installs needed.

Usage (inside the WBC container):
    python3 bridge_server.py [--port 8765]

IMPORTANT: The control loop must be started with --keyboard-dispatcher-type ros
so that it subscribes to /keyboard_input instead of reading from stdin.
"""

import json
import math
import sys
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
except ImportError:
    print("\n[bridge_server] ERROR: rclpy not found. Source ROS2 first:")
    print('  docker exec <container> bash -c "source /opt/ros/humble/setup.bash && python3 /tmp/bridge_server.py"')
    sys.exit(1)

KEYBOARD_INPUT_TOPIC = "/keyboard_input"
VEL_STEP = 0.2


class BridgeNode(Node):
    def __init__(self):
        super().__init__("bridge_server")
        self.key_pub = self.create_publisher(String, KEYBOARD_INPUT_TOPIC, 10)
        self.last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
        self.get_logger().info(
            f"Bridge server ROS2 node ready. Publishing to {KEYBOARD_INPUT_TOPIC}"
        )

    def publish_key(self, key: str):
        msg = String()
        msg.data = key
        self.key_pub.publish(msg)

    def publish_key_sequence(self, keys: list[str]):
        """Publish a sequence of keyboard events."""
        for key in keys:
            self.publish_key(key)

    def velocity_to_keys(self, vx: float, vy: float, vyaw: float) -> list[str]:
        """Translate absolute velocities into a key sequence.

        Always starts with 'z' (reset) then adds the right number of
        directional presses to reach the desired velocity.
        """
        keys = ["z"]

        def _repeat(positive_key: str, negative_key: str, value: float):
            n = round(abs(value) / VEL_STEP)
            key = positive_key if value > 0 else negative_key
            return [key] * n

        keys += _repeat("w", "s", vx)
        keys += _repeat("a", "d", vy)
        keys += _repeat("q", "e", vyaw)
        return keys

    def move(self, vx: float, vy: float, vyaw: float):
        keys = self.velocity_to_keys(vx, vy, vyaw)
        self.publish_key_sequence(keys)
        self.last_cmd = {"vx": vx, "vy": vy, "vyaw": vyaw}
        self.get_logger().info(
            f"MOVE vx={vx:.2f} vy={vy:.2f} vyaw={vyaw:.2f} → keys={keys}"
        )

    def stop(self):
        self.publish_key("z")
        self.last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
        self.get_logger().info("STOP → key='z'")

    def activate(self):
        self.publish_key("]")
        self.get_logger().info("ACTIVATE → key=']'")

    def deactivate(self):
        self.publish_key("o")
        self.get_logger().info("DEACTIVATE → key='o'")


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
            bridge_node.move(vx, vy, vyaw)
            _respond(self, 200, {"ok": True, "vx": vx, "vy": vy, "vyaw": vyaw})

        elif self.path == "/stop":
            bridge_node.stop()
            _respond(self, 200, {"ok": True, "stopped": True})

        elif self.path == "/activate":
            bridge_node.activate()
            _respond(self, 200, {"ok": True, "activated": True})

        elif self.path == "/deactivate":
            bridge_node.deactivate()
            _respond(self, 200, {"ok": True, "deactivated": True})

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
                "vel_step": VEL_STEP,
            })
        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format, *args):
        bridge_node.get_logger().debug(f"HTTP: {format % args}")


def main():
    parser = argparse.ArgumentParser(description="Bridge HTTP→ROS2 keyboard server")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    rclpy.init()
    global bridge_node
    bridge_node = BridgeNode()

    spin_thread = threading.Thread(target=rclpy.spin, args=(bridge_node,), daemon=True)
    spin_thread.start()

    HTTPServer.allow_reuse_address = True
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

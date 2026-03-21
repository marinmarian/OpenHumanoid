#!/usr/bin/env python3
"""
Wrapper that starts the HTTP bridge server AND the G1 control loop
in the SAME Python process.

This avoids all CycloneDDS inter-process networking issues because
the bridge publisher and the control loop's ROSKeyboardDispatcher
subscriber share the same ROS2 node in-process.

Usage (inside the WBC Docker container):
    python3 /tmp/run_with_bridge.py [--port 8765] [-- <control loop args>]

Example:
    python3 /tmp/run_with_bridge.py --port 8765 -- --keyboard-dispatcher-type ros
    python3 /tmp/run_with_bridge.py -- --interface real --keyboard-dispatcher-type ros
"""

import json
import sys
import threading
import argparse
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import rclpy
from std_msgs.msg import String

KEYBOARD_INPUT_TOPIC = "/keyboard_input"
VEL_STEP = 0.2

key_pub = None
_node = None
_last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}

# #region agent log
_DEBUG_LOG = "/root/Projects/GR00T-WholeBodyControl/debug_df55b2.log"
def _dlog(hypothesis, location, message, data=None):
    import json as _j, time as _t
    try:
        with open(_DEBUG_LOG, "a") as _f:
            _f.write(_j.dumps({"sessionId":"df55b2","hypothesisId":hypothesis,"location":location,"message":message,"data":data or {},"timestamp":int(_t.time()*1000)})+"\n")
    except Exception:
        pass
# #endregion


def publish_key(key: str):
    # #region agent log
    _dlog("H5", "run_with_bridge.py:publish_key", "publishing key", {"key": key, "pub_is_none": key_pub is None})
    # #endregion
    msg = String()
    msg.data = key
    key_pub.publish(msg)


def velocity_to_keys(vx: float, vy: float, vyaw: float) -> list[str]:
    keys = ["z"]

    def _repeat(pos_key: str, neg_key: str, value: float):
        n = round(abs(value) / VEL_STEP)
        return [pos_key if value > 0 else neg_key] * n

    keys += _repeat("w", "s", vx)
    keys += _repeat("a", "d", vy)
    keys += _repeat("q", "e", vyaw)
    return keys


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
        global _last_cmd
        try:
            data = _read_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _respond(self, 400, {"error": f"Bad JSON: {e}"})
            return

        if self.path == "/move":
            vx = float(data.get("vx", 0.0))
            vy = float(data.get("vy", 0.0))
            vyaw = float(data.get("vyaw", 0.0))
            keys = velocity_to_keys(vx, vy, vyaw)
            for k in keys:
                publish_key(k)
            _last_cmd = {"vx": vx, "vy": vy, "vyaw": vyaw}
            print(f"[BRIDGE] MOVE vx={vx:.2f} vy={vy:.2f} vyaw={vyaw:.2f} → keys={keys}")
            _respond(self, 200, {"ok": True, "vx": vx, "vy": vy, "vyaw": vyaw})

        elif self.path == "/stop":
            publish_key("z")
            _last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            print("[BRIDGE] STOP → key='z'")
            _respond(self, 200, {"ok": True, "stopped": True})

        elif self.path == "/activate":
            publish_key("]")
            print("[BRIDGE] ACTIVATE → key=']'")
            _respond(self, 200, {"ok": True, "activated": True})

        elif self.path == "/deactivate":
            publish_key("o")
            print("[BRIDGE] DEACTIVATE → key='o'")
            _respond(self, 200, {"ok": True, "deactivated": True})

        elif self.path == "/key":
            key = data.get("key", "")
            if not key:
                _respond(self, 400, {"error": "Missing 'key' field"})
                return
            publish_key(key)
            print(f"[BRIDGE] KEY '{key}'")
            _respond(self, 200, {"ok": True, "key": key})

        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def do_GET(self):
        if self.path == "/status":
            _respond(self, 200, {"ok": True, "last_cmd": _last_cmd, "vel_step": VEL_STEP})
        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format, *args):
        pass


def start_bridge_server(port: int):
    """Start the HTTP bridge in a daemon thread."""
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("0.0.0.0", port), BridgeHandler)
    print(f"[BRIDGE] HTTP server listening on 0.0.0.0:{port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main():
    # Split args: everything before '--' is for the bridge, after is for the control loop
    bridge_args = []
    loop_args = []
    if "--" in sys.argv:
        split_idx = sys.argv.index("--")
        bridge_args = sys.argv[1:split_idx]
        loop_args = sys.argv[split_idx + 1:]
    else:
        bridge_args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Bridge + Control Loop launcher")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(bridge_args)

    # Force keyboard-dispatcher-type to ros if not specified
    if "--keyboard-dispatcher-type" not in loop_args:
        loop_args.extend(["--keyboard-dispatcher-type", "ros"])
        print("[BRIDGE] Auto-adding --keyboard-dispatcher-type ros")

    # Step 1: Initialize ROS2 and create the bridge publisher BEFORE the control loop.
    # This way, the control loop's ROSManager will reuse our rclpy context,
    # and the ROSKeyboardDispatcher subscription will be on the same node as
    # our publisher -- pure in-process, no DDS networking needed.
    rclpy.init()
    global _node, key_pub
    _node = rclpy.create_node("bridge_server")
    key_pub = _node.create_publisher(String, KEYBOARD_INPUT_TOPIC, 10)
    spin_thread = threading.Thread(target=rclpy.spin, args=(_node,), daemon=True)
    spin_thread.start()
    print(f"[BRIDGE] ROS2 publisher ready on {KEYBOARD_INPUT_TOPIC}")

    # #region agent log
    time.sleep(0.5)
    try:
        ge = rclpy.get_global_executor()
        ge_nodes = [n.get_name() for n in ge.get_nodes()] if ge else []
    except Exception as ex:
        ge_nodes = f"ERROR: {ex}"
    _dlog("H1", "run_with_bridge.py:main", "ROS2 state after init+spin", {
        "rclpy_ok": rclpy.ok(),
        "bridge_node_name": _node.get_name(),
        "global_executor_nodes": ge_nodes,
    })
    # #endregion

    # Step 2: Start the HTTP server in a background thread.
    start_bridge_server(args.port)

    # Step 3: Patch sys.argv and run the control loop.
    sys.argv = ["run_g1_control_loop.py"] + loop_args
    print(f"[BRIDGE] Launching control loop with args: {loop_args}")

    import tyro
    from decoupled_wbc.control.main.teleop.configs.configs import ControlLoopConfig
    from decoupled_wbc.control.main.teleop.run_g1_control_loop import main as control_main

    config = tyro.cli(ControlLoopConfig)
    control_main(config)


if __name__ == "__main__":
    main()

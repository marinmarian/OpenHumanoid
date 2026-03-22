#!/usr/bin/env python3
"""
Mock bridge server: runs on the HOST for development/testing.
Same HTTP interface as bridge_server.py but prints to console instead of ROS2.

Usage:
    python3 mock_bridge.py [--port 8765]
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
last_arm_cmd = {"ok": False, "message": "No arm command issued yet.", "mock": True}
last_hand_cmd = {"ok": False, "message": "No hand command issued yet.", "mock": True}
last_pick_sequence = {"ok": False, "message": "No pick sequence executed yet.", "mock": True}


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
        global last_cmd, last_arm_cmd, last_hand_cmd, last_pick_sequence
        try:
            data = _read_body(self)
        except (json.JSONDecodeError, ValueError) as e:
            _respond(self, 400, {"error": f"Bad JSON: {e}"})
            return

        if self.path == "/move":
            vx = float(data.get("vx", 0.0))
            vy = float(data.get("vy", 0.0))
            vyaw = float(data.get("vyaw", 0.0))
            last_cmd = {"vx": vx, "vy": vy, "vyaw": vyaw}
            print(f"[MOCK] MOVE  vx={vx:.2f}  vy={vy:.2f}  vyaw={vyaw:.2f} (direct)")
            _respond(self, 200, {"ok": True, "vx": vx, "vy": vy, "vyaw": vyaw})

        elif self.path == "/stop":
            last_cmd = {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}
            print("[MOCK] STOP (direct)")
            _respond(self, 200, {"ok": True, "stopped": True})

        elif self.path == "/activate":
            print("[MOCK] ACTIVATE -> key=']'")
            _respond(self, 200, {"ok": True, "activated": True})

        elif self.path == "/deactivate":
            print("[MOCK] DEACTIVATE -> key='o'")
            _respond(self, 200, {"ok": True, "deactivated": True})

        elif self.path == "/key":
            key = data.get("key", "")
            if not key:
                _respond(self, 400, {"error": "Missing 'key' field"})
                return
            print(f"[MOCK] KEY   '{key}'")
            _respond(self, 200, {"ok": True, "key": key})

        elif self.path == "/arm/pose":
            wrist_pose = data.get("wrist_pose")
            if wrist_pose is None:
                _respond(self, 400, {"ok": False, "error": "Missing 'wrist_pose' field"})
                return
            flattened = list(wrist_pose)
            if len(flattened) not in {7, 14}:
                _respond(self, 400, {"ok": False, "error": "'wrist_pose' must contain either 7 or 14 values"})
                return
            active_arm = str(data.get("active_arm", "right")).lower()
            last_arm_cmd = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "frame": data.get("frame", "base_link"),
                "move_time_s": float(data.get("move_time_s", 1.5)),
                "wrist_pose": flattened,
                "message": "Mock bridge accepted the arm pose request.",
            }
            print(f"[MOCK] ARM   active_arm={active_arm}  frame={last_arm_cmd['frame']}  pose_len={len(flattened)}")
            _respond(self, 200, last_arm_cmd)

        elif self.path == "/hand/command":
            active_arm = str(data.get("active_arm", "right")).lower()
            posture = str(data.get("posture", "open")).lower()
            hand_q = list(data.get("hand_q", [])) if data.get("hand_q") is not None else []
            last_hand_cmd = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "posture": posture,
                "hand_q": hand_q,
                "message": "Mock bridge accepted the hand command.",
            }
            print(f"[MOCK] HAND  active_arm={active_arm}  posture={posture}")
            _respond(self, 200, last_hand_cmd)

        elif self.path == "/manipulation/pick_sequence":
            active_arm = str(data.get("active_arm", "right")).lower()
            frame = data.get("frame", "base_link")
            stages = []
            if data.get("open_hand_first", True):
                last_hand_cmd = {
                    "ok": True,
                    "mock": True,
                    "active_arm": active_arm,
                    "posture": "open",
                    "hand_q": [],
                    "message": "Mock bridge accepted the hand command.",
                }
                stages.append({"name": "open_hand", "ok": True, "detail": f"Opened the {active_arm} hand.", "result": last_hand_cmd})
            last_arm_cmd = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "frame": frame,
                "move_time_s": float(data.get("pregrasp_move_time_s", 1.6)),
                "wrist_pose": list(data.get("pregrasp_pose", [])),
                "message": "Mock bridge accepted the arm pose request.",
            }
            stages.append({"name": "move_pregrasp", "ok": True, "detail": f"Moved the {active_arm} wrist to pregrasp.", "result": last_arm_cmd})
            last_arm_cmd = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "frame": frame,
                "move_time_s": float(data.get("grasp_move_time_s", 1.0)),
                "wrist_pose": list(data.get("grasp_pose", [])),
                "message": "Mock bridge accepted the arm pose request.",
            }
            stages.append({"name": "move_grasp", "ok": True, "detail": f"Moved the {active_arm} wrist to grasp.", "result": last_arm_cmd})
            if data.get("close_hand", True):
                last_hand_cmd = {
                    "ok": True,
                    "mock": True,
                    "active_arm": active_arm,
                    "posture": "grasp",
                    "hand_q": [],
                    "message": "Mock bridge accepted the hand command.",
                }
                stages.append({"name": "close_hand", "ok": True, "detail": f"Closed the {active_arm} hand.", "result": last_hand_cmd})
            last_arm_cmd = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "frame": frame,
                "move_time_s": float(data.get("retreat_move_time_s", 1.4)),
                "wrist_pose": list(data.get("retreat_pose", [])),
                "message": "Mock bridge accepted the arm pose request.",
            }
            stages.append({"name": "move_retreat", "ok": True, "detail": f"Retreated the {active_arm} wrist with the grasped object.", "result": last_arm_cmd})
            last_pick_sequence = {
                "ok": True,
                "mock": True,
                "active_arm": active_arm,
                "frame": frame,
                "gripper_width": float(data.get("gripper_width", 0.08)),
                "stages": stages,
                "message": "Mock bridge executed the staged pick sequence.",
            }
            print(f"[MOCK] PICK  active_arm={active_arm}  stages={len(stages)}")
            _respond(self, 200, last_pick_sequence)

        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def do_GET(self):
        if self.path == "/status":
            _respond(
                self,
                200,
                {
                    "ok": True,
                    "last_cmd": last_cmd,
                    "last_arm_cmd": last_arm_cmd,
                    "last_hand_cmd": last_hand_cmd,
                    "last_pick_sequence": last_pick_sequence,
                    "actual_cmd": [last_cmd["vx"], last_cmd["vy"], last_cmd["vyaw"]],
                    "arm_endpoint_ready": True,
                    "hand_endpoint_ready": True,
                    "mock": True,
                    "policy_connected": True,
                },
            )
        else:
            _respond(self, 404, {"error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Mock bridge server (no ROS2)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", args.port), MockHandler)
    print(f"[MOCK] Bridge server listening on http://127.0.0.1:{args.port}")
    print("[MOCK] Endpoints: POST /move, /stop, /activate, /deactivate, /key, /arm/pose, /hand/command, /manipulation/pick_sequence  |  GET /status")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MOCK] Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .state import CapabilityState


class CapabilityHandler(BaseHTTPRequestHandler):
    state: CapabilityState

    def do_GET(self) -> None:
        if self.path == "/status":
            self._respond(200, self.state.status_snapshot())
        elif self.path == "/maps":
            self._respond(200, self.state.list_maps())
        elif self.path == "/localization/status":
            self._respond(200, self.state.localization_status())
        elif self.path == "/navigation/status":
            self._respond(200, self.state.navigation_status())
        elif self.path == "/perception/raw-capture":
            try:
                png_bytes = self.state.raw_capture()
            except Exception as exc:
                self._respond(500, {"ok": False, "error": str(exc)})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png_bytes)))
            self.end_headers()
            self.wfile.write(png_bytes)
        else:
            self._respond(404, {"ok": False, "error": f"Unknown endpoint: {self.path}"})

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._respond(400, {"ok": False, "error": str(exc)})
            return

        if self.path == "/maps/build":
            body = self.state.build_map(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/maps/load":
            body = self.state.load_map(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/localization/initialize":
            body = self.state.initialize_localization(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/navigation/goal":
            body = self.state.navigate(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/navigation/cancel":
            self._respond(200, self.state.cancel_navigation())
        elif self.path == "/perception/scene":
            body = self.state.scene(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/perception/object_pose":
            body = self.state.object_pose(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/perception/grasp_pose":
            body = self.state.grasp_pose(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/perception/face/enroll":
            body = self.state.enroll_face(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/perception/face/recognize":
            body = self.state.recognize_faces(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/manipulation/pick":
            body = self.state.pick(payload)
            self._respond(200 if body.get("ok") else 400, body)
        elif self.path == "/mission/pick_object":
            body = self.state.pick_object_task(payload)
            self._respond(200 if body.get("ok") else 400, body)
        else:
            self._respond(404, {"ok": False, "error": f"Unknown endpoint: {self.path}"})

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Bad JSON: {exc}") from exc

    def _respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenHumanoid capability stack server")
    parser.add_argument("--host", default=os.environ.get("CAPABILITY_SERVER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CAPABILITY_SERVER_PORT", "8787")))
    parser.add_argument(
        "--state-path",
        default=os.environ.get("CAPABILITY_STATE_PATH", "capabilities/runtime/state.json"),
    )
    parser.add_argument("--camera-name", default=os.environ.get("NAV_CAMERA_NAME", "zed-mini"))
    parser.add_argument("--lidar-name", default=os.environ.get("LIDAR_NAME", "lidar"))
    parser.add_argument("--base-frame", default=os.environ.get("ROBOT_BASE_FRAME", "base_link"))
    parser.add_argument("--map-frame", default=os.environ.get("WORLD_FRAME", "map"))
    parser.add_argument("--bridge-url", default=os.environ.get("BRIDGE_URL", "http://localhost:8765"))
    parser.add_argument(
        "--perception-backend",
        default=os.environ.get("PERCEPTION_BACKEND"),
        help="Perception backend to use: 'mock' or 'zed'. Defaults to 'mock' in mock mode and 'zed' in real-backend mode.",
    )
    parser.add_argument(
        "--perception-detections-path",
        default=os.environ.get("PERCEPTION_DETECTIONS_PATH"),
        help="Optional JSON file containing 2D detections to ground with the ZED point cloud.",
    )
    parser.add_argument(
        "--detector-backend",
        default=os.environ.get("DETECTOR_BACKEND"),
        help="Detector backend for the ZED pipeline: 'none' or 'http'.",
    )
    parser.add_argument(
        "--detector-url",
        default=os.environ.get("DETECTOR_URL"),
        help="HTTP detector service endpoint, for example http://127.0.0.1:8790/detect.",
    )
    parser.add_argument(
        "--detector-timeout-s",
        type=float,
        default=float(os.environ.get("DETECTOR_TIMEOUT_S", "4.0")),
        help="Timeout for detector backend requests.",
    )
    parser.add_argument(
        "--detector-model",
        default=os.environ.get("DETECTOR_MODEL"),
        help="Optional detector model name to forward to the detector service.",
    )
    parser.add_argument(
        "--real-backend",
        action="store_true",
        help="Mark the server as backed by real sensor/control adapters instead of the mock state machine.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    state = CapabilityState(
        state_path=args.state_path,
        camera_name=args.camera_name,
        lidar_name=args.lidar_name,
        base_frame=args.base_frame,
        map_frame=args.map_frame,
        bridge_url=args.bridge_url,
        mock_mode=not args.real_backend,
        perception_backend_name=args.perception_backend,
        perception_detections_path=args.perception_detections_path,
        detector_backend_name=args.detector_backend,
        detector_url=args.detector_url,
        detector_timeout_s=args.detector_timeout_s,
        detector_model=args.detector_model,
    )
    CapabilityHandler.state = state

    server = ThreadingHTTPServer((args.host, args.port), CapabilityHandler)
    print(f"[CAPABILITIES] Server listening on http://{args.host}:{args.port}")
    print(f"[CAPABILITIES] State file: {args.state_path}")
    print(f"[CAPABILITIES] Camera={args.camera_name} LiDAR={args.lidar_name} mock_mode={state.mock_mode}")
    print(f"[CAPABILITIES] Bridge={args.bridge_url}")
    print(f"[CAPABILITIES] Perception={state.perception_backend.describe()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CAPABILITIES] Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

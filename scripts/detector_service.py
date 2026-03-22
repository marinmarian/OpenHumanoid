#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
import requests


def _normalize_label(label: str) -> str:
    normalized = label.strip().lower().replace("_", " ")
    aliases = {
        "dining table": "table",
        "table": "table",
    }
    return aliases.get(normalized, normalized)


def _expand_requested_labels(labels: list[str]) -> set[str]:
    expanded: set[str] = set()
    for label in labels:
        normalized = _normalize_label(label)
        if not normalized:
            continue
        expanded.add(normalized)
        parts = normalized.split()
        if len(parts) > 1:
            expanded.add(parts[-1])
    return expanded


def _infer_color(crop_rgb: np.ndarray) -> str | None:
    if crop_rgb.size == 0:
        return None
    red = float(np.mean(crop_rgb[..., 0]))
    green = float(np.mean(crop_rgb[..., 1]))
    blue = float(np.mean(crop_rgb[..., 2]))
    if green > red * 1.12 and green > blue * 1.1:
        return "green"
    if red > green * 1.12 and red > blue * 1.05:
        return "red"
    if red > 80 and green > 80 and blue < 120:
        return "yellow"
    if blue > red * 1.08 and blue > green * 1.08:
        return "blue"
    return None


def _encode_png_base64(image_rgb: np.ndarray) -> str:
    image = Image.fromarray(np.ascontiguousarray(image_rgb[..., :3]))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _clamp_bbox(bbox: list[int] | tuple[int, int, int, int], width: int, height: int) -> list[int] | None:
    x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
    x1 = max(0, min(x1, max(0, width - 1)))
    y1 = max(0, min(y1, max(0, height - 1)))
    x2 = max(0, min(x2, width))
    y2 = max(0, min(y2, height))
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def _extract_response_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text
    raise ValueError("OpenAI response did not include output text.")


def _build_vlm_detection_prompt(labels: list[str], width: int, height: int) -> str:
    target_text = ", ".join(labels) if labels else "all salient tabletop objects"
    return (
        "You are an object detector for a humanoid robot. "
        f"Find only these targets if they are visible: {target_text}. "
        "Return only grounded, visually present objects. "
        "Use integer pixel bounding boxes in xyxy format relative to the full image. "
        f"The image width is {width} and the image height is {height}. "
        "For each detection include: label, optional color, confidence from 0 to 1, bbox, and optional support_surface. "
        "Do not invent detections for objects that are not clearly visible."
    )


class BaseDetectionBackend:
    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    def detect(self, image_rgb: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError


class FixtureDetectionBackend(BaseDetectionBackend):
    def __init__(self, fixture_path: str | None):
        self.fixture_path = Path(fixture_path).expanduser() if fixture_path else None

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "fixture",
            "fixture_path": str(self.fixture_path) if self.fixture_path else None,
            "ready": self.fixture_path is not None and self.fixture_path.exists(),
        }

    def detect(self, image_rgb: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.fixture_path or not self.fixture_path.exists():
            return []
        raw = json.loads(self.fixture_path.read_text())
        detections = raw.get("detections", raw) if isinstance(raw, dict) else raw
        if not isinstance(detections, list):
            return []
        labels = _expand_requested_labels([str(item) for item in payload.get("labels", [])])
        if not labels:
            return detections
        filtered = []
        for item in detections:
            label = _normalize_label(str(item.get("label", "")))
            if label in labels:
                filtered.append(item)
        return filtered


class UltralyticsDetectionBackend(BaseDetectionBackend):
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._load_error: str | None = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            self._load_error = f"Failed to import ultralytics: {exc}"
            raise RuntimeError(self._load_error) from exc
        try:
            self._model = YOLO(self.model_name)
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            self._load_error = f"Failed to load detector model '{self.model_name}': {exc}"
            raise RuntimeError(self._load_error) from exc
        self._load_error = None

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "ultralytics",
            "model": self.model_name,
            "ready": self._load_error is None,
            "load_error": self._load_error,
        }

    def detect(self, image_rgb: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self._ensure_model()
        confidence = float(payload.get("confidence", 0.25))
        iou = float(payload.get("iou", 0.45))
        max_detections = int(payload.get("max_detections", 25))
        requested_labels = _expand_requested_labels([str(item) for item in payload.get("labels", [])])

        results = self._model.predict(source=image_rgb, conf=confidence, iou=iou, max_det=max_detections, verbose=False)
        detections: list[dict[str, Any]] = []
        detection_index = 0
        for result in results:
            names = result.names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy() if hasattr(boxes.xyxy, "cpu") else np.asarray(boxes.xyxy)
            confs = boxes.conf.cpu().numpy() if hasattr(boxes.conf, "cpu") else np.asarray(boxes.conf)
            classes = boxes.cls.cpu().numpy().astype(int) if hasattr(boxes.cls, "cpu") else np.asarray(boxes.cls).astype(int)
            for coords, conf_value, class_id in zip(xyxy, confs, classes):
                label = _normalize_label(str(names[int(class_id)]))
                if requested_labels and label not in requested_labels:
                    continue
                x1, y1, x2, y2 = [int(round(float(value))) for value in coords.tolist()]
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = image_rgb[max(y1, 0):max(y2, 0), max(x1, 0):max(x2, 0)]
                color = _infer_color(crop)
                detection_index += 1
                detections.append(
                    {
                        "label": label,
                        "color": color,
                        "confidence": float(conf_value),
                        "bbox": [x1, y1, x2, y2],
                        "object_id": f"{label}-{color or 'unknown'}-{detection_index:02d}",
                    }
                )
        return detections


class OpenAIVisionDetectionBackend(BaseDetectionBackend):
    def __init__(
        self,
        model_name: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 20.0,
        organization: str | None = None,
        project: str | None = None,
        reasoning_effort: str | None = None,
    ):
        self.model_name = model_name or "gpt-4.1-mini"
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout_s = timeout_s
        self.organization = organization or os.environ.get("OPENAI_ORG_ID")
        self.project = project or os.environ.get("OPENAI_PROJECT_ID")
        self.reasoning_effort = reasoning_effort or os.environ.get("OPENAI_VLM_REASONING_EFFORT")
        self._last_error: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "openai",
            "model": self.model_name,
            "ready": bool(self.api_key) and self._last_error is None,
            "base_url": self.base_url,
            "timeout_s": self.timeout_s,
            "reasoning_effort": self.reasoning_effort,
            "last_error": self._last_error,
        }

    def detect(self, image_rgb: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when DETECTOR_SERVICE_BACKEND=openai.")

        labels = [str(item).strip() for item in payload.get("labels", []) if str(item).strip()]
        width = int(image_rgb.shape[1])
        height = int(image_rgb.shape[0])
        image_url = f"data:image/png;base64,{_encode_png_base64(image_rgb)}"
        prompt = _build_vlm_detection_prompt(labels, width, height)

        try:
            response_data = self._post_responses(self._build_structured_request(prompt=prompt, image_url=image_url, payload=payload))
            parsed = self._parse_detection_payload(response_data)
        except Exception as exc:
            self._last_error = str(exc)
            response_data = self._post_responses(
                self._build_unstructured_request(
                    prompt=prompt + " Return strict JSON with a top-level 'detections' array.",
                    image_url=image_url,
                    payload=payload,
                )
            )
            parsed = self._parse_detection_payload(response_data)

        self._last_error = None
        requested_labels = _expand_requested_labels(labels)
        detections: list[dict[str, Any]] = []
        raw_detections = parsed.get("detections", parsed if isinstance(parsed, list) else [])
        if not isinstance(raw_detections, list):
            raise RuntimeError("OpenAI VLM detector did not return a detections list.")

        for index, item in enumerate(raw_detections, start=1):
            if not isinstance(item, dict):
                continue
            label = _normalize_label(str(item.get("label", "")))
            if not label:
                continue
            if requested_labels and label not in requested_labels:
                continue
            bbox = item.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            clamped = _clamp_bbox(list(bbox), width, height)
            if clamped is None:
                continue
            x1, y1, x2, y2 = clamped
            crop = image_rgb[y1:y2, x1:x2]
            color = item.get("color")
            if color:
                color = str(color).strip().lower()
            if not color:
                color = _infer_color(crop)
            confidence = float(item.get("confidence", 0.0))
            detections.append(
                {
                    "label": label,
                    "color": color,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "bbox": [x1, y1, x2, y2],
                    "support_surface": str(item["support_surface"]).strip().lower() if item.get("support_surface") else None,
                    "object_id": item.get("object_id") or f"{label}-{color or 'unknown'}-{index:02d}",
                }
            )
        return detections

    def _build_structured_request(self, *, prompt: str, image_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_body: dict[str, Any] = {
            "model": payload.get("model") or self.model_name,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "robot_detections",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "detections": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "label": {"type": "string"},
                                        "color": {"type": ["string", "null"]},
                                        "confidence": {"type": "number"},
                                        "bbox": {
                                            "type": "array",
                                            "minItems": 4,
                                            "maxItems": 4,
                                            "items": {"type": "integer"},
                                        },
                                        "support_surface": {"type": ["string", "null"]},
                                        "object_id": {"type": ["string", "null"]},
                                    },
                                    "required": ["label", "confidence", "bbox", "color", "support_surface", "object_id"],
                                },
                            }
                        },
                        "required": ["detections"],
                    },
                }
            },
            "max_output_tokens": int(payload.get("max_output_tokens", os.environ.get("OPENAI_VLM_MAX_OUTPUT_TOKENS", "1200"))),
        }
        if self.reasoning_effort:
            request_body["reasoning"] = {"effort": self.reasoning_effort}
        return request_body

    def _build_unstructured_request(self, *, prompt: str, image_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_body: dict[str, Any] = {
            "model": payload.get("model") or self.model_name,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
            "max_output_tokens": int(payload.get("max_output_tokens", os.environ.get("OPENAI_VLM_MAX_OUTPUT_TOKENS", "1200"))),
        }
        if self.reasoning_effort:
            request_body["reasoning"] = {"effort": self.reasoning_effort}
        return request_body

    def _post_responses(self, request_body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        if self.project:
            headers["OpenAI-Project"] = self.project
        response = requests.post(
            f"{self.base_url}/responses",
            headers=headers,
            json=request_body,
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response.json()

    def _parse_detection_payload(self, response_data: dict[str, Any]) -> dict[str, Any]:
        output_parsed = response_data.get("output_parsed")
        if isinstance(output_parsed, dict):
            return output_parsed
        text = _extract_response_text(response_data)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI VLM detector returned non-JSON text: {text[:240]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI VLM detector returned JSON that is not an object.")
        return parsed


class DetectorHandler(BaseHTTPRequestHandler):
    backend: BaseDetectionBackend

    def do_GET(self) -> None:
        if self.path == "/status":
            self._respond(200, {"ok": True, "detector": self.backend.describe()})
        else:
            self._respond(404, {"ok": False, "error": f"Unknown endpoint: {self.path}"})

    def do_POST(self) -> None:
        if self.path != "/detect":
            self._respond(404, {"ok": False, "error": f"Unknown endpoint: {self.path}"})
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._respond(400, {"ok": False, "error": str(exc)})
            return

        image_base64 = payload.get("image_base64")
        if not image_base64:
            self._respond(400, {"ok": False, "error": "Missing 'image_base64'."})
            return
        try:
            image = Image.open(io.BytesIO(base64.b64decode(image_base64))).convert("RGB")
            image_rgb = np.array(image)
        except Exception as exc:
            self._respond(400, {"ok": False, "error": f"Failed to decode image: {exc}"})
            return

        try:
            detections = self.backend.detect(image_rgb, payload)
        except Exception as exc:
            self._respond(500, {"ok": False, "error": f"Detector backend failed: {exc}"})
            return
        self._respond(200, {"ok": True, "detections": detections, "detector": self.backend.describe()})

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Bad JSON: {exc}") from exc

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_backend(args: argparse.Namespace) -> BaseDetectionBackend:
    backend_name = args.backend.lower()
    if backend_name == "fixture":
        return FixtureDetectionBackend(args.fixture_path)
    if backend_name == "ultralytics":
        return UltralyticsDetectionBackend(args.model or "yolov8n.pt")
    if backend_name == "openai":
        return OpenAIVisionDetectionBackend(
            args.model or "gpt-4.1-mini",
            api_key=args.openai_api_key,
            base_url=args.openai_base_url,
            timeout_s=args.timeout_s,
            organization=args.openai_org_id,
            project=args.openai_project_id,
            reasoning_effort=args.openai_reasoning_effort,
        )
    raise ValueError(f"Unsupported detector backend '{args.backend}'.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local detector service for the OpenHumanoid ZED perception stack")
    parser.add_argument("--host", default=os.environ.get("DETECTOR_SERVER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DETECTOR_SERVER_PORT", "8790")))
    parser.add_argument("--backend", default=os.environ.get("DETECTOR_SERVICE_BACKEND", "ultralytics"))
    parser.add_argument("--model", default=os.environ.get("DETECTOR_MODEL", ""))
    parser.add_argument("--fixture-path", default=os.environ.get("DETECTOR_FIXTURE_PATH"))
    parser.add_argument("--timeout-s", type=float, default=float(os.environ.get("DETECTOR_TIMEOUT_S", "20.0")))
    parser.add_argument("--openai-api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--openai-base-url", default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--openai-org-id", default=os.environ.get("OPENAI_ORG_ID"))
    parser.add_argument("--openai-project-id", default=os.environ.get("OPENAI_PROJECT_ID"))
    parser.add_argument("--openai-reasoning-effort", default=os.environ.get("OPENAI_VLM_REASONING_EFFORT"))
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    backend = build_backend(args)
    DetectorHandler.backend = backend
    server = ThreadingHTTPServer((args.host, args.port), DetectorHandler)
    print(f"[DETECTOR] Listening on http://{args.host}:{args.port}")
    print(f"[DETECTOR] Backend={backend.describe()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DETECTOR] Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

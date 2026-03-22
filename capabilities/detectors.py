from __future__ import annotations

import base64
import io
import os
from typing import Any

import numpy as np
import requests


class BaseDetectorBackend:
    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    def detect(self, image_bgr: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError


class NoopDetectorBackend(BaseDetectorBackend):
    def describe(self) -> dict[str, Any]:
        return {
            "name": "none",
            "enabled": False,
            "ready": True,
        }

    def detect(self, image_bgr: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return []


class HttpDetectorBackend(BaseDetectorBackend):
    def __init__(
        self,
        *,
        url: str,
        timeout_s: float = 4.0,
        model: str | None = None,
        token: str | None = None,
        default_labels: list[str] | None = None,
    ):
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.model = model
        self.token = token
        self.default_labels = [label for label in (default_labels or []) if label]
        self.last_error: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "name": "http",
            "enabled": True,
            "ready": self.last_error is None,
            "url": self.url,
            "model": self.model,
            "timeout_s": self.timeout_s,
            "last_error": self.last_error,
            "default_labels": self.default_labels,
        }

    def detect(self, image_bgr: np.ndarray, payload: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            body = {
                "image_base64": _encode_png_base64(image_bgr),
                "labels": _build_detector_labels(payload, self.default_labels),
                "prompt": payload.get("detector_prompt") or _build_detector_prompt(payload, self.default_labels),
                "model": payload.get("detector_model") or self.model,
                "confidence": float(payload.get("detector_confidence", os.environ.get("DETECTOR_CONFIDENCE", "0.25"))),
                "iou": float(payload.get("detector_iou", os.environ.get("DETECTOR_IOU", "0.45"))),
                "max_detections": int(payload.get("detector_max_detections", os.environ.get("DETECTOR_MAX_DETECTIONS", "25"))),
            }
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            response = requests.post(self.url, json=body, headers=headers, timeout=self.timeout_s)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            self.last_error = str(exc)
            return []

        detections = data.get("detections", [])
        if not isinstance(detections, list):
            self.last_error = "Detector response did not contain a 'detections' list."
            return []
        self.last_error = None
        normalized: list[dict[str, Any]] = []
        for item in detections:
            if not isinstance(item, dict):
                continue
            bbox = _normalize_bbox(item)
            if bbox is None:
                continue
            normalized.append(
                {
                    "label": item.get("label"),
                    "color": item.get("color"),
                    "confidence": float(item.get("confidence", item.get("score", 0.0))),
                    "bbox": list(bbox),
                    "support_surface": item.get("support_surface"),
                    "object_id": item.get("object_id"),
                }
            )
        return normalized


def build_detector_backend(
    *,
    backend_name: str | None,
    url: str | None,
    timeout_s: float | None,
    model: str | None,
) -> BaseDetectorBackend:
    resolved = (backend_name or os.environ.get("DETECTOR_BACKEND", "none")).strip().lower()
    if resolved in {"", "none", "disabled", "off"}:
        return NoopDetectorBackend()
    if resolved != "http":
        raise ValueError(f"Unsupported detector backend '{backend_name}'. Expected 'none' or 'http'.")
    resolved_url = (url or os.environ.get("DETECTOR_URL", "")).strip()
    if not resolved_url:
        raise ValueError("DETECTOR_BACKEND=http requires DETECTOR_URL or --detector-url.")
    raw_labels = os.environ.get("DETECTOR_DEFAULT_LABELS", "table,apple")
    default_labels = [item.strip() for item in raw_labels.split(",") if item.strip()]
    return HttpDetectorBackend(
        url=resolved_url,
        timeout_s=float(timeout_s if timeout_s is not None else os.environ.get("DETECTOR_TIMEOUT_S", "4.0")),
        model=model or os.environ.get("DETECTOR_MODEL"),
        token=os.environ.get("DETECTOR_TOKEN"),
        default_labels=default_labels,
    )


def _build_detector_labels(payload: dict[str, Any], default_labels: list[str]) -> list[str]:
    labels: list[str] = []
    if payload.get("detector_labels"):
        labels.extend(str(item).strip() for item in payload["detector_labels"] if str(item).strip())
    color = payload.get("color")
    label = payload.get("label") or payload.get("object_label")
    support_surface = payload.get("support_surface")
    if label:
        labels.append(str(label).strip())
        if color:
            labels.append(f"{color} {label}".strip())
    if support_surface:
        labels.append(str(support_surface).strip())
    labels.extend(default_labels)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in labels:
        normalized = item.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped


def _build_detector_prompt(payload: dict[str, Any], default_labels: list[str]) -> str:
    labels = _build_detector_labels(payload, default_labels)
    if not labels:
        return "Detect relevant tabletop objects in the image."
    return "Detect the following objects in the image: " + ", ".join(labels)


def _normalize_bbox(item: dict[str, Any]) -> tuple[int, int, int, int] | None:
    bbox = item.get("bbox")
    if bbox and len(bbox) == 4:
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox]
        if x2 > x1 and y2 > y1:
            return x1, y1, x2, y2
    coords = item.get("bounding_box_2d")
    if coords:
        xs = [int(round(float(point[0]))) for point in coords]
        ys = [int(round(float(point[1]))) for point in coords]
        if xs and ys:
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            if x2 > x1 and y2 > y1:
                return x1, y1, x2, y2
    return None


def _encode_png_base64(image_bgr: np.ndarray) -> str:
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        raise RuntimeError("Pillow is required for DETECTOR_BACKEND=http. Install it with 'uv sync'.") from exc

    rgb = np.ascontiguousarray(image_bgr[..., :3][:, :, ::-1])
    image = Image.fromarray(rgb)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

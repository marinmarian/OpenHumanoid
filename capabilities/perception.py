from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .models import PerceivedObject, Pose2D, Pose3D, SceneObservation, utc_now_iso
from .detectors import build_detector_backend


@dataclass
class DetectionCandidate:
    label: str
    color: str | None
    confidence: float
    bbox: tuple[int, int, int, int]
    support_surface: str | None = None
    object_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePerceptionBackend:
    def describe(self) -> dict[str, Any]:
        raise NotImplementedError

    def raw_capture(self) -> bytes:
        """Capture a single frame and return it as PNG bytes."""
        raise NotImplementedError("raw_capture is not supported by this backend.")

    def observe_scene(
        self,
        payload: dict[str, Any],
        *,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> SceneObservation:
        raise NotImplementedError


class MockPerceptionBackend(BasePerceptionBackend):
    def __init__(self, camera_name: str, map_frame: str, objects: list[PerceivedObject]):
        self.camera_name = camera_name
        self.map_frame = map_frame
        self.objects = list(objects)

    def describe(self) -> dict[str, Any]:
        return {
            "name": "mock",
            "ready": True,
            "camera_name": self.camera_name,
            "mode": "static_fixture",
            "object_count": len(self.objects),
        }

    def observe_scene(
        self,
        payload: dict[str, Any],
        *,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> SceneObservation:
        requested_label = payload.get("label")
        requested_color = payload.get("color")
        objects = [
            item
            for item in self.objects
            if (not requested_label or item.label == requested_label)
            and (not requested_color or item.color == requested_color)
        ]
        frame_id = map_frame if localization else f"{self.camera_name}_frame"
        return SceneObservation(
            camera_name=payload.get("camera_name", self.camera_name),
            frame_id=frame_id,
            objects=objects,
            summary=_scene_summary(objects),
            updated_at=utc_now_iso(),
        )


class ZedStereoPerceptionBackend(BasePerceptionBackend):
    def __init__(
        self,
        *,
        camera_name: str,
        map_frame: str,
        base_frame: str,
        detections_path: str | None = None,
        detector_backend_name: str | None = None,
        detector_url: str | None = None,
        detector_timeout_s: float | None = None,
        detector_model: str | None = None,
    ):
        self.camera_name = camera_name
        self.map_frame = map_frame
        self.base_frame = base_frame
        self.camera_frame = os.environ.get("ZED_CAMERA_FRAME", f"{camera_name}_frame")
        self.detections_path = Path(detections_path).expanduser() if detections_path else None
        self.coordinate_system = os.environ.get("ZED_COORDINATE_SYSTEM", "RIGHT_HANDED_Z_UP_X_FWD")
        self.resolution = os.environ.get("ZED_RESOLUTION", "HD720")
        self.depth_mode = os.environ.get("ZED_DEPTH_MODE", "PERFORMANCE")
        self.fps = int(os.environ.get("ZED_FPS", "60"))
        self.min_depth_m = float(os.environ.get("ZED_MIN_DEPTH_M", "0.15"))
        self.max_depth_m = float(os.environ.get("ZED_MAX_DEPTH_M", "3.5"))
        self.point_stride = max(1, int(os.environ.get("ZED_POINT_STRIDE", "2")))
        self.color_mask_min_pixels = max(80, int(os.environ.get("ZED_COLOR_MASK_MIN_PIXELS", "220")))
        self.table_height_min = float(os.environ.get("ZED_TABLE_HEIGHT_MIN_M", "0.45"))
        self.table_height_max = float(os.environ.get("ZED_TABLE_HEIGHT_MAX_M", "1.25"))
        self.table_band_width = float(os.environ.get("ZED_TABLE_BAND_WIDTH_M", "0.04"))
        self.table_min_inliers = max(500, int(os.environ.get("ZED_TABLE_MIN_INLIERS", "1200")))
        self.camera_to_base_translation = np.array(
            [
                float(os.environ.get("ZED_TO_BASE_X", "0.0")),
                float(os.environ.get("ZED_TO_BASE_Y", "0.0")),
                float(os.environ.get("ZED_TO_BASE_Z", "0.0")),
            ],
            dtype=np.float64,
        )
        self.camera_to_base_rpy = (
            float(os.environ.get("ZED_TO_BASE_ROLL", "0.0")),
            float(os.environ.get("ZED_TO_BASE_PITCH", "0.0")),
            float(os.environ.get("ZED_TO_BASE_YAW", "0.0")),
        )
        self._camera_to_base_rotation = _rpy_matrix(*self.camera_to_base_rpy)
        self.detector_backend = build_detector_backend(
            backend_name=detector_backend_name,
            url=detector_url,
            timeout_s=detector_timeout_s,
            model=detector_model,
        )
        self._lock = threading.Lock()
        self._sl = None
        self._camera = None
        self._image_mat = None
        self._point_cloud_mat = None
        self._sdk_import_error: str | None = None
        self._last_runtime_error: str | None = None
        self._last_detection_source = "none"

    def describe(self) -> dict[str, Any]:
        return {
            "name": "zed",
            "ready": self._sdk_import_error is None and self._last_runtime_error is None,
            "camera_name": self.camera_name,
            "camera_frame": self.camera_frame,
            "sdk_available": self._sdk_import_error is None,
            "opened": self._camera is not None,
            "resolution": self.resolution,
            "fps": self.fps,
            "depth_mode": self.depth_mode,
            "coordinate_system": self.coordinate_system,
            "detections_path": str(self.detections_path) if self.detections_path else None,
            "last_detection_source": self._last_detection_source,
            "sdk_error": self._sdk_import_error,
            "runtime_error": self._last_runtime_error,
            "detector_backend": self.detector_backend.describe(),
        }

    def raw_capture(self) -> bytes:
        image, _point_cloud = self._capture_frame()
        rgb = np.ascontiguousarray(image[..., :3][:, :, ::-1])
        try:
            from PIL import Image as _PILImage
        except ImportError as exc:
            raise RuntimeError("Pillow is required for raw_capture. Install with 'uv sync'.") from exc
        import io
        pil_img = _PILImage.fromarray(rgb)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()

    def observe_scene(
        self,
        payload: dict[str, Any],
        *,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> SceneObservation:
        image, point_cloud = self._capture_frame()
        explicit_detections = self._load_explicit_detections(payload)
        detector_raw = self.detector_backend.detect(image, payload) if not explicit_detections else []
        detector_detections = self._parse_detections(detector_raw, source=self.detector_backend.describe().get("name", "detector")) if detector_raw else []
        heuristic_objects = self._infer_heuristic_objects(payload, image, point_cloud, localization, map_frame, base_frame)

        objects: list[PerceivedObject] = []
        source_detections = explicit_detections or detector_detections
        if source_detections:
            self._last_detection_source = source_detections[0].metadata.get("source", "payload")
            grounded = self._ground_explicit_detections(
                source_detections,
                point_cloud,
                localization=localization,
                map_frame=map_frame,
                base_frame=base_frame,
            )
            objects.extend(grounded)
        else:
            self._last_detection_source = "heuristic"

        objects.extend(heuristic_objects)
        objects = _deduplicate_objects(objects)

        requested_label = payload.get("label")
        requested_color = payload.get("color")
        filtered = [
            item
            for item in objects
            if (not requested_label or item.label == requested_label)
            and (not requested_color or item.color == requested_color)
        ]
        frame_id = map_frame if localization else base_frame
        return SceneObservation(
            camera_name=payload.get("camera_name", self.camera_name),
            frame_id=frame_id,
            objects=filtered,
            summary=_scene_summary(filtered),
            updated_at=utc_now_iso(),
        )

    def _import_sdk(self):
        if self._sl is not None:
            return self._sl
        try:
            import pyzed.sl as sl  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on host SDK install
            self._sdk_import_error = f"Failed to import pyzed.sl: {exc}"
            raise RuntimeError(self._sdk_import_error) from exc
        self._sl = sl
        self._sdk_import_error = None
        return sl

    def _ensure_camera(self):
        with self._lock:
            if self._camera is not None:
                return
            sl = self._import_sdk()
            init_params = sl.InitParameters()
            init_params.camera_resolution = getattr(sl.RESOLUTION, self.resolution, sl.RESOLUTION.HD720)
            init_params.camera_fps = self.fps
            init_params.coordinate_units = sl.UNIT.METER
            init_params.coordinate_system = getattr(
                sl.COORDINATE_SYSTEM,
                self.coordinate_system,
                sl.COORDINATE_SYSTEM.RIGHT_HANDED_Z_UP_X_FWD,
            )
            init_params.depth_mode = getattr(sl.DEPTH_MODE, self.depth_mode, sl.DEPTH_MODE.PERFORMANCE)
            if hasattr(init_params, "depth_minimum_distance"):
                init_params.depth_minimum_distance = self.min_depth_m
            if hasattr(init_params, "depth_maximum_distance"):
                init_params.depth_maximum_distance = self.max_depth_m

            camera = sl.Camera()
            open_result = camera.open(init_params)
            if open_result != sl.ERROR_CODE.SUCCESS:
                self._last_runtime_error = f"Failed to open ZED camera: {open_result}"
                raise RuntimeError(self._last_runtime_error)

            self._camera = camera
            self._image_mat = sl.Mat()
            self._point_cloud_mat = sl.Mat()
            self._last_runtime_error = None

    def _capture_frame(self) -> tuple[np.ndarray, np.ndarray]:
        self._ensure_camera()
        sl = self._sl
        runtime = sl.RuntimeParameters()
        grab_result = self._camera.grab(runtime)
        if grab_result != sl.ERROR_CODE.SUCCESS:
            self._last_runtime_error = f"Failed to grab a frame from the ZED camera: {grab_result}"
            raise RuntimeError(self._last_runtime_error)

        self._camera.retrieve_image(self._image_mat, sl.VIEW.LEFT)
        self._camera.retrieve_measure(self._point_cloud_mat, sl.MEASURE.XYZRGBA)
        image = np.array(self._image_mat.get_data(), copy=True)
        point_cloud = np.array(self._point_cloud_mat.get_data(), copy=True)
        self._last_runtime_error = None
        return image, point_cloud

    def _load_explicit_detections(self, payload: dict[str, Any]) -> list[DetectionCandidate]:
        if payload.get("detections"):
            return self._parse_detections(payload["detections"], source="payload")
        if self.detections_path and self.detections_path.exists():
            raw = json.loads(self.detections_path.read_text())
            if isinstance(raw, dict):
                raw = raw.get("detections", [])
            if isinstance(raw, list):
                return self._parse_detections(raw, source="fixture")
        return []

    def _parse_detections(self, items: list[dict[str, Any]], *, source: str) -> list[DetectionCandidate]:
        detections: list[DetectionCandidate] = []
        for index, item in enumerate(items):
            label = str(item.get("label", "object")).strip()
            if not label:
                continue
            bbox = _normalize_bbox(item)
            if bbox is None:
                continue
            detections.append(
                DetectionCandidate(
                    label=label,
                    color=item.get("color"),
                    confidence=float(item.get("confidence", item.get("probability", 0.8))),
                    bbox=bbox,
                    support_surface=item.get("support_surface"),
                    object_id=item.get("object_id") or f"{label}-{item.get('color') or 'unknown'}-{index + 1:02d}",
                    metadata={"source": source},
                )
            )
        return detections

    def _ground_explicit_detections(
        self,
        detections: list[DetectionCandidate],
        point_cloud: np.ndarray,
        *,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> list[PerceivedObject]:
        grounded: list[PerceivedObject] = []
        ordered = sorted(detections, key=lambda item: (item.label != "table", item.label, item.color or ""))
        table_height_camera: float | None = None
        for index, detection in enumerate(ordered):
            pose_camera = self._bbox_pose_from_point_cloud(
                point_cloud,
                detection.bbox,
                table_height_camera=table_height_camera if detection.label != "table" else None,
            )
            if pose_camera is None:
                continue
            pose = self._camera_pose_to_robot_pose(pose_camera, localization, map_frame, base_frame)
            object_id = detection.object_id or f"{detection.label}-{detection.color or 'unknown'}-{index + 1:02d}"
            support_surface = detection.support_surface
            if detection.label == "table":
                table_height_camera = pose_camera.z
                support_surface = None
                object_id = object_id or "table-main"
            elif support_surface is None and table_height_camera is not None and pose_camera.z >= table_height_camera - 0.03:
                support_surface = "table"
            grounded.append(
                PerceivedObject(
                    object_id=object_id,
                    label=detection.label,
                    color=detection.color,
                    confidence=detection.confidence,
                    pose=pose,
                    support_surface=support_surface,
                )
            )
        return grounded

    def _bbox_pose_from_point_cloud(
        self,
        point_cloud: np.ndarray,
        bbox: tuple[int, int, int, int],
        *,
        table_height_camera: float | None,
    ) -> Pose3D | None:
        x1, y1, x2, y2 = bbox
        region = point_cloud[y1:y2, x1:x2, :3]
        if region.size == 0:
            return None
        points = region.reshape(-1, 3)
        valid = np.isfinite(points).all(axis=1)
        valid &= points[:, 0] > self.min_depth_m
        valid &= points[:, 0] < self.max_depth_m
        if table_height_camera is not None:
            valid &= points[:, 2] >= table_height_camera - 0.02
            valid &= points[:, 2] <= table_height_camera + 0.35
        points = points[valid]
        if len(points) < 20:
            return None
        centroid = _robust_point_centroid(points)
        return Pose3D(x=float(centroid[0]), y=float(centroid[1]), z=float(centroid[2]), frame=self.camera_frame)

    def _infer_heuristic_objects(
        self,
        payload: dict[str, Any],
        image: np.ndarray,
        point_cloud: np.ndarray,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> list[PerceivedObject]:
        requested_label = payload.get("label")
        requested_color = payload.get("color")
        objects: list[PerceivedObject] = []

        table_object, table_height_camera = self._detect_table(point_cloud, localization, map_frame, base_frame)
        if table_object and (requested_label in (None, "table") or requested_label == table_object.label):
            objects.append(table_object)

        colors_to_try: list[str | None]
        if requested_color:
            colors_to_try = [requested_color]
        elif requested_label == "apple":
            colors_to_try = ["green", "red", "yellow"]
        elif requested_label and requested_label != "table":
            colors_to_try = [None]
        else:
            colors_to_try = ["green", "red", "yellow", "blue"]

        if requested_label != "table":
            for color in colors_to_try:
                inferred = self._detect_color_object(
                    label=requested_label or ("apple" if color else "object"),
                    color=color,
                    image=image,
                    point_cloud=point_cloud,
                    table_height_camera=table_height_camera,
                    localization=localization,
                    map_frame=map_frame,
                    base_frame=base_frame,
                )
                if inferred is None:
                    continue
                if requested_label and inferred.label != requested_label:
                    continue
                if requested_color and inferred.color != requested_color:
                    continue
                objects.append(inferred)
        return objects

    def _detect_table(
        self,
        point_cloud: np.ndarray,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> tuple[PerceivedObject | None, float | None]:
        xyz = point_cloud[..., :3]
        rows, cols = xyz.shape[:2]
        row_slice = slice(rows // 4, rows)
        col_slice = slice(cols // 10, cols - cols // 10)
        region = xyz[row_slice, col_slice]
        sample = region[:: self.point_stride, :: self.point_stride].reshape(-1, 3)
        if sample.size == 0:
            return None, None
        valid = np.isfinite(sample).all(axis=1)
        valid &= sample[:, 0] > 0.2
        valid &= sample[:, 0] < self.max_depth_m
        valid &= np.abs(sample[:, 1]) < 1.8
        valid &= sample[:, 2] > self.table_height_min
        valid &= sample[:, 2] < self.table_height_max
        points = sample[valid]
        if len(points) < self.table_min_inliers:
            return None, None

        z_values = points[:, 2]
        bins = max(12, int((self.table_height_max - self.table_height_min) / max(self.table_band_width, 1e-3)))
        hist, edges = np.histogram(z_values, bins=bins, range=(self.table_height_min, self.table_height_max))
        if hist.size == 0:
            return None, None
        best_bin = int(np.argmax(hist))
        center_z = float((edges[best_bin] + edges[best_bin + 1]) * 0.5)
        inliers = points[np.abs(points[:, 2] - center_z) <= self.table_band_width]
        if len(inliers) < self.table_min_inliers:
            return None, None

        centroid = np.median(inliers, axis=0)
        pose_camera = Pose3D(
            x=float(centroid[0]),
            y=float(centroid[1]),
            z=float(centroid[2]),
            frame=self.camera_frame,
        )
        pose = self._camera_pose_to_robot_pose(pose_camera, localization, map_frame, base_frame)
        confidence = max(0.55, min(0.98, len(inliers) / max(len(points), 1)))
        return (
            PerceivedObject(
                object_id="table-main",
                label="table",
                color=None,
                confidence=float(confidence),
                pose=pose,
                support_surface=None,
            ),
            pose_camera.z,
        )

    def _detect_color_object(
        self,
        *,
        label: str,
        color: str | None,
        image: np.ndarray,
        point_cloud: np.ndarray,
        table_height_camera: float | None,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> PerceivedObject | None:
        bgr = image[..., :3].astype(np.float32)
        blue = bgr[..., 0]
        green = bgr[..., 1]
        red = bgr[..., 2]

        valid = np.isfinite(point_cloud[..., :3]).all(axis=2)
        valid &= point_cloud[..., 0] > self.min_depth_m
        valid &= point_cloud[..., 0] < self.max_depth_m
        if table_height_camera is not None:
            valid &= point_cloud[..., 2] >= table_height_camera - 0.02
            valid &= point_cloud[..., 2] <= table_height_camera + 0.30

        color_key = (color or "").lower()
        if color_key == "green":
            mask = (green > 70) & (green > red * 1.18) & (green > blue * 1.12)
        elif color_key == "red":
            mask = (red > 75) & (red > green * 1.18) & (red > blue * 1.1)
        elif color_key == "yellow":
            mask = (red > 80) & (green > 80) & (blue < 120) & (np.abs(red - green) < 70)
        elif color_key == "blue":
            mask = (blue > 70) & (blue > red * 1.15) & (blue > green * 1.1)
        elif label == "apple":
            mask = (
                ((green > 70) & (green > red * 1.15) & (green > blue * 1.1))
                | ((red > 75) & (red > green * 1.15) & (red > blue * 1.05))
                | ((red > 80) & (green > 80) & (blue < 120) & (np.abs(red - green) < 70))
            )
        else:
            return None

        mask &= valid
        rows, cols = np.where(mask)
        if len(rows) < self.color_mask_min_pixels:
            return None

        points = point_cloud[rows, cols, :3]
        centroid = _robust_point_centroid(points)
        distances = np.linalg.norm(points - centroid, axis=1)
        keep = distances <= np.quantile(distances, 0.8)
        if np.any(keep):
            rows = rows[keep]
            cols = cols[keep]
            points = points[keep]
            centroid = _robust_point_centroid(points)

        if len(points) < max(30, self.color_mask_min_pixels // 4):
            return None

        pose_camera = Pose3D(
            x=float(centroid[0]),
            y=float(centroid[1]),
            z=float(centroid[2]),
            frame=self.camera_frame,
        )
        pose = self._camera_pose_to_robot_pose(pose_camera, localization, map_frame, base_frame)
        compactness = float(np.quantile(distances, 0.5)) if len(distances) else 0.0
        confidence = 0.55
        if table_height_camera is not None:
            confidence += 0.12
        confidence += min(0.2, len(points) / 4000.0)
        confidence -= min(0.15, compactness * 0.8)
        confidence = max(0.35, min(0.95, confidence))
        inferred_label = label or "object"
        inferred_color = color or self._infer_color_name(red[rows, cols], green[rows, cols], blue[rows, cols])
        return PerceivedObject(
            object_id=f"{inferred_label}-{inferred_color or 'unknown'}-01",
            label=inferred_label,
            color=inferred_color,
            confidence=confidence,
            pose=pose,
            support_surface="table" if table_height_camera is not None else None,
        )

    def _camera_pose_to_robot_pose(
        self,
        pose_camera: Pose3D,
        localization: Pose2D | None,
        map_frame: str,
        base_frame: str,
    ) -> Pose3D:
        point_camera = np.array([pose_camera.x, pose_camera.y, pose_camera.z], dtype=np.float64)
        point_base = self._camera_to_base_rotation @ point_camera + self.camera_to_base_translation
        if localization is None:
            return Pose3D(
                x=float(point_base[0]),
                y=float(point_base[1]),
                z=float(point_base[2]),
                roll=pose_camera.roll,
                pitch=pose_camera.pitch,
                yaw=pose_camera.yaw + self.camera_to_base_rpy[2],
                frame=base_frame,
            )

        cos_yaw = math.cos(localization.yaw)
        sin_yaw = math.sin(localization.yaw)
        x_map = localization.x + cos_yaw * point_base[0] - sin_yaw * point_base[1]
        y_map = localization.y + sin_yaw * point_base[0] + cos_yaw * point_base[1]
        return Pose3D(
            x=float(x_map),
            y=float(y_map),
            z=float(point_base[2]),
            roll=pose_camera.roll,
            pitch=pose_camera.pitch,
            yaw=pose_camera.yaw + self.camera_to_base_rpy[2] + localization.yaw,
            frame=map_frame,
        )

    def _infer_color_name(self, red: np.ndarray, green: np.ndarray, blue: np.ndarray) -> str | None:
        if red.size == 0:
            return None
        red_mean = float(np.mean(red))
        green_mean = float(np.mean(green))
        blue_mean = float(np.mean(blue))
        if green_mean > red_mean * 1.1 and green_mean > blue_mean * 1.1:
            return "green"
        if red_mean > green_mean * 1.1 and red_mean > blue_mean * 1.05:
            return "red"
        if blue_mean > red_mean * 1.05 and blue_mean > green_mean * 1.05:
            return "blue"
        if red_mean > 70 and green_mean > 70 and blue_mean < 120:
            return "yellow"
        return None


def build_perception_backend(
    *,
    backend_name: str | None,
    mock_mode: bool,
    camera_name: str,
    map_frame: str,
    base_frame: str,
    detections_path: str | None,
    default_objects: list[PerceivedObject],
    detector_backend_name: str | None = None,
    detector_url: str | None = None,
    detector_timeout_s: float | None = None,
    detector_model: str | None = None,
) -> BasePerceptionBackend:
    resolved = (backend_name or ("mock" if mock_mode else "zed")).strip().lower()
    if resolved == "mock":
        return MockPerceptionBackend(camera_name=camera_name, map_frame=map_frame, objects=default_objects)
    if resolved != "zed":
        raise ValueError(f"Unsupported perception backend '{backend_name}'. Expected 'mock' or 'zed'.")
    return ZedStereoPerceptionBackend(
        camera_name=camera_name,
        map_frame=map_frame,
        base_frame=base_frame,
        detections_path=detections_path,
        detector_backend_name=detector_backend_name,
        detector_url=detector_url,
        detector_timeout_s=detector_timeout_s,
        detector_model=detector_model,
    )


def _normalize_bbox(item: dict[str, Any]) -> tuple[int, int, int, int] | None:
    if item.get("bbox") and len(item["bbox"]) == 4:
        x1, y1, x2, y2 = [int(round(float(value))) for value in item["bbox"]]
        return _sanitize_bbox(x1, y1, x2, y2)
    if item.get("bounding_box_2d"):
        coords = item["bounding_box_2d"]
        xs = [int(round(float(point[0]))) for point in coords]
        ys = [int(round(float(point[1]))) for point in coords]
        return _sanitize_bbox(min(xs), min(ys), max(xs), max(ys))
    return None


def _sanitize_bbox(x1: int, y1: int, x2: int, y2: int) -> tuple[int, int, int, int] | None:
    if x2 <= x1 or y2 <= y1:
        return None
    return max(0, x1), max(0, y1), max(1, x2), max(1, y2)


def _robust_point_centroid(points: np.ndarray) -> np.ndarray:
    centroid = np.median(points, axis=0)
    if len(points) < 8:
        return centroid
    distances = np.linalg.norm(points - centroid, axis=1)
    keep = distances <= np.quantile(distances, 0.7)
    if np.any(keep):
        centroid = np.median(points[keep], axis=0)
    return centroid


def _scene_summary(objects: list[PerceivedObject]) -> str:
    if not objects:
        return "No relevant objects detected in the current scene."
    bits = []
    for item in objects:
        qualifier = f"{item.color} " if item.color else ""
        bits.append(f"{qualifier}{item.label} at ({item.pose.x:.2f}, {item.pose.y:.2f}, {item.pose.z:.2f})")
    return "Detected " + ", ".join(bits) + "."


def _rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr = math.cos(roll)
    sr = math.sin(roll)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cy = math.cos(yaw)
    sy = math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=np.float64,
    )


def _deduplicate_objects(objects: list[PerceivedObject]) -> list[PerceivedObject]:
    deduped: dict[str, PerceivedObject] = {}
    for item in objects:
        key = item.object_id
        current = deduped.get(key)
        if current is None or item.confidence > current.confidence:
            deduped[key] = item
    return list(deduped.values())

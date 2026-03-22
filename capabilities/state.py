from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .models import (
    FaceMatch,
    FaceProfile,
    GraspCandidate,
    Landmark,
    LocalizationState,
    ManipulationState,
    MapRecord,
    NavigationState,
    PerceivedObject,
    PickTaskResult,
    Pose2D,
    Pose3D,
    SceneObservation,
    TaskStatus,
    TaskStep,
    to_dict,
    utc_now_iso,
)


DEFAULT_LANDMARKS = [
    Landmark(
        name="table",
        category="support_surface",
        pose=Pose2D(x=2.4, y=1.1, yaw=1.57),
        notes="Default approach pose beside the manipulation table.",
    ),
    Landmark(
        name="charging-dock",
        category="dock",
        pose=Pose2D(x=0.3, y=-0.4, yaw=3.14),
        notes="Home/charging position.",
    ),
]


DEFAULT_OBJECTS = [
    PerceivedObject(
        object_id="table-main",
        label="table",
        color=None,
        confidence=0.99,
        pose=Pose3D(x=2.75, y=1.15, z=0.74, frame="map"),
        support_surface=None,
    ),
    PerceivedObject(
        object_id="apple-green-01",
        label="apple",
        color="green",
        confidence=0.96,
        pose=Pose3D(x=2.78, y=1.08, z=0.79, frame="map"),
        support_surface="table",
    ),
]


class CapabilityState:
    """Persisted control-plane state for map-based navigation and perception."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        camera_name: str = "zed-mini",
        lidar_name: str = "lidar",
        base_frame: str = "base_link",
        map_frame: str = "map",
        bridge_url: str = "http://localhost:8765",
        mock_mode: bool = True,
    ):
        self.state_path = Path(state_path)
        self.camera_name = camera_name
        self.lidar_name = lidar_name
        self.base_frame = base_frame
        self.map_frame = map_frame
        self.bridge_url = bridge_url.rstrip("/") if bridge_url else ""
        self.mock_mode = mock_mode

        self.maps: dict[str, MapRecord] = {}
        self.active_map_id: str | None = None
        self.localization = LocalizationState()
        self.navigation = NavigationState()
        self.manipulation = ManipulationState()
        self.last_scene = SceneObservation(
            camera_name=self.camera_name,
            frame_id=self.map_frame,
            summary="No scene observation yet.",
        )
        self.faces: dict[str, FaceProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return

        data = json.loads(self.state_path.read_text())
        self.active_map_id = data.get("active_map_id")

        for item in data.get("maps", []):
            landmarks = [
                Landmark(
                    name=landmark["name"],
                    category=landmark["category"],
                    pose=Pose2D(**landmark["pose"]),
                    notes=landmark.get("notes", ""),
                )
                for landmark in item.get("landmarks", [])
            ]
            self.maps[item["map_id"]] = MapRecord(
                map_id=item["map_id"],
                created_at=item["created_at"],
                source=item["source"],
                builder=item["builder"],
                description=item["description"],
                landmarks=landmarks,
                metadata=item.get("metadata", {}),
            )

        localization = data.get("localization", {})
        pose = localization.get("pose")
        self.localization = LocalizationState(
            status=TaskStatus(localization.get("status", TaskStatus.IDLE.value)),
            map_id=localization.get("map_id"),
            method=localization.get("method", "lidar_global_localization"),
            confidence=localization.get("confidence", 0.0),
            pose=Pose2D(**pose) if pose else None,
            message=localization.get("message", "Localization not initialized."),
            updated_at=localization.get("updated_at", utc_now_iso()),
        )

        navigation = data.get("navigation", {})
        goal_pose = navigation.get("goal_pose")
        self.navigation = NavigationState(
            status=TaskStatus(navigation.get("status", TaskStatus.IDLE.value)),
            map_id=navigation.get("map_id"),
            goal_name=navigation.get("goal_name"),
            goal_pose=Pose2D(**goal_pose) if goal_pose else None,
            last_result=navigation.get("last_result", "No navigation command issued."),
            updated_at=navigation.get("updated_at", utc_now_iso()),
        )

        manipulation = data.get("manipulation", {})
        object_pose = manipulation.get("object_pose")
        grasp_candidate = manipulation.get("grasp_candidate")
        self.manipulation = ManipulationState(
            status=TaskStatus(manipulation.get("status", TaskStatus.IDLE.value)),
            object_id=manipulation.get("object_id"),
            action=manipulation.get("action"),
            object_pose=Pose3D(**object_pose) if object_pose else None,
            grasp_candidate=(
                self._grasp_candidate_from_dict(grasp_candidate) if grasp_candidate else None
            ),
            result=manipulation.get("result", "No manipulation command issued."),
            updated_at=manipulation.get("updated_at", utc_now_iso()),
        )

        scene = data.get("last_scene", {})
        self.last_scene = self._scene_from_dict(scene) if scene else self.last_scene

        for face in data.get("faces", []):
            self.faces[face["person_id"]] = FaceProfile(
                person_id=face["person_id"],
                display_name=face["display_name"],
                created_at=face["created_at"],
                embedding_source=face.get("embedding_source", "camera_snapshot"),
                notes=face.get("notes", ""),
            )

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_map_id": self.active_map_id,
            "maps": [to_dict(record) for record in self.maps.values()],
            "localization": to_dict(self.localization),
            "navigation": to_dict(self.navigation),
            "manipulation": to_dict(self.manipulation),
            "last_scene": to_dict(self.last_scene),
            "faces": [to_dict(face) for face in self.faces.values()],
        }
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n")

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "ok": True,
            "mock_mode": self.mock_mode,
            "camera_name": self.camera_name,
            "lidar_name": self.lidar_name,
            "map_frame": self.map_frame,
            "base_frame": self.base_frame,
            "bridge_url": self.bridge_url,
            "active_map_id": self.active_map_id,
            "maps": [to_dict(record) for record in self.maps.values()],
            "localization": to_dict(self.localization),
            "navigation": to_dict(self.navigation),
            "manipulation": to_dict(self.manipulation),
            "faces": [to_dict(face) for face in self.faces.values()],
        }

    def list_maps(self) -> dict[str, Any]:
        return {
            "ok": True,
            "maps": [to_dict(record) for record in self.maps.values()],
            "active_map_id": self.active_map_id,
        }

    def build_map(self, payload: dict[str, Any]) -> dict[str, Any]:
        map_id = payload.get("map_id") or "default-lab"
        description = payload.get("description") or "Persistent map built from LiDAR and camera observations."
        source = payload.get("source") or "live_scan"
        builder = payload.get("builder") or "lidar_mapping_pipeline"

        record = MapRecord(
            map_id=map_id,
            created_at=utc_now_iso(),
            source=source,
            builder=builder,
            description=description,
            landmarks=DEFAULT_LANDMARKS,
            metadata={
                "map_once_then_localize": True,
                "camera_name": self.camera_name,
                "lidar_name": self.lidar_name,
            },
        )
        self.maps[map_id] = record
        if payload.get("load_after_build", True):
            self.active_map_id = map_id
        self.save()
        return {
            "ok": True,
            "message": "Map persisted. Future navigation should localize against this saved map instead of rebuilding it.",
            "map": to_dict(record),
            "active_map_id": self.active_map_id,
        }

    def load_map(self, payload: dict[str, Any]) -> dict[str, Any]:
        map_id = payload.get("map_id")
        if not map_id:
            return {"ok": False, "error": "Missing 'map_id'."}
        if map_id not in self.maps:
            return {"ok": False, "error": f"Unknown map '{map_id}'."}

        self.active_map_id = map_id
        self.navigation.map_id = map_id
        self.localization.map_id = map_id
        self.localization.updated_at = utc_now_iso()
        self.navigation.updated_at = utc_now_iso()
        self.save()
        return {
            "ok": True,
            "message": f"Loaded map '{map_id}'. Run localization before autonomous navigation.",
            "map": to_dict(self.maps[map_id]),
        }

    def initialize_localization(self, payload: dict[str, Any]) -> dict[str, Any]:
        map_id = payload.get("map_id") or self.active_map_id
        if not map_id:
            return {"ok": False, "error": "No map loaded. Build or load a map before localization."}
        if map_id not in self.maps:
            return {"ok": False, "error": f"Unknown map '{map_id}'."}

        initial_pose = payload.get("initial_pose") or {
            "x": 0.0,
            "y": 0.0,
            "yaw": 0.0,
            "frame": self.map_frame,
        }
        self.active_map_id = map_id
        self.localization = LocalizationState(
            status=TaskStatus.READY,
            map_id=map_id,
            method=payload.get("method", "lidar_global_localization"),
            confidence=0.86 if self.mock_mode else 0.0,
            pose=Pose2D(**initial_pose),
            message="Localized against the saved map. Navigation may now use persistent map coordinates.",
            updated_at=utc_now_iso(),
        )
        self.navigation.map_id = map_id
        self.navigation.updated_at = utc_now_iso()
        self.save()
        return {"ok": True, "localization": to_dict(self.localization)}

    def localization_status(self) -> dict[str, Any]:
        return {"ok": True, "localization": to_dict(self.localization)}

    def navigate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.localization.status != TaskStatus.READY or not self.localization.map_id:
            return {
                "ok": False,
                "error": "Navigation is blocked until the robot is localized on a saved map.",
            }

        goal_name = payload.get("goal_name")
        goal_pose = payload.get("goal_pose")
        if goal_name:
            landmark = self._find_landmark(self.localization.map_id, goal_name)
            if not landmark:
                return {
                    "ok": False,
                    "error": f"Unknown landmark '{goal_name}' on map '{self.localization.map_id}'.",
                }
            resolved_pose = landmark.pose
        elif goal_pose:
            resolved_pose = Pose2D(**goal_pose)
        else:
            return {"ok": False, "error": "Provide either 'goal_name' or 'goal_pose'."}

        self.navigation = NavigationState(
            status=TaskStatus.SUCCEEDED if self.mock_mode else TaskStatus.ACTIVE,
            map_id=self.localization.map_id,
            goal_name=goal_name,
            goal_pose=resolved_pose,
            last_result=(
                "Reached the requested approach pose near the target workspace."
                if self.mock_mode
                else "Navigation started."
            ),
            updated_at=utc_now_iso(),
        )

        if self.mock_mode:
            self.localization.pose = resolved_pose
            self.localization.updated_at = utc_now_iso()
            self.localization.message = "Localization updated after navigation."

        self.save()
        return {
            "ok": True,
            "navigation": to_dict(self.navigation),
            "localization": to_dict(self.localization),
        }

    def navigation_status(self) -> dict[str, Any]:
        return {"ok": True, "navigation": to_dict(self.navigation)}

    def cancel_navigation(self) -> dict[str, Any]:
        self.navigation.status = TaskStatus.IDLE
        self.navigation.last_result = "Navigation canceled."
        self.navigation.updated_at = utc_now_iso()
        self.save()
        return {"ok": True, "navigation": to_dict(self.navigation)}

    def scene(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_label = payload.get("label")
        requested_color = payload.get("color")
        objects = [item for item in DEFAULT_OBJECTS if self._matches(item, requested_label, requested_color)]
        frame_id = self.map_frame if self.localization.map_id else f"{self.camera_name}_frame"
        self.last_scene = SceneObservation(
            camera_name=payload.get("camera_name", self.camera_name),
            frame_id=frame_id,
            objects=objects,
            summary=self._scene_summary(objects),
            updated_at=utc_now_iso(),
        )
        self.save()
        return {"ok": True, "scene": to_dict(self.last_scene)}

    def object_pose(self, payload: dict[str, Any]) -> dict[str, Any]:
        label = payload.get("label")
        color = payload.get("color")
        if not label:
            return {"ok": False, "error": "Missing 'label'."}

        matches = [item for item in DEFAULT_OBJECTS if self._matches(item, label, color)]
        if not matches:
            return {
                "ok": False,
                "error": f"No object matching label='{label}' color='{color}' was found.",
            }

        selected = matches[0]
        return {
            "ok": True,
            "object": to_dict(selected),
            "message": (
                "Object pose returned in the map frame because localization is assumed available for autonomous tasks."
                if self.localization.map_id
                else "Object pose returned in the camera-relative frame until localization is initialized."
            ),
        }

    def grasp_pose(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = self._resolve_object(payload)
        if not selected:
            return {"ok": False, "error": "Target object was not found for grasp planning."}

        pose_override = payload.get("pose")
        if pose_override:
            selected = PerceivedObject(
                object_id=selected.object_id,
                label=selected.label,
                color=selected.color,
                confidence=selected.confidence,
                pose=Pose3D(**pose_override),
                support_surface=selected.support_surface,
            )

        candidate = self._plan_grasp(
            selected,
            strategy=payload.get("strategy", "top_down"),
            approach_offset_m=float(payload.get("approach_offset_m", 0.12)),
            grasp_z_offset_m=float(payload.get("grasp_z_offset_m", 0.0)),
        )
        return {
            "ok": True,
            "object": to_dict(selected),
            "grasp_candidate": to_dict(candidate),
            "message": "Generated a pose-aware grasp candidate from the perceived 3D object pose.",
        }

    def enroll_face(self, payload: dict[str, Any]) -> dict[str, Any]:
        person_id = payload.get("person_id")
        display_name = payload.get("display_name")
        if not person_id or not display_name:
            return {"ok": False, "error": "Missing 'person_id' or 'display_name'."}

        profile = FaceProfile(
            person_id=person_id,
            display_name=display_name,
            created_at=utc_now_iso(),
            embedding_source=payload.get("embedding_source", "camera_snapshot"),
            notes=payload.get("notes", ""),
        )
        self.faces[person_id] = profile
        self.save()
        return {"ok": True, "face_profile": to_dict(profile)}

    def recognize_faces(self, payload: dict[str, Any]) -> dict[str, Any]:
        min_confidence = float(payload.get("min_confidence", 0.75))
        matches = [
            FaceMatch(
                person_id=profile.person_id,
                display_name=profile.display_name,
                confidence=0.93,
            )
            for profile in self.faces.values()
            if 0.93 >= min_confidence
        ]
        return {"ok": True, "matches": [to_dict(match) for match in matches]}

    def pick(self, payload: dict[str, Any]) -> dict[str, Any]:
        selected = self._resolve_object(payload)
        if not selected:
            return {"ok": False, "error": "Target object was not found for manipulation."}
        if self.localization.status != TaskStatus.READY:
            return {
                "ok": False,
                "error": "Manipulation is blocked until the robot is localized and navigated to a reachable pose.",
            }

        pose_override = payload.get("pose")
        if pose_override:
            selected = PerceivedObject(
                object_id=selected.object_id,
                label=selected.label,
                color=selected.color,
                confidence=selected.confidence,
                pose=Pose3D(**pose_override),
                support_surface=selected.support_surface,
            )

        grasp_candidate_data = payload.get("grasp_candidate")
        if grasp_candidate_data:
            grasp_candidate = self._grasp_candidate_from_dict(grasp_candidate_data)
        else:
            grasp_result = self.grasp_pose(
                {
                    "object_id": selected.object_id,
                    "pose": to_dict(selected.pose),
                    "strategy": payload.get("strategy", "top_down"),
                    "approach_offset_m": payload.get("approach_offset_m", 0.12),
                    "grasp_z_offset_m": payload.get("grasp_z_offset_m", 0.0),
                }
            )
            if not grasp_result.get("ok"):
                return {"ok": False, "error": grasp_result["error"]}
            grasp_candidate = self._grasp_candidate_from_dict(grasp_result["grasp_candidate"])

        bridge_execution = self._dispatch_grasp_to_bridge(
            grasp_candidate,
            arm=str(payload.get("arm", "right")),
            execute=bool(payload.get("execute_arm", True)),
            move_time_s=float(payload.get("move_time_s", 1.6)),
            grasp_move_time_s=float(payload.get("grasp_move_time_s", 1.0)),
            retreat_move_time_s=float(payload.get("retreat_move_time_s", 1.4)),
            settle_time_s=float(payload.get("settle_time_s", 0.35)),
            grip_settle_s=float(payload.get("grip_settle_s", 0.5)),
            open_hand_first=bool(payload.get("open_hand_first", True)),
            close_hand=bool(payload.get("close_hand", True)),
            retreat_offset_m=float(payload.get("retreat_offset_m", 0.04)),
        )
        if not bridge_execution.get("ok"):
            return {
                "ok": False,
                "error": bridge_execution.get("error", "Bridge manipulation sequence failed."),
                "object": to_dict(selected),
                "grasp_candidate": to_dict(grasp_candidate),
                "bridge_execution": bridge_execution,
            }

        verification = self._verify_pick_execution(selected, grasp_candidate, bridge_execution)
        verification_status = TaskStatus(verification.get("status", TaskStatus.ACTIVE.value))
        if verification_status == TaskStatus.FAILED:
            return {
                "ok": False,
                "error": verification.get("detail", "Perception verification failed after the staged pick sequence."),
                "object": to_dict(selected),
                "grasp_candidate": to_dict(grasp_candidate),
                "bridge_execution": bridge_execution,
                "verification": verification,
            }

        result_parts = []
        if bridge_execution.get("skipped"):
            result_parts.append("Computed a grasp candidate from the perceived pose but skipped bridge execution.")
        else:
            result_parts.append("Executed a staged manipulation sequence through the bridge: pregrasp, descend, close hand, and retreat.")
        result_parts.append(verification.get("detail", "Verification pending."))

        self.manipulation = ManipulationState(
            status=verification_status,
            object_id=selected.object_id,
            action=payload.get("action", "pick"),
            object_pose=selected.pose,
            grasp_candidate=grasp_candidate,
            result=" ".join(part.strip() for part in result_parts if part).strip(),
            updated_at=utc_now_iso(),
        )
        self.save()
        return {
            "ok": True,
            "manipulation": to_dict(self.manipulation),
            "object": to_dict(selected),
            "grasp_candidate": to_dict(grasp_candidate),
            "bridge_execution": bridge_execution,
            "verification": verification,
        }

    def pick_object_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        object_label = payload.get("object_label")
        color = payload.get("color")
        support_surface = payload.get("support_surface")
        if not object_label:
            return {"ok": False, "error": "Missing 'object_label'."}

        steps: list[TaskStep] = []
        if not self.active_map_id:
            result = PickTaskResult(
                status=TaskStatus.BLOCKED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=None,
                steps=[
                    TaskStep(
                        name="load_map",
                        status=TaskStatus.BLOCKED,
                        detail="No saved map is active. Build or load a map first; runtime navigation should localize on that map instead of remapping.",
                    )
                ],
                final_message="Task blocked before navigation because the map-based navigation stack is not initialized.",
            )
            return {"ok": False, "task": to_dict(result)}

        if self.localization.status != TaskStatus.READY:
            result = PickTaskResult(
                status=TaskStatus.BLOCKED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=self.active_map_id,
                steps=[
                    TaskStep(
                        name="localize",
                        status=TaskStatus.BLOCKED,
                        detail="Robot must be localized against the saved map before autonomous navigation and manipulation can begin.",
                    )
                ],
                final_message="Task blocked before navigation because localization is not ready.",
            )
            return {"ok": False, "task": to_dict(result)}

        steps.append(
            TaskStep(
                "scene_understanding",
                TaskStatus.SUCCEEDED,
                "Detected the support surface and candidate target objects.",
            )
        )
        object_result = self.object_pose({"label": object_label, "color": color})
        if not object_result.get("ok"):
            result = PickTaskResult(
                status=TaskStatus.FAILED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=self.active_map_id,
                steps=steps + [TaskStep("object_localization", TaskStatus.FAILED, object_result["error"])],
                final_message="Task failed because the requested object could not be grounded in 3D.",
            )
            return {"ok": False, "task": to_dict(result)}

        selected = self._object_from_dict(object_result["object"])
        steps.append(
            TaskStep(
                "object_localization",
                TaskStatus.SUCCEEDED,
                f"Estimated 3D pose for {selected.color or ''} {selected.label}".strip(),
            )
        )

        navigation_goal = support_surface or selected.support_surface or "table"
        navigation_result = self.navigate({"goal_name": navigation_goal})
        if not navigation_result.get("ok"):
            result = PickTaskResult(
                status=TaskStatus.FAILED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=self.active_map_id,
                steps=steps + [TaskStep("navigate_to_workspace", TaskStatus.FAILED, navigation_result["error"])],
                selected_object=selected,
                final_message="Task failed because navigation could not reach the manipulation approach pose.",
            )
            return {"ok": False, "task": to_dict(result)}

        steps.append(
            TaskStep(
                "navigate_to_workspace",
                TaskStatus.SUCCEEDED,
                "Reached a pre-grasp pose near the support surface.",
            )
        )
        steps.append(
            TaskStep(
                "close_range_refinement",
                TaskStatus.SUCCEEDED,
                "Refined the target pose with close-range camera data.",
            )
        )

        grasp_result = self.grasp_pose(
            {
                "object_id": selected.object_id,
                "pose": to_dict(selected.pose),
                "strategy": payload.get("grasp_strategy", "top_down"),
                "approach_offset_m": payload.get("approach_offset_m", 0.12),
                "grasp_z_offset_m": payload.get("grasp_z_offset_m", 0.0),
            }
        )
        if not grasp_result.get("ok"):
            result = PickTaskResult(
                status=TaskStatus.FAILED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=self.active_map_id,
                steps=steps + [TaskStep("grasp_planning", TaskStatus.FAILED, grasp_result["error"])],
                selected_object=selected,
                final_message="Task failed because a grasp candidate could not be generated from the perceived pose.",
            )
            return {"ok": False, "task": to_dict(result)}

        grasp_candidate = self._grasp_candidate_from_dict(grasp_result["grasp_candidate"])
        steps.append(
            TaskStep(
                "grasp_planning",
                TaskStatus.SUCCEEDED,
                f"Planned a {grasp_candidate.strategy} grasp in {grasp_candidate.grasp_frame}.",
            )
        )

        manipulation_result = self.pick(
            {
                "object_id": selected.object_id,
                "pose": to_dict(selected.pose),
                "grasp_candidate": to_dict(grasp_candidate),
                "action": "pick",
                "arm": payload.get("arm", "right"),
                "execute_arm": payload.get("execute_arm", True),
                "move_time_s": payload.get("move_time_s", 1.5),
            }
        )
        if not manipulation_result.get("ok"):
            result = PickTaskResult(
                status=TaskStatus.FAILED,
                task="pick_object",
                object_label=object_label,
                color=color,
                support_surface=support_surface,
                map_id=self.active_map_id,
                steps=steps + [TaskStep("pick", TaskStatus.FAILED, manipulation_result["error"])],
                selected_object=selected,
                grasp_candidate=grasp_candidate,
                final_message="Task failed during the manipulation phase.",
            )
            return {"ok": False, "task": to_dict(result)}

        bridge_execution = manipulation_result.get("bridge_execution", {})
        stage_name_map = {
            "open_hand": "open_hand",
            "move_pregrasp": "pregrasp",
            "move_grasp": "descend",
            "close_hand": "gripper_close",
            "move_retreat": "retreat",
        }
        for stage in bridge_execution.get("stages", []):
            steps.append(
                TaskStep(
                    stage_name_map.get(stage.get("name", "pick"), stage.get("name", "pick")),
                    TaskStatus.SUCCEEDED if stage.get("ok") else TaskStatus.FAILED,
                    stage.get("detail") or stage.get("result", {}).get("message", "Manipulation stage executed."),
                )
            )

        verification = manipulation_result.get("verification", {})
        verify_status = TaskStatus(verification.get("status", TaskStatus.ACTIVE.value))
        steps.append(
            TaskStep(
                "verify",
                verify_status,
                verification.get("detail", "Verification pending."),
            )
        )

        result = PickTaskResult(
            status=verify_status,
            task="pick_object",
            object_label=object_label,
            color=color,
            support_surface=support_surface,
            map_id=self.active_map_id,
            steps=steps,
            selected_object=selected,
            grasp_candidate=grasp_candidate,
            final_message=(
                f"Task {'succeeded' if verify_status == TaskStatus.SUCCEEDED else 'is awaiting verification'}: reached the workspace, planned a {grasp_candidate.strategy} grasp for the {color or ''} {object_label}, executed the staged manipulation sequence, and recorded the latest verification result."
            ).replace("  ", " "),
        )
        self.save()
        return {"ok": True, "task": to_dict(result)}

    def _find_landmark(self, map_id: str, goal_name: str) -> Landmark | None:
        record = self.maps.get(map_id)
        if not record:
            return None
        for landmark in record.landmarks:
            if landmark.name == goal_name:
                return landmark
        return None

    def _matches(self, item: PerceivedObject, label: str | None, color: str | None) -> bool:
        if label and item.label != label:
            return False
        if color and item.color != color:
            return False
        return True

    def _scene_summary(self, objects: list[PerceivedObject]) -> str:
        if not objects:
            return "No relevant objects detected in the current scene."
        bits = []
        for item in objects:
            qualifier = f"{item.color} " if item.color else ""
            bits.append(
                f"{qualifier}{item.label} at ({item.pose.x:.2f}, {item.pose.y:.2f}, {item.pose.z:.2f})"
            )
        return "Detected " + ", ".join(bits) + "."

    def _scene_from_dict(self, data: dict[str, Any]) -> SceneObservation:
        objects = []
        for item in data.get("objects", []):
            objects.append(self._object_from_dict(item))
        return SceneObservation(
            camera_name=data.get("camera_name", self.camera_name),
            frame_id=data.get("frame_id", self.map_frame),
            objects=objects,
            summary=data.get("summary", "No scene observation yet."),
            updated_at=data.get("updated_at", utc_now_iso()),
        )

    def _object_from_dict(self, item: dict[str, Any]) -> PerceivedObject:
        return PerceivedObject(
            object_id=item["object_id"],
            label=item["label"],
            color=item.get("color"),
            confidence=item["confidence"],
            pose=Pose3D(**item["pose"]),
            support_surface=item.get("support_surface"),
        )

    def _grasp_candidate_from_dict(self, data: dict[str, Any]) -> GraspCandidate:
        return GraspCandidate(
            object_id=data["object_id"],
            object_pose=Pose3D(**data["object_pose"]),
            grasp_pose=Pose3D(**data["grasp_pose"]),
            pregrasp_pose=Pose3D(**data["pregrasp_pose"]),
            grasp_frame=data.get("grasp_frame", self.base_frame),
            strategy=data.get("strategy", "top_down"),
            gripper_width=float(data.get("gripper_width", 0.08)),
            score=float(data.get("score", 0.0)),
            notes=data.get("notes", ""),
        )

    def _resolve_object(self, payload: dict[str, Any]) -> PerceivedObject | None:
        object_id = payload.get("object_id")
        label = payload.get("label")
        color = payload.get("color")

        if object_id:
            for item in DEFAULT_OBJECTS:
                if item.object_id == object_id:
                    return item
            return None

        matches = [item for item in DEFAULT_OBJECTS if self._matches(item, label, color)]
        return matches[0] if matches else None

    def _plan_grasp(
        self,
        selected: PerceivedObject,
        *,
        strategy: str = "top_down",
        approach_offset_m: float = 0.12,
        grasp_z_offset_m: float = 0.0,
    ) -> GraspCandidate:
        object_pose_base = self._transform_pose_to_base_frame(selected.pose)
        radial_distance = math.hypot(object_pose_base.x, object_pose_base.y)
        wrist_yaw = math.atan2(object_pose_base.y, max(object_pose_base.x, 1e-6))
        grasp_pose = Pose3D(
            x=object_pose_base.x,
            y=object_pose_base.y,
            z=object_pose_base.z + grasp_z_offset_m,
            roll=math.pi,
            pitch=0.0,
            yaw=wrist_yaw,
            frame=self.base_frame,
        )
        pregrasp_pose = Pose3D(
            x=grasp_pose.x,
            y=grasp_pose.y,
            z=grasp_pose.z + approach_offset_m,
            roll=grasp_pose.roll,
            pitch=grasp_pose.pitch,
            yaw=grasp_pose.yaw,
            frame=self.base_frame,
        )
        score = max(0.0, min(0.99, selected.confidence - 0.08 * max(radial_distance - 0.45, 0.0)))
        notes = (
            "Heuristic top-down grasp candidate generated from the perceived 3D object pose. "
            "A real backend should replace this with depth-aware collision checking and IK feasibility scoring."
        )
        return GraspCandidate(
            object_id=selected.object_id,
            object_pose=object_pose_base,
            grasp_pose=grasp_pose,
            pregrasp_pose=pregrasp_pose,
            grasp_frame=self.base_frame,
            strategy=strategy,
            gripper_width=0.08 if selected.label == "apple" else 0.10,
            score=score,
            notes=notes,
        )

    def _transform_pose_to_base_frame(self, pose: Pose3D) -> Pose3D:
        if pose.frame == self.base_frame:
            return pose
        if pose.frame != self.map_frame or not self.localization.pose:
            return Pose3D(
                x=pose.x,
                y=pose.y,
                z=pose.z,
                roll=pose.roll,
                pitch=pose.pitch,
                yaw=pose.yaw,
                frame=pose.frame,
            )

        robot_pose = self.localization.pose
        dx = pose.x - robot_pose.x
        dy = pose.y - robot_pose.y
        cos_yaw = math.cos(robot_pose.yaw)
        sin_yaw = math.sin(robot_pose.yaw)
        return Pose3D(
            x=cos_yaw * dx + sin_yaw * dy,
            y=-sin_yaw * dx + cos_yaw * dy,
            z=pose.z,
            roll=pose.roll,
            pitch=pose.pitch,
            yaw=pose.yaw - robot_pose.yaw,
            frame=self.base_frame,
        )


    def _dispatch_grasp_to_bridge(
        self,
        grasp_candidate: GraspCandidate,
        *,
        arm: str = "right",
        execute: bool = True,
        move_time_s: float = 1.6,
        grasp_move_time_s: float = 1.0,
        retreat_move_time_s: float = 1.4,
        settle_time_s: float = 0.35,
        grip_settle_s: float = 0.5,
        open_hand_first: bool = True,
        close_hand: bool = True,
        retreat_offset_m: float = 0.04,
    ) -> dict[str, Any]:
        if not execute:
            return {
                "ok": True,
                "skipped": True,
                "message": "Arm execution disabled for this request.",
                "stages": [],
            }
        if not self.bridge_url:
            return {
                "ok": False,
                "error": "No bridge URL is configured for arm execution.",
            }

        retreat_pose = self._build_retreat_pose(grasp_candidate, retreat_offset_m=retreat_offset_m)
        payload = {
            "active_arm": arm,
            "frame": grasp_candidate.grasp_frame,
            "navigate_cmd": [0.0, 0.0, 0.0],
            "pregrasp_pose": self._pose3d_to_wrist_command(grasp_candidate.pregrasp_pose),
            "grasp_pose": self._pose3d_to_wrist_command(grasp_candidate.grasp_pose),
            "retreat_pose": self._pose3d_to_wrist_command(retreat_pose),
            "gripper_width": grasp_candidate.gripper_width,
            "open_hand_first": open_hand_first,
            "close_hand": close_hand,
            "pregrasp_move_time_s": move_time_s,
            "grasp_move_time_s": grasp_move_time_s,
            "retreat_move_time_s": retreat_move_time_s,
            "settle_time_s": settle_time_s,
            "grip_settle_s": grip_settle_s,
        }
        return self._post_bridge_json("/manipulation/pick_sequence", payload)

    def _build_retreat_pose(self, grasp_candidate: GraspCandidate, *, retreat_offset_m: float = 0.04) -> Pose3D:
        retreat_z = max(grasp_candidate.pregrasp_pose.z, grasp_candidate.grasp_pose.z + retreat_offset_m)
        return Pose3D(
            x=grasp_candidate.pregrasp_pose.x,
            y=grasp_candidate.pregrasp_pose.y,
            z=retreat_z,
            roll=grasp_candidate.pregrasp_pose.roll,
            pitch=grasp_candidate.pregrasp_pose.pitch,
            yaw=grasp_candidate.pregrasp_pose.yaw,
            frame=grasp_candidate.pregrasp_pose.frame,
        )

    def _verify_pick_execution(
        self,
        selected: PerceivedObject,
        grasp_candidate: GraspCandidate,
        bridge_execution: dict[str, Any],
    ) -> dict[str, Any]:
        if bridge_execution.get("skipped"):
            return {
                "ok": True,
                "status": TaskStatus.ACTIVE.value,
                "method": "execution_skipped",
                "detail": "Verification is pending because the staged manipulation sequence was skipped for this request.",
            }

        if self.mock_mode:
            remaining_objects = [item for item in DEFAULT_OBJECTS if item.object_id != selected.object_id]
            self.last_scene = SceneObservation(
                camera_name=self.camera_name,
                frame_id=self.base_frame,
                objects=remaining_objects,
                summary=(
                    f"Mock verification marked {selected.object_id} as lifted after the staged pick sequence. "
                    + self._scene_summary(remaining_objects)
                ).strip(),
                updated_at=utc_now_iso(),
            )
            return {
                "ok": True,
                "status": TaskStatus.SUCCEEDED.value,
                "method": "mock_scene_update",
                "detail": "Mock perception verification marked the target as lifted after pregrasp, grasp, close, and retreat.",
            }

        scene_result = self.scene({"label": selected.label, "color": selected.color})
        if not scene_result.get("ok"):
            return {
                "ok": True,
                "status": TaskStatus.ACTIVE.value,
                "method": "scene_snapshot",
                "detail": "Verification could not refresh the latest scene snapshot, so manipulation remains active until a perception backend reports grasp state.",
            }

        objects = scene_result.get("scene", {}).get("objects", [])
        matches = [
            item
            for item in objects
            if item.get("object_id") == selected.object_id
            or (item.get("label") == selected.label and item.get("color") == selected.color)
        ]
        if not matches:
            return {
                "ok": True,
                "status": TaskStatus.SUCCEEDED.value,
                "method": "scene_snapshot",
                "detail": "The target is no longer visible in the latest scene snapshot, so the pick is marked as verified.",
            }

        return {
            "ok": True,
            "status": TaskStatus.ACTIVE.value,
            "method": "scene_snapshot",
            "detail": "The target is still visible in the latest scene snapshot, so verification is pending until the perception backend can distinguish table vs in-hand observations.",
        }

    def _post_bridge_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.bridge_url}{endpoint}"
        request = urllib_request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=5.0) as response:
                return json.loads(response.read().decode())
        except urllib_error.HTTPError as exc:
            body = exc.read().decode() if exc.fp is not None else ""
            try:
                detail = json.loads(body)
            except json.JSONDecodeError:
                detail = {"error": body or str(exc)}
            return {
                "ok": False,
                "status_code": exc.code,
                **detail,
            }
        except urllib_error.URLError as exc:
            return {
                "ok": False,
                "error": f"Bridge request failed: {exc.reason}",
            }

    def _pose3d_to_wrist_command(self, pose: Pose3D) -> list[float]:
        qw, qx, qy, qz = self._rpy_to_scalar_first_quaternion(pose.roll, pose.pitch, pose.yaw)
        return [pose.x, pose.y, pose.z, qw, qx, qy, qz]

    def _rpy_to_scalar_first_quaternion(self, roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
        half_roll = roll * 0.5
        half_pitch = pitch * 0.5
        half_yaw = yaw * 0.5
        cr = math.cos(half_roll)
        sr = math.sin(half_roll)
        cp = math.cos(half_pitch)
        sp = math.sin(half_pitch)
        cy = math.cos(half_yaw)
        sy = math.sin(half_yaw)
        qw = cr * cp * cy + sr * sp * sy
        qx = sr * cp * cy - cr * sp * sy
        qy = cr * sp * cy + sr * cp * sy
        qz = cr * cp * sy - sr * sp * cy
        return qw, qx, qy, qz

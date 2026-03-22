from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for API responses and persisted state."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_dict(value: Any) -> Any:
    """Recursively convert dataclasses and enums into JSON-serializable objects."""
    if is_dataclass(value):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    return value


class TaskStatus(str, Enum):
    IDLE = "idle"
    READY = "ready"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class Pose2D:
    x: float
    y: float
    yaw: float
    frame: str = "map"


@dataclass
class Pose3D:
    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    frame: str = "map"


@dataclass
class GraspCandidate:
    object_id: str
    object_pose: Pose3D
    grasp_pose: Pose3D
    pregrasp_pose: Pose3D
    grasp_frame: str = "base_link"
    strategy: str = "top_down"
    gripper_width: float = 0.08
    score: float = 0.0
    notes: str = ""


@dataclass
class Landmark:
    name: str
    category: str
    pose: Pose2D
    notes: str = ""


@dataclass
class MapRecord:
    map_id: str
    created_at: str
    source: str
    builder: str
    description: str
    landmarks: list[Landmark] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LocalizationState:
    status: TaskStatus = TaskStatus.IDLE
    map_id: str | None = None
    method: str = "lidar_global_localization"
    confidence: float = 0.0
    pose: Pose2D | None = None
    message: str = "Localization not initialized."
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class NavigationState:
    status: TaskStatus = TaskStatus.IDLE
    map_id: str | None = None
    goal_name: str | None = None
    goal_pose: Pose2D | None = None
    last_result: str = "No navigation command issued."
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class PerceivedObject:
    object_id: str
    label: str
    color: str | None
    confidence: float
    pose: Pose3D
    support_surface: str | None = None


@dataclass
class SceneObservation:
    camera_name: str
    frame_id: str
    objects: list[PerceivedObject] = field(default_factory=list)
    summary: str = ""
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class FaceProfile:
    person_id: str
    display_name: str
    created_at: str
    embedding_source: str = "camera_snapshot"
    notes: str = ""


@dataclass
class FaceMatch:
    person_id: str
    display_name: str
    confidence: float


@dataclass
class ManipulationState:
    status: TaskStatus = TaskStatus.IDLE
    object_id: str | None = None
    action: str | None = None
    object_pose: Pose3D | None = None
    grasp_candidate: GraspCandidate | None = None
    result: str = "No manipulation command issued."
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class TaskStep:
    name: str
    status: TaskStatus
    detail: str


@dataclass
class PickTaskResult:
    status: TaskStatus
    task: str
    object_label: str
    color: str | None
    support_surface: str | None
    map_id: str | None
    steps: list[TaskStep] = field(default_factory=list)
    selected_object: PerceivedObject | None = None
    grasp_candidate: GraspCandidate | None = None
    final_message: str = ""
    updated_at: str = field(default_factory=utc_now_iso)

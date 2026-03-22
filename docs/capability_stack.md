# Capability Stack

This repo now includes a local capability server at `capabilities/server.py` that acts as the control plane for:

- map building and persistence
- localization against a saved map
- autonomous navigation to named landmarks or poses
- camera-based scene understanding and 3D object grounding
- face enrollment and recognition
- manipulation and an end-to-end pick-object task pipeline

## Design intent

The current bridge remains the low-level locomotion interface for teleop and simple voice control. The new capability stack is the higher-level interface that OpenClaw should use for autonomous tasks.

The navigation model is intentionally "map once, then localize and navigate":

1. Build and save a map.
2. Load that map in later sessions.
3. Initialize localization on the saved map.
4. Navigate using persistent map coordinates and named landmarks.

## Server endpoints

### Status

- `GET /status`
- `GET /maps`
- `GET /localization/status`
- `GET /navigation/status`

### Navigation lifecycle

- `POST /maps/build`
- `POST /maps/load`
- `POST /localization/initialize`
- `POST /navigation/goal`
- `POST /navigation/cancel`

### Perception

- `POST /perception/scene`
- `POST /perception/object_pose`
- `POST /perception/grasp_pose`
- `POST /perception/face/enroll`
- `POST /perception/face/recognize`

### Manipulation

- `POST /manipulation/pick`
- `POST /mission/pick_object`

## Example pipeline: "reach for the table and take the green apple"

1. OpenClaw calls `perception_stack` to identify the table and green apple.
2. OpenClaw calls `navigation_stack` to ensure a saved map is loaded and localization is ready.
3. OpenClaw calls `navigation_stack` again to move to the `table` landmark.
4. OpenClaw calls `perception_stack` again to refine the green apple pose at close range.
5. OpenClaw calls `perception_stack` to turn that refined 3D pose into a candidate grasp.
6. OpenClaw calls `manipulation_stack` to execute the pick with the pose-aware grasp candidate.
7. OpenClaw verifies completion from the returned task status.

## Mock versus real backends

The current implementation is an honest scaffold:

- the API surface, state transitions, persistence, task sequencing, and pose-aware grasp planning contract are implemented
- sensor fusion, object detection, SLAM, path planning, IK feasibility checks, and arm control are still represented by mock results inside `capabilities/state.py`

That means this is ready to serve as the orchestration contract for OpenClaw and for future ROS2 adapters, but it is not yet a production autonomy stack.

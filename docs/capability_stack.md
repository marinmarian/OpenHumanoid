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

## Real ZED backend

In real-backend mode, the capability stack now defaults to a live ZED stereo perception backend.

- `scene()` captures `LEFT` images and `XYZRGBA` point clouds from the ZED camera.
- If you provide 2D detections directly, the backend grounds them into 3D using the ZED point cloud.
- If `DETECTOR_BACKEND=http` is configured, the backend sends the current ZED frame to an HTTP detector service and grounds the returned detections into 3D.
- A local detector service is included in `scripts/detector_service.py`; it can run an Ultralytics / YOLO model, an OpenAI vision-language model, or a fixture mode for debugging.
- If you do not provide detections and no detector service is enabled, the backend falls back to heuristic tabletop and color-based segmentation for simple scenes like a green apple on a table.
- Face recognition remains mock-only for now; the real ZED backend does not yet include a face embedding/recognition adapter.
- Camera-to-base extrinsics can be configured with `ZED_TO_BASE_{X,Y,Z,ROLL,PITCH,YAW}`.
- `GET /status` now reports the active `perception_backend` block, including the active detector backend, so you can see whether the live ZED backend actually initialized.

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

`mock_mode` is a flag on the capability server itself.

- `./scripts/start_capability_server.sh` starts the server in mock mode by default.
- `CAPABILITY_REAL_BACKEND=1 PERCEPTION_BACKEND=zed ./scripts/start_capability_server.sh` starts it in real-backend mode, where the default perception backend becomes `zed`.
- `DETECTOR_BACKEND=http DETECTOR_URL=http://127.0.0.1:8790/detect` enables the detector-service path for the live ZED backend; inside that detector service you can choose `DETECTOR_SERVICE_BACKEND=ultralytics`, `openai`, or `fixture`.
- `PERCEPTION_DETECTIONS_PATH=/path/to/detections.json` still lets you inject 2D detections from a fixture file for grounding.
- `GET /status` includes `mock_mode` and `perception_backend`, so you can verify which mode is live and which detector backend is active.

In mock mode:

- localization, navigation, and verification can succeed from the stored mock scene state
- pick verification succeeds by updating the in-memory scene after the staged pick executes

In real-backend mode:

- the server stops fabricating verification success from the mock scene state
- the staged pick still runs through the bridge and WBC path
- if every bridge stage succeeds, verification currently falls back to `bridge_execution_trust` and marks the pick as succeeded
- the long-term fix is still real perception confirmation that the object disappeared from the table or is now in hand

The current implementation is still an honest scaffold:

- the API surface, state transitions, persistence, task sequencing, and pose-aware grasp planning contract are implemented
- sensor fusion, object detection, SLAM, path planning, IK feasibility checks, and perception-based grasp verification are still represented by mock results inside `capabilities/state.py`

That means this is ready to serve as the orchestration contract for OpenClaw and for future ROS2 adapters, but it is not yet a production autonomy stack.

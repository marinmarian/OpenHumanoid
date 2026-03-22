# OpenHumanoid — AI Context

> This file provides project context for AI coding agents (Cursor, Copilot, Aider, etc.).

## Project Purpose

Voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes: a fast path (OpenAI Realtime API, ~500ms, locomotion only) and a full path (OpenClaw Gateway, ~2-5s, full orchestration with TTS and multi-channel input). Both share a single HTTP bridge that translates velocity commands into keyboard events for the WBC policy.

The fast path supports: activate ("get ready"), continuous ("walk forward"), timed ("walk forward for 3 seconds"), distance-based ("walk forward 2 meters"), angle-based ("turn left 90 degrees"), sequential chains ("walk forward 1 meter then turn right"), and release/hold ("relax"). All timed movements are interruptible.

The full path (OpenClaw) supports voice (Talk Mode), text (WebChat), and WhatsApp. It uses the `exec` tool to send `curl` commands either to the bridge via the `robot_control` skill or to the local capability stack via the `navigation_stack`, `perception_stack`, and `manipulation_stack` skills.

## Architecture

```
Fast mode:  Mic → Realtime API → function call → HTTP → run_with_bridge.py → /keyboard_input → WBC → G1
Full mode:  Voice/Text/WhatsApp → OpenClaw → exec curl → bridge and capability stack APIs → WBC / autonomy services → G1
```

The bridge and WBC control loop run in the **same Python process** (`bridge/run_with_bridge.py`) to avoid CycloneDDS inter-process networking issues in Docker. The bridge publishes keyboard key strings to `/keyboard_input`, and the control loop's `ROSKeyboardDispatcher` receives them on the same ROS2 node.

Mode is selected via `VOICE_MODE` env variable (`realtime` or `openclaw`).

## Key Files

| File | Description |
|------|-------------|
| `bridge/run_with_bridge.py` | **Primary launcher.** Starts HTTP bridge + WBC control loop in one process. Runs inside Docker. |
| `bridge/mock_bridge.py` | Same HTTP API, prints to console. For host-side dev without Docker. |
| `realtime/client.py` | WebSocket client for OpenAI Realtime API. Handles audio, function calls, interruptible timed movements, and sequential command chaining. |
| `realtime/tools.py` | Function tool definitions (move_robot, stop_robot, turn_robot, activate_robot, release_robot) with speed/direction maps and calibrated speeds. |
| `realtime/audio.py` | Microphone capture + speaker playback via sounddevice. PCM16 24kHz. |
| `realtime/main.py` | Fast mode entry point. |
| `openclaw/openclaw.json` | OpenClaw Gateway config: auth, model, exec tool, TTS-1, WhatsApp channel. |
| `openclaw/workspace/AGENTS.md` | Agent persona and voice-to-action mappings, including the autonomy workflow. |
| `openclaw/workspace/skills/robot-control/SKILL.md` | Teaches OpenClaw to use curl for bridge HTTP API. |
| `openclaw/workspace/skills/navigation-stack/SKILL.md` | Teaches OpenClaw to build/load maps, localize, and navigate. |
| `openclaw/workspace/skills/perception-stack/SKILL.md` | Teaches OpenClaw to query objects, scenes, and faces. |
| `openclaw/workspace/skills/manipulation-stack/SKILL.md` | Teaches OpenClaw to run pick tasks. |
| `capabilities/server.py` | Local HTTP capability server for saved-map navigation, perception, and manipulation orchestration. |
| `capabilities/state.py` | Persistent state machine and task pipeline for the capability stack. |
| `openclaw/setup.sh` | One-time OpenClaw setup (symlinks config + workspace to `~/.openclaw/`). |
| `scripts/start_bridge.sh` | Wrapper to launch `run_with_bridge.py` inside Docker. |
| `scripts/start_capability_server.sh` | Starts the capability stack server. |

## Important Constants

| Constant | Value | Source |
|----------|-------|--------|
| Velocity step per keypress | 0.2 m/s | `G1GearWbcPolicy.handle_keyboard_button()` |
| Keyboard input topic | `/keyboard_input` | `decoupled_wbc/control/main/constants.py` |
| Bridge HTTP port | 8765 | Configurable via `--port` and `BRIDGE_URL` |
| OpenClaw Gateway port | 18789 | `openclaw.json` / systemd service |
| Capability stack port | 8787 | `capabilities/server.py` / `CAPABILITY_SERVER_PORT` |
| Speed: slow | 0.2 m/s commanded, 0.18 m/s calibrated | `realtime/tools.py` |
| Speed: medium | 0.4 m/s commanded, 0.35 m/s calibrated | `realtime/tools.py` |
| Speed: fast | 0.6 m/s commanded, 0.50 m/s calibrated | `realtime/tools.py` |
| Yaw: slow | 0.20 rad/s calibrated | `realtime/tools.py` |
| Yaw: medium | 0.40 rad/s calibrated | `realtime/tools.py` |
| Yaw: fast | 0.55 rad/s calibrated | `realtime/tools.py` |

## External Dependencies

- **Decoupled WBC**: Python-based whole-body controller from NVIDIA GR00T-WholeBodyControl repo. Runs in Docker (`decoupled_wbc-bash-root`) with ROS2. Uses `ROSKeyboardDispatcher` when started with `--keyboard-dispatcher-type ros` (forced by `run_with_bridge.py`).
- **GEAR-SONIC** (alternative): C++/TensorRT kinematic planner in the same repo (`gear_sonic_deploy/`). 27 motion modes (walk, run, squat, crawl, box, dance, etc.). Accepts commands via ZMQ. Cannot run simultaneously with Decoupled WBC.
- **OpenAI Realtime API**: `wss://api.openai.com/v1/realtime?model=gpt-realtime`. WebSocket, PCM16 audio, native function calling, server-side VAD.
- **OpenClaw Gateway**: Node.js AI agent gateway. `exec` tool runs shell commands on the gateway host. Skills teach the LLM what commands to run. TTS-1 for voice output. Supports WebChat, Talk Mode, WhatsApp.

## Design Decisions

- **In-process bridge**: `run_with_bridge.py` starts the HTTP server and control loop in one Python process. CycloneDDS in the Docker container can't do inter-process multicast on loopback, so separate processes can't communicate via ROS2 topics.
- **Keyboard-based control**: The bridge translates HTTP velocities into keyboard key sequences (`z` to reset, then directional presses). This matches `G1GearWbcPolicy.handle_keyboard_button()` which increments velocity by ±0.2 per keypress. A better approach exists (publishing `navigate_cmd` to `CONTROL_GOAL_TOPIC` for direct velocity control with interpolation) but the keyboard path was simpler to wire up.
- **HTTP everywhere**: Fast mode talks HTTP to the bridge; full mode talks HTTP to both the bridge and the capability stack. Simple, debuggable with curl, works across Docker boundary.
- **Map once, then localize**: The capability stack persists named maps and blocks autonomous navigation until localization is initialized against a saved map.
- **Two independent modes**: No delegation between Realtime API and OpenClaw. Switch via env variable.
- **Interruptible sleep**: Timed movements use `asyncio.wait_for` on an `asyncio.Event`. User speech sets the event and the robot stops immediately.
- **Calibrated speeds**: `ACTUAL_SPEED` and `ACTUAL_YAW_SPEED` in `realtime/tools.py` are empirically tuned values used to compute durations for distance/angle commands (different from the commanded velocity sent to the bridge).

## Current Status

- [x] Bridge server (in-process + mock)
- [x] Realtime API voice client (fast mode)
- [x] Activate / release / stop via voice
- [x] Sequential, distance-based, and angle-based voice commands
- [x] Interruptible timed movements
- [x] MuJoCo simulation verified working
- [x] OpenClaw Gateway (full mode) with WebChat, Talk Mode, WhatsApp
- [x] OpenClaw `robot_control` skill with correct bridge API
- [ ] End-to-end testing with real robot
- [ ] GEAR-SONIC integration (ZMQ bridge backend)
- [x] Prototype capability stack API for saved-map navigation, perception, face recognition, and manipulation orchestration
- [ ] Real Task 2 backend: SLAM/LiDAR navigation adapters
- [ ] Real Task 3 backend: perception/manipulation adapters and arm control

## Conventions

- Python 3.10+, managed with `uv` (`uv sync` to install, `uv run` to execute)
- Bridge server has zero external dependencies (stdlib + rclpy)
- Host-side dependencies declared in `pyproject.toml`: websockets, sounddevice, numpy, requests, python-dotenv
- API keys via environment variables, never hardcoded
- OpenClaw config lives in `openclaw/`, symlinked to `~/.openclaw/` by `setup.sh` (uses `ln -sfn` to avoid recursive symlinks)
- New robot capabilities = new OpenClaw skill in `openclaw/workspace/skills/` plus, when needed, a capability-stack endpoint in `capabilities/server.py`

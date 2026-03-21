# OpenHumanoid — AI Context

> This file provides project context for AI coding agents (Cursor, Copilot, Aider, etc.).

## Project Purpose

Voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes: a fast path (OpenAI Realtime API, ~500ms, locomotion only) and a full path (OpenClaw Gateway, ~2-5s, full orchestration with TTS). Both share a single HTTP bridge that translates velocity commands into keyboard events for the WBC policy.

The fast path supports: activate/deactivate ("get ready", "go to sleep"), continuous commands ("walk forward"), timed commands ("walk forward for 3 seconds"), distance-based commands ("walk forward 2 meters"), and sequential chains ("walk forward 1 meter then turn right"). All timed movements are interruptible.

## Architecture

```
Fast mode:  Mic → Realtime API → function call → HTTP → run_with_bridge.py → /keyboard_input → WBC → G1
Full mode:  Voice/Text → OpenClaw → exec curl → HTTP → run_with_bridge.py → /keyboard_input → WBC → G1
```

The bridge and WBC control loop run in the **same Python process** (`bridge/run_with_bridge.py`) to avoid CycloneDDS inter-process networking issues in Docker. The bridge publishes keyboard key strings to `/keyboard_input`, and the control loop's `ROSKeyboardDispatcher` receives them on the same ROS2 node.

Mode is selected via `VOICE_MODE` env variable (`realtime` or `openclaw`).

## Key Files

| File | Description |
|------|-------------|
| `bridge/run_with_bridge.py` | **Primary launcher.** Starts HTTP bridge + WBC control loop in one process. Runs inside Docker. |
| `bridge/bridge_server.py` | Standalone bridge (for reference). Not used in production due to DDS issues. |
| `bridge/mock_bridge.py` | Same HTTP API, prints to console. For host-side dev without Docker. |
| `realtime/client.py` | WebSocket client for OpenAI Realtime API. Handles audio, function calls, interruptible timed movements, and sequential command chaining. |
| `realtime/tools.py` | Function tool definitions (move_robot, stop_robot, turn_robot, activate_robot, deactivate_robot) with speed/direction maps. |
| `realtime/audio.py` | Microphone capture + speaker playback via sounddevice. PCM16 24kHz. |
| `realtime/main.py` | Fast mode entry point. |
| `openclaw/openclaw.json` | OpenClaw Gateway config. WebChat, exec, TTS-1. |
| `openclaw/workspace/skills/robot-control/SKILL.md` | Teaches OpenClaw to use curl for bridge HTTP API. |

## Important Constants

| Constant | Value | Source |
|----------|-------|--------|
| Velocity step per keypress | 0.2 m/s | `G1GearWbcPolicy.handle_keyboard_button()` |
| Max linear velocity | 0.5 m/s | Decoupled WBC `KeyboardNavigationPolicy` |
| Max angular velocity | 0.5 rad/s | Decoupled WBC `KeyboardNavigationPolicy` |
| Keyboard input topic | `/keyboard_input` | `decoupled_wbc/control/main/constants.py` |
| Bridge HTTP port | 8765 | Configurable via `--port` and `BRIDGE_URL` |
| Speed: slow | 0.2 m/s (1 keypress) | `realtime/tools.py` SPEED_MAP |
| Speed: medium | 0.4 m/s (2 keypresses) | `realtime/tools.py` SPEED_MAP |
| Speed: fast | 0.6 m/s (3 keypresses) | `realtime/tools.py` SPEED_MAP |

## External Dependencies

- **Decoupled WBC**: Python-based whole-body controller from NVIDIA GR00T-WholeBodyControl repo. Runs in Docker with ROS2. Uses `ROSKeyboardDispatcher` (subscribes to `/keyboard_input`) when started with `--keyboard-dispatcher-type ros`.
- **OpenAI Realtime API**: `wss://api.openai.com/v1/realtime?model=gpt-realtime`. WebSocket, PCM16 audio, native function calling, server-side VAD.
- **OpenClaw Gateway**: Node.js AI agent gateway. `exec` tool runs shell commands. Skills teach the LLM what commands to run. TTS-1 for voice output.

## Design Decisions

- **In-process bridge**: `run_with_bridge.py` starts the HTTP server and control loop in one Python process. CycloneDDS in the Docker container can't do inter-process multicast on loopback, so separate processes can't communicate via ROS2 topics. Same-process avoids this entirely.
- **Keyboard-based control**: The bridge translates HTTP velocities into keyboard key sequences (`z` to reset, then `w`/`s`/`a`/`d`/`q`/`e` presses). This matches how the WBC policy actually works -- `G1GearWbcPolicy.handle_keyboard_button()` increments velocity by ±0.2 per keypress.
- **HTTP everywhere**: Both modes talk HTTP to the bridge. Simple, debuggable with curl.
- **Two independent modes**: No delegation between Realtime API and OpenClaw. Switch via env variable.
- **Mock bridge**: Develop voice pipeline without Docker or robot.
- **Interruptible sleep**: Timed movements use `asyncio.wait_for` on an `asyncio.Event`. User speech sets the event and the robot stops immediately.

## Current Status

- [x] Bridge server (in-process + mock)
- [x] Realtime API voice client (fast mode)
- [x] Activate/deactivate robot via voice
- [x] Sequential and distance-based voice commands
- [x] Interruptible timed movements
- [x] MuJoCo simulation verified working
- [x] OpenClaw config + skills (full mode)
- [ ] End-to-end testing with real robot
- [ ] Task 2: VLA pipeline
- [ ] Task 3: DiMOS navigation
- [ ] Task 4: DiMOS + VLA orchestration

## Conventions

- Python 3.10+, managed with `uv` (`uv sync` to install, `uv run` to execute)
- No type: ignore unless unavoidable
- Bridge server has zero external dependencies (stdlib + rclpy)
- Host-side dependencies declared in `pyproject.toml`: websockets, sounddevice, numpy, requests, python-dotenv
- API keys via environment variables, never hardcoded
- New robot capabilities = new OpenClaw skill in `openclaw/workspace/skills/`

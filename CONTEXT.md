# OpenHumanoid — AI Context

> This file provides project context for AI coding agents (Cursor, Copilot, Aider, etc.).

## Project Purpose

Voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes: a fast path (OpenAI Realtime API, ~500ms, locomotion only) and a full path (OpenClaw Gateway, ~2-5s, full orchestration with TTS). Both share a single HTTP bridge server inside the WBC Docker container.

The fast path supports continuous commands ("walk forward"), timed commands ("walk forward for 3 seconds"), distance-based commands ("walk forward 2 meters"), and sequential command chains ("walk forward 1 meter then turn right"). All timed movements are interruptible -- saying "stop" mid-movement halts the robot immediately.

## Architecture

```
Fast mode:  Mic → Realtime API → function call → HTTP → bridge_server.py (Docker) → ROS2 → WBC → G1
Full mode:  Voice/Text → OpenClaw → exec curl → HTTP → bridge_server.py (Docker) → ROS2 → WBC → G1
```

Mode is selected via `VOICE_MODE` env variable (`realtime` or `openclaw`).

## Key Files

| File | Description |
|------|-------------|
| `bridge/bridge_server.py` | HTTP→ROS2 bridge. Runs inside WBC Docker. stdlib + rclpy only. |
| `bridge/mock_bridge.py` | Same HTTP API, prints to console. For host-side dev without Docker. |
| `realtime/client.py` | WebSocket client for OpenAI Realtime API. Handles audio, function calls, interruptible timed movements, and sequential command chaining. |
| `realtime/tools.py` | Function tool definitions (move_robot, stop_robot, turn_robot) with duration_seconds and distance_meters support + speed/direction maps. |
| `realtime/audio.py` | Microphone capture + speaker playback via sounddevice. PCM16 24kHz. Stderr-redirect suppresses ALSA warnings. |
| `realtime/main.py` | Fast mode entry point. |
| `openclaw/openclaw.json` | OpenClaw Gateway config. WebChat, exec, TTS-1. |
| `openclaw/workspace/AGENTS.md` | System prompt for OpenClaw: robot orchestrator persona. |
| `openclaw/workspace/skills/robot-control/SKILL.md` | Teaches OpenClaw to use curl for bridge HTTP API. |
| `openclaw/setup.sh` | Installs OpenClaw, symlinks config + workspace. |

## Important Constants

| Constant | Value | Source |
|----------|-------|--------|
| Max linear velocity | 0.5 m/s | Decoupled WBC `KeyboardNavigationPolicy` |
| Max angular velocity | 0.5 rad/s | Decoupled WBC `KeyboardNavigationPolicy` |
| Keyboard input topic | `/keyboard_input` | `decoupled_wbc/control/main/constants.py` |
| Nav command topic | `/nav_cmd` | `decoupled_wbc/control/main/constants.py` |
| Bridge HTTP port | 8765 | Configurable via BRIDGE_URL |
| OpenClaw WebChat port | 18789 | OpenClaw default |
| Speed: slow | 0.15 m/s | Our mapping in `realtime/tools.py` |
| Speed: medium | 0.30 m/s | Our mapping in `realtime/tools.py` |
| Speed: fast | 0.45 m/s | Our mapping in `realtime/tools.py` |

## External Dependencies

- **Decoupled WBC**: Python-based whole-body controller from NVIDIA GR00T-WholeBodyControl repo. Runs in Docker with ROS2. Subscribes to `/keyboard_input` (String) and `/nav_cmd` (Float32MultiArray).
- **OpenAI Realtime API**: `wss://api.openai.com/v1/realtime?model=gpt-realtime`. WebSocket, PCM16 audio, native function calling, server-side VAD.
- **OpenClaw Gateway**: Node.js AI agent gateway. `exec` tool runs shell commands. Skills teach the LLM what commands to run. TTS-1 for voice output.

## Design Decisions

- **Single file bridge**: One ~120-line Python script in Docker using stdlib + rclpy. No extra dependencies, no ZMQ, no FastAPI. Minimal failure surface.
- **HTTP everywhere**: Both modes talk HTTP to the bridge. Simple, debuggable with curl.
- **Two independent modes**: No delegation between Realtime API and OpenClaw. Switch via env variable. Avoids routing complexity.
- **OpenClaw exec + curl**: No custom plugin needed. The skill teaches the LLM to use `exec` with `curl`, the standard OpenClaw pattern.
- **Mock bridge**: Develop voice pipeline without Docker or robot.
- **Background task dispatch**: `_handle_response_done` runs via `asyncio.create_task` so the WebSocket event loop stays responsive during timed movements. This allows `speech_started` events to interrupt a sleep.
- **Interruptible sleep**: Timed movements use `asyncio.wait_for` on an `asyncio.Event` instead of plain `asyncio.sleep`. User speech sets the event and the robot stops immediately.
- **VAD-aware response creation**: `response.create` is only sent after function call processing (model needs a nudge to respond to tool output). Voice-only replies don't trigger it, and the `_response_active` flag prevents collision with VAD-triggered responses.

## Current Status

- [x] Bridge server (real + mock)
- [x] Realtime API voice client (fast mode)
- [x] Sequential and distance-based voice commands
- [x] Interruptible timed movements
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

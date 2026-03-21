# OpenHumanoid Architecture

## Overview

OpenHumanoid provides voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes share a single HTTP bridge to the robot's Whole-Body Controller (WBC).

## Modes

### Fast Mode (`VOICE_MODE=realtime`)

Low-latency voice control (~500ms) using the OpenAI Realtime API.

```
Microphone → OpenAI Realtime API (gpt-realtime, WebSocket)
    → function call (move_robot / stop_robot / turn_robot)
    → HTTP POST to bridge_server.py in Docker
    → rclpy publish to ROS2 topics
    → Decoupled WBC → G1 Robot
    
Realtime API → voice reply → Speaker
```

Locomotion only. If the user asks for complex tasks, it tells them to switch to full mode.

**Voice command types:**

| Type | Example | Behavior |
|------|---------|----------|
| Continuous | "walk forward" | Moves until user says "stop" |
| Timed | "walk forward for 3 seconds" | Moves, auto-stops after duration |
| Distance-based | "walk forward 2 meters" | Duration computed from distance/speed |
| Sequential | "walk forward 1 meter then turn right" | Chained function calls, executed in order |

All timed/distance movements are **interruptible** -- saying "stop" or any new command mid-movement halts the robot immediately. This is achieved by dispatching `_handle_response_done` as a background `asyncio.Task` (so the event loop stays responsive to new WebSocket events) and using `asyncio.wait_for` on an `asyncio.Event` that fires when the VAD detects new speech.

### Full Mode (`VOICE_MODE=openclaw`)

Full orchestration (~2-5s latency) using OpenClaw Gateway.

```
Voice/Text → OpenClaw Gateway (LLM + exec tool + skills)
    → exec: curl -X POST http://localhost:8765/move ...
    → bridge_server.py in Docker
    → rclpy publish to ROS2 topics
    → Decoupled WBC → G1 Robot

OpenClaw → TTS-1 → voice reply (auto-TTS)
```

Supports locomotion now. Future DiMOS navigation and GR00T VLA manipulation plug in as additional OpenClaw skills.

## Bridge Server

Single Python file (`bridge/bridge_server.py`) running inside the WBC Docker container. Uses only Python stdlib + rclpy (both already in the Docker image).

### HTTP API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/move` | `{"vx": 0.3, "vy": 0.0, "vyaw": 0.0}` | Set velocity (clamped to safe range) |
| POST | `/stop` | (none) | Stop all movement |
| POST | `/key` | `{"key": "w"}` | Emulate keyboard press |
| GET | `/status` | — | Current velocity and limits |

### Safety

All velocities are clamped inline:
- Linear (vx, vy): -0.5 to 0.5 m/s
- Angular (vyaw): -0.5 to 0.5 rad/s

These match the `KeyboardNavigationPolicy` limits in the Decoupled WBC.

### ROS2 Topics

| Topic | Type | Used by |
|-------|------|---------|
| `/keyboard_input` | `std_msgs/String` | Key emulation (w/a/s/d/q/e/z) |
| `/nav_cmd` | `std_msgs/Float32MultiArray` | Direct velocity `[vx, vy, vyaw]` |

## Deployment

Everything runs on one laptop:

| Location | Component | Port |
|----------|-----------|------|
| Docker container | bridge_server.py + Decoupled WBC | 8765 (exposed) |
| Host | Realtime client (fast mode) | — |
| Host | OpenClaw Gateway (full mode) | 18789 |
| Cloud | OpenAI Realtime API | 443 |
| Cloud | OpenAI TTS-1 (for OpenClaw) | 443 |
| Network | G1 Robot | Unitree SDK |

The WBC Docker container uses `--network host`, so port 8765 is automatically accessible from the host.

## Mock Mode

For development without Docker or the robot, run `uv run python bridge/mock_bridge.py` on the host. Same HTTP interface, prints commands to console.

## Future Tasks

| Task | Integration Point | What to Add |
|------|-------------------|-------------|
| Task 2 (VLA) | New OpenClaw skill + bridge `/manipulation` endpoint | `vla-control` skill, extend bridge_server.py |
| Task 3 (DiMOS) | New OpenClaw skill, uses existing `/move` endpoint | `dimos-navigation` skill |
| Task 4 (DiMOS+VLA) | OpenClaw orchestrates both skills | No new code, just skill composition |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_MODE` | `realtime` | `realtime` or `openclaw` |
| `OPENAI_API_KEY` | (required) | Used by both modes |
| `BRIDGE_URL` | `http://localhost:8765` | Bridge server address |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Speed Reference

| Label | Velocity (m/s or rad/s) | Distance→Duration Example |
|-------|------------------------|---------------------------|
| slow | 0.15 | 2m → 13.3s |
| medium | 0.30 | 2m → 6.7s |
| fast | 0.45 | 2m → 4.4s |
| max (clamp) | 0.50 | — |

### Realtime API Event Handling

Key design points for the WebSocket client (`realtime/client.py`):

- **VAD-aware `response.create`**: Only sent after function call processing (model needs to respond to tool output). For voice-only replies, the next response is triggered naturally by VAD detecting new speech. A `_response_active` flag prevents sending `response.create` when the API already has an in-progress response.
- **Background task dispatch**: `response.done` handlers run via `asyncio.create_task` so the event loop continues processing WebSocket messages during timed waits. Without this, `speech_started` events would be buffered and the interrupt mechanism would not work.
- **Interruptible sleep**: `_interruptible_sleep` uses `asyncio.wait_for` on an `asyncio.Event`. When `speech_started` fires, the event is set, the sleep terminates, a `/stop` is sent to the bridge, and the remaining command sequence is aborted.

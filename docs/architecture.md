# OpenHumanoid Architecture

## Overview

OpenHumanoid provides voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes share a single HTTP bridge that translates velocity commands into keyboard events for the WBC's `G1GearWbcPolicy`.

## Modes

### Fast Mode (`VOICE_MODE=realtime`)

Low-latency voice control (~500ms) using the OpenAI Realtime API.

```
Microphone → OpenAI Realtime API (gpt-realtime, WebSocket)
    → function call (move_robot / stop_robot / turn_robot / activate_robot / deactivate_robot)
    → HTTP POST to bridge (in-process with control loop)
    → publish keyboard keys to /keyboard_input ROS2 topic
    → G1GearWbcPolicy.handle_keyboard_button() → WBC → G1 Robot
    
Realtime API → voice reply → Speaker
```

Locomotion only. If the user asks for complex tasks, it tells them to switch to full mode.

**Voice command types:**

| Type | Example | Behavior |
|------|---------|----------|
| Activate | "get ready" / "stand up" | Activates walking policy (key `]`) |
| Continuous | "walk forward" | Moves until user says "stop" |
| Timed | "walk forward for 3 seconds" | Moves, auto-stops after duration |
| Distance-based | "walk forward 2 meters" | Duration computed from distance/speed |
| Sequential | "walk forward 1 meter then turn right" | Chained function calls, executed in order |
| Deactivate | "go to sleep" / "deactivate" | Deactivates policy (key `o`) |

All timed/distance movements are **interruptible** -- saying "stop" or any new command mid-movement halts the robot immediately.

### Full Mode (`VOICE_MODE=openclaw`)

Full orchestration (~2-5s latency) using OpenClaw Gateway.

```
Voice/Text → OpenClaw Gateway (LLM + exec tool + skills)
    → exec: curl -X POST http://localhost:8765/move ...
    → bridge HTTP server (in-process)
    → publish keyboard keys → WBC → G1 Robot

OpenClaw → TTS-1 → voice reply (auto-TTS)
```

Supports locomotion now. Future DiMOS navigation and GR00T VLA manipulation plug in as additional OpenClaw skills.

## Bridge Server

The bridge runs **in the same process** as the WBC control loop via `bridge/run_with_bridge.py`. This avoids CycloneDDS inter-process networking issues in Docker (the container's loopback interface doesn't support multicast).

The bridge translates HTTP velocity commands into keyboard key sequences published on the `/keyboard_input` ROS2 topic. The WBC's `G1GearWbcPolicy.handle_keyboard_button()` processes these keys (each press changes velocity by ±0.2 m/s).

### HTTP API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/move` | `{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}` | Translate to key sequence: `z` (reset) + directional presses |
| POST | `/stop` | (none) | Publish `z` key (zero all velocities) |
| POST | `/activate` | (none) | Publish `]` key (activate walking policy) |
| POST | `/deactivate` | (none) | Publish `o` key (deactivate policy) |
| POST | `/key` | `{"key": "w"}` | Publish arbitrary keyboard key |
| GET | `/status` | — | Current velocity and step size |

### Velocity → Key Translation

The `/move` endpoint converts absolute velocities to keyboard sequences:

1. Always starts with `z` (reset all to zero)
2. Then repeats directional keys: `w`/`s` for vx, `a`/`d` for vy, `q`/`e` for vyaw
3. Number of presses = `round(abs(velocity) / 0.2)`

Example: `{"vx": 0.4}` → keys `['z', 'w', 'w']` → vx = 0.0 → 0.2 → 0.4

## Deployment

Everything runs on one laptop:

| Location | Component | Port |
|----------|-----------|------|
| Docker container | `run_with_bridge.py` (bridge + WBC control loop, single process) | 8765 (exposed) |
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
| Task 2 (VLA) | New OpenClaw skill + bridge endpoint | `vla-control` skill, extend bridge |
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

| Label | Velocity (m/s) | Key presses | Distance→Duration Example |
|-------|---------------|-------------|---------------------------|
| slow | 0.2 | 1 press | 2m → 10.0s |
| medium | 0.4 | 2 presses | 2m → 5.0s |
| fast | 0.6 | 3 presses | 2m → 3.3s |

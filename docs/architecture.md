# OpenHumanoid Architecture

## Overview

OpenHumanoid provides voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes share a single HTTP bridge that sets velocities directly on the WBC's `G1GearWbcPolicy.cmd` via a monkey-patched policy reference.

## System Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ HOST MACHINE                                                         │
│                                                                      │
│  ┌─────────────────────┐     ┌──────────────────────────────┐       │
│  │ Fast Mode           │     │ Full Mode                    │       │
│  │ (realtime/)         │     │ (openclaw/)                  │       │
│  │                     │     │                              │       │
│  │ Mic → Realtime API  │     │ Voice/Text/WhatsApp          │       │
│  │ → function calls    │     │ → OpenClaw Gateway (LLM)     │       │
│  │ → HTTP POST         │     │ → exec: curl → HTTP POST     │       │
│  └─────────┬───────────┘     └──────────────┬───────────────┘       │
│            │                                │                        │
│            └───────────┬────────────────────┘                        │
│                        ▼                                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ DOCKER CONTAINER (decoupled_wbc-bash-root, --network host)  │    │
│  │                                                             │    │
│  │  run_with_bridge.py (single process)                        │    │
│  │  ┌──────────────────┐    ┌────────────────────────────┐    │    │
│  │  │ HTTP Bridge      │    │ WBC Control Loop           │    │    │
│  │  │ :8765            │───▶│ G1GearWbcPolicy            │    │    │
│  │  │ /move → cmd      │    │   (direct policy.cmd set)  │    │    │
│  │  │ /activate /key   │    │ → MuJoCo sim / Real robot  │    │    │
│  │  └──────────────────┘    └────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

## Modes

### Fast Mode (`VOICE_MODE=realtime`)

Low-latency voice control (~500ms) using the OpenAI Realtime API with native function calling.

```
Microphone → OpenAI Realtime API (WebSocket, gpt-realtime)
    → function call (move_robot / stop_robot / turn_robot / activate_robot / release_robot)
    → HTTP POST to bridge
    → /move, /stop: direct policy.cmd assignment (no quantization)
    → /activate, /key: keyboard event via /keyboard_input ROS2 topic
    → WBC → Robot
    
Realtime API → voice reply → Speaker
```

**Voice command types:**

| Type | Example | Behavior |
|------|---------|----------|
| Activate | "get ready" / "stand up" | Activates walking policy (key `]`) |
| Continuous | "walk forward" | Moves until user says "stop" |
| Timed | "walk forward for 3 seconds" | Moves, auto-stops after duration |
| Distance | "walk forward 2 meters" | Duration computed from calibrated speed |
| Angle | "turn left 90 degrees" | Duration computed from calibrated yaw speed |
| Sequential | "walk 1 meter then turn right" | Chained function calls, executed in order |
| Release | "release" / "relax" | Toggles hold/limp (key `9`) |

All timed/distance movements are **interruptible** -- saying "stop" or any new command halts the robot immediately.

### Full Mode (`VOICE_MODE=openclaw`)

Full orchestration (~2-5s latency) using the OpenClaw Gateway. Supports multiple input channels.

```
Voice/Text/WhatsApp → OpenClaw Gateway (LLM + exec tool + skills)
    → exec: curl -X POST http://localhost:8765/move ...
    → bridge HTTP server → direct policy.cmd → WBC → Robot

OpenClaw → TTS-1 → voice reply (auto-TTS)
```

**Input channels:**
- **WebChat** — browser UI at http://127.0.0.1:18789
- **Talk Mode** — voice input/output via the WebChat microphone
- **WhatsApp** — send commands from your phone (requires `openclaw channels login --channel whatsapp`)

The OpenClaw agent uses the `robot_control` skill for direct locomotion.

## Bridge Server

The bridge runs **in the same process** as the WBC control loop via `bridge/run_with_bridge.py`. This avoids CycloneDDS inter-process networking issues in Docker.

### Why in-process?

The Docker container's loopback interface doesn't support multicast, so CycloneDDS (ROS2's default middleware) cannot route messages between separate processes. Running bridge + control loop in one process means the ROS2 publisher and subscriber share the same node -- no DDS networking needed.

### Direct Velocity Control

The `/move` and `/stop` endpoints write directly to `G1GearWbcPolicy.lower_body_policy.cmd`, a 3-element array `[vx, vy, vyaw]` that feeds the locomotion neural network. Any float value is accepted — there is no quantization.

The bridge captures the policy object at startup by monkey-patching `get_wbc_policy()` in the WBC policy factory module. This avoids modifying any GR00T-WholeBodyControl code.

Other endpoints (`/activate`, `/deactivate`, `/key`) still publish keyboard events via the `/keyboard_input` ROS2 topic for actions that don't map to velocity (policy activation, release/hold toggle, base height, gait frequency, torso posture).

### HTTP API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/move` | `{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}` | Set velocity directly on policy.cmd |
| POST | `/stop` | — | Zero all velocities (direct) |
| POST | `/activate` | — | Activate walking policy (key `]`) |
| POST | `/deactivate` | — | Deactivate policy (key `o`) |
| POST | `/key` | `{"key": "9"}` | Publish arbitrary key |
| GET | `/status` | — | Current velocity, policy state |

### Available Keys (via `/key` endpoint)

| Key | Action |
|-----|--------|
| `]` | Activate policy |
| `o` | Deactivate policy |
| `9` | Toggle release/hold |
| `1`/`2` | Raise/lower base height ±0.1 |
| `n`/`m` | Decrease/increase gait frequency ±0.1 |
| `3`-`8` | Torso roll/pitch/yaw ±10° |

## Deployment

| Location | Component | Port |
|----------|-----------|------|
| Docker container | `run_with_bridge.py` (bridge + WBC, single process) | 8765 |
| Host | Realtime API client (fast mode) | — |
| Host | OpenClaw Gateway (full mode) | 18789 |
| Cloud | OpenAI Realtime API / TTS-1 | 443 |
| Network | G1 Robot | Unitree SDK (192.168.123.x) |

## Speed Reference

| Label | Commanded (m/s) | Calibrated linear (m/s) | Calibrated yaw (rad/s) |
|-------|----------------|------------------------|----------------------|
| slow | 0.2 | 0.18 | 0.20 |
| medium | 0.4 | 0.35 | 0.40 |
| fast | 0.6 | 0.50 | 0.55 |

Calibrated values are empirically measured ground speeds used for distance-based ("walk 2 meters") and angle-based ("turn 90 degrees") duration calculations. The commanded velocity is set directly on `policy.cmd` — any float value is valid, not just these presets.

## Planned Features

See [README_future.md](README_future.md) for navigation, perception, manipulation, VLA, GEAR-SONIC, and the capability stack roadmap.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_MODE` | `realtime` | `realtime` or `openclaw` |
| `OPENAI_API_KEY` | (required) | Used by both modes |
| `BRIDGE_URL` | `http://localhost:8765` | Bridge server address |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

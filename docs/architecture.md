# OpenHumanoid Architecture

## Overview

OpenHumanoid provides voice-controlled locomotion for a Unitree G1 humanoid robot. Two switchable modes share a single HTTP bridge that translates velocity commands into keyboard events for the WBC's `G1GearWbcPolicy`.

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
│  │  │ :8765            │───▶│ ROSKeyboardDispatcher      │    │    │
│  │  │ /move /stop      │    │ → G1GearWbcPolicy          │    │    │
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
    → keyboard keys published to /keyboard_input ROS2 topic
    → G1GearWbcPolicy.handle_keyboard_button() → WBC → Robot
    
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
    → bridge HTTP server
    → keyboard keys → WBC → Robot

OpenClaw → TTS-1 → voice reply (auto-TTS)
```

**Input channels:**
- **WebChat** — browser UI at http://127.0.0.1:18789
- **Talk Mode** — voice input/output via the WebChat microphone
- **WhatsApp** — send commands from your phone (requires `openclaw channels login --channel whatsapp`)

The OpenClaw agent uses the `robot_control` skill which teaches it to send `curl` commands to the bridge. Future skills (SLAM/LiDAR navigation, VLA manipulation) plug in the same way.

## Bridge Server

The bridge runs **in the same process** as the WBC control loop via `bridge/run_with_bridge.py`. This avoids CycloneDDS inter-process networking issues in Docker.

### Why in-process?

The Docker container's loopback interface doesn't support multicast, so CycloneDDS (ROS2's default middleware) cannot route messages between separate processes. Running bridge + control loop in one process means the ROS2 publisher and subscriber share the same node -- no DDS networking needed.

### Velocity → Key Translation

The `/move` endpoint converts absolute velocities to keyboard key sequences:

1. Publish `z` (reset all velocities to zero)
2. Publish directional keys: `w`/`s` for vx, `a`/`d` for vy, `q`/`e` for vyaw
3. Number of presses = `round(abs(velocity) / 0.2)`

Example: `{"vx": 0.4}` → keys `['z', 'w', 'w']` → vx = 0.0 → 0.2 → 0.4

### HTTP API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/move` | `{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}` | Translate to key sequence |
| POST | `/stop` | — | Publish `z` (zero all velocities) |
| POST | `/activate` | — | Publish `]` (activate walking policy) |
| POST | `/deactivate` | — | Publish `o` (deactivate policy) |
| POST | `/key` | `{"key": "9"}` | Publish arbitrary key |
| GET | `/status` | — | Current velocity and step size |

### Available Keys

| Key | Action |
|-----|--------|
| `]` | Activate policy |
| `o` | Deactivate policy |
| `9` | Toggle release/hold |
| `w`/`s` | Forward/backward velocity ±0.2 |
| `a`/`d` | Strafe left/right ±0.2 |
| `q`/`e` | Turn left/right ±0.2 |
| `z` | Zero all velocities |
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

| Label | Commanded (m/s) | Calibrated linear (m/s) | Calibrated yaw (rad/s) | Key presses |
|-------|----------------|------------------------|----------------------|-------------|
| slow | 0.2 | 0.18 | 0.20 | 1 |
| medium | 0.4 | 0.35 | 0.40 | 2 |
| fast | 0.6 | 0.50 | 0.55 | 3 |

Calibrated values are used for distance-based ("walk 2 meters") and angle-based ("turn 90 degrees") duration calculations in the Realtime API client.

## Future: GEAR-SONIC

The GR00T-WholeBodyControl repo also contains **GEAR-SONIC** (`gear_sonic_deploy/`), a C++/TensorRT kinematic planner with 27 motion modes:

| Category | Modes |
|----------|-------|
| Locomotion | idle, slowWalk, walk, run |
| Ground | squat, kneelTwoLeg, kneelOneLeg, lyingFacedown, handCrawling, elbowCrawling |
| Boxing | idleBoxing, walkBoxing, leftJab, rightJab, randomPunches, leftHook, rightHook |
| Styled walks | happy, stealth, injured, careful, objectCarrying, crouch, happyDance, zombie, point, scared |

GEAR-SONIC accepts commands via a ZMQ interface (`mode`, `movement_direction`, `facing_direction`, `speed`, `height`). It cannot run simultaneously with the Decoupled WBC (both write motor commands), but could serve as an alternative locomotion backend for expressive demos.

## Future Tasks

| Task | Integration Point | What to Add |
|------|-------------------|-------------|
| Task 2 (SLAM/LiDAR Nav) | New OpenClaw skill, waypoint API or `/move` | `slam-navigation` skill, LiDAR SLAM stack |
| Task 3 (VLA + Nav + WBC) | OpenClaw orchestrates all skills | `vla-control` skill, vision pipeline |
| GEAR-SONIC | Alternative bridge backend | ZMQ publisher, mode mapping |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_MODE` | `realtime` | `realtime` or `openclaw` |
| `OPENAI_API_KEY` | (required) | Used by both modes |
| `BRIDGE_URL` | `http://localhost:8765` | Bridge server address |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

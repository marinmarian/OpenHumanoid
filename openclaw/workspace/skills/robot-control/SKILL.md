---
name: robot_control
description: Control the G1 humanoid robot locomotion via the bridge HTTP API.
---

# Robot Control

Use `exec` to send curl commands to the bridge server at http://localhost:8765.

The bridge sets velocity **directly on the WBC neural network policy** — any float value is accepted (no quantization).

## Activate the robot (required before moving)

```bash
curl -s -X POST http://localhost:8765/activate
```

## Move the robot

```bash
curl -s -X POST http://localhost:8765/move \
  -H 'Content-Type: application/json' \
  -d '{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}'
```

Parameters:
- `vx`: forward/backward velocity (m/s). Positive = forward. Any float value works.
- `vy`: left/right strafe velocity (m/s). Positive = left.
- `vyaw`: turning velocity (rad/s). Positive = turn left.

## Stop the robot

```bash
curl -s -X POST http://localhost:8765/stop
```

## Distance-based movement

To move a specific distance, calculate: `sleep_seconds = distance_meters / actual_speed`

Actual ground speeds (use these for timing, NOT the commanded velocity):

| Speed  | Commanded (m/s) | Actual ground (m/s) | Actual yaw (rad/s) |
|--------|-----------------|---------------------|---------------------|
| slow   | 0.2             | 0.18                | 0.20                |
| medium | 0.4             | 0.35                | 0.40                |
| fast   | 0.6             | 0.50                | 0.55                |

Example — "walk forward 5 meters" at medium speed: `sleep = 5 / 0.35 = 14.3s`

```bash
curl -s -X POST http://localhost:8765/move -H 'Content-Type: application/json' -d '{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}' && sleep 14.3 && curl -s -X POST http://localhost:8765/stop
```

Example — "turn left 90 degrees" at medium speed: `sleep = 1.5708 / 0.40 = 3.9s`

```bash
curl -s -X POST http://localhost:8765/move -H 'Content-Type: application/json' -d '{"vx": 0.0, "vy": 0.0, "vyaw": 0.4}' && sleep 3.9 && curl -s -X POST http://localhost:8765/stop
```

## Turn in place

```bash
curl -s -X POST http://localhost:8765/move \
  -H 'Content-Type: application/json' \
  -d '{"vx": 0.0, "vy": 0.0, "vyaw": 0.4}'
```

## Release / hold toggle

```bash
curl -s -X POST http://localhost:8765/key \
  -H 'Content-Type: application/json' \
  -d '{"key": "9"}'
```

## Send a raw key press

```bash
curl -s -X POST http://localhost:8765/key \
  -H 'Content-Type: application/json' \
  -d '{"key": "w"}'
```

Keys: `]`=activate, `o`=deactivate, `9`=release/hold, `1`/`2`=raise/lower base height, `n`/`m`=gait frequency, `3`-`8`=torso posture

## Check status

```bash
curl -s http://localhost:8765/status
```

## Speed reference

| Label  | vx / vy (m/s) | vyaw (rad/s) |
|--------|---------------|--------------|
| slow   | 0.2           | 0.2          |
| medium | 0.4           | 0.4          |
| fast   | 0.6           | 0.6          |

## Safety

- Always call `/activate` before any movement commands.
- Always send `/stop` after timed or distance-based movements.
- Confirm with the user before sending fast speeds (0.6+).
- For large distances (>3m), prefer medium speed to reduce overshoot.
- Keep replies short -- the user is controlling a robot in real time.

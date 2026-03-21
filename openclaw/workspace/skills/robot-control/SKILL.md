---
name: robot_control
description: Control the G1 humanoid robot locomotion via the bridge HTTP API.
---

# Robot Control

Use `exec` to send curl commands to the bridge server at http://localhost:8765.

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

Velocities are translated to keyboard key presses (step = 0.2 m/s per press). Use multiples of 0.2 for best results.

Parameters:
- `vx`: forward/backward velocity. Positive = forward. (0.2 = slow, 0.4 = medium, 0.6 = fast)
- `vy`: left/right strafe velocity. Positive = left.
- `vyaw`: turning velocity (rad/s). Positive = turn left.

## Stop the robot

```bash
curl -s -X POST http://localhost:8765/stop
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

## Send a key press (emulates keyboard control)

```bash
curl -s -X POST http://localhost:8765/key \
  -H 'Content-Type: application/json' \
  -d '{"key": "w"}'
```

Keys: `]`=activate, `o`=deactivate, `9`=release/hold, `w`=forward, `s`=backward, `a`=strafe-left, `d`=strafe-right, `q`=turn-left, `e`=turn-right, `z`=zero-velocity

## Check status

```bash
curl -s http://localhost:8765/status
```

## Speed reference

| Label  | vx / vy | vyaw   | Key presses |
|--------|---------|--------|-------------|
| slow   | 0.2     | 0.2    | 1           |
| medium | 0.4     | 0.4    | 2           |
| fast   | 0.6     | 0.6    | 3           |

## Safety

- Always call `/activate` before any movement commands.
- Always send `/stop` after timed movements.
- Confirm with the user before sending fast speeds (0.6+).
- Keep replies short -- the user is controlling a robot in real time.

---
name: robot_control
description: Control the G1 humanoid robot locomotion via the bridge HTTP API.
---

# Robot Control

Use `exec` to send curl commands to the bridge server at http://localhost:8765.

## Move the robot

```bash
curl -s -X POST http://localhost:8765/move \
  -H 'Content-Type: application/json' \
  -d '{"vx": 0.3, "vy": 0.0, "vyaw": 0.0}'
```

Parameters:
- `vx`: forward/backward velocity (-0.5 to 0.5 m/s). Positive = forward.
- `vy`: left/right strafe velocity (-0.5 to 0.5 m/s). Positive = left.
- `vyaw`: turning velocity (-0.5 to 0.5 rad/s). Positive = turn left.

## Stop the robot

```bash
curl -s -X POST http://localhost:8765/stop
```

## Send a key press (emulates keyboard control)

```bash
curl -s -X POST http://localhost:8765/key \
  -H 'Content-Type: application/json' \
  -d '{"key": "w"}'
```

Keys: w=forward, s=backward, a=strafe-left, d=strafe-right, q=turn-left, e=turn-right, z=reset-all

## Check status

```bash
curl -s http://localhost:8765/status
```

## Safety

- The bridge clamps all velocities to the safe range automatically.
- Max linear velocity: 0.5 m/s
- Max angular velocity: 0.5 rad/s
- Always send `/stop` after timed movements.
- Confirm with the user before sending velocities above 0.4.

## Speed reference

| Label  | Velocity |
|--------|----------|
| slow   | 0.15     |
| medium | 0.30     |
| fast   | 0.45     |

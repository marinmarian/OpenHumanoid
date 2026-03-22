# OpenHumanoid

Voice-controlled humanoid robot integrating **OpenClaw**, **SLAM/LiDAR Navigation**, and **GR00T WBC + VLA** for voice-driven locomotion and loco-manipulation on the Unitree G1.

## Known Gaps (capability stack)

The manipulation pipeline is architecturally wired end-to-end but has the following gaps before it works on real hardware:

1. **Real perception now has a ZED path, but detection is still the main gap.** In real-backend mode the capability stack now uses a live ZED stereo backend for `scene()` and `object_pose()`, grounds detections into 3D with the point cloud, and can fall back to heuristic tabletop/color segmentation. The remaining gap is robust detection quality: for anything beyond simple tabletop/color cases, you still need a real detector feeding 2D boxes or masks into the stack.

2. **Hands are opt-in on the real robot.** `scripts/start_bridge.sh` keeps `--no-with_hands` as the safe default for the real robot. That means `hand_controller = None`, `/hand/command` returns 503, and the pick sequence will fail at the gripper step unless you start the bridge with `BRIDGE_WITH_HANDS=1 ./scripts/start_bridge.sh real`.

3. **ZED extrinsics still need calibration.** The live perception backend now supports camera-to-base extrinsics through `ZED_TO_BASE_{X,Y,Z,ROLL,PITCH,YAW}`, but those default to zero. Until you calibrate them, real object poses will only be as good as that assumed transform.

4. **Pick sequence blocks the HTTP thread ~5+ seconds.** `_execute_pick_sequence` runs synchronously: pregrasp (1.6s) + descend (1.0s) + grip (0.5s) + retreat (1.4s) ≈ 4.5s minimum. The capability server calls this via `_post_bridge_json` with a blocking HTTP request. Check the timeout on that call.

5. **Verification in real mode is still provisional.** `_verify_pick_execution()` now marks the pick as succeeded when every bridge stage reports success, even without a real perception confirmation. That is useful for exercising the WBC path, but it is still a trust-based fallback until `scene()` is backed by real ZED perception.

## How It Works

Two switchable voice-control modes, both sharing a single HTTP bridge to the robot:


| Mode                             | Latency | Input                              | Capabilities                                                     |
| -------------------------------- | ------- | ---------------------------------- | ---------------------------------------------------------------- |
| **Fast** (`VOICE_MODE=realtime`) | ~500ms  | Voice (Realtime API)               | Locomotion: walk, turn, stop, distance/timed/sequential commands |
| **Full** (`VOICE_MODE=openclaw`) | ~2-5s   | Voice + Text + WhatsApp (OpenClaw) | Locomotion + prototype map/localize/navigate/perceive/manipulate stack |


![Architecture](docs/architecture_diagram.png)

See [docs/architecture.md](docs/architecture.md) for the full architecture and data flow, and [docs/capability_stack.md](docs/capability_stack.md) for the new map/localize/navigate/perceive/manipulate control plane.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker (for the WBC container)
- A Unitree G1 robot connected via Ethernet (or use mock mode for dev)
- An [OpenAI API key](https://platform.openai.com/api-keys) with Realtime API access
- A working microphone and speaker (for voice modes)

## Quick Start

### 1. Clone and install

```bash
sudo apt-get install -y libportaudio2
git clone git@github.com:alexzh3/OpenHumanoid.git
cd OpenHumanoid
uv sync
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 3. Set up the WBC (one-time)

```bash
git lfs install
git clone https://github.com/NVlabs/GR00T-WholeBodyControl.git
cd GR00T-WholeBodyControl/decoupled_wbc
./docker/run_docker.sh --install --root    # first time: pulls Docker image
./docker/run_docker.sh --root              # subsequent runs: enters container
```

> Container uses `--network host` so the bridge port (8765) is accessible from the host.
> Container name: `decoupled_wbc-bash-root`.

### 4. Launch bridge + control loop

```bash
# Simulation (MuJoCo)
./scripts/start_bridge.sh

# Real robot, locomotion only
./scripts/start_bridge.sh real

# Real robot, enable hand endpoints for staged pick execution
BRIDGE_WITH_HANDS=1 ./scripts/start_bridge.sh real
```

Verify: `curl http://localhost:8765/status`

Kill bridge: `docker exec decoupled_wbc-bash-root pkill -9 -f run_with_bridge.py`

> **Without Docker/robot:** Run `uv run python bridge/mock_bridge.py` instead. Same API, prints to console.

#### Real robot prerequisites

Before `start_bridge.sh real` will work, the host ethernet NIC must have an IPv4 address on the robot subnet. CycloneDDS (used by the Unitree SDK) ignores interfaces without an IP.

```bash
# 1. Assign IP to the robot NIC (one-time per boot)
sudo ip addr add 192.168.123.222/24 dev enp0s31f6

# 2. Allow DDS multicast traffic through the firewall
sudo ufw allow in on enp0s31f6

# 3. Put the robot in damping mode (L2+B on controller) before launching
```

**Different laptop?** You may need to change the NIC name. Find yours with:

```bash
ip link show          # look for the wired ethernet interface
```

Then either set it inline or export it:

```bash
ROBOT_NIC=eth0 ./scripts/start_bridge.sh real
```

### 4.5. Start the capability stack

```bash
# Default: mock mode for development (fake perception / verification success)
./scripts/start_capability_server.sh

# Real-backend mode: use the live ZED perception backend by default
CAPABILITY_REAL_BACKEND=1 ./scripts/start_capability_server.sh

# Force the ZED backend explicitly and optionally load 2D detections from JSON
CAPABILITY_REAL_BACKEND=1 PERCEPTION_BACKEND=zed PERCEPTION_DETECTIONS_PATH=/path/to/detections.json ./scripts/start_capability_server.sh
```

This starts the local capability server used by OpenClaw skills for saved-map navigation, perception, face recognition, and manipulation orchestration. Check `curl -s http://127.0.0.1:8787/status` at any time; the JSON includes `mock_mode` and `perception_backend`.

### 5. Run a voice mode

**Fast mode** (OpenAI Realtime API):

```bash
uv run python -m realtime.main
```

Voice commands:

- "get ready" / "stand up" — activate robot (required first)
- "walk forward" — continuous until "stop"
- "walk forward slowly" / "walk forward fast" — speed control
- "walk forward for 3 seconds" — timed, auto-stops
- "walk forward 2 meters" — distance-based
- "walk forward 1 meter then turn right" — sequential
- "release" / "relax" — toggle hold/limp
- "stop" — immediate halt

**Full mode** (OpenClaw Gateway):

```bash
cd openclaw && bash setup.sh && cd ..
openclaw gateway start
```

Open [http://127.0.0.1:18789](http://127.0.0.1:18789) for WebChat, or use Talk Mode for voice. Supports text and voice via WhatsApp when configured. For autonomy tasks, start the capability stack first so OpenClaw can call the navigation, perception, and manipulation skills.

## Bridge HTTP API


| Method | Endpoint      | Body                                  | Description                                        |
| ------ | ------------- | ------------------------------------- | -------------------------------------------------- |
| POST   | `/move`       | `{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}` | Set velocity (translated to key presses, step=0.2) |
| POST   | `/stop`       | —                                     | Zero all velocities (key `z`)                      |
| POST   | `/activate`   | —                                     | Activate walking policy (key `]`)                  |
| POST   | `/deactivate` | —                                     | Deactivate policy (key `o`)                        |
| POST   | `/key`        | `{"key": "9"}`                        | Publish arbitrary key (e.g. `9` = release/hold)    |
| GET    | `/status`     | —                                     | Current velocity and step size                     |


Speed reference: slow=0.2, medium=0.4, fast=0.6 m/s (1/2/3 key presses).

## Capability Stack API

The prototype autonomy stack runs as a local HTTP server on port `8787` by default. It persists saved maps and exposes higher-level endpoints for map building, localization, navigation, perception, face recognition, and object picking.

Key endpoints:

- `POST /maps/build`
- `POST /maps/load`
- `POST /localization/initialize`
- `POST /navigation/goal`
- `POST /perception/scene`
- `POST /perception/object_pose`
- `POST /perception/grasp_pose`
- `POST /perception/face/enroll`
- `POST /perception/face/recognize`
- `POST /manipulation/pick`
- `POST /mission/pick_object`

See [docs/capability_stack.md](docs/capability_stack.md) for the full contract and the "reach for the table and take the green apple" pipeline. The manipulation path is now pose-aware: perception can return a grasp candidate, and `POST /manipulation/pick` can consume either a raw 3D pose or a precomputed grasp candidate.

## Testing

```bash
# Terminal 1: mock bridge
uv run python bridge/mock_bridge.py

# Terminal 2: test
curl -X POST http://localhost:8765/activate
curl -X POST http://localhost:8765/move -H 'Content-Type: application/json' -d '{"vx": 0.4}'
curl -X POST http://localhost:8765/stop
```

## Planning


| Task                                | Scope  | Description                                         |
| ----------------------------------- | ------ | --------------------------------------------------- |
| **Task 1 — OpenClaw + WBC**         | MVP    | Voice → locomotion pipeline via shared bridge       |
| **Task 2 — SLAM/LiDAR Navigation**  | Tier 2 | Saved-map navigation stack scaffolded; real SLAM/nav adapters still to be wired |
| **Task 3 — VLA + Navigation + WBC** | Tier 3 | Perception/manipulation orchestration scaffolded; real vision and arm control adapters still to be wired |


**Future: GEAR-SONIC integration** — The repo includes NVIDIA's GEAR-SONIC kinematic planner (`gear_sonic_deploy/`) with 27 motion modes (walk, run, squat, crawl, box, dance, zombie walk, etc.). This C++/TensorRT stack accepts commands via ZMQ and could replace or complement the Decoupled WBC for expressive locomotion demos.

## Project Structure

```
OpenHumanoid/
├── bridge/              # Bridge server (run_with_bridge.py for Docker, mock for host)
├── realtime/            # Fast mode: OpenAI Realtime API voice client
├── openclaw/            # Full mode: OpenClaw Gateway config, skills, workspace
├── capabilities/         # Prototype autonomy control plane (navigation/perception/manipulation)
├── scripts/             # Launch and utility scripts (start_bridge.sh, launch.sh)
├── docs/                # Architecture docs and planning assets
├── GR00T-WholeBodyControl/  # NVIDIA WBC repo (gitignored, clone separately)
├── CONTEXT.md           # AI-readable project context
├── .env.example         # Environment variable template
└── pyproject.toml       # Python dependencies (uv sync)
```

## Documentation

- [Architecture & Data Flow](docs/architecture.md)
- [Capability Stack](docs/capability_stack.md)
- [AI Context](CONTEXT.md)
- [Planning Image](docs/planning.png)

## License

TBD
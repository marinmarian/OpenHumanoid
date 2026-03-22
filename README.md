# OpenHumanoid

Voice-controlled humanoid robot integrating **OpenClaw**, **SLAM/LiDAR Navigation**, and **GR00T WBC + VLA** for voice-driven locomotion and loco-manipulation on the Unitree G1.

## How It Works

Two switchable voice-control modes, both sharing a single HTTP bridge to the robot:


| Mode                             | Latency | Input                              | Capabilities                                                     |
| -------------------------------- | ------- | ---------------------------------- | ---------------------------------------------------------------- |
| **Fast** (`VOICE_MODE=realtime`) | ~500ms  | Voice (Realtime API)               | Locomotion: walk, turn, stop, distance/timed/sequential commands |
| **Full** (`VOICE_MODE=openclaw`) | ~2-5s   | Voice + Text + WhatsApp (OpenClaw) | Locomotion + prototype map/localize/navigate/perceive/manipulate stack |


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

# Real robot
./scripts/start_bridge.sh real
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
./scripts/start_capability_server.sh
```

This starts the local capability server used by OpenClaw skills for saved-map navigation, perception, face recognition, and manipulation orchestration.

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
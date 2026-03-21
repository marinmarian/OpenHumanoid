# OpenHumanoid

Voice-controlled humanoid robot integrating **OpenClaw**, **SLAM/LiDAR Navigation**, and **GR00T WBC + VLA** for voice-driven locomotion and loco-manipulation on the Unitree G1.

## How It Works

Two switchable voice-control modes, both sharing a single HTTP bridge to the robot:

| Mode | Latency | Input | Capabilities |
|------|---------|-------|--------------|
| **Fast** (`VOICE_MODE=realtime`) | ~500ms | Voice (Realtime API) | Locomotion: walk, turn, stop, distance/timed/sequential commands |
| **Full** (`VOICE_MODE=openclaw`) | ~2-5s | Voice + Text + WhatsApp (OpenClaw) | Full orchestration + future Navigation/VLA |

See [docs/architecture.md](docs/architecture.md) for the full architecture and data flow.

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

# Real robot (host IP must be 192.168.123.222)
./scripts/start_bridge.sh real
```

Verify: `curl http://localhost:8765/status`

> **Without Docker/robot:** Run `uv run python bridge/mock_bridge.py` instead. Same API, prints to console.

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

Open [http://127.0.0.1:18789](http://127.0.0.1:18789) for WebChat, or use Talk Mode for voice. Supports text and voice via WhatsApp when configured.

## Bridge HTTP API

| Method | Endpoint | Body | Description |
|--------|----------|------|-------------|
| POST | `/move` | `{"vx": 0.4, "vy": 0.0, "vyaw": 0.0}` | Set velocity (translated to key presses, step=0.2) |
| POST | `/stop` | — | Zero all velocities (key `z`) |
| POST | `/activate` | — | Activate walking policy (key `]`) |
| POST | `/deactivate` | — | Deactivate policy (key `o`) |
| POST | `/key` | `{"key": "9"}` | Publish arbitrary key (e.g. `9` = release/hold) |
| GET | `/status` | — | Current velocity and step size |

Speed reference: slow=0.2, medium=0.4, fast=0.6 m/s (1/2/3 key presses).

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

| Task | Scope | Description |
|------|-------|-------------|
| **Task 1 — OpenClaw + WBC** | MVP | Voice → locomotion pipeline via shared bridge |
| **Task 2 — SLAM/LiDAR Navigation** | Tier 2 | Autonomous navigation with obstacle avoidance |
| **Task 3 — VLA + Navigation + WBC** | Tier 3 | Full loco-manipulation with vision-language actions |

**Future: GEAR-SONIC integration** — The repo includes NVIDIA's GEAR-SONIC kinematic planner (`gear_sonic_deploy/`) with 27 motion modes (walk, run, squat, crawl, box, dance, zombie walk, etc.). This C++/TensorRT stack accepts commands via ZMQ and could replace or complement the Decoupled WBC for expressive locomotion demos.

## Project Structure

```
OpenHumanoid/
├── bridge/              # Bridge server (run_with_bridge.py for Docker, mock for host)
├── realtime/            # Fast mode: OpenAI Realtime API voice client
├── openclaw/            # Full mode: OpenClaw Gateway config, skills, workspace
├── scripts/             # Launch and utility scripts (start_bridge.sh, launch.sh)
├── docs/                # Architecture docs and planning assets
├── GR00T-WholeBodyControl/  # NVIDIA WBC repo (gitignored, clone separately)
├── CONTEXT.md           # AI-readable project context
├── .env.example         # Environment variable template
└── pyproject.toml       # Python dependencies (uv sync)
```

## Documentation

- [Architecture & Data Flow](docs/architecture.md)
- [AI Context](CONTEXT.md)
- [Planning Image](docs/planning.png)

## License

TBD

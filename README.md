# OpenHumanoid

Whole-body-controlled humanoid robot integrating **OpenClaw**, **DiMOS**, and **GR00T VLA** for voice-driven locomotion and loco-manipulation.

## Planning

![Task dependency graph](docs/planning.png)

### Task Overview

| Task | Scope | Tier | Description |
|------|-------|------|-------------|
| **WBC Research** | Gate | — | Evaluate LeRobot vs GR00T for whole-body control; decision required before Task 1 & 2 |
| **Task 1 — OpenClaw + WBC** | MVP | Green | Voice → locomotion pipeline. Integrate OpenClaw with WBC, build the shared robot bridge (fatal blocker). |
| **Task 2 — VLA Pipeline** | Tier 2 | Orange | GR00T inference pipeline and incorporation with LeRobot. |
| **Task 3 — DiMOS + WBC** | Tier 2 | — | Navigation stack → locomotion via DiMOS. Fallback: standalone WBC integration. |
| **Task 4 — DiMOS + WBC + VLA** | Tier 3 | — | Full loco-manipulation: VLA inference driven by DiMOS through WBC. |

### Dependencies

- Tasks 1 & 2 run **in parallel** after the WBC research gate.
- Task 3 depends on Task 1.
- Task 4 depends on Tasks 2 & 3.

## Project Structure

```
OpenHumanoid/
├── docs/            # Planning assets and documentation
├── openclaw/        # OpenClaw integration and robot bridge
├── vla/             # VLA inference pipeline (GR00T / LeRobot)
├── wbc/             # Whole-body control layer
├── dimos/           # DiMOS navigation stack integration
└── scripts/         # Utility and launch scripts
```

## Getting Started

```bash
git clone git@github.com:alexzh3/OpenHumanoid.git
cd OpenHumanoid
# setup instructions coming soon
```

## License

TBD

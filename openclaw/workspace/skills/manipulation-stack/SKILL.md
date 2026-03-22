---
name: manipulation_stack
description: Use the manipulation stack for grasping and for the combined pick-object pipeline.
---

# Manipulation Stack

The manipulation stack lives at `http://localhost:8787` unless `CAPABILITY_SERVER_URL` says otherwise.

## Pick a grounded object directly

```bash
curl -s -X POST http://localhost:8787/manipulation/pick \
  -H 'Content-Type: application/json' \
  -d '{"object_id":"apple-green-01","action":"pick"}'
```

## Pick using an explicit perceived pose

```bash
curl -s -X POST http://localhost:8787/manipulation/pick \
  -H 'Content-Type: application/json' \
  -d '{"object_id":"apple-green-01","pose":{"x":2.78,"y":1.08,"z":0.79,"frame":"map"},"action":"pick"}'
```

## Run the full pick-object pipeline

```bash
curl -s -X POST http://localhost:8787/mission/pick_object \
  -H 'Content-Type: application/json' \
  -d '{"object_label":"apple","color":"green","support_surface":"table"}'
```

## Usage notes

- The combined mission endpoint assumes a saved map is already loaded and localization is ready.
- If the mission is blocked, call the navigation stack first to load a map and localize.
- `POST /manipulation/pick` can now consume either an explicit object pose or a precomputed `grasp_candidate`.
- For object pick tasks, prefer the combined mission endpoint unless you already have a high-confidence object pose and approach pose.

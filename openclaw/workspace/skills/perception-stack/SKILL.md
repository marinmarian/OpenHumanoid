---
name: perception_stack
description: Use the camera-driven perception stack for scene understanding, 3D object grounding, and face recognition.
---

# Perception Stack

The perception stack lives at `http://localhost:8787` unless `CAPABILITY_SERVER_URL` says otherwise.

## Understand the current scene

```bash
curl -s -X POST http://localhost:8787/perception/scene \
  -H 'Content-Type: application/json' \
  -d '{"camera_name":"zed-mini"}'
```

## Find a specific object and return its 3D pose

```bash
curl -s -X POST http://localhost:8787/perception/object_pose \
  -H 'Content-Type: application/json' \
  -d '{"label":"apple","color":"green"}'
```

## Turn a grounded object pose into a grasp candidate

```bash
curl -s -X POST http://localhost:8787/perception/grasp_pose \
  -H 'Content-Type: application/json' \
  -d '{"object_id":"apple-green-01","pose":{"x":2.78,"y":1.08,"z":0.79,"frame":"map"}}'
```

## Enroll a face

```bash
curl -s -X POST http://localhost:8787/perception/face/enroll \
  -H 'Content-Type: application/json' \
  -d '{"person_id":"alice","display_name":"Alice"}'
```

## Recognize known faces

```bash
curl -s -X POST http://localhost:8787/perception/face/recognize \
  -H 'Content-Type: application/json' \
  -d '{"min_confidence":0.8}'
```

## Usage notes

- Use perception before navigation when the task depends on finding an object or support surface.
- Use perception again after navigation to refine the close-range pose before manipulation.
- Use `perception/grasp_pose` when the downstream manipulation step needs an explicit wrist target rather than just an object ID.
- Face recognition should be treated as identity verification with a confidence threshold, not as a free-form VLM guess.

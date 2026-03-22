---
name: navigation_stack
description: Use the saved-map navigation stack for map building, localization, and autonomous navigation.
---

# Navigation Stack

The navigation stack lives at `http://localhost:8787` unless `CAPABILITY_SERVER_URL` says otherwise.

## Important operating model

- Build the map once, then persist it.
- For normal runtime tasks, load the saved map and localize against it.
- Do not rebuild the map for every task.
- Navigation is blocked until localization is ready.

## Build and persist a map

```bash
curl -s -X POST http://localhost:8787/maps/build \
  -H 'Content-Type: application/json' \
  -d '{"map_id":"lab-main","description":"Main lab map","source":"live_scan"}'
```

## Load an existing map

```bash
curl -s -X POST http://localhost:8787/maps/load \
  -H 'Content-Type: application/json' \
  -d '{"map_id":"lab-main"}'
```

## Initialize localization on the saved map

```bash
curl -s -X POST http://localhost:8787/localization/initialize \
  -H 'Content-Type: application/json' \
  -d '{"map_id":"lab-main","method":"lidar_global_localization"}'
```

## Navigate to a named landmark

```bash
curl -s -X POST http://localhost:8787/navigation/goal \
  -H 'Content-Type: application/json' \
  -d '{"goal_name":"table"}'
```

## Check navigation and localization state

```bash
curl -s http://localhost:8787/navigation/status
curl -s http://localhost:8787/localization/status
curl -s http://localhost:8787/maps
```

## Safety

- If no map is loaded, ask the user whether to build a new map or load an existing one.
- If localization is not ready, do not issue a navigation goal yet.
- Prefer named landmarks such as `table` over freehand map-frame poses unless the user explicitly gives a pose.

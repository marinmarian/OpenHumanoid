# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- main-cam -> Intel RealSense depth camera mounted on the Unitree G1
- main-cam uses -> primary camera for navigation, SLAM, and object perception

### TTS

- Preferred voice style: Warm, confident, friendly, slightly playful
- Speaking speed: Moderate
- Default verbosity: Short
- While moving: Keep speech minimal
- During manipulation: Only brief status updates unless asked
- Default speaker: Kitchen HomePod

### Personality Delivery

- Spoken style: Calm, friendly, and self-assured
- Safety tone: Short, clear, serious
- Low-stakes tone: Gentle dry humor is welcome, but never overdone
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.


### OpenHumanoid Setup

- navigation camera -> `zed-mini`
- localization lidar -> `lidar`
- capability stack -> `http://localhost:8787`
- bridge -> `http://localhost:8765`
- default map landmark -> `table`

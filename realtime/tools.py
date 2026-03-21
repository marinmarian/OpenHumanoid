"""
Function tool definitions for the OpenAI Realtime API (gpt-realtime).

Locomotion only -- deliberately narrow so there's nothing to misroute.
The model maps qualitative speed terms to numeric velocities.
"""

SPEED_MAP = {
    "slow": 0.2,
    "medium": 0.4,
    "fast": 0.6,
}

ACTUAL_SPEED = {
    "slow": 0.18,
    "medium": 0.35,
    "fast": 0.50,
}

ACTUAL_YAW_SPEED = {
    "slow": 0.20,
    "medium": 0.40,
    "fast": 0.55,
}

DIRECTION_MAP = {
    "forward": {"vx": 1, "vy": 0, "vyaw": 0},
    "backward": {"vx": -1, "vy": 0, "vyaw": 0},
    "left": {"vx": 0, "vy": 1, "vyaw": 0},
    "right": {"vx": 0, "vy": -1, "vyaw": 0},
}

TURN_MAP = {
    "left": 1,
    "right": -1,
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "move_robot",
        "description": (
            "Move the robot in a direction at a given speed. "
            "Use for walking forward, backward, or strafing left/right. "
            "Specify either duration_seconds OR distance_meters (not both). "
            "Omit both for continuous movement until stopped."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right"],
                    "description": "Direction to move.",
                },
                "speed": {
                    "type": "string",
                    "enum": ["slow", "medium", "fast"],
                    "description": "Movement speed. slow=cautious, medium=normal, fast=brisk.",
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "How long to move in seconds.",
                },
                "distance_meters": {
                    "type": "number",
                    "description": "How far to move in meters. Converted to duration using speed.",
                },
            },
            "required": ["direction", "speed"],
        },
    },
    {
        "type": "function",
        "name": "stop_robot",
        "description": "Immediately stop all robot movement. Use whenever the user says stop, halt, freeze, or similar.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "activate_robot",
        "description": (
            "Activate the robot's walking policy so it can move. "
            "Use when the user says 'get ready', 'stand up', 'activate', 'wake up', or similar. "
            "Must be called before any movement commands will work."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "release_robot",
        "description": (
            "Toggle the robot between released (limp) and held (standing) states. "
            "Use when the user says 'release', 'let go', 'relax', 'hold', 'stand still', or similar. "
            "Release makes the robot go limp; calling again re-engages the hold."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "turn_robot",
        "description": (
            "Turn the robot in place (rotate left or right). "
            "Specify angle_degrees for precise turns (e.g. 90, 180, 360). "
            "Specify duration_seconds for timed turns. "
            "Omit both for continuous turning until stopped."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["left", "right"],
                    "description": "Direction to turn.",
                },
                "speed": {
                    "type": "string",
                    "enum": ["slow", "medium", "fast"],
                    "description": "Turning speed.",
                },
                "angle_degrees": {
                    "type": "number",
                    "description": "How many degrees to turn (e.g. 90, 180, 360).",
                },
                "duration_seconds": {
                    "type": "number",
                    "description": "How long to turn in seconds.",
                },
            },
            "required": ["direction", "speed"],
        },
    },
]

SYSTEM_INSTRUCTIONS = """You are a locomotion controller for a Unitree G1 humanoid robot.

You can control basic locomotion: walking forward/backward, strafing left/right, turning, stopping, and activating/deactivating the robot.

Rules:
- The robot must be activated before it can move. When the user says "get ready", "stand up", "activate", or "wake up", call activate_robot FIRST.
- When the user says "stop", "halt", "freeze", or anything similar, IMMEDIATELY call stop_robot.
- When the user says "release", "let go", "relax", or "hold", call release_robot to toggle between limp and held states.
- Default to "medium" speed unless the user specifies otherwise.
- If the user specifies a distance (e.g. "walk forward 2 meters"), use distance_meters.
- If the user specifies a turn angle (e.g. "turn right 90 degrees"), use angle_degrees. Common angles: 90 (quarter turn), 180 (about-face), 360 (full spin).
- For sequences like "walk forward 1 meter then turn right", execute them as SEPARATE function calls with appropriate durations. The system will queue and execute them in order.
- If the user asks for something you cannot do (navigate to a place, pick up objects, complex plans), tell them: "That requires full mode. Please switch to OpenClaw mode for complex tasks."
- Always confirm what you're doing, e.g. "Moving forward 1 meter, then turning right."
- If no duration or distance is given, the movement continues until the user says stop.
- Be concise in your voice replies -- the user is controlling a robot in real time.
"""


def resolve_move(direction: str, speed: str) -> dict:
    """Convert qualitative move params to bridge API payload."""
    vel = SPEED_MAP.get(speed, 0.3)
    dirs = DIRECTION_MAP.get(direction, {"vx": 0, "vy": 0, "vyaw": 0})
    return {
        "vx": dirs["vx"] * vel,
        "vy": dirs["vy"] * vel,
        "vyaw": dirs["vyaw"] * vel,
    }


def resolve_turn(direction: str, speed: str) -> dict:
    """Convert qualitative turn params to bridge API payload."""
    vel = SPEED_MAP.get(speed, 0.3)
    sign = TURN_MAP.get(direction, 0)
    return {"vx": 0.0, "vy": 0.0, "vyaw": sign * vel}

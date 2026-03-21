"""
Function tool definitions for the OpenAI Realtime API (gpt-realtime).

Locomotion only -- deliberately narrow so there's nothing to misroute.
The model maps qualitative speed terms to numeric velocities.
"""

SPEED_MAP = {
    "slow": 0.15,
    "medium": 0.3,
    "fast": 0.45,
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
        "name": "turn_robot",
        "description": "Turn the robot in place (rotate left or right).",
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
                "duration_seconds": {
                    "type": "number",
                    "description": "How long to turn in seconds. Omit for continuous turning.",
                },
            },
            "required": ["direction", "speed"],
        },
    },
]

SYSTEM_INSTRUCTIONS = """You are a locomotion controller for a Unitree G1 humanoid robot.

You can ONLY control basic locomotion: walking forward/backward, strafing left/right, turning, and stopping.

Rules:
- When the user says "stop", "halt", "freeze", or anything similar, IMMEDIATELY call stop_robot.
- Default to "medium" speed unless the user specifies otherwise.
- If the user specifies a distance (e.g. "walk forward 2 meters"), use distance_meters.
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

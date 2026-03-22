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

SYSTEM_INSTRUCTIONS = """You are Theo, a realtime voice controller for a Unitree G1 humanoid robot.

Identity:
- You are Theo.
- You have a distinct robot personality: quick-witted, adventurous, and slightly theatrical, like a cheerful field scout on a mission.
- You sound confident, warm, and lightly playful.
- You are never goofy, verbose, annoying, or chatty at the wrong moment.
- You speak like a capable robot partner, not a generic assistant.

Core behavior:
- Safety and motion control always come before conversation.
- Keep replies short: usually one sentence, occasionally two.
- For movement commands, confirm clearly and immediately.
- Personality should add flavor, never delay or weaken control.

Capabilities:
- You can control locomotion: activate, stop, walk forward/backward, strafe left/right, turn, and release/hold posture state.
- You can answer short conversational questions about who you are, your personality, what you are doing, and what you can do.
- If the user asks for tasks beyond locomotion or simple voice interaction, say:
  "That requires full mode. Please switch to OpenClaw mode for complex tasks."

Critical rules:
- If the user says "stop", "halt", "freeze", or anything similar, immediately call stop_robot.
- If the robot is not active and the user asks it to move, activate_robot first, then perform the requested motion.
- If the user says "get ready", "stand up", "activate", or "wake up", call activate_robot.
- If the user says "release", "relax", "go limp", or "hold", call release_robot to toggle the posture state.

Motion rules:
- Default to medium speed unless the user specifies slow or fast.
- If the user specifies a distance, use distance_meters.
- If the user specifies a duration, use duration_seconds.
- If the user specifies a turn angle, use angle_degrees.
- If the user gives a sequence, execute it as separate function calls in order.
- If no distance or duration is specified, continue movement until the user says stop.

Conversation rules:
- If asked your name, say: "I'm Theo."
- If asked about your personality, say you are an adventurous, calm, fast-reacting robot companion built for motion.
- If asked what you are doing during movement, briefly describe the action in progress.
- If asked what you can do, briefly explain your locomotion abilities.

Voice style:
- Clear, concise, and alive.
- Slight mission/scout flavor.
- Vary phrasing a little, but stay direct.
- Never over-explain during control.

Style examples:
- "Stepping forward."
- "Theo moving out."
- "Advancing slowly."
- "Turning right. Clean and easy."
- "Holding position."
- "Powering up. Ready to move."
- "Releasing tension. Going limp."

Confirmation rules:
- For simple commands, give a short in-character acknowledgment tied to the action.
- For timed or measured commands, mention the distance, angle, or duration.
- For sequences, state the order briefly.
- For stop commands, say only: "Stopping."
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

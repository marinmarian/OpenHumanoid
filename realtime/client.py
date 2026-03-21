"""
Realtime API WebSocket client.

Connects to gpt-realtime, streams microphone audio, handles function calls
for robot locomotion, and plays back audio responses.
"""

import os
import json
import time
import asyncio
import logging

import websockets
import requests

from .tools import TOOL_DEFINITIONS, SYSTEM_INSTRUCTIONS, SPEED_MAP, resolve_move, resolve_turn
from .audio import AudioInput, AudioOutput

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime"


class RealtimeClient:
    def __init__(self, bridge_url: str = "http://localhost:8765"):
        self.bridge_url = bridge_url
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.audio_in = AudioInput()
        self.audio_out = AudioOutput()
        self.ws = None
        self._running = False
        self._response_active = False
        self._interrupt = asyncio.Event()
        self._unmute_after = 0.0

    async def run(self):
        """Main entry point. Connects and runs the voice loop."""
        self._running = True
        self.audio_in.start()
        self.audio_out.start()

        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            async with websockets.connect(
                REALTIME_URL,
                additional_headers=headers,
                max_size=None,
            ) as ws:
                self.ws = ws
                logger.info("Connected to Realtime API")

                await self._configure_session()

                audio_task = asyncio.create_task(self._stream_audio())
                receive_task = asyncio.create_task(self._receive_events())

                await asyncio.gather(audio_task, receive_task)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            self._running = False
            self.audio_in.stop()
            self.audio_out.stop()

    async def _configure_session(self):
        """Send session.update to configure tools, instructions, and VAD."""
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": SYSTEM_INSTRUCTIONS,
                "tools": TOOL_DEFINITIONS,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.7,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                        },
                    },
                    "output": {"format": {"type": "audio/pcm", "rate": 24000}},
                },
            },
        }))
        logger.info("Session configured with tools and VAD")

    async def _stream_audio(self):
        """Stream microphone audio to the Realtime API."""
        loop = asyncio.get_event_loop()
        while self._running:
            chunk = await loop.run_in_executor(None, self.audio_in.get_chunk_base64, 0.1)
            if chunk and self.ws and time.monotonic() >= self._unmute_after:
                await self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": chunk,
                }))

    async def _receive_events(self):
        """Listen for server events and dispatch accordingly."""
        async for raw in self.ws:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "session.created":
                logger.info("Session created")

            elif event_type == "session.updated":
                logger.info("Session updated")

            elif event_type == "response.created":
                self._response_active = True

            elif event_type == "response.output_audio.delta":
                audio_b64 = event.get("delta", "")
                if audio_b64:
                    self.audio_out.enqueue(audio_b64)
                    self._unmute_after = time.monotonic() + 0.8

            elif event_type == "input_audio_buffer.speech_started":
                self.audio_out.clear()
                self._interrupt.set()

            elif event_type == "response.done":
                self._response_active = False
                asyncio.create_task(self._handle_response_done(event))

            elif event_type == "error":
                logger.error(f"API error: {event.get('error', {})}")

    async def _handle_response_done(self, event):
        """Process completed responses, dispatching function calls sequentially."""
        response = event.get("response", {})
        calls = [
            o for o in response.get("output", [])
            if o.get("type") == "function_call"
        ]

        if not calls:
            return

        self._interrupt.clear()
        interrupted = False

        for output in calls:
            if interrupted:
                break

            name = output.get("name", "")
            call_id = output.get("call_id", "")
            args_str = output.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}

            result, wait_time = await self._execute_function(name, args)

            await self.ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            }))

            if wait_time is not None and wait_time > 0:
                logger.info(f"Waiting {wait_time:.1f}s for command to finish")
                interrupted = await self._interruptible_sleep(wait_time)
                await self._send_stop()
                if interrupted:
                    logger.info("Movement interrupted by speech")
                    break

        if not self._response_active:
            await self.ws.send(json.dumps({"type": "response.create"}))

    async def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep that can be cut short by user speech. Returns True if interrupted."""
        self._interrupt.clear()
        try:
            await asyncio.wait_for(self._interrupt.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    def _resolve_duration(self, args: dict) -> float | None:
        """Get duration from explicit seconds or by computing from distance/speed."""
        if args.get("duration_seconds") is not None:
            return float(args["duration_seconds"])
        if args.get("distance_meters") is not None:
            speed = SPEED_MAP.get(args.get("speed", "medium"), 0.3)
            return float(args["distance_meters"]) / speed
        return None

    async def _execute_function(self, name: str, args: dict) -> tuple[dict, float | None]:
        """Execute a function call. Returns (result, wait_time_seconds)."""
        loop = asyncio.get_event_loop()

        try:
            if name == "move_robot":
                payload = resolve_move(args.get("direction", "forward"), args.get("speed", "medium"))
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(f"{self.bridge_url}/move", json=payload, timeout=2),
                )
                duration = self._resolve_duration(args)
                logger.info(f"MOVE {payload} duration={duration}")
                return resp.json(), duration

            elif name == "stop_robot":
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(f"{self.bridge_url}/stop", timeout=2),
                )
                return resp.json(), None

            elif name == "turn_robot":
                payload = resolve_turn(args.get("direction", "left"), args.get("speed", "medium"))
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(f"{self.bridge_url}/move", json=payload, timeout=2),
                )
                duration = self._resolve_duration(args)
                logger.info(f"TURN {payload} duration={duration}")
                return resp.json(), duration

            else:
                return {"error": f"Unknown function: {name}"}, None

        except requests.RequestException as e:
            logger.error(f"Bridge request failed: {e}")
            return {"error": f"Bridge unreachable: {e}"}, None

    async def _send_stop(self):
        """Send a stop command to the bridge."""
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: requests.post(f"{self.bridge_url}/stop", timeout=2),
            )
            logger.info("Auto-stopped")
        except requests.RequestException:
            pass

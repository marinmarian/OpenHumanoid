#!/usr/bin/env python3
"""
Fast mode entry point: OpenAI Realtime API voice client for robot locomotion.

Usage:
    python -m realtime.main

Requires:
    - OPENAI_API_KEY environment variable
    - Bridge server running at BRIDGE_URL (default http://localhost:8765)
"""

import os
import sys
import asyncio
import logging

from dotenv import load_dotenv

from .client import RealtimeClient


def main():
    load_dotenv()

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    bridge_url = os.environ.get("BRIDGE_URL", "http://localhost:8765")

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required.")
        print("Set it in .env or export it in your shell.")
        sys.exit(1)

    print(f"Starting Realtime voice client (fast mode)")
    print(f"Bridge URL: {bridge_url}")
    print(f"Press Ctrl+C to stop\n")

    client = RealtimeClient(bridge_url=bridge_url)

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

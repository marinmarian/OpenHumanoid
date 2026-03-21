#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== OpenHumanoid — OpenClaw Gateway Setup ==="

# 1. Install OpenClaw if not present
if ! command -v openclaw &>/dev/null; then
    echo "Installing OpenClaw..."
    curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard
else
    echo "OpenClaw already installed: $(openclaw --version)"
fi

# 2. Symlink config
OPENCLAW_DIR="$HOME/.openclaw"
mkdir -p "$OPENCLAW_DIR"

if [ -f "$OPENCLAW_DIR/openclaw.json" ] && [ ! -L "$OPENCLAW_DIR/openclaw.json" ]; then
    echo "Backing up existing openclaw.json → openclaw.json.bak"
    mv "$OPENCLAW_DIR/openclaw.json" "$OPENCLAW_DIR/openclaw.json.bak"
fi
ln -sfn "$SCRIPT_DIR/openclaw.json" "$OPENCLAW_DIR/openclaw.json"
echo "Linked config: $OPENCLAW_DIR/openclaw.json → $SCRIPT_DIR/openclaw.json"

# 3. Symlink workspace (-n prevents following existing symlink into directory)
if [ -d "$OPENCLAW_DIR/workspace" ] && [ ! -L "$OPENCLAW_DIR/workspace" ]; then
    echo "Backing up existing workspace → workspace.bak"
    mv "$OPENCLAW_DIR/workspace" "$OPENCLAW_DIR/workspace.bak"
fi
ln -sfn "$SCRIPT_DIR/workspace" "$OPENCLAW_DIR/workspace"
echo "Linked workspace: $OPENCLAW_DIR/workspace → $SCRIPT_DIR/workspace"

echo ""
echo "Setup complete. Start the gateway with:"
echo "  openclaw gateway start"
echo ""
echo "WebChat available at: http://127.0.0.1:18789"
echo "Make sure OPENAI_API_KEY is set in your environment."

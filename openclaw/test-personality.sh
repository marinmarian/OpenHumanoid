#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$SCRIPT_DIR/workspace"

print_section() {
  local title="$1"
  local file="$2"

  echo "===== $title ====="
  if [ -f "$file" ]; then
    cat "$file"
  else
    echo "(missing: $file)"
  fi
  echo
}

echo "OpenClaw offline personality preview"
echo
echo "This does not call any model. It shows the files that shape the agent's personality and behavior."
echo

print_section "IDENTITY" "$WORKSPACE_DIR/IDENTITY.md"
print_section "SOUL" "$WORKSPACE_DIR/SOUL.md"
print_section "AGENTS" "$WORKSPACE_DIR/AGENTS.md"
print_section "USER" "$WORKSPACE_DIR/USER.md"

echo "Suggested offline checks:"
echo "- Does the voice in SOUL.md sound like the assistant you want?"
echo "- Does AGENTS.md keep task instructions separate from personality?"
echo "- Does IDENTITY.md make the character feel specific instead of generic?"
echo
echo "If you want real conversations without an OpenAI key, point OpenClaw at another model provider or a local OpenAI-compatible server."

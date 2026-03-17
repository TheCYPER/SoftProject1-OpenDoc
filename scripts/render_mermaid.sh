#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCH_DIR="$ROOT_DIR/docs/architecture"

render() {
  local input="$1"
  local output="$2"

  if command -v mmdc >/dev/null 2>&1; then
    mmdc -i "$input" -o "$output"
  else
    npx -y @mermaid-js/mermaid-cli -i "$input" -o "$output"
  fi
}

render "$ARCH_DIR/system-context.mermaid" "$ARCH_DIR/system-context.png"
render "$ARCH_DIR/container-diagram.mermaid" "$ARCH_DIR/container-diagram.png"
render "$ARCH_DIR/ai-orchestration-component.mermaid" "$ARCH_DIR/ai-orchestration-component.png"
render "$ARCH_DIR/data-model-erd.mermaid" "$ARCH_DIR/data-model-erd.png"

echo "Rendered Mermaid diagrams into $ARCH_DIR"

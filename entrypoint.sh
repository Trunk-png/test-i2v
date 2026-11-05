#!/usr/bin/env bash
set -euo pipefail

cd "${COMFYUI_DIR:-/opt/ComfyUI}"
exec python3 main.py --listen 0.0.0.0 --port 8188 "$@"


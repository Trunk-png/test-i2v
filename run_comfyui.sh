#!/usr/bin/env bash
set -euo pipefail

COMFY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${COMFY_ROOT}"
exec "${COMFY_ROOT}/.venv/bin/python" main.py --listen 0.0.0.0 --port 8188 "$@"


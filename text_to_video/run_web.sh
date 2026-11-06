#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
exec "${PYTHON_BIN:-python3}" -m uvicorn app:app --host 0.0.0.0 --port "${WEB_PORT:-8000}"


#!/usr/bin/env bash
set -euo pipefail

COMFYUI_DIR="${COMFYUI_DIR:-}"
if [[ -n "${CUSTOM_NODES_DIR:-}" ]]; then
  CUSTOM_NODES="${CUSTOM_NODES_DIR}"
elif [[ -n "${COMFYUI_DIR}" && -d "${COMFYUI_DIR}" ]]; then
  CUSTOM_NODES="${COMFYUI_DIR}/custom_nodes"
else
  echo "ERROR: đặt COMFYUI_DIR hoặc CUSTOM_NODES_DIR." >&2
  exit 1
fi
mkdir -p "${CUSTOM_NODES}"

sync_repo() {
  local url="$1"
  local name="${url##*/}"
  name="${name%.git}"
  local target="${CUSTOM_NODES}/${name}"
  if [[ -d "${target}/.git" ]]; then
    echo "Updating ${name}..."
    git -C "${target}" pull --ff-only
  else
    echo "Cloning ${name}..."
    git clone --depth 1 "${url}" "${target}"
  fi
  if [[ -f "${target}/requirements.txt" && -n "${PYTHON_BIN:-}" ]]; then
    "${PYTHON_BIN}" -m pip install -r "${target}/requirements.txt"
  elif [[ -f "${target}/requirements.txt" && -n "${COMFYUI_DIR}" && -x "${COMFYUI_DIR}/.venv/bin/python" ]]; then
    "${COMFYUI_DIR}/.venv/bin/python" -m pip install -r "${target}/requirements.txt"
  elif [[ -f "${target}/requirements.txt" ]]; then
    echo "Có requirements tại ${target}; đặt PYTHON_BIN để tự động cài."
  fi
}

sync_repo "https://github.com/Hieunohair/ComfyUI-safety-checker.git"
sync_repo "https://github.com/trungnk-png/comfyUI-detect-nsfw-text.git"
echo "Custom nodes đã sẵn sàng. Khởi động lại ComfyUI để nạp node."


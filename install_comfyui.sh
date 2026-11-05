#!/usr/bin/env bash
set -euo pipefail

# Cài ComfyUI native với Python virtualenv và PyTorch CUDA 13.
# Có thể đổi thư mục: COMFYUI_DIR=/duong/dan/ComfyUI ./install_comfyui.sh

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMFYUI_DIR="${COMFYUI_DIR:-${SCRIPT_DIR}/ComfyUI}"
VENV_DIR="${VENV_DIR:-${COMFYUI_DIR}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TORCH_VERSION="${TORCH_VERSION:-2.14.1}"
TORCHVISION_VERSION="${TORCHVISION_VERSION:-0.29.1}"
PYTORCH_INDEX_URL="${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cu130}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: Không tìm thấy lệnh '$1'." >&2
    echo "Ubuntu/Debian: sudo apt-get install -y git python3 python3-venv python3-pip ffmpeg" >&2
    exit 1
  fi
}

require_command git
require_command "${PYTHON_BIN}"

if [[ -e "${COMFYUI_DIR}" && ! -d "${COMFYUI_DIR}/.git" ]]; then
  echo "ERROR: ${COMFYUI_DIR} đã tồn tại nhưng không phải repository ComfyUI." >&2
  exit 1
fi

if [[ -d "${COMFYUI_DIR}/.git" ]]; then
  echo "Đang cập nhật ComfyUI..."
  git -C "${COMFYUI_DIR}" pull --ff-only
else
  echo "Đang tải ComfyUI mới nhất vào ${COMFYUI_DIR}..."
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "${COMFYUI_DIR}"
fi

echo "Đang tạo Python virtualenv..."
"${PYTHON_BIN}" -m venv "${VENV_DIR}"
VENV_PYTHON="${VENV_DIR}/bin/python"

"${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel

echo "Đang cài PyTorch ${TORCH_VERSION} cho CUDA 13.0..."
"${VENV_PYTHON}" -m pip install \
  "torch==${TORCH_VERSION}" \
  "torchvision==${TORCHVISION_VERSION}" \
  --index-url "${PYTORCH_INDEX_URL}"

echo "Đang cài dependencies của ComfyUI và batch Excel..."
"${VENV_PYTHON}" -m pip install -r "${COMFYUI_DIR}/requirements.txt"
"${VENV_PYTHON}" -m pip install -r "${SCRIPT_DIR}/requirements-batch.txt"

mkdir -p \
  "${COMFYUI_DIR}/models/diffusion_models" \
  "${COMFYUI_DIR}/models/text_encoders" \
  "${COMFYUI_DIR}/models/vae" \
  "${COMFYUI_DIR}/models/loras" \
  "${COMFYUI_DIR}/input" \
  "${COMFYUI_DIR}/output"

cp "${SCRIPT_DIR}/run_comfyui.sh" "${COMFYUI_DIR}/run_comfyui.sh"
chmod +x "${COMFYUI_DIR}/run_comfyui.sh"

echo
echo "Cài đặt hoàn tất."
echo "Tải model:"
echo "  MODEL_ROOT='${COMFYUI_DIR}/models' '${SCRIPT_DIR}/download.sh'"
echo "Chạy ComfyUI:"
echo "  '${COMFYUI_DIR}/run_comfyui.sh'"
echo "Giao diện: http://127.0.0.1:8188"
echo
echo "Lưu ý: máy cần NVIDIA driver tương thích CUDA 13; PyTorch wheel đã chứa CUDA runtime cần thiết."



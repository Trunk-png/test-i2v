#!/usr/bin/env bash
set -euo pipefail

MODEL_ROOT="${MODEL_ROOT:-${COMFYUI_DIR:-/opt/ComfyUI}/models}"

download() {
  local folder="$1"
  local url="$2"
  local name="${url##*/}"
  mkdir -p "${MODEL_ROOT}/${folder}"
  echo "Downloading ${name} -> ${MODEL_ROOT}/${folder}/"
  curl --fail --location --retry 5 --retry-delay 3 --continue-at - \
    --output "${MODEL_ROOT}/${folder}/${name}" "$url"
}

# Các model đúng theo tên được workflow JSON tham chiếu.
download diffusion_models \
  "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"
download text_encoders \
  "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
download vae \
  "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors"

# Hai LoRA Pika H3 Flex Turbo theo yêu cầu.
download loras \
  "https://huggingface.co/Pika-Labs/Pika-H3-Flex-Turbo-LoRA/resolve/main/pika_h3_flex_turbo_4step_fl2va.safetensors"
download loras \
  "https://huggingface.co/Pika-Labs/Pika-H3-Flex-Turbo-LoRA/resolve/main/pika_h3_flex_turbo_4step_fl2va_lite_r32.safetensors"

echo "All model downloads completed."


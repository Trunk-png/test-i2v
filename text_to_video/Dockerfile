ARG CUDA_IMAGE=nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 COMFYUI_DIR=/opt/ComfyUI
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip git curl ca-certificates ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git ${COMFYUI_DIR}
RUN python3 -m pip install --break-system-packages torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu130 && python3 -m pip install --break-system-packages -r ${COMFYUI_DIR}/requirements.txt
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages -r /app/requirements.txt
COPY . /app
RUN git clone --depth 1 https://github.com/Hieunohair/ComfyUI-safety-checker.git ${COMFYUI_DIR}/custom_nodes/ComfyUI-safety-checker \
    && git clone --depth 1 https://github.com/trungnk-png/comfyUI-detect-nsfw-text.git ${COMFYUI_DIR}/custom_nodes/comfyUI-detect-nsfw-text \
    && for req in ${COMFYUI_DIR}/custom_nodes/*/requirements.txt; do [ ! -f "$req" ] || python3 -m pip install --break-system-packages -r "$req"; done
EXPOSE 8000 8188


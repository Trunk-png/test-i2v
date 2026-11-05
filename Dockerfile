ARG CUDA_IMAGE=nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    COMFYUI_DIR=/opt/ComfyUI

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv git curl ca-certificates ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ComfyUI được lấy từ nhánh mới nhất tại thời điểm build ảnh Docker.
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git ${COMFYUI_DIR}
RUN python3 -m pip install --break-system-packages \
      torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cu130 \
    && python3 -m pip install --break-system-packages -r ${COMFYUI_DIR}/requirements.txt

WORKDIR /workspace
COPY requirements-batch.txt /workspace/requirements-batch.txt
RUN python3 -m pip install --break-system-packages -r /workspace/requirements-batch.txt
COPY batch_excel.py entrypoint.sh video_pika_h3_flex_t2v_test.json /workspace/
RUN chmod +x /workspace/entrypoint.sh

EXPOSE 8188
ENTRYPOINT ["/workspace/entrypoint.sh"]


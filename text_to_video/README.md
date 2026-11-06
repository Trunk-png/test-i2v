# Pika H3 Flex — Text-only Web UI

Ứng dụng chỉ nhận prompt text, gửi workflow tới ComfyUI và phát video kết quả ngay trên trình duyệt. Không có upload ảnh và workflow không chứa `LoadImage`/`first_frame`.

## Chạy native

```bash
cd ../image_to_video
./install_comfyui.sh

cd ../text_to_video
COMFYUI_DIR=../image_to_video/ComfyUI ./clone_custom_nodes.sh
MODEL_ROOT=../image_to_video/ComfyUI/models ./download_models.sh
../image_to_video/ComfyUI/run_comfyui.sh
```

Mở terminal thứ hai:

```bash
cd text_to_video
../image_to_video/ComfyUI/.venv/bin/pip install -r requirements.txt
PYTHON_BIN=../image_to_video/ComfyUI/.venv/bin/python ./run_web.sh
```

Truy cập `http://localhost:8000`.

## Chạy Docker

```bash
docker compose build
MODEL_ROOT="$PWD/models" ./download_models.sh
docker compose up
```

Docker image tự clone hai custom node lúc build. Nếu muốn chỉ clone source ra
thư mục local mà chưa cài dependency:

```bash
CUSTOM_NODES_DIR="$PWD/custom_nodes" ./clone_custom_nodes.sh
```

## Text encoder

Workflow trỏ tới `qwen3vl_8b_int8_convrot.safetensors` theo yêu cầu và giữ `CLIPLoader.type=minimax` vì conditioning được đưa vào MiniMax H3. Model Qwen 8B này được phát hành cho Qwen Image 2.1 (`type=qwen_image` trong workflow Qwen), nên khả năng tương thích tensor với MiniMax H3/Pika H3 cần được kiểm tra thực tế. Nếu ComfyUI báo sai kích thước conditioning, dùng lại `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` dành riêng cho MiniMax H3.

Hai custom node được clone bởi `clone_custom_nodes.sh`. Workflow text-only hiện chỉ loại bỏ ảnh và tạo video; muốn nối node kiểm duyệt vào graph cần dùng đúng `class_type` do phiên bản custom node đã clone cung cấp.


# Pika H3 Flex batch cho ComfyUI

Project đọc từng dòng Excel, đưa ảnh và prompt vào workflow ComfyUI, tải video kết quả, upload lên Google Drive với quyền **bất kỳ ai có link đều xem được**, rồi ghi lại Excel gồm thumbnail ảnh, prompt gốc, link video, thời gian và VRAM.

## Cài ComfyUI trực tiếp bằng Bash

Nếu không dùng Docker, chạy script cài đặt:

```bash
chmod +x install_comfyui.sh download.sh
./install_comfyui.sh
```

Script tạo `ComfyUI/.venv`, cài PyTorch CUDA 13, ComfyUI mới nhất và toàn bộ dependencies của batch Excel. Sau khi cài xong:

```bash
MODEL_ROOT="$PWD/ComfyUI/models" ./download.sh
./ComfyUI/run_comfyui.sh
```

Cài vào thư mục khác:

```bash
COMFYUI_DIR=/data/ComfyUI ./install_comfyui.sh
```

## Cấu trúc Excel đầu vào

Hàng 1 cần tối thiểu hai cột:

| prompt | image | duration (không bắt buộc) | seed (không bắt buộc) |
|---|---|---:|---:|
| A person smiles and waves | images/person.jpg | 5 | 12345 |

`image` nhận đường dẫn local (đường dẫn tương đối tính từ thư mục chứa Excel) hoặc URL HTTP/HTTPS. File kết quả giữ nguyên các cột đầu vào và thêm `input_preview`, `video_drive_link`, `video_local_path`, `started_at`, `elapsed_seconds`, `peak_vram_mb`, `vram_delta_mb`, `status`, `error`.

## Chuẩn bị

Yêu cầu máy host có Docker, Docker Compose, NVIDIA driver tương thích CUDA 13 và NVIDIA Container Toolkit.

```bash
mkdir -p models data input output secrets
MODEL_ROOT="$PWD/models" ./download.sh
cp .env.example .env
```

Đặt Excel tại `data/input.xlsx`. Đặt JSON Service Account tại `secrets/google-service-account.json`, bật Google Drive API, rồi chia sẻ thư mục Drive đích cho email của Service Account với quyền Editor. Điền ID thư mục vào `.env` (phần nằm sau `/folders/` trong URL Drive).

> Một số tài khoản Google Workspace cấm quyền chia sẻ công khai. Khi đó API sẽ trả lỗi và project ghi lỗi vào cột `error`; quản trị viên Workspace phải cho phép `anyone with the link`.

## Build và chạy

```bash
docker compose build
docker compose up -d comfyui
docker compose --profile batch run --rm batch
```

Kết quả nằm ở `data/result.xlsx`; video local nằm trong `generated_videos` bên trong container theo mặc định. Khi chạy bằng Compose nên đổi command để lưu vào volume `/data/videos`:

```bash
docker compose --profile batch run --rm batch \
  --input /data/input.xlsx \
  --output /data/result.xlsx \
  --workflow /workspace/video_pika_h3_flex_t2v_test.json \
  --download-dir /data/videos
```

Chạy không upload Drive (hữu ích để thử luồng):

```bash
docker compose --profile batch run --rm batch \
  --input /data/input.xlsx --output /data/result.xlsx \
  --workflow /workspace/video_pika_h3_flex_t2v_test.json \
  --download-dir /data/videos --skip-drive
```

ComfyUI mở tại `http://localhost:8188`. `Dockerfile` clone nhánh ComfyUI mới nhất tại thời điểm build. Muốn cập nhật về bản mới nhất sau này, chạy `docker compose build --no-cache`.

## Lưu ý VRAM

`peak_vram_mb` là tổng VRAM cao nhất do `nvidia-smi` báo trên tất cả GPU trong lúc render; `vram_delta_mb` là phần tăng so với ngay trước job. Nếu GPU đang chạy tiến trình khác, số này cũng bao gồm tiến trình đó. Model trong workflow khá lớn, cần kiểm tra dung lượng ổ đĩa và VRAM trước khi chạy thực tế.


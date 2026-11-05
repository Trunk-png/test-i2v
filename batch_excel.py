#!/usr/bin/env python3
"""Chạy workflow ComfyUI từ từng dòng Excel và xuất kết quả lên Drive/Excel."""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import requests
from google.auth import default as google_auth_default
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from PIL import Image as PILImage


INPUT_ALIASES = {
    "prompt": ("prompt", "prompts", "mô tả", "mo ta"),
    "image": ("image", "ảnh", "anh", "image_path", "image_url"),
    "duration": ("duration", "seconds", "thời lượng", "thoi luong"),
    "seed": ("seed",),
}
RESULT_HEADERS = (
    "input_preview",
    "video_drive_link",
    "video_local_path",
    "started_at",
    "elapsed_seconds",
    "peak_vram_mb",
    "vram_delta_mb",
    "status",
    "error",
)


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Excel -> ComfyUI -> Google Drive -> Excel")
    parser.add_argument("--input", required=True, type=Path, help="File Excel đầu vào")
    parser.add_argument("--output", required=True, type=Path, help="File Excel kết quả")
    parser.add_argument("--workflow", required=True, type=Path, help="Workflow dạng API JSON")
    parser.add_argument("--sheet", help="Tên sheet; mặc định dùng sheet đang active")
    parser.add_argument("--comfy-url", default=os.getenv("COMFY_URL", "http://127.0.0.1:8188"))
    parser.add_argument("--drive-folder-id", default=os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""))
    parser.add_argument("--credentials", type=Path, default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    parser.add_argument("--download-dir", type=Path, default=Path("generated_videos"))
    parser.add_argument("--timeout", type=int, default=3600, help="Timeout mỗi video, đơn vị giây")
    parser.add_argument("--skip-drive", action="store_true", help="Chỉ lưu video local, không upload Drive")
    return parser.parse_args()


def normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def column_map(ws) -> dict[str, int]:
    headers = {normalized(cell.value): cell.column for cell in ws[1] if cell.value is not None}
    found: dict[str, int] = {}
    for field, aliases in INPUT_ALIASES.items():
        for alias in aliases:
            if normalized(alias) in headers:
                found[field] = headers[normalized(alias)]
                break
    missing = [name for name in ("prompt", "image") if name not in found]
    if missing:
        raise ValueError(f"Thiếu cột bắt buộc: {', '.join(missing)}. Cần tối thiểu prompt và image.")
    return found


def result_columns(ws) -> dict[str, int]:
    headers = {normalized(cell.value): cell.column for cell in ws[1] if cell.value is not None}
    result: dict[str, int] = {}
    for name in RESULT_HEADERS:
        key = normalized(name)
        if key not in headers:
            col = ws.max_column + 1
            ws.cell(1, col, name)
            headers[key] = col
        result[name] = headers[key]
    return result


def fetch_image(source: str, work_dir: Path, base_dir: Path) -> Path:
    parsed = urlparse(source)
    if parsed.scheme in ("http", "https"):
        suffix = Path(parsed.path).suffix or ".jpg"
        target = work_dir / f"input{suffix}"
        with requests.get(source, stream=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as stream:
                shutil.copyfileobj(response.raw, stream)
        return target
    path = Path(source).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh: {path}")
    return path


def upload_comfy_image(base_url: str, image_path: Path) -> str:
    with image_path.open("rb") as stream:
        response = requests.post(
            f"{base_url}/upload/image",
            files={"image": (image_path.name, stream, mimetypes.guess_type(image_path)[0] or "image/jpeg")},
            data={"overwrite": "true", "type": "input"},
            timeout=180,
        )
    response.raise_for_status()
    body = response.json()
    return "/".join(part for part in (body.get("subfolder"), body["name"]) if part)


def configure_workflow(template: dict[str, Any], prompt: str, image_name: str, row: int,
                       duration: Any = None, seed: Any = None) -> dict[str, Any]:
    workflow = copy.deepcopy(template)
    matched_prompt = matched_image = False
    for node in workflow.values():
        node_type = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if node_type == "LoadImage" and "image" in inputs:
            inputs["image"] = image_name
            matched_image = True
        if node_type == "MiniMaxH3ImageToVideo" and "prompt" in inputs:
            inputs["prompt"] = prompt
            matched_prompt = True
        if duration not in (None, "") and node_type == "PrimitiveFloat" and "value" in inputs:
            inputs["value"] = float(duration)
        if seed not in (None, "") and node_type == "RandomNoise" and "noise_seed" in inputs:
            inputs["noise_seed"] = int(seed)
        if node_type == "SaveVideo" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = f"video/pika_row_{row}_{int(time.time())}"
    if not (matched_prompt and matched_image):
        raise ValueError("Workflow không có node LoadImage/MiniMaxH3ImageToVideo cần thiết")
    return workflow


def gpu_used_mb() -> int | None:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return sum(int(line.strip()) for line in output.splitlines() if line.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class VramMonitor:
    def __init__(self) -> None:
        self.baseline = gpu_used_mb()
        self.peak = self.baseline
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            value = gpu_used_mb()
            if value is not None and (self.peak is None or value > self.peak):
                self.peak = value

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_args):
        self._stop.set()
        self._thread.join(timeout=2)


def queue_and_wait(base_url: str, workflow: dict[str, Any], timeout: int) -> dict[str, Any]:
    client_id = str(uuid.uuid4())
    response = requests.post(
        f"{base_url}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=60
    )
    response.raise_for_status()
    body = response.json()
    if body.get("node_errors"):
        raise RuntimeError(f"ComfyUI từ chối workflow: {json.dumps(body['node_errors'], ensure_ascii=False)}")
    prompt_id = body["prompt_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        history_response = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
        history_response.raise_for_status()
        history = history_response.json().get(prompt_id)
        if history:
            status = history.get("status", {})
            if status.get("status_str") == "error" or status.get("completed") is False:
                messages = status.get("messages", [])
                raise RuntimeError(f"ComfyUI render lỗi: {json.dumps(messages, ensure_ascii=False)}")
            if status.get("completed") or history.get("outputs"):
                return history
        time.sleep(2)
    raise TimeoutError(f"Quá thời gian chờ ComfyUI ({timeout}s), prompt_id={prompt_id}")


def video_descriptor(history: dict[str, Any]) -> dict[str, str]:
    for node_output in history.get("outputs", {}).values():
        for key in ("videos", "video", "gifs", "images", "files"):
            candidates = node_output.get(key, [])
            if isinstance(candidates, dict):
                candidates = [candidates]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                filename = str(item.get("filename", ""))
                if filename.lower().endswith((".mp4", ".webm", ".mov", ".mkv", ".gif")):
                    return item
    raise RuntimeError("ComfyUI hoàn thành nhưng history không chứa file video")


def download_output(base_url: str, descriptor: dict[str, str], destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    filename = Path(descriptor["filename"]).name
    target = destination / filename
    query = urlencode({
        "filename": descriptor["filename"],
        "subfolder": descriptor.get("subfolder", ""),
        "type": descriptor.get("type", "output"),
    })
    with requests.get(f"{base_url}/view?{query}", stream=True, timeout=600) as response:
        response.raise_for_status()
        with target.open("wb") as stream:
            shutil.copyfileobj(response.raw, stream)
    return target


def drive_service(credentials_path: Path | None):
    scopes = ["https://www.googleapis.com/auth/drive"]
    if credentials_path:
        credentials = service_account.Credentials.from_service_account_file(str(credentials_path), scopes=scopes)
    else:
        credentials, _ = google_auth_default(scopes=scopes)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def upload_public_video(service, video: Path, folder_id: str) -> str:
    metadata: dict[str, Any] = {"name": video.name}
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaFileUpload(str(video), mimetype=mimetypes.guess_type(video)[0] or "video/mp4", resumable=True)
    created = service.files().create(
        body=metadata,
        media_body=media,
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()
    service.permissions().create(
        fileId=created["id"],
        body={"type": "anyone", "role": "reader", "allowFileDiscovery": False},
        supportsAllDrives=True,
        fields="id",
    ).execute()
    info = service.files().get(fileId=created["id"], fields="webViewLink", supportsAllDrives=True).execute()
    return info.get("webViewLink") or f"https://drive.google.com/file/d/{created['id']}/view"


def add_thumbnail(ws, row: int, column: int, source: Path, temp_dir: Path) -> None:
    thumb_path = temp_dir / f"thumb_{row}.png"
    with PILImage.open(source) as image:
        image.thumbnail((160, 100))
        image.convert("RGB").save(thumb_path, "PNG")
    picture = ExcelImage(str(thumb_path))
    picture.width, picture.height = 160, 100
    ws.add_image(picture, ws.cell(row, column).coordinate)
    ws.row_dimensions[row].height = 78
    ws.column_dimensions[ws.cell(1, column).column_letter].width = 24


def main() -> int:
    args = cli()
    args.comfy_url = args.comfy_url.rstrip("/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.download_dir.mkdir(parents=True, exist_ok=True)
    with args.workflow.open(encoding="utf-8") as stream:
        workflow_template = json.load(stream)
    workbook = load_workbook(args.input)
    ws = workbook[args.sheet] if args.sheet else workbook.active
    inputs = column_map(ws)
    outputs = result_columns(ws)
    drive = None if args.skip_drive else drive_service(args.credentials)

    with tempfile.TemporaryDirectory(prefix="pika_batch_") as temp_name:
        temp_dir = Path(temp_name)
        for row in range(2, ws.max_row + 1):
            prompt = str(ws.cell(row, inputs["prompt"]).value or "").strip()
            source = str(ws.cell(row, inputs["image"]).value or "").strip()
            if not prompt and not source:
                continue
            report_timezone = os.getenv("REPORT_TIMEZONE", "Asia/Ho_Chi_Minh")
            started_text = datetime.now(ZoneInfo(report_timezone)).isoformat(timespec="seconds")
            started = time.monotonic()
            status = "error"
            error = ""
            peak = delta = None
            try:
                if not prompt or not source:
                    raise ValueError("Dòng phải có cả prompt và image")
                row_dir = temp_dir / f"row_{row}"
                row_dir.mkdir()
                image_path = fetch_image(source, row_dir, args.input.resolve().parent)
                add_thumbnail(ws, row, outputs["input_preview"], image_path, temp_dir)
                comfy_image = upload_comfy_image(args.comfy_url, image_path)
                workflow = configure_workflow(
                    workflow_template,
                    prompt,
                    comfy_image,
                    row,
                    ws.cell(row, inputs["duration"]).value if "duration" in inputs else None,
                    ws.cell(row, inputs["seed"]).value if "seed" in inputs else None,
                )
                with VramMonitor() as monitor:
                    history = queue_and_wait(args.comfy_url, workflow, args.timeout)
                peak = monitor.peak
                delta = None if peak is None or monitor.baseline is None else max(0, peak - monitor.baseline)
                local_video = download_output(args.comfy_url, video_descriptor(history), args.download_dir)
                link = "" if drive is None else upload_public_video(drive, local_video, args.drive_folder_id)
                ws.cell(row, outputs["video_local_path"], str(local_video.resolve()))
                ws.cell(row, outputs["video_drive_link"], link)
                if link:
                    ws.cell(row, outputs["video_drive_link"]).hyperlink = link
                    ws.cell(row, outputs["video_drive_link"]).style = "Hyperlink"
                status = "success"
            except Exception as exc:  # tiếp tục xử lý các dòng sau
                error = f"{type(exc).__name__}: {exc}"
                print(f"[row {row}] ERROR {error}", flush=True)
            elapsed = round(time.monotonic() - started, 2)
            ws.cell(row, outputs["started_at"], started_text)
            ws.cell(row, outputs["elapsed_seconds"], elapsed)
            ws.cell(row, outputs["peak_vram_mb"], peak)
            ws.cell(row, outputs["vram_delta_mb"], delta)
            ws.cell(row, outputs["status"], status)
            ws.cell(row, outputs["error"], error)
            workbook.save(args.output)
            print(f"[row {row}] {status} ({elapsed}s)", flush=True)
    workbook.save(args.output)
    print(f"Đã ghi kết quả: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


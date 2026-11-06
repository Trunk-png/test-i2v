#!/usr/bin/env python3
"""Web UI text-to-video backed by a local ComfyUI server."""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
WORKFLOW_PATH = Path(os.getenv("WORKFLOW_PATH", ROOT / "workflow_text_only.json"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", ROOT / "outputs"))
COMFY_URL = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "7200"))

app = FastAPI(title="Pika Text to Video", docs_url="/api/docs", redoc_url=None)
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
gpu_queue = threading.Semaphore(1)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    duration: float = Field(default=5, ge=1, le=15)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "success", "error"]
    progress: int
    message: str
    created_at: float
    elapsed_seconds: float | None = None
    video_url: str | None = None


def update_job(job_id: str, **values: Any) -> None:
    with jobs_lock:
        jobs[job_id].update(values)


def configure_workflow(prompt: str, duration: float, seed: int, job_id: str) -> dict[str, Any]:
    with WORKFLOW_PATH.open(encoding="utf-8") as stream:
        workflow = copy.deepcopy(json.load(stream))
    prompt_set = False
    for node in workflow.values():
        node_type = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if node_type == "LoadImage" or "image" in inputs:
            raise RuntimeError("Workflow text-only không được chứa node/đầu vào ảnh")
        if node_type == "MiniMaxH3ImageToVideo" and "prompt" in inputs:
            inputs["prompt"] = prompt
            inputs.pop("first_frame", None)
            inputs.pop("last_frame", None)
            prompt_set = True
        elif "prompt" in inputs and isinstance(inputs["prompt"], str):
            inputs["prompt"] = prompt
            prompt_set = True
        if node_type == "PrimitiveFloat" and "value" in inputs:
            inputs["value"] = duration
        if node_type == "RandomNoise" and "noise_seed" in inputs:
            inputs["noise_seed"] = seed
        if node_type == "SaveVideo" and "filename_prefix" in inputs:
            inputs["filename_prefix"] = f"text-ui/{job_id}"
    if not prompt_set:
        raise RuntimeError("Không tìm thấy trường prompt trong workflow")
    return workflow


def find_video(history: dict[str, Any]) -> dict[str, str]:
    for output in history.get("outputs", {}).values():
        for key in ("videos", "video", "gifs", "images", "files"):
            values = output.get(key, [])
            if isinstance(values, dict):
                values = [values]
            for value in values:
                if not isinstance(value, dict):
                    continue
                name = str(value.get("filename", ""))
                if name.lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
                    return value
    raise RuntimeError("ComfyUI hoàn tất nhưng không trả về file video")


def render_job(job_id: str, request: GenerateRequest) -> None:
    started = time.monotonic()
    try:
        with gpu_queue:
            update_job(job_id, status="running", progress=8, message="Đang chuẩn bị workflow")
            seed = request.seed if request.seed is not None else uuid.uuid4().int % (2**63)
            workflow = configure_workflow(request.prompt.strip(), request.duration, seed, job_id)
            response = requests.post(
                f"{COMFY_URL}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())},
                timeout=60,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("node_errors"):
                raise RuntimeError(json.dumps(body["node_errors"], ensure_ascii=False))
            prompt_id = body["prompt_id"]
            update_job(job_id, progress=15, message="Đã vào hàng đợi ComfyUI", prompt_id=prompt_id)

            deadline = time.monotonic() + JOB_TIMEOUT
            pulse = 15
            history = None
            while time.monotonic() < deadline:
                response = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=30)
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise RuntimeError(json.dumps(status.get("messages", []), ensure_ascii=False))
                    if status.get("completed") or history.get("outputs"):
                        break
                pulse = min(88, pulse + 1)
                update_job(job_id, progress=pulse, message="Đang tạo video trên GPU")
                time.sleep(2)
            else:
                raise TimeoutError(f"Quá thời gian chờ {JOB_TIMEOUT} giây")

            descriptor = find_video(history or {})
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            suffix = Path(descriptor["filename"]).suffix or ".mp4"
            target = OUTPUT_DIR / f"{job_id}{suffix}"
            query = urlencode({
                "filename": descriptor["filename"],
                "subfolder": descriptor.get("subfolder", ""),
                "type": descriptor.get("type", "output"),
            })
            with requests.get(f"{COMFY_URL}/view?{query}", stream=True, timeout=900) as response:
                response.raise_for_status()
                with target.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
            update_job(
                job_id,
                status="success",
                progress=100,
                message="Video đã sẵn sàng",
                elapsed_seconds=round(time.monotonic() - started, 2),
                video_path=str(target),
                video_url=f"/api/jobs/{job_id}/video",
            )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            progress=100,
            message=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=round(time.monotonic() - started, 2),
        )


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        response = requests.get(f"{COMFY_URL}/system_stats", timeout=5)
        comfy_ready = response.ok
    except requests.RequestException:
        comfy_ready = False
    return {"ok": True, "comfyui": comfy_ready, "workflow": WORKFLOW_PATH.name}


@app.post("/api/generate", response_model=JobResponse, status_code=202)
def generate(request: GenerateRequest) -> dict[str, Any]:
    prompt = request.prompt.strip()
    if len(prompt) < 3:
        raise HTTPException(422, "Prompt quá ngắn")
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "queued",
        "progress": 2,
        "message": "Đang chờ GPU",
        "created_at": time.time(),
        "elapsed_seconds": None,
        "video_url": None,
    }
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=render_job, args=(job_id, request), daemon=True).start()
    return job


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> dict[str, Any]:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Không tìm thấy job")
        return dict(job)


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "success":
            raise HTTPException(404, "Video chưa sẵn sàng")
        path = Path(job["video_path"])
    return FileResponse(path, media_type="video/mp4", filename=path.name)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="site")


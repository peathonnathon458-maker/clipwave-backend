import os
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_MB = 100
MAX_CLIP_SECONDS = 120


@app.get("/")
def home():
    return {"status": "Clipwave backend is running"}


@app.post("/clip")
def clip(
    video: UploadFile = File(...),
    start: float = Form(...),
    end: float = Form(...),
):
    if start < 0 or end <= start:
        raise HTTPException(400, "End time must be after start time.")
    if end - start > MAX_CLIP_SECONDS:
        raise HTTPException(400, f"Clips can be at most {MAX_CLIP_SECONDS} seconds.")

    work_dir = tempfile.mkdtemp()
    ext = os.path.splitext(video.filename or "")[1] or ".mp4"
    src = os.path.join(work_dir, f"in_{uuid.uuid4().hex}{ext}")
    out = os.path.join(work_dir, "clip.mp4")

    with open(src, "wb") as f:
        shutil.copyfileobj(video.file, f)

    if os.path.getsize(src) > MAX_UPLOAD_MB * 1024 * 1024:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(413, f"File too big. Max {MAX_UPLOAD_MB} MB.")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", src,
        "-t", str(end - start),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-movflags", "+faststart",
        out,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(504, "Rendering took too long.")

    if result.returncode != 0 or not os.path.exists(out):
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(500, "Could not render this video.")

    return FileResponse(
        out,
        media_type="video/mp4",
        filename="clipwave-clip.mp4",
        background=BackgroundTask(shutil.rmtree, work_dir, True),
)

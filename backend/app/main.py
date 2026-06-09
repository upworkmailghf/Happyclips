from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import requests
from backend.app.moments import (
    clamp_moments,
    dedupe_moments,
    fallback_moments,
    normalize_transcript,
    parse_ai_moments,
)
from flask import Flask, Response, jsonify, request, send_file, send_from_directory

DATA_DIR = Path(os.getenv("HAPPYCLIPS_DATA_DIR", APP_ROOT / "data"))
DOWNLOAD_DIR = DATA_DIR / "downloads"
OUTPUT_DIR = DATA_DIR / "output"
FRONTEND_DIR = APP_ROOT / "frontend"
AI_ENDPOINT = os.getenv(
    "HAPPYCLIPS_AI_ENDPOINT",
    "https://devtoolbox-api.devtoolbox-api.workers.dev/ai/generate",
)
TARGET_CLIP_COUNT = int(os.getenv("HAPPYCLIPS_CLIP_COUNT", "3"))
MIN_CLIP_SECONDS = float(os.getenv("HAPPYCLIPS_MIN_CLIP_SECONDS", "0"))
MAX_CLIP_SECONDS = float(os.getenv("HAPPYCLIPS_MAX_CLIP_SECONDS", "25"))
PROCESS_RATE_LIMIT_SECONDS = int(os.getenv("HAPPYCLIPS_RATE_LIMIT_SECONDS", "60"))

for directory in (DOWNLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


@dataclass
class JobState:
    job_id: str
    status: str = "processing"
    step: str = "queued"
    progress: int = 0
    detail: str = "Waiting to start"
    clips: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=lambda: ["Job queued"])
    error: str | None = None


jobs: dict[str, JobState] = {}
process_attempts: dict[str, float] = {}
state_lock = threading.Lock()

app = Flask(
    __name__,
    static_folder=str(FRONTEND_DIR),
    static_url_path="",
)


@app.after_request
def add_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.get("/")
def index() -> Response:
    return send_file(FRONTEND_DIR / "index.html")


@app.get("/app.js")
def app_js() -> Response:
    return send_file(FRONTEND_DIR / "app.js")


@app.get("/styles.css")
def styles() -> Response:
    return send_file(FRONTEND_DIR / "styles.css")


@app.get("/output/<job_id>/<path:filename>")
def output_file(job_id: str, filename: str) -> Response:
    return send_from_directory(OUTPUT_DIR / job_id, filename)


@app.post("/process")
def process_video() -> tuple[Response, int] | Response:
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not is_supported_url(url):
        return jsonify({"detail": "Please enter a valid YouTube URL."}), 400

    limited = rate_limit_response(client_key())
    if limited is not None:
        return limited

    job_id = uuid.uuid4().hex[:12]
    with state_lock:
        jobs[job_id] = JobState(job_id=job_id)

    thread = threading.Thread(target=run_pipeline, args=(job_id, url), daemon=True)
    thread.start()
    return jsonify(get_serialized_job(job_id))


@app.get("/status/<job_id>")
def job_status(job_id: str) -> tuple[Response, int] | Response:
    job = get_serialized_job(job_id)
    if job is None:
        return jsonify({"detail": "Job not found"}), 404
    return jsonify(job)


def is_supported_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower().removeprefix("www.")
    return host in {"youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}


def client_key() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded_for or request.remote_addr or "local"


def rate_limit_response(key: str) -> tuple[Response, int] | None:
    now = time.monotonic()
    with state_lock:
        last_attempt = process_attempts.get(key)
        if last_attempt is not None and now - last_attempt < PROCESS_RATE_LIMIT_SECONDS:
            retry_after = max(1, int(PROCESS_RATE_LIMIT_SECONDS - (now - last_attempt)))
            response = jsonify({"detail": f"Please wait {retry_after} seconds before starting another video."})
            response.headers["Retry-After"] = str(retry_after)
            return response, 429
        process_attempts[key] = now
    return None


def get_serialized_job(job_id: str) -> dict[str, Any] | None:
    with state_lock:
        job = jobs.get(job_id)
        return serialize_job(job) if job else None


def serialize_job(job: JobState) -> dict[str, Any]:
    payload = asdict(job)
    payload["clips"] = job.clips
    return payload


def update_job(job_id: str, step: str, detail: str, progress: int) -> None:
    with state_lock:
        job = jobs[job_id]
        job.step = step
        job.detail = detail
        job.progress = progress
        job.log.append(detail)


def run_pipeline(job_id: str, url: str) -> None:
    try:
        job_dir = DATA_DIR / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        update_job(job_id, "downloading", "Fetching video via yt-dlp", 10)
        video_path = download_video(url, job_dir)

        update_job(job_id, "processing_video", "Validating and preparing video", 25)
        prepared_video = prepare_video(video_path, job_dir)

        update_job(job_id, "transcription", "AI is analyzing video audio", 50)
        transcript = transcribe_video(prepared_video, job_dir)

        update_job(job_id, "ai_analysis", "Finding viral moments", 70)
        moments = select_moments(transcript)

        update_job(job_id, "cutting_clips", "Rendering short clips", 90)
        clips = render_clips(prepared_video, moments, job_id)

        with state_lock:
            job = jobs[job_id]
            job.status = "completed"
            job.step = "completed"
            job.detail = f"Generated {len(clips)} clips"
            job.progress = 100
            job.clips = clips
            job.log.append("Clips ready")
    except Exception as exc:  # noqa: BLE001 - user-facing job failures should be captured.
        with state_lock:
            job = jobs[job_id]
            job.status = "failed"
            job.step = "failed"
            job.detail = "Processing failed"
            job.error = str(exc)
            job.log.append(f"Error: {exc}")


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required command not found: {name}")
    return path


def download_video(url: str, job_dir: Path) -> Path:
    require_binary("yt-dlp")
    output_template = str(job_dir / "source.%(ext)s")
    command = [
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "-f",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "-o",
        output_template,
        url,
    ]
    run_command(command)
    candidates = sorted(job_dir.glob("source.*"))
    if not candidates:
        raise RuntimeError("yt-dlp did not produce a video file")
    return candidates[0]


def prepare_video(video_path: Path, job_dir: Path) -> Path:
    require_binary("ffmpeg")
    require_binary("ffprobe")
    run_command(["ffprobe", "-v", "error", "-show_format", "-show_streams", str(video_path)])
    prepared = job_dir / "video.mp4"
    if video_path.suffix.lower() == ".mp4":
        shutil.copyfile(video_path, prepared)
        return prepared
    run_command([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(prepared),
    ])
    return prepared


def transcribe_video(video_path: Path, job_dir: Path) -> list[dict[str, Any]]:
    audio_path = job_dir / "audio.wav"
    run_command([
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ])

    whisper_command = os.getenv("HAPPYCLIPS_WHISPER_COMMAND")
    if whisper_command:
        transcript_path = job_dir / "transcript.json"
        command = whisper_command.format(audio=str(audio_path), output=str(transcript_path))
        subprocess.run(command, shell=True, check=True)  # noqa: S602 - explicit local operator command.
        return normalize_transcript(json.loads(transcript_path.read_text()))

    try:
        import whisper  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Whisper is not installed. Install it only if your phone can handle it, or set HAPPYCLIPS_WHISPER_COMMAND to a whisper.cpp command."
        ) from exc

    model_name = os.getenv("HAPPYCLIPS_WHISPER_MODEL", "base")
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path))
    segments = normalize_transcript(result.get("segments", []))
    (job_dir / "transcript.json").write_text(json.dumps(segments, indent=2))
    return segments


def select_moments(transcript: list[dict[str, Any]]) -> list[dict[str, float]]:
    transcript_text = "\n".join(
        f"[{item['start']:.1f}-{item['end']:.1f}] {item['text']}" for item in transcript
    )
    prompt = (
        "Extract exactly 3 viral short-form video moments. Return ONLY JSON array "
        f"with start and end timestamps. Clips can be any length up to {MAX_CLIP_SECONDS:g} seconds, "
        "should not be padded, must contain complete ideas, and should be ordered "
        "from strongest to weakest. Transcript:\n"
        f"{transcript_text[:12000]}"
    )
    try:
        response = requests.post(
            AI_ENDPOINT,
            json={"prompt": prompt, "max_tokens": 500},
            timeout=60,
        )
        response.raise_for_status()
        moments = parse_ai_moments(response.text)
    except (requests.RequestException, ValueError, json.JSONDecodeError):
        moments = []

    valid = clamp_moments(moments, transcript, MIN_CLIP_SECONDS, MAX_CLIP_SECONDS)
    if len(valid) < TARGET_CLIP_COUNT:
        valid.extend(fallback_moments(transcript, TARGET_CLIP_COUNT - len(valid), MIN_CLIP_SECONDS))
    return dedupe_moments(valid)[:TARGET_CLIP_COUNT]


def render_clips(video_path: Path, moments: list[dict[str, float]], job_id: str) -> list[str]:
    if not moments:
        raise RuntimeError("No clip moments were selected")
    job_output = OUTPUT_DIR / job_id
    job_output.mkdir(parents=True, exist_ok=True)
    clip_urls: list[str] = []
    for index, moment in enumerate(moments[:TARGET_CLIP_COUNT], start=1):
        clip_path = job_output / f"clip{index}.mp4"
        run_command([
            "ffmpeg",
            "-y",
            "-ss",
            str(moment["start"]),
            "-to",
            str(moment["end"]),
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(clip_path),
        ])
        clip_urls.append(f"/output/{job_id}/{clip_path.name}")
    return clip_urls


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), threaded=True)

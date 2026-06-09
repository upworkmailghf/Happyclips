# Happyclips

Happyclips is a lightweight localhost AI video clipping app designed to run in Termux on Android. Paste a YouTube URL, watch each processing stage update in real time, and receive 3 downloadable short-form clips.

## Features

- FastAPI backend with `/process` and `/status/{job_id}` endpoints.
- Vanilla HTML/CSS/JS frontend with progress bar, status steps, activity log, error modal, and clip results grid.
- `yt-dlp` download pipeline for YouTube links.
- FFmpeg validation, audio extraction, conversion, and clip rendering.
- Whisper transcription with timestamped segments.
- AI moment detection through `https://devtoolbox-api.devtoolbox-api.workers.dev/ai/generate`.
- Fallback moment selection so the pipeline still tries to create 3 clips when AI output is malformed or unavailable.
- One-minute `/process` rate limit per client to keep phone CPU, storage, and battery usage predictable.

## Termux setup

```bash
pkg update
pkg install python ffmpeg
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Install `yt-dlp` if it is not already available:

```bash
pip install -U yt-dlp
```

> Whisper can be heavy on phones. The default uses `openai-whisper` with the `base` model. For a lighter custom CLI, set `HAPPYCLIPS_WHISPER_COMMAND` to a command that writes transcript JSON with `start`, `end`, and `text` fields.
>
> I am not adding `auto-editor` by default: it is useful for silence removal, but this app already uses FFmpeg for exact cuts and Whisper+AI for semantic moment selection. Adding another media package would make Termux installs heavier without improving the core viral-moment workflow. You can still run auto-editor manually before/after Happyclips if you specifically want silence compression.

Example custom command:

```bash
export HAPPYCLIPS_WHISPER_COMMAND='whisper-cli -f {audio} --output-json {output}'
```

## Run locally

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your Android browser.

## API

### `POST /process`

```json
{
  "url": "https://youtube.com/watch?v=..."
}
```

Returns a queued job:

```json
{
  "job_id": "abc123",
  "status": "processing",
  "step": "queued",
  "progress": 0,
  "detail": "Waiting to start",
  "clips": [],
  "log": ["Job queued"],
  "error": null
}
```

### `GET /status/{job_id}`

Returns live progress and final clip URLs:

```json
{
  "job_id": "abc123",
  "status": "completed",
  "step": "completed",
  "progress": 100,
  "detail": "Generated 3 clips",
  "clips": [
    "/output/abc123/clip1.mp4",
    "/output/abc123/clip2.mp4",
    "/output/abc123/clip3.mp4"
  ]
}
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HAPPYCLIPS_AI_ENDPOINT` | DevToolbox AI endpoint | AI timestamp selector endpoint. |
| `HAPPYCLIPS_CLIP_COUNT` | `3` | Number of clips to render per video. |
| `HAPPYCLIPS_MIN_CLIP_SECONDS` | `0` | Optional minimum clip duration. The default does not pad short complete ideas. |
| `HAPPYCLIPS_MAX_CLIP_SECONDS` | `25` | Maximum clip duration; clips can be shorter. |
| `HAPPYCLIPS_WHISPER_MODEL` | `base` | `openai-whisper` model name. |
| `HAPPYCLIPS_WHISPER_COMMAND` | unset | Optional external whisper/whisper.cpp command. |
| `HAPPYCLIPS_RATE_LIMIT_SECONDS` | `60` | Per-client cooldown between `/process` requests. |
| `HAPPYCLIPS_DATA_DIR` | `./data` | Working directory for jobs and output. |

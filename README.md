# Happyclips

Happyclips is a small local web app for Android + Termux. You paste a YouTube link, the app downloads the video, transcribes it, asks AI for the best moments, and gives you 3 short clips to download.

This version uses **Flask instead of FastAPI/Pydantic** because Flask is lighter on Termux. FastAPI uses Pydantic, and Pydantic can force Rust/clang builds on some Android phones. That can take a lot of storage. Flask avoids that heavy web stack.

## What the app does

1. You open the app in your phone browser.
2. You paste a YouTube link.
3. The backend downloads the video with `yt-dlp`.
4. FFmpeg checks/prepares the video.
5. Whisper or whisper.cpp makes a timestamped transcript.
6. The AI endpoint picks viral moments from the transcript.
7. FFmpeg cuts up to 3 clips.
8. The page shows the clips with preview and download buttons.

## Important notes before installing

- You still need **FFmpeg** because it cuts the video clips.
- You still need **yt-dlp** because it downloads YouTube videos.
- The included `backend/requirements.txt` is intentionally light: Flask, requests, yt-dlp, and pytest.
- `openai-whisper` is **not installed by default** because it can be heavy on phones. Use whisper.cpp if possible, or manually install `openai-whisper` if your phone can handle it.
- The app has a 1-minute limit between new `/process` requests so your phone does not get overloaded.
- Clips do **not** have to be 25 seconds. They can be shorter. The default only caps clips at 25 seconds.

## Install on Termux, step by step

### 1. Install phone packages

Open Termux and run:

```bash
pkg update
pkg install python ffmpeg
```

### 2. Create a Python environment

From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the start of your Termux prompt after activating it.

### 3. Install the lightweight Python requirements

```bash
pip install -r backend/requirements.txt
```

If YouTube downloads stop working later, update yt-dlp:

```bash
pip install -U yt-dlp
```

## Transcription setup

The app needs a transcript before AI can pick clips. You have two choices.

### Option A: lighter phone setup with whisper.cpp

This is the recommended Android idea. Set `HAPPYCLIPS_WHISPER_COMMAND` to a command that creates a JSON transcript file. The command can use two placeholders:

- `{audio}` = the WAV audio file Happyclips creates
- `{output}` = where your command should write transcript JSON

Example shape:

```bash
export HAPPYCLIPS_WHISPER_COMMAND='your-whisper-command {audio} {output}'
```

The JSON should contain segments like this:

```json
[
  { "start": 10.2, "end": 15.6, "text": "what was said here" }
]
```

### Option B: heavier Python Whisper setup

Only do this if your phone has enough storage and the install works:

```bash
pip install openai-whisper
```

Then Happyclips will use Python Whisper automatically if `HAPPYCLIPS_WHISPER_COMMAND` is not set.

## Run the app

From the project folder with `.venv` activated:

```bash
python backend/app/main.py
```

Then open this in your Android browser:

```text
http://127.0.0.1:8000
```

## How to use it

1. Paste a YouTube URL into the box.
2. Tap **Generate**.
3. Wait while the progress screen shows each step.
4. When finished, download the 3 clips from the results screen.

## API, if you want to test manually

### Start a job

```http
POST /process
Content-Type: application/json
```

Body:

```json
{
  "url": "https://youtube.com/watch?v=..."
}
```

Response:

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

### Check progress

```http
GET /status/abc123
```

Finished response example:

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

## Settings you can change

You can set these before running the app:

| Variable | Default | What it means |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Server host. Keep this for local phone use. |
| `PORT` | `8000` | Server port. |
| `HAPPYCLIPS_AI_ENDPOINT` | DevToolbox AI endpoint | AI timestamp selector endpoint. |
| `HAPPYCLIPS_CLIP_COUNT` | `3` | Number of clips to render per video. |
| `HAPPYCLIPS_MIN_CLIP_SECONDS` | `0` | Optional minimum clip duration. Default means no padding. |
| `HAPPYCLIPS_MAX_CLIP_SECONDS` | `25` | Maximum clip duration. Clips can be shorter. |
| `HAPPYCLIPS_WHISPER_MODEL` | `base` | Python Whisper model name, only used if Python Whisper is installed. |
| `HAPPYCLIPS_WHISPER_COMMAND` | unset | Optional whisper.cpp/custom transcript command. |
| `HAPPYCLIPS_RATE_LIMIT_SECONDS` | `60` | Wait time between starting new videos. |
| `HAPPYCLIPS_DATA_DIR` | `./data` | Folder for temporary jobs and final clips. |

Example:

```bash
export HAPPYCLIPS_RATE_LIMIT_SECONDS=30
python backend/app/main.py
```

## Why auto-editor is not installed by default

`auto-editor` is useful when you want to remove silence automatically. Happyclips already uses FFmpeg for exact cuts and Whisper + AI for finding meaningful moments. Adding auto-editor by default would make the phone install heavier. You can still use it manually before or after Happyclips if silence removal is important to you.

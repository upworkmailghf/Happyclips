# Happyclips

Happyclips is a small local web app for Android + Termux. You paste a YouTube link, the app downloads the video, transcribes it, asks AI for the best moments, and gives you 3 short clips to download.

This version uses **Flask instead of FastAPI/Pydantic** because Flask is lighter on Termux. FastAPI uses Pydantic, and Pydantic can force Rust/clang builds on some Android phones. That can take a lot of storage. Flask avoids that heavy web stack.

## What the app does

1. You open the app in your phone browser.
2. You paste a YouTube link.
3. The backend first asks `yt-dlp` for YouTube captions/transcripts without downloading the video.
4. If captions exist, AI uses those timestamps immediately. This is fastest and saves data.
5. If captions do not exist, the backend downloads audio only and uses Whisper/whisper.cpp.
6. The AI endpoint picks viral moments from the transcript.
7. Only the selected short video sections are downloaded. The full long video is not downloaded first.
8. FFmpeg normalizes up to 3 clips, then the page shows preview and download buttons.

## Important notes before installing

- You still need **FFmpeg** because it cuts the video clips.
- You still need **yt-dlp** because it reads YouTube captions and downloads only the selected clip sections.
- The included `backend/requirements.txt` is intentionally light: Flask, requests, yt-dlp, and pytest.
- `openai-whisper` is **not installed by default** because it can be heavy on phones. The app tries YouTube captions first, so many videos do not need Whisper at all.
- If a video has no captions, audio transcription is limited by default to 30 minutes to protect your data and battery.
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

The app needs a transcript before AI can pick clips. It now tries the lightest option first.

### Best option: YouTube captions, no Whisper needed

For many YouTube videos, yt-dlp can download captions or auto-captions. This uses very little data because it is just text. Happyclips tries this automatically. If captions are found, it skips the big transcription step.

This is the best way for very long videos, like livestreams or 11-hour videos, because downloading/transcribing all audio can be slow and expensive.

If a video has no captions, then use one of these fallback choices.

### Fallback A: lighter phone setup with whisper.cpp

This is the recommended Android idea. Set `HAPPYCLIPS_WHISPER_COMMAND` to a command that creates a JSON transcript file. The command can use two placeholders:

- `{audio}` = the WAV audio file Happyclips creates
- `{output}` = where your command should write transcript JSON

Do **not** copy `your-whisper-command`; that is only a placeholder. Replace it with the real command you installed. Example shape:

```bash
export HAPPYCLIPS_WHISPER_COMMAND='real-whisper-command --input {audio} --output {output}'
```

The JSON should contain segments like this:

```json
[
  { "start": 10.2, "end": 15.6, "text": "what was said here" }
]
```

### Fallback B: heavier Python Whisper setup

Only do this if your phone has enough storage and the install works:

```bash
pip install openai-whisper
```

Then Happyclips will use Python Whisper automatically if `HAPPYCLIPS_WHISPER_COMMAND` is not set.

### Why long videos are now safer

The app no longer downloads the whole video before knowing the clip timestamps. The new order is:

1. Try YouTube captions.
2. Use AI to choose timestamps.
3. Download only those short timestamp sections.

If there are no captions, the app downloads audio only for transcription, not full video. By default it refuses audio transcription for videos longer than 30 minutes. You can change that with `HAPPYCLIPS_MAX_AUDIO_TRANSCRIBE_SECONDS`, but higher values can use much more time, data, battery, and storage.

## Run the app

From the project folder with `.venv` activated:

```bash
python backend/app/main.py
```

Then open this in your Android browser:

```text
http://127.0.0.1:8000
```

The browser checks job progress every few seconds. The server hides those repeated `/status` access logs so your Termux screen stays readable.

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
| `HAPPYCLIPS_MAX_AUDIO_TRANSCRIBE_SECONDS` | `1800` | Max no-caption audio transcription length, in seconds. Default is 30 minutes. |
| `HAPPYCLIPS_SUB_LANGS` | `en.*,en` | Caption languages yt-dlp should try first. |
| `HAPPYCLIPS_DATA_DIR` | `./data` | Folder for temporary jobs and final clips. |

Example:

```bash
export HAPPYCLIPS_RATE_LIMIT_SECONDS=30
python backend/app/main.py
```

## Why auto-editor is not installed by default

`auto-editor` is useful when you want to remove silence automatically. Happyclips already uses FFmpeg for exact cuts and Whisper + AI for finding meaningful moments. Adding auto-editor by default would make the phone install heavier. You can still use it manually before or after Happyclips if silence removal is important to you.

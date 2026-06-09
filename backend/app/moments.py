from __future__ import annotations

import json
import re
from typing import Any

MIN_CLIP_SECONDS = 0.0
MAX_CLIP_SECONDS = 25.0


def parse_ai_moments(text: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return []
        parsed = json.loads(match.group(0))
    if isinstance(parsed, dict):
        parsed = parsed.get("clips") or parsed.get("moments") or parsed.get("response") or []
        if isinstance(parsed, str):
            return parse_ai_moments(parsed)
    return parsed if isinstance(parsed, list) else []


def normalize_transcript(raw: Any) -> list[dict[str, Any]]:
    segments = raw.get("segments", raw) if isinstance(raw, dict) else raw
    normalized: list[dict[str, Any]] = []
    for segment in segments:
        try:
            normalized.append(
                {
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "text": str(segment.get("text", "")).strip(),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not normalized:
        raise RuntimeError("Transcript did not contain timestamped segments")
    return normalized


def clamp_moments(
    moments: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    min_seconds: float = MIN_CLIP_SECONDS,
    max_seconds: float = MAX_CLIP_SECONDS,
) -> list[dict[str, float]]:
    video_end = max(float(item["end"]) for item in transcript)
    cleaned: list[dict[str, float]] = []
    for moment in moments:
        try:
            start = max(0.0, float(moment["start"]))
            end = min(video_end, float(moment["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if min_seconds > 0 and end - start < min_seconds:
            end = min(video_end, start + min_seconds)
        if end - start > max_seconds:
            end = start + max_seconds
        if end - start >= 1:
            cleaned.append({"start": round(start, 2), "end": round(end, 2)})
    return dedupe_moments(cleaned)


def fallback_moments(
    transcript: list[dict[str, Any]],
    needed: int,
    min_seconds: float = MIN_CLIP_SECONDS,
    max_seconds: float = MAX_CLIP_SECONDS,
) -> list[dict[str, float]]:
    ranked = sorted(transcript, key=lambda item: len(str(item.get("text", ""))), reverse=True)
    moments: list[dict[str, float]] = []
    for item in ranked:
        start = max(0.0, float(item["start"]))
        end = min(float(item["end"]), start + max_seconds)
        if min_seconds > 0 and end - start < min_seconds:
            continue
        moments.append({"start": round(start, 2), "end": round(end, 2)})
        unique = dedupe_moments(moments)
        if len(unique) >= needed:
            return unique[:needed]
    return dedupe_moments(moments)[:needed]


def dedupe_moments(moments: list[dict[str, float]]) -> list[dict[str, float]]:
    unique: list[dict[str, float]] = []
    for moment in moments:
        overlaps = any(moment["start"] < item["end"] and moment["end"] > item["start"] for item in unique)
        if not overlaps:
            unique.append(moment)
    return unique

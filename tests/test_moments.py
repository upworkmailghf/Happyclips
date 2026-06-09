from backend.app.moments import clamp_moments, fallback_moments, normalize_transcript, parse_ai_moments


def sample_transcript():
    return [
        {"start": 0, "end": 4, "text": "short intro"},
        {"start": 4, "end": 16, "text": "a strong complete moment with a surprising hook"},
        {"start": 20, "end": 36, "text": "another detailed story with useful payoff and context"},
        {"start": 42, "end": 55, "text": "final segment with a memorable ending"},
    ]


def test_parse_ai_moments_from_wrapped_text():
    moments = parse_ai_moments('Here: [{"start": 4, "end": 18}]')
    assert moments == [{"start": 4, "end": 18}]


def test_clamp_moments_limits_duration():
    moments = clamp_moments([{"start": 4, "end": 40}], sample_transcript())
    assert moments == [{"start": 4.0, "end": 29.0}]


def test_fallback_moments_returns_needed_non_overlapping_clips():
    moments = fallback_moments(sample_transcript(), 3)
    assert len(moments) == 3
    assert all(moment["end"] - moment["start"] >= 8 for moment in moments)


def test_normalize_transcript_accepts_whisper_result_shape():
    normalized = normalize_transcript({"segments": [{"start": "1", "end": "2", "text": " hi "}]})
    assert normalized == [{"start": 1.0, "end": 2.0, "text": "hi"}]

from backend.app.moments import clamp_moments, fallback_moments, normalize_transcript, parse_ai_moments


def sample_transcript():
    return [
        {"start": 0, "end": 4, "text": "short intro"},
        {"start": 4, "end": 16, "text": "a strong complete moment with a surprising hook"},
        {"start": 20, "end": 60, "text": "another detailed story with useful payoff and context"},
        {"start": 62, "end": 67, "text": "final segment with a memorable ending"},
    ]


def test_parse_ai_moments_from_wrapped_text():
    moments = parse_ai_moments('Here: [{"start": 4, "end": 18}]')
    assert moments == [{"start": 4, "end": 18}]


def test_clamp_moments_caps_duration_without_padding_short_clips():
    moments = clamp_moments([
        {"start": 0, "end": 4},
        {"start": 20, "end": 60},
    ], sample_transcript())
    assert moments == [{"start": 0.0, "end": 4.0}, {"start": 20.0, "end": 45.0}]


def test_fallback_moments_returns_needed_non_overlapping_unpadded_clips():
    moments = fallback_moments(sample_transcript(), 3)
    assert len(moments) == 3
    assert {"start": 62.0, "end": 67.0} in moments
    assert all(moment["end"] - moment["start"] <= 25 for moment in moments)


def test_normalize_transcript_accepts_whisper_result_shape():
    normalized = normalize_transcript({"segments": [{"start": "1", "end": "2", "text": " hi "}]})
    assert normalized == [{"start": 1.0, "end": 2.0, "text": "hi"}]

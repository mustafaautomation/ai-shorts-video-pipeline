"""Word timings shared by the script rubric, offline voice, and captions.

Keep the constants in sync with web/lib/timing.ts so the live demo estimates
the same spoken length as the pipeline.
"""

from __future__ import annotations

from shorts_pipeline.models import WordTiming

LEAD_IN = 0.18
TAIL = 0.45
GAP = 0.065
MIN_WORD = 0.22
MAX_WORD = 0.56
PER_ALNUM = 0.046
BASE_WORD = 0.14


def word_duration(word: str) -> float:
    letters = sum(1 for char in word if char.isalnum())
    raw = BASE_WORD + PER_ALNUM * max(1, letters)
    return max(MIN_WORD, min(MAX_WORD, raw))


def plan_timings(text: str) -> list[WordTiming]:
    words = [part for part in text.split() if part]
    cursor = LEAD_IN
    timings: list[WordTiming] = []
    for index, word in enumerate(words):
        duration = word_duration(word)
        start = round(cursor, 3)
        end = round(cursor + duration, 3)
        timings.append(WordTiming(text=word, start=start, end=end))
        cursor += duration
        if index != len(words) - 1:
            cursor += GAP
    return timings


def timeline_duration(words: list[WordTiming]) -> float:
    if not words:
        return 0.0
    return round(words[-1].end + TAIL, 3)


def estimate_seconds(text: str) -> float:
    return timeline_duration(plan_timings(text))


def align_timings(words: list[WordTiming], audio_duration: float) -> list[WordTiming]:
    """Keep caption times inside the audio file.

    Real word boundaries already match the file and are left alone. Planned
    timings, used when a provider returns audio without boundaries, are scaled
    so the last word ends just before the file does.
    """
    if not words or audio_duration <= 0:
        return words
    speech_end = words[-1].end
    if speech_end <= 0:
        return words
    inside = speech_end <= audio_duration + 0.08 and speech_end >= audio_duration * 0.62
    if inside:
        return words
    usable = max(0.4, audio_duration - 0.12)
    factor = usable / speech_end
    scaled = [
        WordTiming(
            text=word.text,
            start=round(word.start * factor, 3),
            end=round(max(word.start * factor + 0.05, word.end * factor), 3),
        )
        for word in words
    ]
    return normalize_timings(scaled)


def normalize_timings(words: list[WordTiming]) -> list[WordTiming]:
    """Force timings to be monotonic so caption cues never sit on top of each other."""
    fixed: list[WordTiming] = []
    cursor = 0.0
    for word in words:
        start = max(float(word.start), cursor)
        end = max(float(word.end), start + 0.05)
        fixed.append(WordTiming(text=word.text, start=round(start, 3), end=round(end, 3)))
        cursor = end
    return fixed

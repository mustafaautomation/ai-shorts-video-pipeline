"""Edge TTS voiceover, with an offline tone bed that still has word timings."""

from __future__ import annotations

import array
import asyncio
import json
import logging
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path

from shorts_pipeline.models import Voiceover, WordTiming
from shorts_pipeline.timing import (
    align_timings,
    normalize_timings,
    plan_timings,
    timeline_duration,
)

logger = logging.getLogger(__name__)

SAMPLE_RATE = 22050


def _write_tone_bed(path: Path, words: list[WordTiming], duration: float) -> None:
    total = int(duration * SAMPLE_RATE)
    samples = array.array("h", [0] * total)
    for index, word in enumerate(words):
        start = int(word.start * SAMPLE_RATE)
        end = min(total, int(word.end * SAMPLE_RATE))
        span = max(1, end - start)
        fundamental = 132 + (index % 6) * 17
        for offset in range(max(0, start), end):
            local = (offset - start) / span
            envelope = math.sin(math.pi * local) ** 1.15
            time = offset / SAMPLE_RATE
            value = 0.55 * math.sin(2 * math.pi * fundamental * time)
            value += 0.18 * math.sin(2 * math.pi * fundamental * 2.01 * time)
            samples[offset] = max(-32767, min(32767, int(envelope * value * 32767)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def synthesize_offline(text: str, audio_path: Path) -> Voiceover:
    words = plan_timings(text)
    duration = timeline_duration(words)
    _write_tone_bed(audio_path, words, duration)
    return Voiceover(
        audio_path=str(audio_path),
        words=words,
        provider="offline",
        duration=duration,
    )


def _ticks_to_seconds(value: int | float) -> float:
    return float(value) / 10_000_000


def _audio_duration(path: Path, fallback: float) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.exists():
        return fallback
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return fallback
    try:
        return float(json.loads(completed.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return fallback


async def _edge_stream(text: str, audio_path: Path, voice: str) -> list[WordTiming]:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    audio = bytearray()
    words: list[WordTiming] = []
    async for chunk in communicate.stream():
        kind = chunk.get("type")
        if kind == "audio":
            audio.extend(chunk["data"])
        elif kind == "WordBoundary":
            start = _ticks_to_seconds(chunk["offset"])
            end = start + _ticks_to_seconds(chunk["duration"])
            token = str(chunk.get("text") or "").strip()
            if token:
                words.append(WordTiming(text=token, start=start, end=end))
    if not audio:
        raise RuntimeError("Edge TTS returned no audio")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(audio)
    return normalize_timings(words)


def synthesize_edge(text: str, audio_path: Path, voice: str | None = None) -> Voiceover:
    chosen = voice or os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")
    words = asyncio.run(_edge_stream(text, audio_path, chosen))
    probed = _audio_duration(audio_path, 0.0)
    if not words:
        words = plan_timings(text)
        logger.warning("Edge TTS returned audio without word boundaries; using planned timings")
    if probed <= 0:
        probed = timeline_duration(words)
    words = align_timings(normalize_timings(words), probed)
    return Voiceover(
        audio_path=str(audio_path),
        words=words,
        provider="edge",
        duration=round(probed, 3),
    )


def synthesize(text: str, audio_path: Path, provider: str | None = None) -> Voiceover:
    if not text.strip():
        raise ValueError("voiceover text is empty")
    choice = (provider or os.getenv("VOICE_PROVIDER") or "auto").strip().lower()
    if choice == "offline":
        return synthesize_offline(text, audio_path)
    if choice in {"edge", "auto"}:
        try:
            return synthesize_edge(text, audio_path)
        except Exception as exc:
            reason = exc.__class__.__name__
            if choice == "edge":
                logger.warning("Edge TTS failed (%s); using the offline voice", reason)
            else:
                logger.info("Edge TTS unavailable (%s); using the offline voice", reason)
            return synthesize_offline(text, audio_path)
    logger.warning("unknown VOICE_PROVIDER %s; using offline", choice)
    return synthesize_offline(text, audio_path)

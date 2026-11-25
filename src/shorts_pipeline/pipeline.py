"""Run script, voice, picture, and optional mock publish as one job."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from shorts_pipeline.models import PipelineResult
from shorts_pipeline.publish.adapters import PublishJob, publish_all
from shorts_pipeline.render.ffmpeg import probe_media, render_reel
from shorts_pipeline.script.generator import generate_script
from shorts_pipeline.script.rubric import evaluate_script
from shorts_pipeline.voice.synthesize import synthesize

logger = logging.getLogger(__name__)


def slugify(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    return slug[:48] or "reel"


def output_root() -> Path:
    root = Path(os.getenv("OUTPUT_DIR", "out"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_pipeline(
    topic: str,
    output_path: Path | None = None,
    *,
    script_provider: str | None = None,
    voice_provider: str | None = None,
    publish: bool = False,
    dry_run: bool = True,
    scheduled_at: str | None = None,
) -> PipelineResult:
    script = generate_script(topic, provider=script_provider)
    rubric = evaluate_script(script)
    logger.info(
        "script via %s, rubric %.2f, about %.1fs",
        script.provider,
        rubric.score,
        rubric.estimated_seconds,
    )
    root = output_root()
    work = root / "work" / slugify(script.topic)
    work.mkdir(parents=True, exist_ok=True)
    destination = output_path or (root / f"{slugify(script.topic)}.mp4")
    spoken = script.spoken_text()
    voice_choice = (voice_provider or os.getenv("VOICE_PROVIDER") or "auto").strip().lower()
    audio_path = work / ("voice.wav" if voice_choice == "offline" else "voice.mp3")
    voice = synthesize(spoken, audio_path, provider=voice_provider)
    if voice.provider == "offline" and Path(voice.audio_path).suffix != ".wav":
        wav_path = Path(voice.audio_path).with_suffix(".wav")
        Path(voice.audio_path).replace(wav_path)
        voice.audio_path = str(wav_path)
    broll: list[Path] = []
    visual_source = "generated"
    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        from shorts_pipeline.visuals.pexels import download_broll

        broll = download_broll(script.topic, pexels_key, work / "broll")
        if broll:
            visual_source = "pexels"
    video, captions = render_reel(
        script=script,
        audio_path=Path(voice.audio_path),
        words=voice.words,
        duration=voice.duration,
        output_path=destination,
        work_dir=work,
        broll=broll,
    )
    info = probe_media(video)
    video_stream = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    duration = float(info["format"].get("duration") or voice.duration)
    receipts = []
    if publish:
        receipts = publish_all(
            PublishJob(video_path=video, script=script, scheduled_at=scheduled_at),
            dry_run=dry_run,
        )
    public_script = {
        "topic": script.topic,
        "hook": script.hook,
        "body": script.body,
        "cta": script.cta,
        "provider": script.provider,
        "full_text": spoken,
        "word_count": len(spoken.split()),
        "estimated_seconds": rubric.estimated_seconds,
        "rubric": rubric.to_dict(),
    }
    return PipelineResult(
        topic=script.topic,
        script=public_script,
        voice_provider=voice.provider,
        visual_source=visual_source,
        video_path=str(video),
        captions_path=str(captions),
        duration=round(duration, 3),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        receipts=receipts,
    )

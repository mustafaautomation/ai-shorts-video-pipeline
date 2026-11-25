"""HTTP API used by the CLI's serve command and by the n8n / Make blueprints."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shorts_pipeline import __version__
from shorts_pipeline.pipeline import run_pipeline
from shorts_pipeline.publish.adapters import RealPublishDisabled
from shorts_pipeline.script.generator import generate_script
from shorts_pipeline.script.rubric import evaluate_script

app = FastAPI(
    title="AI Shorts Video Pipeline",
    version=__version__,
    summary="Portfolio demo. Publishing is mock-only.",
)


class ScriptIn(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    provider: str | None = None


class PipelineIn(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    script_provider: str | None = None
    voice_provider: str | None = None
    publish: bool = False
    dry_run: bool = True
    scheduled_at: str | None = None


def _script_payload(topic: str, provider: str | None) -> dict:
    try:
        script = generate_script(topic, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rubric = evaluate_script(script)
    spoken = script.spoken_text()
    return {
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


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "publish": "mock",
        "script_provider": os.getenv("SCRIPT_PROVIDER", "auto"),
        "voice_provider": os.getenv("VOICE_PROVIDER", "auto"),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "gemini": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "pexels": bool(os.getenv("PEXELS_API_KEY")),
    }


@app.post("/v1/script")
def create_script(body: ScriptIn) -> dict:
    return _script_payload(body.topic, body.provider)


@app.post("/v1/pipeline")
def create_pipeline(body: PipelineIn) -> dict:
    root = Path(os.getenv("OUTPUT_DIR", "out"))
    try:
        result = run_pipeline(
            body.topic,
            script_provider=body.script_provider,
            voice_provider=body.voice_provider or "offline",
            publish=body.publish,
            dry_run=body.dry_run,
            scheduled_at=body.scheduled_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RealPublishDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = result.model_dump()
    video = Path(result.video_path)
    try:
        payload["video_name"] = str(video.resolve().relative_to(root.resolve()))
    except ValueError:
        payload["video_name"] = video.name
    return payload

"""Shared data passed between script, voice, render, and publish."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    text: str
    start: float
    end: float


class Script(BaseModel):
    topic: str
    hook: str
    body: list[str] = Field(min_length=1)
    cta: str
    provider: str

    def spoken_text(self) -> str:
        parts = [self.hook, *self.body, self.cta]
        return " ".join(part.strip() for part in parts if part and part.strip())


class Voiceover(BaseModel):
    audio_path: str
    words: list[WordTiming]
    provider: str
    duration: float


class CaptionCue(BaseModel):
    start: float
    end: float
    active: str
    active_index: int
    line_words: list[str]

    @property
    def line(self) -> str:
        return " ".join(self.line_words)


class PublishReceipt(BaseModel):
    platform: str
    dry_run: bool
    video_path: str
    saved_to: str
    request: dict


class PipelineResult(BaseModel):
    topic: str
    script: dict
    voice_provider: str
    visual_source: str
    video_path: str
    captions_path: str
    duration: float
    width: int
    height: int
    receipts: list[PublishReceipt] = Field(default_factory=list)

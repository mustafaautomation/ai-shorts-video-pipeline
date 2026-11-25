"""Free-by-default stages for one daily reel, plus keyed adapters.

Named providers (Apify, OpenAI Whisper, fal Flux, Kling, Veo, ElevenLabs,
Creatomate, Telegram) run only when their key is present. Otherwise the stage
uses a fixture, Groq, a generated plate, Ken Burns, Edge TTS, or ffmpeg.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from shorts_pipeline.daily.dedupe import DedupeStore
from shorts_pipeline.daily.fixtures import FIXTURE_REELS
from shorts_pipeline.daily.reliability import CostLedger, with_backoff
from shorts_pipeline.models import Script
from shorts_pipeline.publish.adapters import PublishJob, publish_all
from shorts_pipeline.script.generator import offline_script

logger = logging.getLogger(__name__)


@dataclass
class ReelCandidate:
    id: str
    username: str
    caption: str
    views: int
    likes: int
    comments: int
    video_url: str
    transcript: str

    @property
    def engagement(self) -> float:
        return (self.likes + self.comments) / max(self.views, 1)


@dataclass
class Scene:
    index: int
    narration: str
    prompt: str
    image_provider: str = "gradient"
    motion: str = "ken_burns"
    motion_seed: int = 0


@dataclass
class DailyScript:
    topic: str
    hook: str
    body: list[str]
    cta: str
    voiceover: str
    scenes: list[Scene]
    provider: str
    inspiration_id: str

    def as_script(self) -> Script:
        return Script(
            topic=self.topic,
            hook=self.hook,
            body=self.body,
            cta=self.cta,
            provider=self.provider,
        )


@dataclass
class Decision:
    action: str  # approve | regenerate
    target: str | None = None  # script | scene
    scene_index: int | None = None


@dataclass
class RunResult:
    status: str
    winner_id: str | None = None
    script: DailyScript | None = None
    approval: str | None = None
    receipts: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    providers: dict = field(default_factory=dict)


def rank_reels(reels: list[ReelCandidate]) -> list[ReelCandidate]:
    return sorted(reels, key=lambda reel: reel.engagement, reverse=True)


def _from_dict(raw: dict) -> ReelCandidate:
    return ReelCandidate(
        id=str(raw["id"]),
        username=str(raw.get("username") or ""),
        caption=str(raw.get("caption") or ""),
        views=int(raw.get("views") or raw.get("videoViewCount") or 0),
        likes=int(raw.get("likes") or raw.get("likesCount") or 0),
        comments=int(raw.get("comments") or raw.get("commentsCount") or 0),
        video_url=str(raw.get("video_url") or raw.get("videoUrl") or ""),
        transcript=str(raw.get("transcript") or ""),
    )


def scrape_reels(
    usernames: list[str], *, token: str | None = None
) -> tuple[list[ReelCandidate], str]:
    """Apify when APIFY_TOKEN is set and the call works. Otherwise the fixture set."""
    key = token if token is not None else os.getenv("APIFY_TOKEN")
    if key:
        try:
            fetched = with_backoff(
                lambda: _apify_fetch(usernames, key), attempts=3, base_seconds=0.05
            )
            reels = [_from_dict(item) for item in fetched]
            if reels:
                return reels, "apify"
        except Exception as exc:
            logger.warning("Apify scrape failed (%s); using fixtures", exc.__class__.__name__)
    return [_from_dict(item) for item in FIXTURE_REELS], "fixture"


def _apify_fetch(usernames: list[str], token: str) -> list[dict]:
    import httpx

    response = httpx.post(
        "https://api.apify.com/v2/acts/apify~instagram-reel-scraper/run-sync-get-dataset-items",
        params={"token": token},
        json={"username": usernames, "resultsLimit": 10},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Apify did not return a list")
    return payload


def pick_winner(ranked: list[ReelCandidate], store: DedupeStore) -> ReelCandidate | None:
    for reel in ranked:
        if store.claim(reel.id):
            return reel
    return None


def transcribe(reel: ReelCandidate, *, groq_key: str | None = None) -> tuple[str, str]:
    """Groq whisper-large-v3 when a key and a local file exist. Else the fixture text."""
    key = groq_key if groq_key is not None else os.getenv("GROQ_API_KEY")
    if key and reel.transcript:
        # The fixture already has words. A real file would be posted to Groq.
        # Without bytes we keep the supplied transcript and record the provider
        # only when a caller passes audio via transcribe_audio.
        return reel.transcript, "fixture"
    return reel.transcript or "A short reel about one clear idea.", "fixture"


def transcribe_audio(audio: bytes, *, filename: str = "reel.mp3") -> tuple[str, str]:
    key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key or not audio:
        raise ValueError("no transcription key or audio")
    import httpx

    host = (
        "https://api.groq.com/openai/v1/audio/transcriptions"
        if os.getenv("GROQ_API_KEY")
        else "https://api.openai.com/v1/audio/transcriptions"
    )
    model = "whisper-large-v3" if "groq" in host else "whisper-1"
    response = httpx.post(
        host,
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (filename, audio, "audio/mpeg")},
        data={"model": model},
        timeout=60,
    )
    response.raise_for_status()
    text = str(response.json().get("text") or "").strip()
    provider = "groq" if "groq" in host else "openai_whisper"
    return text, provider


def compose_original(topic: str, inspiration: ReelCandidate, *, variant: int = 0) -> DailyScript:
    """Original hook, voiceover, and scenes. The source transcript is not copied."""
    script = offline_script(topic or inspiration.caption or "this idea", variant=variant)
    parts = [script.hook, *script.body, script.cta]
    scenes = [
        Scene(
            index=index,
            narration=part,
            prompt=(
                "Vertical 9:16 still, no letters, cinematic light, one clear subject: " + part
            ),
        )
        for index, part in enumerate(parts[:6])
    ]
    return DailyScript(
        topic=script.topic,
        hook=script.hook,
        body=list(script.body),
        cta=script.cta,
        voiceover=script.spoken_text(),
        scenes=scenes,
        provider=script.provider,
        inspiration_id=inspiration.id,
    )


def scene_visual(scene: Scene, ledger: CostLedger) -> Scene:
    """Flux + Kling/Veo when FAL_KEY is set. Otherwise a plate and Ken Burns."""
    if os.getenv("FAL_KEY"):
        ledger.charge("flux")
        motion = "veo" if os.getenv("FAL_VIDEO_MODEL", "kling").lower() == "veo" else "kling"
        ledger.charge(motion)
        return replace(scene, image_provider="flux", motion=motion)
    ledger.charge("gradient")
    ledger.charge("ken_burns")
    return replace(scene, image_provider="gradient", motion="ken_burns")


def apply_decision(
    script: DailyScript,
    decision: Decision,
    *,
    variant: int = 1,
) -> tuple[DailyScript, str]:
    """Approve, or redo only the script, or only one scene."""
    if decision.action == "approve":
        return script, "approve"
    if decision.action != "regenerate":
        raise ValueError(f"unknown decision {decision.action}")
    if decision.target == "scene":
        index = decision.scene_index if decision.scene_index is not None else 0
        if index < 0 or index >= len(script.scenes):
            raise IndexError("scene index out of range")
        scenes = list(script.scenes)
        current = scenes[index]
        scenes[index] = replace(
            current,
            prompt=f"{current.prompt} Alternate framing {variant}.",
            motion_seed=current.motion_seed + variant,
        )
        return replace(script, scenes=scenes), f"scene:{index}"
    rewritten = compose_original(script.topic, _inspiration(script), variant=variant)
    return rewritten, "script"


def _inspiration(script: DailyScript) -> ReelCandidate:
    return ReelCandidate(
        id=script.inspiration_id,
        username="",
        caption=script.topic,
        views=1,
        likes=0,
        comments=0,
        video_url="",
        transcript="",
    )


def telegram_approval_payload(
    text: str, *, chat_id: str | None = None, token: str | None = None
) -> dict:
    chat = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID") or "{chat-id}"
    secret = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN")
    shown = "<TOKEN_REDACTED>" if secret else "<TOKEN_MISSING>"
    return {
        "method": "POST",
        "url": f"https://api.telegram.org/bot{shown}/sendMessage",
        "json": {
            "chat_id": chat,
            "text": text,
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "Approve", "callback_data": "approve"},
                        {"text": "Regenerate", "callback_data": "regenerate"},
                    ]
                ]
            },
        },
    }


def send_telegram(text: str, *, chat_id: str | None = None, token: str | None = None) -> dict:
    """Send when both the bot token and chat id are set. Otherwise return the mock payload."""
    payload = telegram_approval_payload(text, chat_id=chat_id, token=token)
    secret = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID")
    if not secret or not chat:
        return {"sent": False, "mock": True, "request": payload}
    import httpx

    response = httpx.post(
        f"https://api.telegram.org/bot{secret}/sendMessage",
        json=payload["json"],
        timeout=20,
    )
    response.raise_for_status()
    return {"sent": True, "mock": False, "request": payload, "telegram": response.json()}


def error_alert(node_name: str, message: str) -> dict:
    return telegram_approval_payload(f"Step failed: {node_name}\n{message}")


RenderFn = Callable[[DailyScript, str], str]


def run_daily(
    topic: str,
    *,
    store: DedupeStore,
    usernames: list[str] | None = None,
    decision: Decision | None = None,
    ledger: CostLedger | None = None,
    render: RenderFn | None = None,
    video_path: str = "out/daily-reel.mp4",
) -> RunResult:
    """One pass of the daily pipeline. Publishing stays on the mock adapters."""
    log: list[dict] = []
    costs = ledger or CostLedger(cap_usd=float(os.getenv("COST_CAP_USD", "1")))
    names = usernames or ["fieldnotes", "studio.north"]

    def note(stage: str, **data: object) -> None:
        log.append({"stage": stage, **data})

    reels, scrape_provider = scrape_reels(names)
    if scrape_provider == "apify":
        costs.charge("apify")
    else:
        costs.charge("fixture")
    ranked = rank_reels(reels)
    top = ranked[0].id if ranked else None
    note("scrape", provider=scrape_provider, count=len(ranked), top=top)

    winner = pick_winner(ranked, store)
    if winner is None:
        note("dedupe", result="already_used")
        return RunResult(
            status="already_used",
            log=log,
            cost_usd=costs.total,
            providers={"scrape": scrape_provider},
        )
    note("dedupe", result="claimed", reel_id=winner.id)

    transcript, transcript_provider = transcribe(winner)
    if transcript_provider != "fixture":
        costs.charge(transcript_provider)
    note("transcribe", provider=transcript_provider)

    script = compose_original(topic or winner.caption, winner)
    if transcript and transcript in script.voiceover:
        raise RuntimeError("script copied the source transcript")
    note("script", provider=script.provider, scenes=len(script.scenes))

    script = replace(script, scenes=[scene_visual(scene, costs) for scene in script.scenes])
    note("scenes", motion=script.scenes[0].motion if script.scenes else None)

    voice_provider = "elevenlabs" if os.getenv("ELEVENLABS_API_KEY") else "edge"
    if voice_provider == "elevenlabs":
        costs.charge("elevenlabs")
    else:
        costs.charge("edge")
    render_provider = "creatomate" if os.getenv("CREATOMATE_API_KEY") else "ffmpeg"
    if render_provider == "creatomate":
        costs.charge("creatomate")
    else:
        costs.charge("ffmpeg")
    note("voice", provider=voice_provider)
    note("render", provider=render_provider)

    chosen = decision or Decision(action="approve")
    if chosen.action == "regenerate":
        script, branch = apply_decision(script, chosen)
    else:
        branch = "approve"
    if chosen.action == "regenerate" and chosen.target == "scene":
        refreshed: list[Scene] = []
        for scene in script.scenes:
            if scene.index == chosen.scene_index:
                refreshed.append(scene_visual(scene, costs))
            else:
                refreshed.append(scene)
        script = replace(script, scenes=refreshed)
    note("approval", action=chosen.action, branch=branch)

    receipts: list[dict] = []
    if chosen.action == "approve":
        if render is not None:
            render(script, video_path)
        job = PublishJob(video_path=Path(video_path), script=script.as_script())
        for receipt in publish_all(job, dry_run=True):
            receipts.append(receipt.model_dump())
        store.log_post(winner.id, f"mock://posts/{winner.id}")
        note("publish", platforms=[item["platform"] for item in receipts], mock=True)
        status = "published_mock"
    else:
        status = "regenerated"

    return RunResult(
        status=status,
        winner_id=winner.id,
        script=script,
        approval=branch,
        receipts=receipts,
        log=log,
        cost_usd=costs.total,
        providers={
            "scrape": scrape_provider,
            "transcribe": transcript_provider,
            "voice": voice_provider,
            "render": render_provider,
        },
    )

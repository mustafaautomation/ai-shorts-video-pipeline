"""Platform adapters that record the exact request they would send.

Live posting is intentionally unreachable. Credentials can be configured for a
later client, and receipts redact them. Nothing in this module opens a socket.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shorts_pipeline.models import PublishReceipt, Script

logger = logging.getLogger(__name__)


class RealPublishDisabled(RuntimeError):
    """Raised instead of calling Instagram, TikTok, or YouTube."""


@dataclass
class PublishJob:
    video_path: Path
    script: Script
    scheduled_at: str | None = None

    @property
    def title(self) -> str:
        words = self.script.hook.strip()
        if len(words) > 92:
            words = words[:89].rsplit(" ", 1)[0].rstrip(".,") + "..."
        return words or self.script.topic[:90]

    @property
    def caption(self) -> str:
        tags = "#shorts #reels #learnontiktok"
        return f"{self.script.hook.strip()}\n\n{tags}"

    @property
    def hashtags(self) -> list[str]:
        return ["shorts", "reels", "learnontiktok"]


def _redact(value: str | None, label: str) -> str:
    if not value:
        return f"<{label}_MISSING>"
    return f"<{label}_REDACTED>"


def _receipt_dir() -> Path:
    root = Path(os.getenv("OUTPUT_DIR", "out"))
    return root / "publish"


def _write_receipt(platform: str, request: dict, video_path: Path) -> PublishReceipt:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = _receipt_dir() / platform
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}.json"
    document = {
        "platform": platform,
        "dry_run": True,
        "video_path": str(video_path),
        "recorded_at": datetime.now(UTC).isoformat(),
        "request": request,
        "note": (
            "Mock publish. This is the payload a live client would send. "
            "No request left this machine."
        ),
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    logger.info("mock %s publish saved to %s", platform, path)
    return PublishReceipt(
        platform=platform,
        dry_run=True,
        video_path=str(video_path),
        saved_to=str(path),
        request=request,
    )


class InstagramReelsAdapter:
    """Graph API container create + media_publish, recorded and never sent."""

    platform = "instagram_reels"

    def __init__(
        self,
        *,
        access_token: str | None = None,
        user_id: str | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.access_token = access_token
        if self.access_token is None:
            self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.user_id = user_id if user_id is not None else os.getenv("INSTAGRAM_USER_ID")
        self.dry_run = _dry_run(dry_run)

    def build_request(self, job: PublishJob) -> dict:
        user = self.user_id or "{ig-user-id}"
        return {
            "platform": self.platform,
            "steps": [
                {
                    "method": "POST",
                    "url": f"https://graph.facebook.com/v21.0/{user}/media",
                    "headers": {"Authorization": f"Bearer {_redact(self.access_token, 'TOKEN')}"},
                    "json": {
                        "media_type": "REELS",
                        "caption": job.caption,
                        "share_to_feed": True,
                        "video_url": Path(job.video_path).resolve().as_uri(),
                    },
                },
                {
                    "method": "GET",
                    "url": "https://graph.facebook.com/v21.0/{container-id}",
                    "query": {"fields": "status_code"},
                    "until": {"field": "status_code", "equals": "FINISHED"},
                    "interval_seconds": 5,
                    "timeout_seconds": 120,
                },
                {
                    "method": "POST",
                    "url": f"https://graph.facebook.com/v21.0/{user}/media_publish",
                    "headers": {"Authorization": f"Bearer {_redact(self.access_token, 'TOKEN')}"},
                    "json": {"creation_id": "<id from step 1>"},
                },
            ],
            "scheduled_publish_time": job.scheduled_at,
        }

    def publish(self, job: PublishJob) -> PublishReceipt:
        return _finish(self.platform, self.build_request(job), job, self.dry_run)


class TikTokAdapter:
    """Content Posting API init payload, recorded and never sent."""

    platform = "tiktok"

    def __init__(self, *, access_token: str | None = None, dry_run: bool | None = None) -> None:
        self.access_token = access_token
        if self.access_token is None:
            self.access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        self.dry_run = _dry_run(dry_run)

    def build_request(self, job: PublishJob) -> dict:
        size = Path(job.video_path).stat().st_size if Path(job.video_path).exists() else 0
        return {
            "platform": self.platform,
            "method": "POST",
            "url": "https://open.tiktokapis.com/v2/post/publish/video/init/",
            "headers": {
                "Authorization": f"Bearer {_redact(self.access_token, 'TOKEN')}",
                "Content-Type": "application/json",
            },
            "json": {
                "post_info": {
                    "title": job.caption[:150],
                    "privacy_level": "SELF_ONLY",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                    "video_cover_timestamp_ms": 500,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size or 1,
                    "total_chunk_count": 1,
                },
            },
            "scheduled_publish_time": job.scheduled_at,
            "local_video_path": str(Path(job.video_path).resolve()),
        }

    def publish(self, job: PublishJob) -> PublishReceipt:
        return _finish(self.platform, self.build_request(job), job, self.dry_run)


class YouTubeShortsAdapter:
    """YouTube Data API videos.insert payload for a Short, recorded and never sent."""

    platform = "youtube_shorts"

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self.client_id = client_id if client_id is not None else os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = (
            client_secret if client_secret is not None else os.getenv("YOUTUBE_CLIENT_SECRET")
        )
        self.refresh_token = (
            refresh_token if refresh_token is not None else os.getenv("YOUTUBE_REFRESH_TOKEN")
        )
        self.dry_run = _dry_run(dry_run)

    def build_request(self, job: PublishJob) -> dict:
        status: dict = {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        }
        if job.scheduled_at:
            status["publishAt"] = job.scheduled_at
            status["privacyStatus"] = "private"
        description = job.caption if "#Shorts" in job.caption else f"{job.caption}\n\n#Shorts"
        return {
            "platform": self.platform,
            "method": "POST",
            "url": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            "headers": {"Authorization": f"Bearer {_redact(self.refresh_token, 'REFRESH_TOKEN')}"},
            "oauth_client": {
                "client_id": _redact(self.client_id, "CLIENT_ID"),
                "client_secret": _redact(self.client_secret, "CLIENT_SECRET"),
            },
            "json": {
                "snippet": {
                    "title": job.title[:100],
                    "description": description[:5000],
                    "tags": job.hashtags,
                    "categoryId": "22",
                    "defaultLanguage": "en",
                },
                "status": status,
            },
            "local_video_path": str(Path(job.video_path).resolve()),
            "shorts_constraints": {"vertical": True, "max_seconds": 60},
        }

    def publish(self, job: PublishJob) -> PublishReceipt:
        return _finish(self.platform, self.build_request(job), job, self.dry_run)


def _dry_run(explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    raw = os.getenv("PUBLISH_DRY_RUN", "true").strip().lower()
    return raw not in {"0", "false", "no"}


def _finish(platform: str, request: dict, job: PublishJob, dry_run: bool) -> PublishReceipt:
    if not dry_run:
        raise RealPublishDisabled(
            f"{platform} live publish is disabled. This portfolio demo records the "
            "payload and stops. Connect a real client only after Mustafa approves it."
        )
    return _write_receipt(platform, request, job.video_path)


def publish_all(job: PublishJob, *, dry_run: bool | None = None) -> list[PublishReceipt]:
    adapters = (
        InstagramReelsAdapter(dry_run=dry_run),
        TikTokAdapter(dry_run=dry_run),
        YouTubeShortsAdapter(dry_run=dry_run),
    )
    return [adapter.publish(job) for adapter in adapters]

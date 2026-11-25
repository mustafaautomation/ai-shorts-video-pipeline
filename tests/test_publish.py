from pathlib import Path

import pytest

from shorts_pipeline.models import Script
from shorts_pipeline.publish.adapters import (
    InstagramReelsAdapter,
    PublishJob,
    RealPublishDisabled,
    TikTokAdapter,
    YouTubeShortsAdapter,
    publish_all,
)


def _job(tmp_path: Path) -> PublishJob:
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"not a real mp4, just a payload size")
    return PublishJob(
        video_path=video,
        script=Script(
            topic="focus",
            hook="Stop scrolling. Focus is a one-breath skill.",
            body=["Name the next step.", "Do it once."],
            cta="Save this and try it today.",
            provider="test",
        ),
        scheduled_at="2026-12-01T15:00:00Z",
    )


def test_dry_run_writes_exact_payloads_and_redacts_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig-secret")
    monkeypatch.setenv("INSTAGRAM_USER_ID", "1789")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "tt-secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "yt-secret")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "yt-client-secret")
    receipts = publish_all(_job(tmp_path), dry_run=True)
    platforms = [receipt.platform for receipt in receipts]
    assert platforms == ["instagram_reels", "tiktok", "youtube_shorts"]
    blob = "\n".join(Path(receipt.saved_to).read_text(encoding="utf-8") for receipt in receipts)
    assert "ig-secret" not in blob
    assert "tt-secret" not in blob
    assert "yt-secret" not in blob
    assert "yt-client-secret" not in blob
    assert "<TOKEN_REDACTED>" in blob
    instagram = receipts[0].request
    assert instagram["steps"][0]["json"]["media_type"] == "REELS"
    assert instagram["steps"][0]["url"].endswith("/1789/media")
    assert instagram["scheduled_publish_time"] == "2026-12-01T15:00:00Z"
    tiktok = receipts[1].request
    assert tiktok["url"].endswith("/post/publish/video/init/")
    assert tiktok["json"]["source_info"]["source"] == "FILE_UPLOAD"
    youtube = receipts[2].request
    assert "youtube/v3/videos" in youtube["url"]
    assert youtube["json"]["status"]["publishAt"] == "2026-12-01T15:00:00Z"
    assert "#Shorts" in youtube["json"]["snippet"]["description"]


def test_live_mode_refuses_before_any_network(tmp_path) -> None:
    job = _job(tmp_path)
    with pytest.raises(RealPublishDisabled):
        InstagramReelsAdapter(dry_run=False).publish(job)
    with pytest.raises(RealPublishDisabled):
        TikTokAdapter(dry_run=False).publish(job)
    with pytest.raises(RealPublishDisabled):
        YouTubeShortsAdapter(dry_run=False).publish(job)

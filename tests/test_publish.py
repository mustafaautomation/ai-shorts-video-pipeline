from pathlib import Path

import pytest

from shorts_pipeline.models import Script
from shorts_pipeline.publish.adapters import (
    DEFAULT_GRAPH_API_VERSION,
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


def _graph_urls(tmp_path: Path) -> list[str]:
    request = InstagramReelsAdapter(user_id="1789", dry_run=True).build_request(_job(tmp_path))
    return [step["url"] for step in request["steps"]]


def test_graph_api_version_defaults_to_v21(tmp_path, monkeypatch) -> None:
    assert DEFAULT_GRAPH_API_VERSION == "v21.0"
    for value in (None, "", "  "):
        if value is None:
            monkeypatch.delenv("GRAPH_API_VERSION", raising=False)
        else:
            monkeypatch.setenv("GRAPH_API_VERSION", value)
        assert _graph_urls(tmp_path) == [
            "https://graph.facebook.com/v21.0/1789/media",
            "https://graph.facebook.com/v21.0/{container-id}",
            "https://graph.facebook.com/v21.0/1789/media_publish",
        ]


def test_graph_api_version_comes_from_one_setting(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GRAPH_API_VERSION", "v0.0-test")
    urls = _graph_urls(tmp_path)
    assert len(urls) == 3
    assert all(url.startswith("https://graph.facebook.com/v0.0-test/") for url in urls)


def test_graph_api_version_literal_appears_once_per_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    python_hits = [
        path.name
        for path in (root / "src").rglob("*.py")
        for _ in range(path.read_text(encoding="utf-8").count("v21.0"))
    ]
    assert python_hits == ["adapters.py"]
    web = (root / "web" / "lib" / "pipeline.ts").read_text(encoding="utf-8")
    assert web.count("v21.0") == 1
    assert 'process.env.GRAPH_API_VERSION || "v21.0"' in web
    assert web.count("${GRAPH_API_BASE}/") == 3
    config = (root / "web" / "next.config.mjs").read_text(encoding="utf-8")
    assert "GRAPH_API_VERSION: process.env.GRAPH_API_VERSION" in config

from pathlib import Path

import pytest

from shorts_pipeline.daily.dedupe import DedupeStore
from shorts_pipeline.daily.engine import (
    Decision,
    ReelCandidate,
    apply_decision,
    compose_original,
    rank_reels,
    run_daily,
    telegram_approval_payload,
)
from shorts_pipeline.daily.fixtures import FIXTURE_REELS
from shorts_pipeline.daily.reliability import (
    CostCapExceeded,
    CostLedger,
    PollTimeout,
    poll_until,
    with_backoff,
)
from shorts_pipeline.models import Script
from shorts_pipeline.publish.adapters import InstagramReelsAdapter, PublishJob


def test_dedupe_claim_is_idempotent(tmp_path: Path) -> None:
    store = DedupeStore(tmp_path / "used.json").load()
    assert store.claim("reel_sample_alpha") is True
    assert store.claim("reel_sample_alpha") is False
    again = DedupeStore(tmp_path / "used.json").load()
    assert again.claim("reel_sample_alpha") is False
    again.log_post("reel_sample_alpha", "mock://posts/reel_sample_alpha")
    assert again.posts[0]["permalink"].endswith("reel_sample_alpha")


def test_poll_timeout_uses_the_injected_clock() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    with pytest.raises(PollTimeout):
        poll_until(
            lambda: "IN_PROGRESS",
            is_done=lambda value: value == "COMPLETED",
            interval=10,
            timeout=25,
            now=now,
            sleep=sleep,
        )
    assert clock["t"] >= 25


def test_backoff_retries_then_returns() -> None:
    waits: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("blip")
        return "ok"

    result = with_backoff(flaky, attempts=3, base_seconds=0.5, sleep=waits.append)
    assert result == "ok"
    assert waits == [0.5, 1.0]


def test_cost_cap_allows_free_and_stops_paid() -> None:
    ledger = CostLedger(cap_usd=0.14)
    ledger.charge("edge")
    ledger.charge("flux")
    ledger.charge("kling")
    assert ledger.total == pytest.approx(0.13)
    with pytest.raises(CostCapExceeded):
        ledger.charge("flux")


def test_rank_puts_the_highest_engagement_first() -> None:
    reels = [
        ReelCandidate(
            id=item["id"],
            username=item["username"],
            caption=item["caption"],
            views=item["views"],
            likes=item["likes"],
            comments=item["comments"],
            video_url=item["video_url"],
            transcript=item["transcript"],
        )
        for item in FIXTURE_REELS
    ]
    assert rank_reels(reels)[0].id == "reel_sample_alpha"


def test_script_is_original_and_regenerate_touches_one_scene() -> None:
    raw = FIXTURE_REELS[0]
    inspiration = ReelCandidate(
        id=raw["id"],
        username=raw["username"],
        caption=raw["caption"],
        views=raw["views"],
        likes=raw["likes"],
        comments=raw["comments"],
        video_url=raw["video_url"],
        transcript=raw["transcript"],
    )
    script = compose_original("desk stretches", inspiration)
    assert inspiration.transcript not in script.voiceover
    assert script.scenes
    original_prompts = [scene.prompt for scene in script.scenes]
    updated, branch = apply_decision(
        script, Decision(action="regenerate", target="scene", scene_index=1), variant=2
    )
    assert branch == "scene:1"
    assert updated.scenes[0].prompt == original_prompts[0]
    assert updated.scenes[1].prompt != original_prompts[1]
    assert updated.scenes[1].motion_seed == 2
    rewritten, branch = apply_decision(
        script, Decision(action="regenerate", target="script"), variant=3
    )
    assert branch == "script"
    assert rewritten.voiceover != script.voiceover
    approved, branch = apply_decision(script, Decision(action="approve"))
    assert branch == "approve"
    assert approved.voiceover == script.voiceover


def test_daily_run_is_idempotent_and_publishes_mock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("CREATOMATE_API_KEY", raising=False)
    store = DedupeStore(tmp_path / "used.json").load()
    rendered: list[str] = []

    def fake_render(script, path: str) -> str:
        Path(path).write_bytes(b"mp4")
        rendered.append(path)
        return path

    video = str(tmp_path / "reel.mp4")
    first = run_daily("desk stretches", store=store, render=fake_render, video_path=video)
    assert first.status == "published_mock"
    assert first.winner_id == "reel_sample_alpha"
    assert first.providers["scrape"] == "fixture"
    assert first.providers["voice"] == "edge"
    assert first.providers["render"] == "ffmpeg"
    assert first.cost_usd == 0
    platforms = [item["platform"] for item in first.receipts]
    assert platforms == ["instagram_reels", "tiktok", "youtube_shorts"]
    assert rendered

    second = run_daily("desk stretches", store=store, render=fake_render, video_path=video)
    assert second.status == "published_mock"
    assert second.winner_id != first.winner_id
    third = run_daily("desk stretches", store=store, render=fake_render, video_path=video)
    assert third.winner_id not in {first.winner_id, second.winner_id}
    fourth = run_daily("desk stretches", store=store, render=fake_render, video_path=video)
    assert fourth.status == "already_used"
    assert fourth.receipts == []


def test_telegram_approval_payload_has_both_buttons() -> None:
    payload = telegram_approval_payload("Ready", chat_id="42", token="secret-token")
    buttons = payload["json"]["reply_markup"]["inline_keyboard"][0]
    assert [button["callback_data"] for button in buttons] == ["approve", "regenerate"]
    assert "secret-token" not in payload["url"]
    assert payload["json"]["chat_id"] == "42"


def test_instagram_reels_container_then_poll_then_publish(tmp_path: Path) -> None:
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"video")
    job = PublishJob(
        video_path=video,
        script=Script(
            topic="focus",
            hook="Stop scrolling. Focus is a one-breath skill.",
            body=["Name the next step.", "Do it once."],
            cta="Save this and try it today.",
            provider="test",
        ),
    )
    adapter = InstagramReelsAdapter(access_token="ig-secret", user_id="1789", dry_run=True)
    request = adapter.build_request(job)
    steps = request["steps"]
    assert steps[0]["json"]["media_type"] == "REELS"
    assert steps[0]["url"].endswith("/1789/media")
    assert steps[1]["method"] == "GET"
    assert steps[1]["until"]["equals"] == "FINISHED"
    assert steps[1]["query"]["fields"] == "status_code"
    assert steps[2]["url"].endswith("/1789/media_publish")
    assert steps[2]["json"]["creation_id"] == "<id from step 1>"
    assert "ig-secret" not in str(request)

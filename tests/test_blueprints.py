import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_n8n_workflow_matches_the_daily_canvas() -> None:
    document = json.loads((ROOT / "blueprints" / "n8n-shorts-pipeline.json").read_text())
    names = {node["name"] for node in document["nodes"]}
    for expected in (
        "09:00 daily",
        "Apify — scrape Reels",
        "Dedupe check",
        "New Reel?",
        "Transcribe (Whisper)",
        "Script + scene prompts",
        "fal.ai Flux",
        "fal.ai Kling / Veo",
        "Poll fal status",
        "COMPLETED?",
        "Send video + buttons",
        "Which button?",
        "IG container (REELS)",
        "status_code = FINISHED?",
        "media_publish",
        "TikTok init",
        "YouTube Shorts",
        "Log the post",
    ):
        assert expected in names
    blob = json.dumps(document)
    assert "apify~instagram-reel-scraper" in blob
    assert "media_type" in blob or "REELS" in blob
    assert "dry_run" in blob
    assert document["connections"]["09:00 daily"]["main"][0][0]["node"] == "Apify — scrape Reels"
    assert document["connections"]["Which button?"]["main"][0][0]["node"] == "IG container (REELS)"
    assert document["settings"]["errorWorkflow"]


def test_error_workflow_alerts_on_failure() -> None:
    document = json.loads((ROOT / "blueprints" / "n8n-error-workflow.json").read_text())
    names = {node["name"] for node in document["nodes"]}
    assert "On any failed node" in names
    assert "Alert — step failed" in names
    assert document["nodes"][0]["type"] == "n8n-nodes-base.errorTrigger"


def test_make_blueprint_covers_the_same_stages() -> None:
    document = json.loads((ROOT / "blueprints" / "make-shorts-scenario.json").read_text())
    blob = json.dumps(document)
    assert "apify~instagram-reel-scraper" in blob
    assert "queue.fal.run" in blob
    assert "media_type" in blob
    assert "dry_run" in blob
    assert document["name"]

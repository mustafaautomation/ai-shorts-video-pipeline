import json

import httpx
import pytest

from shorts_pipeline.script.generator import generate_script, offline_script
from shorts_pipeline.script.rubric import evaluate_script
from shorts_pipeline.timing import estimate_seconds

TOPICS = [
    "AI",
    "how to explain a hard idea",
    "quantum error correction for climate safe compute clusters and the teams who ship them",
    "!!!",
    "a",
]


@pytest.mark.parametrize("topic", TOPICS)
def test_offline_script_fits_structure_and_rubric(topic: str) -> None:
    first = offline_script(topic)
    second = offline_script(topic)
    assert first.model_dump() == second.model_dump()
    assert first.provider == "offline"
    assert first.hook.strip()
    assert 2 <= len(first.body) <= 4
    assert all(beat.strip() for beat in first.body)
    assert first.cta.strip()
    duration = estimate_seconds(first.spoken_text())
    assert 30 <= duration <= 45
    rubric = evaluate_script(first)
    assert rubric.passed
    assert rubric.score == 1.0


def test_thin_script_fails_the_rubric() -> None:
    from shorts_pipeline.models import Script

    script = Script(
        topic="focus",
        hook="Hi",
        body=["Too short."],
        cta="Thanks for watching the show.",
        provider="test",
    )
    rubric = evaluate_script(script)
    assert rubric.passed is False
    names = {check.name for check in rubric.checks if not check.passed}
    assert "duration_window" in names
    assert "body_beats" in names
    assert "cta_verb" in names


def test_empty_topic_is_rejected() -> None:
    with pytest.raises(ValueError):
        generate_script("   ")


def test_auto_without_keys_uses_offline() -> None:
    script = generate_script("morning routines", provider="auto")
    assert script.provider == "offline"


def test_groq_failure_falls_back_to_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    def explode(url: str, headers: dict, payload: dict, timeout: float = 30.0) -> dict:
        raise httpx.ConnectError("offline test")

    monkeypatch.setattr("shorts_pipeline.script.generator._post_json", explode)
    script = generate_script("note taking", provider="groq")
    assert script.provider == "offline"


def test_groq_json_is_accepted_when_it_passes_the_rubric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    good = offline_script("desk stretches")

    def fake_post(url: str, headers: dict, payload: dict, timeout: float = 30.0) -> dict:
        assert "api.groq.com" in url
        assert headers["Authorization"] == "Bearer test-key"
        assert "desk stretches" in payload["messages"][1]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"hook": good.hook, "body": good.body, "cta": good.cta}
                        )
                    }
                }
            ]
        }

    monkeypatch.setattr("shorts_pipeline.script.generator._post_json", fake_post)
    script = generate_script("desk stretches", provider="groq")
    assert script.provider == "groq"
    assert script.hook == good.hook


def test_gemini_is_used_when_groq_returns_a_bad_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    good = offline_script("water the plants")
    calls: list[str] = []

    def fake_post(url: str, headers: dict, payload: dict, timeout: float = 30.0) -> dict:
        calls.append(url)
        if "groq" in url:
            return {"choices": [{"message": {"content": '{"hook": "no"}'}}]}
        assert headers["x-goog-api-key"] == "gemini-key"
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {"hook": good.hook, "body": good.body, "cta": good.cta}
                                )
                            }
                        ]
                    }
                }
            ]
        }

    monkeypatch.setattr("shorts_pipeline.script.generator._post_json", fake_post)
    script = generate_script("water the plants", provider="auto")
    assert script.provider == "gemini"
    assert any("groq" in url for url in calls)
    assert any("generativelanguage.googleapis.com" in url for url in calls)

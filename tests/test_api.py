from fastapi.testclient import TestClient

from shorts_pipeline.api import app


def test_health_and_script_endpoint() -> None:
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["publish"] == "mock"
    assert health.json()["groq"] is False
    created = client.post("/v1/script", json={"topic": "desk stretches", "provider": "offline"})
    assert created.status_code == 200
    body = created.json()
    assert body["provider"] == "offline"
    assert body["hook"]
    assert 2 <= len(body["body"]) <= 4
    assert 30 <= body["estimated_seconds"] <= 45
    assert body["rubric"]["passed"] is True


def test_pipeline_endpoint_renders(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    client = TestClient(app)
    response = client.post(
        "/v1/pipeline",
        json={
            "topic": "why a single example beats a list",
            "script_provider": "offline",
            "voice_provider": "offline",
            "publish": True,
            "dry_run": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == 1080
    assert body["height"] == 1920
    assert len(body["receipts"]) == 3
    refused = client.post(
        "/v1/pipeline",
        json={
            "topic": "no live post",
            "dry_run": False,
            "publish": True,
            "voice_provider": "offline",
        },
    )
    assert refused.status_code == 409

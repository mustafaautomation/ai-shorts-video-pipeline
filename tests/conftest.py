import pytest


@pytest.fixture(autouse=True)
def _isolated_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests stay keyless even if the developer shell has API keys loaded."""
    for name in (
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "PEXELS_API_KEY",
        "INSTAGRAM_ACCESS_TOKEN",
        "TIKTOK_ACCESS_TOKEN",
        "YOUTUBE_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SCRIPT_PROVIDER", "offline")
    monkeypatch.setenv("VOICE_PROVIDER", "offline")
    monkeypatch.setenv("PUBLISH_DRY_RUN", "true")

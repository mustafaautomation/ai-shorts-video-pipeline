from shorts_pipeline.visuals.pexels import _best_file, search_portrait_videos


def test_best_file_prefers_portrait() -> None:
    video = {
        "video_files": [
            {"width": 1920, "height": 1080, "link": "https://example.com/wide.mp4"},
            {"width": 1080, "height": 1920, "link": "https://example.com/tall.mp4"},
            {"width": 540, "height": 960, "link": "https://example.com/small.mp4"},
        ]
    }
    assert _best_file(video) == "https://example.com/tall.mp4"


def test_search_builds_a_portrait_request(monkeypatch) -> None:
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"videos": [{"id": 1}]}

    def fake_get(url: str, params: dict, headers: dict, timeout: float) -> Response:
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return Response()

    monkeypatch.setattr("shorts_pipeline.visuals.pexels.httpx.get", fake_get)
    videos = search_portrait_videos("city night", "pexels-key")
    assert videos == [{"id": 1}]
    assert captured["params"]["orientation"] == "portrait"
    assert captured["headers"]["Authorization"] == "pexels-key"

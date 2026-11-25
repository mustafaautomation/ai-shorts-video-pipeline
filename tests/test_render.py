from shorts_pipeline.pipeline import run_pipeline
from shorts_pipeline.render.ffmpeg import probe_media


def test_keyless_render_is_a_vertical_reel_with_audio(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    result = run_pipeline(
        "Explain a hard idea in one short",
        tmp_path / "reel.mp4",
        script_provider="offline",
        voice_provider="offline",
        publish=True,
        dry_run=True,
    )
    info = probe_media(tmp_path / "reel.mp4")
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
    assert video["width"] == 1080
    assert video["height"] == 1920
    assert video["codec_name"] == "h264"
    assert audio["codec_name"] == "aac"
    duration = float(info["format"]["duration"])
    assert 30 <= duration <= 48
    assert abs(duration - result.duration) < 0.4
    assert result.visual_source == "generated"
    assert result.voice_provider == "offline"
    assert len(result.receipts) == 3
    captions = (tmp_path / "out").rglob("captions.ass")
    assert any(path.exists() for path in captions)

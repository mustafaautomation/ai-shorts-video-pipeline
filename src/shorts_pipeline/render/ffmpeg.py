"""Compose a 1080x1920 H.264 reel with burned-in ASS captions."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from shorts_pipeline.models import Script, WordTiming
from shorts_pipeline.render.captions import render_ass

WIDTH = 1080
HEIGHT = 1920
FPS = 30
FONT_DIR_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/dejavu"),
)


class RenderError(RuntimeError):
    pass


def ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RenderError("ffmpeg is not installed")
    return binary


def ffprobe_binary() -> str:
    binary = shutil.which("ffprobe")
    if not binary:
        raise RenderError("ffprobe is not installed")
    return binary


def run_command(args: list[str]) -> None:
    completed = subprocess.run(args, capture_output=True, text=True)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-2500:]
        raise RenderError(tail or f"command failed: {args[0]}")


def probe_media(path: Path) -> dict:
    completed = subprocess.run(
        [
            ffprobe_binary(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RenderError((completed.stderr or "ffprobe failed").strip())
    return json.loads(completed.stdout)


def _font_dir() -> str | None:
    for candidate in FONT_DIR_CANDIDATES:
        if candidate.is_dir():
            return str(candidate)
    return None


def _filter_path(path: Path) -> str:
    text = str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")
    return text


def _ass_filter(captions: Path) -> str:
    fonts = _font_dir()
    filename = _filter_path(captions)
    if fonts:
        return f"ass='{filename}':fontsdir='{_filter_path(Path(fonts))}'"
    return f"ass='{filename}'"


def _normalize_clip(source: Path, destination: Path, duration: float) -> None:
    run_command(
        [
            ffmpeg_binary(),
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            str(destination),
        ]
    )


def _background_from_clips(clips: list[Path], work_dir: Path, duration: float) -> Path:
    slice_length = duration / len(clips)
    pieces: list[Path] = []
    for index, clip in enumerate(clips):
        piece = work_dir / f"bg-{index}.mp4"
        _normalize_clip(clip, piece, slice_length)
        pieces.append(piece)
    if len(pieces) == 1:
        return pieces[0]
    listing = work_dir / "bg-concat.txt"
    listing.write_text(
        "".join(f"file '{piece.name}'\n" for piece in pieces),
        encoding="utf-8",
    )
    combined = work_dir / "bg.mp4"
    run_command(
        [
            ffmpeg_binary(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(combined),
        ]
    )
    return combined


def _gradient_source(duration: float) -> list[str]:
    gradient = (
        f"gradients=size={WIDTH}x{HEIGHT}:rate={FPS}:duration={duration:.3f}:speed=0.045:"
        "c0=0x14110E:c1=0x3E4A22:c2=0x1A1814:c3=0xD6E35A:c4=0x161410:"
        "c5=0x8A5A28:c6=0x1C1914:c7=0xE7D7B0"
    )
    return ["-f", "lavfi", "-i", gradient]


def render_reel(
    *,
    script: Script,
    audio_path: Path,
    words: list[WordTiming],
    duration: float,
    output_path: Path,
    work_dir: Path,
    broll: list[Path] | None = None,
) -> tuple[Path, Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    captions = work_dir / "captions.ass"
    render_ass(script, words, captions, duration=duration)
    video_filter = _ass_filter(captions)
    command = [ffmpeg_binary(), "-y"]
    clips = [path for path in (broll or []) if path.exists()]
    if clips:
        background = _background_from_clips(clips, work_dir, duration)
        command.extend(["-i", str(background)])
    else:
        command.extend(_gradient_source(duration + 0.2))
    command.extend(
        [
            "-i",
            str(audio_path),
            "-vf",
            video_filter,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    run_command(command)
    return output_path, captions

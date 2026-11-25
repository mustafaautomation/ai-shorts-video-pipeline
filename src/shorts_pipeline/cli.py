"""Command line for a keyless render, a script preview, and the HTTP API."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from pathlib import Path

from shorts_pipeline import __version__
from shorts_pipeline.pipeline import run_pipeline
from shorts_pipeline.publish.adapters import RealPublishDisabled
from shorts_pipeline.script.generator import generate_script
from shorts_pipeline.script.rubric import evaluate_script


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _configured(name: str) -> str:
    return "yes" if os.getenv(name) else "no"


def doctor() -> int:
    ffmpeg = shutil.which("ffmpeg") or "missing"
    ffprobe = shutil.which("ffprobe") or "missing"
    print(f"ai-shorts-video-pipeline {__version__}")
    print("portfolio demo — publish adapters are mock-only")
    print(f"ffmpeg: {ffmpeg}")
    print(f"ffprobe: {ffprobe}")
    print(f"SCRIPT_PROVIDER: {os.getenv('SCRIPT_PROVIDER', 'auto')}")
    print(f"VOICE_PROVIDER: {os.getenv('VOICE_PROVIDER', 'auto')}")
    print(f"GROQ_API_KEY: {_configured('GROQ_API_KEY')}")
    print(f"GEMINI_API_KEY: {_configured('GEMINI_API_KEY')}")
    print(f"PEXELS_API_KEY: {_configured('PEXELS_API_KEY')}")
    print(f"PUBLISH_DRY_RUN: {os.getenv('PUBLISH_DRY_RUN', 'true')}")
    return 0 if ffmpeg != "missing" and ffprobe != "missing" else 1


def _print_script(topic: str, provider: str | None) -> int:
    script = generate_script(topic, provider=provider)
    rubric = evaluate_script(script)
    payload = {
        "topic": script.topic,
        "hook": script.hook,
        "body": script.body,
        "cta": script.cta,
        "provider": script.provider,
        "full_text": script.spoken_text(),
        "estimated_seconds": rubric.estimated_seconds,
        "rubric": rubric.to_dict(),
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shorts-pipeline",
        description="Turn a topic into a vertical reel. Publishing is mocked.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    script = sub.add_parser("script", help="Write a hook, body, and CTA")
    script.add_argument("--topic", required=True)
    script.add_argument("--provider", choices=["auto", "groq", "gemini", "offline"])

    run = sub.add_parser("run", help="Render a 1080x1920 MP4")
    run.add_argument("--topic", required=True)
    run.add_argument("--out", type=Path, default=None)
    run.add_argument("--script-provider", choices=["auto", "groq", "gemini", "offline"])
    run.add_argument("--voice-provider", choices=["auto", "edge", "offline"], default="offline")
    run.add_argument("--publish", action="store_true", help="Write mock publish receipts")
    run.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Refuse live posting. Kept so a future client has a flag to flip.",
    )
    run.add_argument("--schedule", default=None, help="ISO timestamp stored on the mock payload")

    serve = sub.add_parser("serve", help="HTTP API for n8n, Make, and local clients")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)

    sub.add_parser("doctor", help="Show which tools and keys are configured")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "script":
        return _print_script(args.topic, args.provider)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("shorts_pipeline.api:app", host=args.host, port=args.port, reload=False)
        return 0
    if args.command == "run":
        try:
            result = run_pipeline(
                args.topic,
                args.out,
                script_provider=args.script_provider,
                voice_provider=args.voice_provider,
                publish=args.publish,
                dry_run=not args.no_dry_run,
                scheduled_at=args.schedule,
            )
        except (ValueError, RealPublishDisabled) as exc:
            logging.getLogger("shorts_pipeline").error("%s", exc)
            return 2
        print(result.model_dump_json(indent=2))
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

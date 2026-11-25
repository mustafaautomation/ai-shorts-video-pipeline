"""Optional portrait b-roll from the Pexels free API.

When PEXELS_API_KEY is unset, callers skip this module and the renderer draws
its own plates. Failures here never fail the reel.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.pexels.com/videos/search"


def search_portrait_videos(query: str, api_key: str, *, per_page: int = 6) -> list[dict]:
    response = httpx.get(
        SEARCH_URL,
        params={
            "query": query,
            "orientation": "portrait",
            "per_page": per_page,
            "size": "medium",
        },
        headers={"Authorization": api_key},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    videos = payload.get("videos", [])
    return videos if isinstance(videos, list) else []


def _best_file(video: dict) -> str | None:
    files = video.get("video_files") or []
    ranked: list[tuple[int, str]] = []
    for item in files:
        link = item.get("link")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if not link or height < width or height < 640:
            continue
        # Prefer a file close to 1080-wide so downloads stay small.
        ranked.append((abs(width - 1080) + abs(height - 1920) // 4, link))
    if not ranked:
        return None
    ranked.sort()
    return ranked[0][1]


def download_broll(query: str, api_key: str, destination: Path, *, limit: int = 2) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        videos = search_portrait_videos(query, api_key)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Pexels search failed: %s", exc.__class__.__name__)
        return []
    saved: list[Path] = []
    for video in videos:
        if len(saved) >= limit:
            break
        link = _best_file(video)
        if not link:
            continue
        target = destination / f"broll-{len(saved) + 1}.mp4"
        try:
            with httpx.stream("GET", link, timeout=60, follow_redirects=True) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for block in response.iter_bytes():
                        handle.write(block)
        except httpx.HTTPError as exc:
            logger.warning("Pexels download failed: %s", exc.__class__.__name__)
            continue
        if target.stat().st_size > 0:
            saved.append(target)
    return saved

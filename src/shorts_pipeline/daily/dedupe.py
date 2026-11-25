"""Idempotent store of reel ids that have already been used or posted."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class DedupeStore:
    path: Path
    used_ids: set[str] = field(default_factory=set)
    posts: list[dict] = field(default_factory=list)

    def load(self) -> DedupeStore:
        if not self.path.exists():
            return self
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.used_ids = set(raw.get("used_ids", []))
        self.posts = list(raw.get("posts", []))
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "used_ids": sorted(self.used_ids),
            "posts": self.posts,
        }
        self.path.write_text(json.dumps(document, indent=2), encoding="utf-8")

    def claim(self, reel_id: str) -> bool:
        """Return True the first time an id is seen. Later calls are no-ops."""
        if reel_id in self.used_ids:
            return False
        self.used_ids.add(reel_id)
        self.save()
        return True

    def log_post(self, reel_id: str, permalink: str) -> None:
        self.used_ids.add(reel_id)
        self.posts.append(
            {
                "reel_id": reel_id,
                "permalink": permalink,
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )
        self.save()

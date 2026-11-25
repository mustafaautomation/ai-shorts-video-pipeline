"""Turn a raw topic into a short phrase that can be spoken inside a reel."""

from __future__ import annotations

import hashlib


def normalize_topic(topic: str) -> str:
    cleaned = " ".join((topic or "").replace("\n", " ").split())
    cleaned = cleaned.strip(" .,:;!-")
    if not any(char.isalnum() for char in cleaned):
        return "this idea"
    return cleaned


_DANGLING = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "who",
    "with",
    "without",
}


def _strip_dangling(words: list[str]) -> list[str]:
    cleaned = list(words)
    while cleaned and cleaned[-1].lower().strip(".,!?;:") in _DANGLING:
        cleaned.pop()
    return cleaned


def clip_topic(topic: str, *, max_words: int = 12, max_chars: int = 78) -> str:
    words = _strip_dangling(normalize_topic(topic).split()[:max_words])
    text = " ".join(words)
    while words and len(text) > max_chars:
        words = _strip_dangling(words[:-1])
        text = " ".join(words)
    return text or "this idea"


def topic_seed(topic: str) -> int:
    digest = hashlib.sha256(normalize_topic(topic).lower().encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def spoken_topic(topic: str) -> str:
    """Phrase that must appear verbatim in an offline script."""
    return clip_topic(topic)


def contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in " ".join(text.lower().split())

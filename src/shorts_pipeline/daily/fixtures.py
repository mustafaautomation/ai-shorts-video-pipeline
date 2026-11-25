"""Bundled sample scrape. These are invented posts, not copied from an account."""

from __future__ import annotations

FIXTURE_REELS = [
    {
        "id": "reel_sample_alpha",
        "username": "fieldnotes",
        "caption": "One picture, then one action.",
        "views": 180_000,
        "likes": 12_400,
        "comments": 860,
        "video_url": "https://example.invalid/reels/alpha.mp4",
        "transcript": (
            "People remember a single picture. Show the messy desk, name the one "
            "thing to move, and ask them to try it before the next meeting."
        ),
    },
    {
        "id": "reel_sample_beta",
        "username": "fieldnotes",
        "caption": "A list of seven tips.",
        "views": 42_000,
        "likes": 900,
        "comments": 40,
        "video_url": "https://example.invalid/reels/beta.mp4",
        "transcript": "Here are seven tips about focus that you will forget.",
    },
    {
        "id": "reel_sample_gamma",
        "username": "studio.north",
        "caption": "Quiet walkthrough.",
        "views": 96_000,
        "likes": 5_100,
        "comments": 210,
        "video_url": "https://example.invalid/reels/gamma.mp4",
        "transcript": "Walk the idea from the problem to the ask without a list.",
    },
]

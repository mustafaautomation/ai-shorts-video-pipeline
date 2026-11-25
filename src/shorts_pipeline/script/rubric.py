"""Quality rubric for a 30–45 second short-form script."""

from __future__ import annotations

from dataclasses import dataclass

from shorts_pipeline.models import Script
from shorts_pipeline.script.topics import contains_phrase, spoken_topic
from shorts_pipeline.timing import estimate_seconds

CTA_VERBS = (
    "comment",
    "follow",
    "save",
    "send",
    "share",
    "start",
    "subscribe",
    "tap",
    "tell",
    "try",
    "watch",
)

MIN_SECONDS = 30.0
MAX_SECONDS = 45.0


@dataclass(frozen=True)
class RubricCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RubricResult:
    score: float
    passed: bool
    checks: list[RubricCheck]
    estimated_seconds: float

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "passed": self.passed,
            "estimated_seconds": self.estimated_seconds,
            "checks": [
                {"name": check.name, "passed": check.passed, "detail": check.detail}
                for check in self.checks
            ],
        }


def _words(text: str) -> list[str]:
    return [part for part in text.split() if part]


def _cta_has_verb(cta: str) -> bool:
    tokens = {token.strip(".,!?:;\"'").lower() for token in cta.split()}
    return any(verb in tokens for verb in CTA_VERBS)


def evaluate_script(script: Script) -> RubricResult:
    spoken = script.spoken_text()
    duration = estimate_seconds(spoken)
    hook_words = _words(script.hook)
    phrase = spoken_topic(script.topic)
    checks = [
        RubricCheck("hook_present", bool(script.hook.strip()), "hook is present"),
        RubricCheck(
            "hook_length",
            0 < len(hook_words) <= 24,
            f"{len(hook_words)} words",
        ),
        RubricCheck(
            "body_beats",
            2 <= len(script.body) <= 4,
            f"{len(script.body)} beats",
        ),
        RubricCheck(
            "body_nonempty",
            all(beat.strip() for beat in script.body),
            "every beat has text",
        ),
        RubricCheck("cta_present", bool(script.cta.strip()), "cta is present"),
        RubricCheck("cta_verb", _cta_has_verb(script.cta), "cta names an action"),
        RubricCheck(
            "duration_window",
            MIN_SECONDS <= duration <= MAX_SECONDS,
            f"{duration:.2f}s",
        ),
        RubricCheck(
            "topic_mentioned",
            contains_phrase(spoken, phrase),
            phrase,
        ),
        RubricCheck(
            "no_stage_directions",
            "[" not in spoken and "]" not in spoken and "#" not in spoken,
            "spoken words only",
        ),
    ]
    score = sum(1 for check in checks if check.passed) / len(checks)
    required = {
        "hook_present",
        "body_beats",
        "body_nonempty",
        "cta_present",
        "cta_verb",
        "duration_window",
        "topic_mentioned",
    }
    passed = all(check.passed for check in checks if check.name in required)
    return RubricResult(
        score=score,
        passed=passed,
        checks=checks,
        estimated_seconds=round(duration, 3),
    )

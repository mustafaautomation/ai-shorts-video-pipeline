"""Script writers: Groq, Gemini, then a deterministic offline fallback.

No provider is required. Tests and CI use the offline writer, which always
returns a hook, two to four body beats, and a CTA inside the 30–45s window.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable

import httpx

from shorts_pipeline.models import Script
from shorts_pipeline.script.rubric import MAX_SECONDS, MIN_SECONDS, evaluate_script
from shorts_pipeline.script.topics import spoken_topic, topic_seed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write spoken scripts for a 30 to 45 second vertical short. "
    "Return JSON with keys hook (string), body (array of 2 to 4 short sentences), "
    "and cta (string). No markdown, no hashtags, no stage directions, no brackets. "
    "The hook is one or two spoken sentences. The CTA tells the viewer to save, "
    "share, follow, comment, or try something. Mention the topic in the words "
    "the viewer hears. Target 75 to 100 spoken words."
)

HOOKS = (
    "Stop scrolling. {Topic} is simpler than the long version.",
    "Here is the short version of {topic}.",
    "{Topic} gets easier when you keep one shape.",
    "{Topic}, with the extra parts already cut.",
    "Before you swipe, take the useful version of {topic}.",
)

BEATS = (
    "Open on the problem in plain words, then let {topic} be the fix.",
    "Give one picture a stranger could repeat after hearing it a single time.",
    "Drop every detail that does not change what the viewer should do next.",
    "Use one example so the idea can land on the very first pass.",
    "Say what changes today when someone actually applies {topic}.",
    "Contrast the slow way with the one-step way, then stop talking.",
    "Keep every line spoken. If you would not say it out loud, cut it.",
    "Name the person this helps, and the exact moment they need it.",
)

CTAS = (
    "Save this and try {topic} on the next thing you explain.",
    "Follow for the short version, and comment the topic you want next.",
    "Share this with someone who needs {topic} explained cleanly.",
    "Tap save, then teach {topic} once while it is still fresh.",
)

EXTENSIONS = (
    "Say it like you are talking to one person across the table.",
    "Keep a single example in the frame the whole time.",
    "Do not add a second idea after that picture lands.",
    "Let the last line be the thing they should do next.",
    "Stop before you explain the background or the history.",
    "Trust that one clear picture is enough for this short.",
    "Leave a little room for the viewer to try it today.",
    "Cut any word that does not change the next step.",
)

FetchJson = Callable[..., dict]


def _post_json(url: str, headers: dict, payload: dict, timeout: float = 30.0) -> dict:
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def script_from_payload(topic: str, data: dict, provider: str) -> Script:
    if "hook" not in data or "cta" not in data or "body" not in data:
        raise ValueError("script JSON is missing hook, body, or cta")
    hook = str(data["hook"]).strip()
    cta = str(data["cta"]).strip()
    raw_body = data["body"]
    if isinstance(raw_body, str):
        parts = re.split(r"[\n]+|(?<=[.!?])\s+", raw_body)
        body = [part.strip() for part in parts if part.strip()]
    elif isinstance(raw_body, list):
        body = [str(part).strip() for part in raw_body if str(part).strip()]
    else:
        raise ValueError("body must be a list of sentences or a string")
    if not hook or not cta or not 2 <= len(body) <= 4:
        raise ValueError("script shape is outside hook, 2-4 beats, and cta")
    return Script(topic=topic, hook=hook, body=body, cta=cta, provider=provider)


def _phrase_forms(phrase: str) -> dict[str, str]:
    if phrase.isupper() and len(phrase) <= 4:
        lower = phrase
    else:
        lower = phrase[:1].lower() + phrase[1:]
    upper = phrase[:1].upper() + phrase[1:]
    return {"topic": lower, "Topic": upper}


def _hook_for(seed: int, forms: dict[str, str]) -> str:
    for offset in range(len(HOOKS)):
        hook = HOOKS[(seed + offset) % len(HOOKS)].format(**forms)
        words = [word.strip(".,!?;:").lower() for word in hook.split()]
        doubled = any(left == right for left, right in zip(words, words[1:], strict=False))
        if doubled or len(words) > 24:
            continue
        return hook
    return f"{forms['Topic']} in one clean pass."


def _build(topic: str, hook: str, body: list[str], cta: str) -> Script | None:
    if len(hook.split()) > 24:
        return None
    script = Script(topic=topic, hook=hook, body=body, cta=cta, provider="offline")
    result = evaluate_script(script)
    if result.passed and result.score == 1:
        return script
    return None


def offline_script(topic: str) -> Script:
    """Deterministic script. The same topic always yields the same words."""
    phrase = spoken_topic(topic)
    forms = _phrase_forms(phrase)
    seed = topic_seed(topic)
    hook = _hook_for(seed, forms)
    cta = CTAS[seed % len(CTAS)].format(**forms)
    rotated = [BEATS[(seed + offset) % len(BEATS)].format(**forms) for offset in range(len(BEATS))]
    extras = [EXTENSIONS[(seed + offset) % len(EXTENSIONS)] for offset in range(len(EXTENSIONS))]
    for count in (2, 3, 4):
        body = rotated[:count]
        script = _build(topic, hook, body, cta)
        if script is not None:
            return script
        for used in range(1, len(extras) + 1):
            tail = " ".join(extras[:used])
            extended = body[:-1] + [f"{body[-1]} {tail}"]
            script = _build(topic, hook, extended, cta)
            if script is not None:
                return script
    short_hook = f"{forms['Topic']} in one clean pass."
    short_cta = "Save this and try it once today."
    body = [
        "Start with the problem the viewer already feels.",
        "Show one example they can picture immediately.",
        f"Then come back to {forms['topic']} and cut anything extra.",
    ]
    script = _build(topic, short_hook, body, short_cta)
    if script is not None:
        return script
    for used in range(1, len(extras) + 1):
        extended = body[:-1] + [f"{body[-1]} {' '.join(extras[:used])}"]
        script = _build(topic, short_hook, extended, short_cta)
        if script is not None:
            return script
    raise RuntimeError("offline script writer could not fit the 30-45s window")


def _user_prompt(topic: str, hint: str | None) -> str:
    phrase = spoken_topic(topic)
    lines = [
        f"Topic: {topic.strip()}",
        f"Say this phrase out loud somewhere in the script: {phrase}",
        "Spoken length must land between 30 and 45 seconds, about 75 to 100 words.",
    ]
    if hint:
        lines.append(hint)
    return "\n".join(lines)


def _groq_request(topic: str, hint: str | None) -> dict:
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    key = os.environ["GROQ_API_KEY"]
    payload = {
        "model": model,
        "temperature": 0.6,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(topic, hint)},
        ],
    }
    data = _post_json(
        "https://api.groq.com/openai/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        payload,
    )
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(_strip_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("Groq returned a non-object")
    return parsed


def _gemini_request(topic: str, hint: str | None) -> dict:
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    key = os.getenv("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
    prompt = SYSTEM_PROMPT + "\n\n" + _user_prompt(topic, hint)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"},
    }
    data = _post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        {"x-goog-api-key": key, "Content-Type": "application/json"},
        payload,
    )
    content = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(_strip_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini returned a non-object")
    return parsed


def _from_provider(topic: str, provider: str, fetch: FetchJson) -> Script | None:
    hint = None
    for _attempt in range(2):
        try:
            payload = fetch(topic, hint)
            script = script_from_payload(topic, payload, provider)
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("%s script attempt failed: %s", provider, exc.__class__.__name__)
            return None
        result = evaluate_script(script)
        if result.passed:
            return script
        hint = (
            f"The previous draft was {result.estimated_seconds:.1f}s and failed "
            f"{', '.join(check.name for check in result.checks if not check.passed)}. "
            f"Rewrite it so the spoken length is between {MIN_SECONDS:.0f} and "
            f"{MAX_SECONDS:.0f} seconds."
        )
    return None


def _gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _provider_order(choice: str) -> list[str]:
    if choice == "offline":
        return ["offline"]
    if choice == "groq":
        order = ["groq"]
        if _gemini_configured():
            order.append("gemini")
        order.append("offline")
        return order
    if choice == "gemini":
        return ["gemini", "offline"]
    if choice != "auto":
        logger.warning("unknown SCRIPT_PROVIDER %s, using auto", choice)
    order = []
    if os.getenv("GROQ_API_KEY"):
        order.append("groq")
    if _gemini_configured():
        order.append("gemini")
    order.append("offline")
    return order


def generate_script(topic: str, provider: str | None = None) -> Script:
    cleaned = " ".join((topic or "").split())
    if not cleaned:
        raise ValueError("topic is required")
    if len(cleaned) > 240:
        raise ValueError("topic must be 240 characters or fewer")
    choice = (provider or os.getenv("SCRIPT_PROVIDER") or "auto").strip().lower()
    for name in _provider_order(choice):
        if name == "offline":
            return offline_script(cleaned)
        fetch = _groq_request if name == "groq" else _gemini_request
        script = _from_provider(cleaned, name, fetch)
        if script is not None:
            return script
        logger.info("falling back from %s", name)
    return offline_script(cleaned)

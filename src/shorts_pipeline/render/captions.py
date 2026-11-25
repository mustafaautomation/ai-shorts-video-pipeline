"""Word-synced caption cues and an ASS file ffmpeg can burn in with libass."""

from __future__ import annotations

import re
from pathlib import Path

from shorts_pipeline.models import CaptionCue, Script, WordTiming

MAX_LINE_WORDS = 4
MAX_LINE_CHARS = 28


def _norm(token: str) -> str:
    return "".join(char for char in token.lower() if char.isalnum())


def _script_sections(script: Script) -> list[tuple[str, str]]:
    sections = [("HOOK", script.hook)]
    sections.extend((f"POINT {index + 1}", beat) for index, beat in enumerate(script.body))
    sections.append(("TRY THIS", script.cta))
    return sections


def _script_tokens(script: Script) -> list[tuple[str, str, bool]]:
    tokens: list[tuple[str, str, bool]] = []
    for label, text in _script_sections(script):
        words = text.split()
        for index, word in enumerate(words):
            normalized = _norm(word)
            if not normalized:
                continue
            boundary = word[-1:] in ".!?" or index == len(words) - 1
            tokens.append((label, normalized, boundary))
    return tokens


def word_metadata(script: Script, words: list[WordTiming]) -> list[tuple[str, bool]]:
    """Align spoken tokens to the script so section labels survive TTS tokenization."""
    tokens = _script_tokens(script)
    if not words:
        return []
    if not tokens:
        return [("BODY", False) for _ in words]
    meta: list[tuple[str, bool]] = []
    cursor = 0
    for word in words:
        spoken = _norm(word.text)
        match_at = None
        window = range(cursor, min(cursor + 4, len(tokens)))
        for look in window:
            label_norm = tokens[look][1]
            if spoken == label_norm or (
                spoken
                and label_norm
                and len(spoken) > 1
                and len(label_norm) > 1
                and (spoken in label_norm or label_norm in spoken)
            ):
                match_at = look
                break
        if match_at is None:
            label = tokens[min(cursor, len(tokens) - 1)][0]
            meta.append((label, False))
            continue
        label, _normalized, boundary = tokens[match_at]
        cursor = match_at + 1
        meta.append((label, boundary))
    return meta


def chunk_words(
    words: list[WordTiming],
    *,
    max_words: int = MAX_LINE_WORDS,
    max_chars: int = MAX_LINE_CHARS,
    breaks: set[int] | None = None,
) -> list[list[WordTiming]]:
    forced = breaks or set()
    chunks: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for index, word in enumerate(words):
        if current and index in forced:
            chunks.append(current)
            current = [word]
            continue
        prospective = [*current, word]
        length = sum(len(item.text) for item in prospective) + max(0, len(prospective) - 1)
        if current and (len(prospective) > max_words or length > max_chars):
            chunks.append(current)
            current = [word]
        else:
            current = prospective
    if current:
        chunks.append(current)
    return chunks


def build_caption_cues(words: list[WordTiming], script: Script | None = None) -> list[CaptionCue]:
    breaks: set[int] = set()
    if script is not None:
        for index, (_label, boundary) in enumerate(word_metadata(script, words)):
            if boundary and index + 1 < len(words):
                breaks.add(index + 1)
    cues: list[CaptionCue] = []
    for chunk in chunk_words(words, breaks=breaks):
        line_words = [word.text for word in chunk]
        for index, word in enumerate(chunk):
            if index + 1 < len(chunk):
                end = chunk[index + 1].start
            else:
                end = word.end
            end = max(end, word.start + 0.05)
            cues.append(
                CaptionCue(
                    start=round(word.start, 3),
                    end=round(end, 3),
                    active=word.text,
                    active_index=index,
                    line_words=line_words,
                )
            )
    return cues


def ass_timestamp(seconds: float) -> str:
    centiseconds = int(round(max(0.0, seconds) * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _dialogue(start: float, end: float, style: str, text: str) -> str:
    return f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},{style},,0,0,0,,{text}"


def _section_title(script: Script, label: str) -> str:
    if label == "HOOK":
        text = script.hook
    elif label == "TRY THIS":
        text = script.cta
    elif label.startswith("POINT "):
        number = int(label.split()[-1]) - 1
        text = script.body[number] if 0 <= number < len(script.body) else ""
    else:
        text = ""
    sentence = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    return sentence


def section_spans(script: Script, words: list[WordTiming]) -> list[tuple[str, float, float, str]]:
    meta = word_metadata(script, words)
    spans: list[tuple[str, float, float, str]] = []
    start = 0
    for index, (label, _boundary) in enumerate([*meta, ("", False)]):
        if index < len(meta) and (index == start or label == meta[start][0]):
            continue
        chunk = words[start:index]
        if chunk:
            section_label = meta[start][0]
            spans.append(
                (
                    section_label,
                    chunk[0].start,
                    chunk[-1].end,
                    _section_title(script, section_label),
                )
            )
        start = index
    return spans


def render_ass(
    script: Script,
    words: list[WordTiming],
    destination: Path,
    *,
    duration: float,
) -> list[CaptionCue]:
    cues = build_caption_cues(words, script)
    events: list[str] = [
        _dialogue(0, duration, "Footer", ass_escape("PORTFOLIO DEMO  ·  PUBLISH IS MOCKED")),
        _dialogue(0, duration, "Rule", r"{\p1}m -72 -4 l 72 -4 72 4 -72 4{\p0}"),
    ]
    for label, start, end, preview in section_spans(script, words):
        events.append(_dialogue(start, max(end, start + 0.2), "Label", ass_escape(label)))
        events.append(_dialogue(start, max(end, start + 0.2), "Kinetic", ass_escape(preview)))
    for cue in cues:
        pieces: list[str] = []
        for index, word in enumerate(cue.line_words):
            escaped = ass_escape(word)
            if index == cue.active_index:
                pieces.append(r"{\c&H0000E5FF&}" + escaped + r"{\c&H00FFFFFF&}")
            else:
                pieces.append(escaped)
        events.append(_dialogue(cue.start, cue.end, "Caption", " ".join(pieces)))

    document = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                "Style: Caption,DejaVu Sans,74,&H00FFFFFF,&H000000FF,&H00000000,"
                "&H64000000,-1,0,0,0,100,100,0,0,1,7,0,2,80,80,460,1"
            ),
            (
                "Style: Kinetic,DejaVu Sans,52,&H00F7F4EC,&H000000FF,&H00110E0C,"
                "&H00000000,-1,0,0,0,100,100,0,0,1,3,0,8,90,90,250,1"
            ),
            (
                "Style: Label,DejaVu Sans,30,&H0000E5FF,&H000000FF,&H00000000,"
                "&H00000000,-1,0,0,0,100,100,3,0,1,0,0,8,90,90,168,1"
            ),
            (
                "Style: Rule,DejaVu Sans,20,&H0000E5FF,&H000000FF,&H00000000,"
                "&H00000000,0,0,0,0,100,100,0,0,1,0,0,8,0,0,228,1"
            ),
            (
                "Style: Footer,DejaVu Sans,26,&H99F4EFE6,&H000000FF,&H00000000,"
                "&H00000000,0,0,0,0,100,100,2,0,1,0,0,2,70,70,78,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            *events,
            "",
        ]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return cues

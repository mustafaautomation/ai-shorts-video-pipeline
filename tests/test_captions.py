from shorts_pipeline.render.captions import (
    ass_timestamp,
    build_caption_cues,
    render_ass,
    section_spans,
)
from shorts_pipeline.script.generator import offline_script
from shorts_pipeline.timing import plan_timings, timeline_duration


def test_caption_cues_track_every_word() -> None:
    script = offline_script("caption timing")
    words = plan_timings(script.spoken_text())
    cues = build_caption_cues(words)
    assert len(cues) == len(words)
    for word, cue, follower in zip(words, cues, [*words[1:], None], strict=True):
        assert cue.active == word.text
        assert abs(cue.start - word.start) < 0.02
        assert cue.end >= word.end - 0.02 or (
            follower is not None and abs(cue.end - follower.start) < 0.02
        )
        assert cue.end > cue.start
        assert word.text in cue.line_words
        assert len(cue.line_words) <= 4
    for previous, current in zip(cues, cues[1:], strict=False):
        assert current.start >= previous.start
        assert previous.end <= current.start + 0.001 or previous.line != current.line


def test_caption_lines_break_on_sentences() -> None:
    script = offline_script("sentence breaks")
    words = plan_timings(script.spoken_text())
    cues = build_caption_cues(words, script)
    for cue in cues:
        earlier = cue.line_words[:-1]
        assert not any(word[-1:] in ".!?" for word in earlier)
    spans = [label for label, _start, _end, _title in section_spans(script, words)]
    assert spans[0] == "HOOK"
    assert spans[-1] == "TRY THIS"
    assert any(label.startswith("POINT") for label in spans)


def test_ass_file_uses_word_timestamps(tmp_path) -> None:
    script = offline_script("burned in captions")
    words = plan_timings(script.spoken_text())
    destination = tmp_path / "captions.ass"
    render_ass(script, words, destination, duration=timeline_duration(words))
    text = destination.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in text
    assert "PlayResY: 1920" in text
    assert ass_timestamp(words[0].start) in text
    assert words[0].text in text
    assert "PORTFOLIO DEMO" in text
    assert "HOOK" in text
    assert "TRY THIS" in text

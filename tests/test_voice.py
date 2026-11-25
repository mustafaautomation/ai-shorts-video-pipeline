import wave

from shorts_pipeline.models import WordTiming
from shorts_pipeline.timing import align_timings, plan_timings
from shorts_pipeline.voice.synthesize import synthesize_offline


def test_offline_voice_matches_planned_words(tmp_path) -> None:
    text = "Save this and try the short version once today."
    voice = synthesize_offline(text, tmp_path / "voice.wav")
    assert [word.text for word in voice.words] == text.split()
    assert voice.words == plan_timings(text)
    assert voice.duration >= voice.words[-1].end
    with wave.open(voice.audio_path, "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 22050
        assert handle.getnframes() > 0


def test_long_timings_are_scaled_into_the_audio() -> None:
    words = [
        WordTiming(text="one", start=0.0, end=2.0),
        WordTiming(text="two", start=2.2, end=4.0),
    ]
    aligned = align_timings(words, audio_duration=2.0)
    assert aligned[-1].end <= 2.0
    assert aligned[0].start < aligned[1].start
    assert [word.text for word in aligned] == ["one", "two"]


def test_matching_timings_stay_put() -> None:
    words = plan_timings("Save this example.")
    aligned = align_timings(words, audio_duration=words[-1].end + 0.45)
    assert aligned == words

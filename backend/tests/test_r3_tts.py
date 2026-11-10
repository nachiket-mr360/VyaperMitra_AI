from __future__ import annotations

from tts_sentences import split_speakable
from tts_session import play_speakable_chunks


def test_one_sentence_single_chunk():
    assert split_speakable("Today's recorded sales are 80 rupees.") == [
        "Today's recorded sales are 80 rupees."
    ]


def test_multi_sentence_english():
    parts = split_speakable(
        "This period recorded sales of 885 rupees in 5 bills. Today separately: 0 rupees in 0 bills. Not cash or profit."
    )
    assert len(parts) >= 2
    assert parts[0].startswith("This period")
    assert "Not cash" in parts[-1]


def test_hindi_danda_and_indic():
    hi = split_speakable("आज दर्ज बिक्री 80 रुपये है। यह नकद नहीं है।")
    assert len(hi) >= 2
    kn = split_speakable("ಇಂದು ಮಾರಾಟ 80 ರೂ. ಇದು ಲಾಭ ಅಲ್ಲ.")
    assert kn
    mr = split_speakable("आज विक्री 80 रुपये आहे. रोकड नाही.")
    assert len(mr) >= 1


def test_no_split_decimals_currency_abbrev():
    text = "Rice is 12.50 rupees per kg. Dr. Rao sold 2 kg."
    parts = split_speakable(text)
    assert any("12.50" in p for p in parts)
    assert not any(p.strip() == "50" for p in parts)


def test_short_fallback():
    assert len(split_speakable("Done.")) == 1


def test_queue_plays_in_order_serialized():
    spoken: list[str] = []
    played: list[str] = []

    def speak(chunk: str):
        spoken.append(chunk)
        return chunk

    def play(blob: str):
        played.append(blob)

    text = "First sentence is long enough to stand alone here. Second sentence is also long enough to keep."
    out = play_speakable_chunks(text, turn=1, is_current=lambda t: t == 1, speak=speak, play=play)
    assert out["played"] == list(range(len(out["played"])))
    assert played == spoken[: len(played)] or played == [spoken[i] for i in out["played"]]
    assert out["tts_requests"] == out["chunks"]
    assert out["overlap"] is False
    assert out["speak_order"] == [0, 1]
    assert out["first_play_index"] == 0


def test_first_chunk_failure_continues():
    def speak(chunk: str):
        if chunk.startswith("First"):
            raise RuntimeError("tts")
        return chunk

    played: list[str] = []
    text = "First sentence is long enough to stand alone here. Second sentence is also long enough to keep."
    out = play_speakable_chunks(
        text, turn=1, is_current=lambda t: True, speak=speak, play=played.append
    )
    assert out["skipped"] >= 1
    assert out["played"]
    assert out["played"][0] == 1


def test_later_chunk_failure_does_not_block():
    def speak(chunk: str):
        if "Second" in chunk:
            raise RuntimeError("tts")
        return chunk

    played: list[int] = []
    text = (
        "First sentence is long enough to stand alone here. "
        "Second sentence is also long enough to keep. "
        "Third sentence finishes the spoken reply cleanly."
    )
    out = play_speakable_chunks(
        text,
        turn=1,
        is_current=lambda t: True,
        speak=speak,
        play=lambda b: played.append(b),
    )
    assert 0 in out["played"]
    assert 1 not in out["played"]
    assert 2 in out["played"]


def test_interrupt_drops_stale():
    current = {"t": 1}
    played: list[str] = []
    n = {"i": 0}

    def speak(chunk: str):
        n["i"] += 1
        if n["i"] == 1:
            current["t"] = 2
        return chunk

    text = "First sentence is long enough to stand alone here. Second sentence is also long enough to keep."
    out = play_speakable_chunks(
        text,
        turn=1,
        is_current=lambda t: t == current["t"],
        speak=speak,
        play=played.append,
    )
    assert played == []
    assert out["played"] == []


def test_no_duplicate_play():
    played: list[str] = []
    text = "First sentence is long enough to stand alone here. Second sentence is also long enough to keep."
    play_speakable_chunks(
        text, turn=1, is_current=lambda t: True, speak=lambda c: c, play=played.append
    )
    assert len(played) == len(set(played))

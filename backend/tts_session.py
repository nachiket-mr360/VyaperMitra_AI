"""Sentence TTS queue. Keep in sync with frontend/src/audio/ttsSession.ts"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tts_sentences import split_speakable


def play_speakable_chunks(
    text: str,
    *,
    turn: int,
    is_current: Callable[[int], bool],
    speak: Callable[[str], Any | None],
    play: Callable[[Any], None],
) -> dict[str, Any]:
    chunks = split_speakable(text)
    timings: dict[str, Any] = {
        "tts_requests": 0,
        "chunks": len(chunks),
        "skipped": 0,
        "played": [],
        "speak_order": [],
        "first_play_index": None,
        "overlap": False,
    }
    if not chunks:
        return timings

    for i, _chunk in enumerate(chunks):
        if not is_current(turn):
            break
        timings["tts_requests"] += 1
        timings["speak_order"].append(i)
        try:
            blob = speak(chunks[i])
        except Exception:
            timings["skipped"] += 1
            continue
        if not is_current(turn):
            break
        if blob is None:
            timings["skipped"] += 1
            continue
        if timings["first_play_index"] is None:
            timings["first_play_index"] = i
        try:
            play(blob)
            timings["played"].append(i)
        except Exception:
            timings["skipped"] += 1
    return timings

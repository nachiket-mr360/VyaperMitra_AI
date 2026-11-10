"""Mirrors frontend AdaptiveVad energy rules for isolated tests. Not live microphone proof."""

from __future__ import annotations

import math

MIN_SPEECH_MS = 450
SILENCE_MS = 1000
MAX_UTTERANCE_MS = 25000
START_CONFIRM_MS = 180
MIN_NOISE = 0.004
MAX_NOISE = 0.08
BARGE_RMS = 0.05


def rms(frame: list[float]) -> float:
    if not frame:
        return 0.0
    return math.sqrt(sum(s * s for s in frame) / len(frame))


def speech_threshold(noise: float) -> float:
    n = min(MAX_NOISE, max(MIN_NOISE, noise))
    return min(0.12, max(0.012, n * 2.6 + 0.006))


def barge_threshold(noise: float) -> float:
    return max(BARGE_RMS, speech_threshold(noise) * 2.4)


class AdaptiveVad:
    def __init__(self) -> None:
        self.noise = 0.012
        self.calib_ms = 0.0
        self.start_ms = 0.0
        self.speech_ms = 0.0
        self.silence_ms = 0.0
        self.in_speech = False
        self.uttered = False
        self.elapsed_ms = 0.0

    def reset_utterance(self) -> None:
        self.start_ms = 0.0
        self.speech_ms = 0.0
        self.silence_ms = 0.0
        self.in_speech = False
        self.uttered = False
        self.elapsed_ms = 0.0

    def recalibrate(self) -> None:
        self.noise = 0.012
        self.calib_ms = 0.0
        self.reset_utterance()

    def process(self, energy: float, frame_ms: float, *, speaking: bool = False, cooldown: bool = False) -> dict:
        thr = speech_threshold(self.noise)
        barge_thr = barge_threshold(self.noise)
        if speaking and not cooldown and energy >= barge_thr:
            self.reset_utterance()
            self.in_speech = True
            self.uttered = True
            self.speech_ms = frame_ms
            return {"start": True, "end": False, "barge": True, "in_speech": True}
        if speaking or cooldown:
            return {"start": False, "end": False, "barge": False, "in_speech": False}
        self.elapsed_ms += frame_ms
        above = energy >= thr
        near_noise = energy < self.noise * 1.35 + 0.002
        if not self.in_speech:
            if near_noise or not above:
                a = 0.25 if self.calib_ms < 400 else 0.04
                self.noise = min(MAX_NOISE, max(MIN_NOISE, self.noise * (1 - a) + energy * a))
                self.calib_ms += frame_ms
                self.start_ms = 0.0
                return {"start": False, "end": False, "barge": False, "in_speech": False, "noise": self.noise}
            self.start_ms += frame_ms
            if self.start_ms < START_CONFIRM_MS:
                return {"start": False, "end": False, "barge": False, "in_speech": False}
            self.in_speech = True
            self.uttered = True
            self.speech_ms = self.start_ms
            self.silence_ms = 0.0
            return {"start": True, "end": False, "barge": False, "in_speech": True}
        if above:
            self.speech_ms += frame_ms
            self.silence_ms = 0.0
        else:
            self.silence_ms += frame_ms
        end = self.uttered and self.speech_ms >= MIN_SPEECH_MS and (
            self.silence_ms >= SILENCE_MS or self.elapsed_ms >= MAX_UTTERANCE_MS
        )
        if end:
            self.reset_utterance()
            return {"start": False, "end": True, "barge": False, "in_speech": False}
        if self.silence_ms > SILENCE_MS * 1.6 and self.speech_ms < MIN_SPEECH_MS:
            self.reset_utterance()
            return {"start": False, "end": False, "barge": False, "in_speech": False}
        return {"start": False, "end": False, "barge": False, "in_speech": True, "noise": self.noise}


def run(energies: list[float], frame_ms: float = 30.0, **kw) -> list[dict]:
    vad = AdaptiveVad()
    return [vad.process(e, frame_ms, **kw) | {"energy": e, "noise": vad.noise} for e in energies]

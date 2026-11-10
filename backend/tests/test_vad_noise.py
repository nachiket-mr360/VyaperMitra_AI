from __future__ import annotations

from vad_adaptive import AdaptiveVad, run, speech_threshold


def test_silence_does_not_start_speech():
    out = run([0.002] * 80)
    assert not any(d["start"] or d["end"] for d in out)


def test_fan_noise_raises_baseline_without_utterance():
    vad = AdaptiveVad()
    started = False
    for _ in range(120):
        d = vad.process(0.03, 30)
        if d["start"]:
            started = True
    assert vad.noise > 0.02
    assert speech_threshold(vad.noise) > 0.03
    assert not started


def test_traffic_like_noise():
    energies = [0.02 + (i % 5) * 0.002 for i in range(100)]
    out = run(energies)
    assert not any(d["end"] for d in out)


def test_short_impulse_not_speech():
    seq = [0.008] * 20 + [0.2] * 2 + [0.008] * 40
    out = run(seq)
    assert not any(d["end"] for d in out)


def test_short_speech_starts_and_ends():
    seq = [0.006] * 40 + [0.08] * 25 + [0.006] * 50
    out = run(seq)
    assert any(d["start"] for d in out)
    assert any(d["end"] for d in out)


def test_quiet_speech_after_low_noise():
    seq = [0.005] * 50 + [0.02] * 30 + [0.005] * 50
    out = run(seq)
    assert any(d["start"] for d in out)
    assert any(d["end"] for d in out)


def test_speech_in_noise():
    noise = 0.025
    vad = AdaptiveVad()
    for _ in range(80):
        vad.process(noise, 30)
    started = ended = False
    for _ in range(30):
        d = vad.process(0.12, 30)
        started = started or d["start"]
    for _ in range(50):
        d = vad.process(noise, 30)
        ended = ended or d["end"]
    assert started
    assert ended


def test_silence_timeout_hangover():
    seq = [0.006] * 20 + [0.09] * 20 + [0.006] * 5
    early = run(seq)
    assert not any(d["end"] for d in early)
    seq2 = [0.006] * 20 + [0.09] * 20 + [0.006] * 40
    assert any(d["end"] for d in run(seq2))


def test_barge_during_playback():
    vad = AdaptiveVad()
    d = vad.process(0.2, 30, speaking=True, cooldown=False)
    assert d["barge"] is True


def test_recalibrate_resets_floor():
    vad = AdaptiveVad()
    for _ in range(80):
        vad.process(0.028, 30)
    high = vad.noise
    assert high > 0.012
    vad.recalibrate()
    assert vad.noise == 0.012
    assert high > vad.noise

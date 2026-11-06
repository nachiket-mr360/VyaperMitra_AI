from __future__ import annotations

import io
import wave


def make_wav(*, seconds: float = 0.2, rate: int = 8000) -> bytes:
    frames = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()

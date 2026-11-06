"""Validate uploaded audio without trusting the filename or browser MIME type."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass

from config import Config
from errors import ApiError

ALLOWED_EXTS = frozenset({"wav", "mp3", "ogg", "flac", "aac", "m4a"})

MIME_TO_EXT = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "audio/aac": "aac",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
}


@dataclass
class AudioClip:
    data: bytes
    filename: str
    sniffed: str
    duration_seconds: float | None


def _ext(name: str) -> str:
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].strip().lower()


def sniff_format(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:4] == b"OggS":
        return "ogg"
    if data[4:8] == b"ftyp":
        return "m4a"
    if data[:3] == b"ID3":
        return "mp3"
    if data[:2] == b"\xff\xf1" or data[:2] == b"\xff\xf9":
        return "aac"
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        if data[1] & 0x06 == 0:
            return "mp3"
        return "mp3"
    return None


def _wav_duration(data: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def _mutagen_duration(data: bytes, sniffed: str) -> float | None:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None
    try:
        audio = MutagenFile(io.BytesIO(data))
        if audio is None or not audio.info:
            return None
        return float(audio.info.length)
    except Exception:
        if sniffed == "wav":
            return _wav_duration(data)
        return None


def duration_seconds(data: bytes, sniffed: str) -> float | None:
    if sniffed == "wav":
        return _wav_duration(data)
    return _mutagen_duration(data, sniffed)


def validate_audio(*, data: bytes, filename: str, content_type: str | None) -> AudioClip:
    if not data:
        raise ApiError("Recording is empty.", 400, "empty_audio")
    if len(data) > Config.GNANI_STT_MAX_BYTES:
        raise ApiError("Audio file is too large.", 400, "audio_too_large")

    sniffed = sniff_format(data)
    if sniffed not in ALLOWED_EXTS:
        raise ApiError(
            "Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC, or M4A.",
            400,
            "unsupported_format",
        )

    ext = _ext(filename) if filename else sniffed
    if ext and ext not in ALLOWED_EXTS:
        raise ApiError(
            "Unsupported audio format. Use WAV, MP3, OGG, FLAC, AAC, or M4A.",
            400,
            "unsupported_format",
        )
    if ext and ext != sniffed and not (ext == "aac" and sniffed in {"aac", "m4a"}):
        if not (ext == "mp3" and sniffed == "mp3"):
            if ext != sniffed:
                raise ApiError(
                    "File extension does not match the audio contents.",
                    400,
                    "invalid_mime",
                )

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime not in {"application/octet-stream", ""}:
        mapped = MIME_TO_EXT.get(mime)
        if mapped is None:
            raise ApiError("Unsupported audio MIME type.", 400, "invalid_mime")
        if mapped != sniffed and not (mapped == "aac" and sniffed in {"aac", "m4a"}):
            raise ApiError(
                "MIME type does not match the audio contents.",
                400,
                "invalid_mime",
            )

    seconds = duration_seconds(data, sniffed)
    if seconds is None:
        raise ApiError("Could not read audio duration.", 400, "audio_duration_unknown")
    if seconds > Config.GNANI_STT_MAX_SECONDS + 0.05:
        raise ApiError("Audio must be 30 seconds or shorter.", 400, "audio_too_long")
    if seconds <= 0:
        raise ApiError("Recording is empty.", 400, "empty_audio")

    safe_name = filename if filename and _ext(filename) == sniffed else f"clip.{sniffed}"
    return AudioClip(data=data, filename=safe_name, sniffed=sniffed, duration_seconds=seconds)

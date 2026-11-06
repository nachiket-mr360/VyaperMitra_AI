"""Voice STT tests. HTTP to Gnani is mocked — this does not prove live connectivity."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

from wavutil import make_wav


def _post(client, data=None, extra=None, filename="clip.wav", content_type="audio/wav"):
    body = dict(extra or {})
    if data is not None:
        body["audio"] = (BytesIO(data), filename, content_type)
    return client.post("/api/voice/transcribe", data=body)


def test_missing_audio(client):
    res = client.post("/api/voice/transcribe", data={"language": "auto"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "missing_audio"


def test_empty_audio(client):
    res = _post(client, data=b"")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "empty_audio"


def test_unsupported_extension(client):
    res = _post(client, data=b"not audio", filename="notes.txt", content_type="text/plain")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] in {"unsupported_format", "invalid_mime"}


def test_invalid_mime_mismatch(client):
    res = _post(client, data=b"hello world" * 20, filename="clip.wav", content_type="audio/wav")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] in {"unsupported_format", "invalid_mime"}


def test_audio_too_long(client):
    wav = make_wav(seconds=31)
    res = _post(client, data=wav)
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "audio_too_long"


def test_missing_api_key(client, monkeypatch):
    monkeypatch.setattr("config.Config.GNANI_API_KEY", "")
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "")
    wav = make_wav()
    res = _post(client, data=wav)
    assert res.status_code == 503
    assert res.get_json()["error"]["code"] == "gnani_not_configured"


def _ok_payload(**extra):
    body = {
        "success": True,
        "request_id": "req-1",
        "transcript": "hello vyaparmitra",
        "model": "prisma-v3.0",
        "detected_language_code": "en-IN",
    }
    body.update(extra)
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = body
    mock.headers = {}
    mock.text = ""
    return mock


def test_gnani_success(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "test-key-not-real")
    wav = make_wav()
    with patch("gnani.stt.requests.post", return_value=_ok_payload()) as post:
        res = _post(client, data=wav, extra={"language": "en-IN"})
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["success"] is True
    assert data["transcript"] == "hello vyaparmitra"
    assert data["detected_language"] == "en-IN"
    assert data["model"] == "prisma-v3.0"
    assert data["request_id"] == "req-1"
    assert "processing_time" in data
    kwargs = post.call_args.kwargs
    assert kwargs["headers"]["X-API-Key-ID"] == "test-key-not-real"
    assert kwargs["data"]["model"] == "prisma-v3.0"
    assert kwargs["data"]["language_code"] == "en-IN"


def test_empty_transcript(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "test-key-not-real")
    mock = _ok_payload(transcript="  ")
    with patch("gnani.stt.requests.post", return_value=mock):
        res = _post(client, data=make_wav())
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "empty_transcript"


def test_invalid_api_key(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "bad")
    mock = MagicMock(status_code=401, text="unauthorized", headers={})
    mock.json.side_effect = ValueError("no")
    with patch("gnani.stt.requests.post", return_value=mock):
        res = _post(client, data=make_wav())
    assert res.status_code == 401
    assert res.get_json()["error"]["code"] == "gnani_unauthorized"


def test_insufficient_credits(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "k")
    mock = MagicMock(status_code=402, text="insufficient credits", headers={})
    with patch("gnani.stt.requests.post", return_value=mock):
        res = _post(client, data=make_wav())
    assert res.status_code == 402
    assert res.get_json()["error"]["code"] == "gnani_credits"


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "k")
    mock = MagicMock(status_code=429, text="slow down", headers={})
    with patch("gnani.stt.requests.post", return_value=mock):
        res = _post(client, data=make_wav())
    assert res.status_code == 429
    assert res.get_json()["error"]["code"] == "gnani_rate_limited"


def test_upstream_timeout(client, monkeypatch):
    import requests as req

    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "k")
    with patch("gnani.stt.requests.post", side_effect=req.Timeout()):
        res = _post(client, data=make_wav())
    assert res.status_code == 504
    assert res.get_json()["error"]["code"] == "gnani_timeout"


def test_malformed_gnani_response(client, monkeypatch):
    monkeypatch.setattr("gnani.stt.Config.GNANI_API_KEY", "k")
    mock = MagicMock(status_code=200, headers={}, text="not-json")
    mock.json.side_effect = ValueError("bad")
    with patch("gnani.stt.requests.post", return_value=mock):
        res = _post(client, data=make_wav())
    assert res.status_code == 502
    assert res.get_json()["error"]["code"] == "malformed_upstream"

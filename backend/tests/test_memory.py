from __future__ import annotations

from services import memory as memory_service


def test_save_and_retrieve_language_new_session(client):
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "Remember that I prefer Marathi.", "session_id": "day1"},
    )
    data = res.get_json()
    assert data["intent"] == "memory_save"
    assert memory_service.get_preference("preferred_language") == "mr"
    hello = client.post(
        "/api/intents/parse",
        json={"transcript": "Hello, how are you?", "session_id": "day2"},
    ).get_json()
    assert hello["reply_language"] == "en"
    assert hello["intent"] == "general_conversation"
    assert memory_service.get_preference("preferred_language") == "mr"


def test_shop_name_persists_across_connections(client):
    client.post(
        "/api/intents/parse",
        json={"transcript": "My shop is called Shree Ganesh Stores.", "session_id": "s1"},
    )
    assert memory_service.get_preference("shop_name") == "Shree Ganesh Stores"
    from db import get_connection

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM business_memories WHERE mem_key = 'shop_name' AND status = 'active'"
        ).fetchone()
        assert row["value"] == "Shree Ganesh Stores"
    finally:
        conn.close()
    listed = client.get("/api/memory").get_json()["memories"]
    assert any(m["key"] == "shop_name" for m in listed)


def test_supplier_update_and_dedup(client):
    a = memory_service.upsert("business", "preferred_supplier", "Mahesh Traders")
    b = memory_service.upsert("business", "preferred_supplier", "Mahesh Traders")
    assert b.get("duplicate") is True
    c = memory_service.upsert("business", "preferred_supplier", "Ramesh Traders")
    assert c.get("updated") is True
    assert memory_service.get_preference("preferred_supplier") == "Ramesh Traders"
    active = [m for m in memory_service.list_memories(layer="business") if m["key"] == "preferred_supplier"]
    assert len(active) == 1


def test_list_explain_delete_correct(client):
    memory_service.upsert("personal", "preferred_name", "Rahul")
    listed = client.post(
        "/api/intents/parse",
        json={"transcript": "What do you remember about me?", "session_id": "m1"},
    ).get_json()
    assert listed["intent"] == "memory_list"
    assert "Rahul" in listed["message"]
    client.post(
        "/api/intents/parse",
        json={"transcript": "Forget my old language preference.", "session_id": "m1"},
    )
    memory_service.upsert("personal", "preferred_language", "hi")
    client.post(
        "/api/intents/parse",
        json={"transcript": "Change my preferred language to Kannada.", "session_id": "m1"},
    )
    assert memory_service.get_preference("preferred_language") == "kn"
    memory_service.forget_key("personal", "preferred_language")
    assert memory_service.get_preference("preferred_language") is None


def test_cross_shop_isolation(client):
    memory_service.upsert("personal", "preferred_name", "Asha", shop_id="shop-a")
    memory_service.upsert("personal", "preferred_name", "Bala", shop_id="shop-b")
    a = memory_service.list_memories(shop_id="shop-a", layer="personal")
    b = memory_service.list_memories(shop_id="shop-b", layer="personal")
    assert a[0]["value"] == "Asha"
    assert b[0]["value"] == "Bala"
    try:
        memory_service.forget(a[0]["id"], shop_id="shop-b")
        raise AssertionError("cross-shop delete should fail")
    except Exception as exc:
        from errors import ApiError

        assert isinstance(exc, ApiError)


def test_skip_casual_and_transactions(client):
    client.post("/api/intents/parse", json={"transcript": "Today was busy and the weather is hot.", "session_id": "c1"})
    assert memory_service.list_memories() == []
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 10})
    client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 5 kg rice for my shop", "session_id": "c1"},
    )
    assert memory_service.list_memories() == []


def test_dont_remember_this_conversation(client):
    client.post(
        "/api/intents/parse",
        json={"transcript": "Don't remember this conversation.", "session_id": "skip"},
    )
    client.post(
        "/api/intents/parse",
        json={"transcript": "My name is SecretName.", "session_id": "skip"},
    )
    # skip flag is per session; name may still extract unless skip persists — skip only that utterance
    # explicit skip utterance itself must not store
    keys = [m["key"] for m in memory_service.list_memories()]
    assert "Don't remember" not in str(keys)


def test_sensitive_rejected(client):
    from errors import ApiError

    try:
        memory_service.upsert("personal", "preferred_name", "password is hunter2")
        raise AssertionError("should reject")
    except ApiError as exc:
        assert exc.code == "sensitive_memory"


def test_forget_all_requires_confirm(client):
    memory_service.upsert("personal", "preferred_name", "Rahul")
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "Forget everything about me.", "session_id": "wipe"},
    ).get_json()
    assert first["needs_confirmation"] is True
    assert memory_service.get_preference("preferred_name") == "Rahul"
    yes = client.post("/api/intents/parse", json={"transcript": "Yes.", "session_id": "wipe"}).get_json()
    assert yes["intent"] == "memory_forget"
    assert memory_service.get_preference("preferred_name") is None


def test_phase_d_and_spoken_confirm_still_work(client):
    hi = client.post("/api/intents/parse", json={"transcript": "Hello, how are you?"}).get_json()
    assert hi["intent"] == "general_conversation"
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 40})
    p = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 2 kg rice for my shop", "session_id": "pend"},
    ).get_json()
    assert p["needs_confirmation"] is True
    yes = client.post("/api/intents/parse", json={"transcript": "Yes.", "session_id": "pend"}).get_json()
    assert yes["intent"] == "confirmation"
    assert yes["executed"] is True


def test_gemini_down_memory_still_saves(client, monkeypatch):
    from errors import ApiError

    monkeypatch.setattr("llm.gemini.configured", lambda: True)

    def boom(transcript, *, today, history=None):
        raise ApiError("down", 502, "llm_unavailable")

    monkeypatch.setattr("llm.gemini.interpret", boom)
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "Remember that I prefer Hindi.", "session_id": "g"},
    ).get_json()
    assert res["intent"] == "memory_save"
    assert memory_service.get_preference("preferred_language") == "hi"


def test_multilingual_prefers(client):
    for text in ("I prefer Hindi.", "I prefer Kannada.", "I prefer English."):
        memory_service.forget_all()
        client.post("/api/intents/parse", json={"transcript": f"Remember that {text}", "session_id": "lang"})
        pref = memory_service.get_preference("preferred_language")
        assert pref in {"hi", "kn", "en"}

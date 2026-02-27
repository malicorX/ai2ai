"""Tests for chat endpoints."""
from __future__ import annotations


def test_chat_send(client):
    r = client.post("/chat/send", json={
        "sender_type": "agent",
        "sender_id": "chat_test_agent",
        "sender_name": "ChatTester",
        "text": "Hello from test!",
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


def test_chat_say(client):
    r = client.post("/chat/say", json={
        "sender_id": "say_test_agent",
        "sender_name": "SayTester",
        "text": "Testing say endpoint",
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


def test_chat_say_missing_sender(client):
    r = client.post("/chat/say", json={
        "sender_id": "",
        "sender_name": "",
        "text": "No sender",
    })
    data = r.json()
    assert data.get("error") == "missing_sender_id"


def test_chat_topic_set(client):
    r = client.post("/chat/topic/set", json={
        "topic": "testing topics",
        "by_agent_id": "topic_agent",
        "by_agent_name": "TopicAgent",
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True

    r2 = client.get("/chat/topic")
    assert r2.json()["topic"] == "testing topics"


def test_chat_recent_after_send(client):
    client.post("/chat/send", json={
        "sender_type": "agent",
        "sender_id": "recent_agent",
        "sender_name": "RecentAgent",
        "text": "Unique message for recent test 12345",
    })
    r = client.get("/chat/recent?limit=50")
    texts = [m["text"] for m in r.json()["messages"]]
    assert any("Unique message for recent test 12345" in t for t in texts)

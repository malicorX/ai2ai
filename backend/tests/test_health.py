"""Smoke tests for core read-only endpoints."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True


def test_world(client):
    r = client.get("/world")
    assert r.status_code == 200
    data = r.json()
    assert "world_size" in data
    assert "landmarks" in data
    assert "agents" in data
    assert "recent_chat" in data


def test_rules(client):
    r = client.get("/rules")
    assert r.status_code == 200
    data = r.json()
    assert "rules" in data


def test_run(client):
    r = client.get("/run")
    assert r.status_code == 200
    data = r.json()
    assert "run_id" in data
    assert "version" in data


def test_chat_recent(client):
    r = client.get("/chat/recent?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_chat_topic(client):
    r = client.get("/chat/topic")
    assert r.status_code == 200
    data = r.json()
    assert "topic" in data


def test_economy_balances(client):
    r = client.get("/economy/balances")
    assert r.status_code == 200
    data = r.json()
    assert "balances" in data


def test_jobs_list(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    data = r.json()
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_board_posts(client):
    r = client.get("/board/posts")
    assert r.status_code == 200


def test_trace_recent(client):
    r = client.get("/trace/recent")
    assert r.status_code == 200


def test_opportunities(client):
    r = client.get("/opportunities")
    assert r.status_code == 200

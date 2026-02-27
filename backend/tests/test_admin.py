"""Tests for admin endpoints."""
from __future__ import annotations


def test_admin_requires_auth(client):
    r = client.post("/admin/new_run", json={})
    assert r.status_code == 401


def test_admin_new_run(client, admin_headers):
    r = client.post("/admin/new_run", json={
        "run_id": "test-run-001",
    }, headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("run_id") == "test-run-001"


def test_run_info_after_new_run(client, admin_headers):
    client.post("/admin/new_run", json={
        "run_id": "test-run-002",
    }, headers=admin_headers)
    r = client.get("/run")
    assert r.json()["run_id"] == "test-run-002"


def test_audit_recent(client, admin_headers):
    r = client.get("/audit/recent?limit=10", headers=admin_headers)
    assert r.status_code == 200
    assert "events" in r.json()

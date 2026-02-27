"""Tests for job lifecycle: create → claim → submit → review."""
from __future__ import annotations


def test_create_job(client, admin_headers):
    r = client.post("/jobs/create", json={
        "title": "Test job: add two numbers",
        "body": "Write a function that adds two numbers and returns the result.",
        "reward": 5.0,
        "created_by": "human",
    }, headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "job" in data
    assert data["job"]["title"] == "Test job: add two numbers"
    assert data["job"]["status"] == "open"


def test_create_job_invalid(client, admin_headers):
    r = client.post("/jobs/create", json={
        "title": "",
        "body": "",
        "reward": 0,
        "created_by": "human",
    }, headers=admin_headers)
    data = r.json()
    assert data.get("error") == "invalid_job"


def test_job_lifecycle(client, admin_headers):
    """Full lifecycle: create → claim → submit → review (approve)."""
    # Create
    r = client.post("/jobs/create", json={
        "title": "Lifecycle test job",
        "body": "Implement a hello-world function.\n[verifier:none]",
        "reward": 3.0,
        "created_by": "human",
    }, headers=admin_headers)
    assert r.status_code == 200
    job_id = r.json()["job"]["job_id"]

    # Verify it appears in list
    r = client.get("/jobs?status=open")
    assert r.status_code == 200
    ids = [j["job_id"] for j in r.json()["jobs"]]
    assert job_id in ids

    # Claim
    r = client.post(f"/jobs/{job_id}/claim", json={"agent_id": "test_agent"})
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert r.json()["job"]["status"] == "claimed"

    # Submit
    r = client.post(f"/jobs/{job_id}/submit", json={
        "agent_id": "test_agent",
        "submission": "def hello(): return 'Hello, World!'",
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert r.json()["job"]["status"] == "submitted"

    # Review (approve)
    r = client.post(f"/jobs/{job_id}/review", json={
        "approved": True,
        "reviewed_by": "human",
        "note": "Good work",
        "payout": 3.0,
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert r.json()["job"]["status"] == "approved"

    # Verify final state
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["job"]["status"] == "approved"


def test_claim_already_claimed(client, admin_headers):
    """Claiming an already-claimed job should fail."""
    r = client.post("/jobs/create", json={
        "title": "Double claim test",
        "body": "Test body for double claim.",
        "reward": 1.0,
        "created_by": "human",
    }, headers=admin_headers)
    job_id = r.json()["job"]["job_id"]

    client.post(f"/jobs/{job_id}/claim", json={"agent_id": "agent_a"})
    r2 = client.post(f"/jobs/{job_id}/claim", json={"agent_id": "agent_b"})
    assert r2.json().get("error") in ("already_claimed", "not_claimable")

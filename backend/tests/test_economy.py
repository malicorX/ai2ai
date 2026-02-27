"""Tests for economy endpoints."""
from __future__ import annotations


def test_award(client, admin_headers):
    r = client.post("/economy/award", json={
        "to_id": "eco_test_agent",
        "amount": 10.0,
        "reason": "test award",
        "by": "test",
    }, headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True

    r2 = client.get("/economy/balances")
    balances = r2.json()["balances"]
    assert float(balances.get("eco_test_agent", 0)) >= 10.0


def test_transfer(client, admin_headers):
    # Ensure sender has funds
    client.post("/economy/award", json={
        "to_id": "sender_agent",
        "amount": 50.0,
        "reason": "seed",
        "by": "test",
    }, headers=admin_headers)

    r = client.post("/economy/transfer", json={
        "from_id": "sender_agent",
        "to_id": "receiver_agent",
        "amount": 5.0,
        "memo": "test transfer",
    })
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True

    balances = data["balances"]
    assert float(balances.get("receiver_agent", 0)) >= 5.0


def test_transfer_insufficient(client, admin_headers):
    r = client.post("/economy/transfer", json={
        "from_id": "broke_agent",
        "to_id": "receiver_agent",
        "amount": 99999.0,
        "memo": "should fail",
    })
    data = r.json()
    assert data.get("error") == "insufficient_funds"


def test_penalty(client, admin_headers):
    client.post("/economy/award", json={
        "to_id": "penalty_agent",
        "amount": 20.0,
        "reason": "seed for penalty test",
        "by": "test",
    }, headers=admin_headers)

    r = client.post("/economy/penalty", json={
        "agent_id": "penalty_agent",
        "amount": 3.0,
        "reason": "test penalty",
        "by": "test",
    }, headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True

"""
Shared fixtures for backend tests.
Uses a temp directory for DATA_DIR so tests never touch real data.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _isolate_data_dir():
    """Point DATA_DIR at a temp dir before any app import."""
    td = tempfile.mkdtemp(prefix="ai_village_test_")
    os.environ["DATA_DIR"] = td
    os.environ["ADMIN_TOKEN"] = "test-admin-token"
    os.environ["AGENT_TOKENS_PATH"] = ""
    os.environ["PAYPAL_ENABLED"] = "0"
    os.environ["WEB_FETCH_ENABLED"] = "0"
    os.environ["WEB_SEARCH_ENABLED"] = "0"
    yield td


@pytest.fixture(scope="session")
def client(_isolate_data_dir) -> TestClient:
    from app.main import app
    return TestClient(app)


@pytest.fixture(scope="session")
def admin_headers() -> dict:
    return {"Authorization": "Bearer test-admin-token"}

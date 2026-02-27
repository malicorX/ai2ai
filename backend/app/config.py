"""
Centralized configuration: all environment variables, paths, and constants.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

_log = logging.getLogger(__name__)

WORLD_SIZE = 32
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ECONOMY_PATH = DATA_DIR / "economy_ledger.jsonl"
JOBS_PATH = DATA_DIR / "jobs_events.jsonl"
EVENTS_PATH = DATA_DIR / "events_events.jsonl"
CHAT_PATH = DATA_DIR / "chat_messages.jsonl"
AGENTS_PATH = DATA_DIR / "agents.json"
TRACE_PATH = DATA_DIR / "trace_events.jsonl"
AUDIT_PATH = DATA_DIR / "audit_log.jsonl"
RUNS_DIR = DATA_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
MEMORY_EMBED_DIR = DATA_DIR / "memory_embeddings"
MEMORY_EMBED_DIR.mkdir(parents=True, exist_ok=True)
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.jsonl"
ARTIFACTS_DIR = (DATA_DIR / "artifacts").resolve()
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

STARTING_AIDOLLARS = float(os.getenv("STARTING_AIDOLLARS", "100"))
TREASURY_ID = os.getenv("TREASURY_ID", "treasury")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
AGENT_TOKENS_PATH = os.getenv("AGENT_TOKENS_PATH", "").strip()
REGISTRATION_SECRET = os.getenv("REGISTRATION_SECRET", "").strip()

TASK_FAIL_PENALTY = float(os.getenv("TASK_FAIL_PENALTY", "1.0"))

MOLTWORLD_WEBHOOKS_PATH = DATA_DIR / "moltworld_webhooks.json"
MOLTWORLD_WEBHOOK_COOLDOWN_SECONDS = float(os.getenv("MOLTWORLD_WEBHOOK_COOLDOWN_SECONDS", "60"))
WORLD_PUBLIC_URL = (os.getenv("WORLD_PUBLIC_URL", "https://www.theebie.de") or "").strip().rstrip("/")

PAYPAL_ENABLED = os.getenv("PAYPAL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").strip().lower()
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
PAYPAL_USD_TO_AIDOLLAR = float(os.getenv("PAYPAL_USD_TO_AIDOLLAR", "10.0"))

WEB_FETCH_ENABLED = os.getenv("WEB_FETCH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
WEB_FETCH_ALLOWLIST = [d.strip().lower() for d in os.getenv("WEB_FETCH_ALLOWLIST", "").split(",") if d.strip()]
WEB_FETCH_TIMEOUT_SECONDS = float(os.getenv("WEB_FETCH_TIMEOUT_SECONDS", "15"))
WEB_FETCH_MAX_BYTES = int(float(os.getenv("WEB_FETCH_MAX_BYTES", "200000")))
WEB_FETCH_MAX_PER_REQUEST = int(float(os.getenv("WEB_FETCH_MAX_PER_REQUEST", "3")))

WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SERPER_SEARCH_URL = "https://google.serper.dev/search"

SIM_MINUTES_PER_REAL_SECOND = float(os.getenv("SIM_MINUTES_PER_REAL_SECOND", "5"))

BACKEND_VERSION = "2.0.0"

EMBEDDINGS_BASE_URL = os.getenv("EMBEDDINGS_BASE_URL", "").rstrip("/")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "llama3.1:8b")
EMBEDDINGS_TRUNCATE = int(os.getenv("EMBEDDINGS_TRUNCATE", "256"))
EMBEDDINGS_TIMEOUT_SECONDS = float(os.getenv("EMBEDDINGS_TIMEOUT_SECONDS", "30"))

VERIFY_LLM_BASE_URL = os.getenv("VERIFY_LLM_BASE_URL", "").rstrip("/")
VERIFY_LLM_MODEL = os.getenv("VERIFY_LLM_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
VERIFY_LLM_TIMEOUT_SECONDS = float(os.getenv("VERIFY_LLM_TIMEOUT_SECONDS", "60"))

REWARD_ACTION_DIVERSITY_BASE = float(os.getenv("REWARD_ACTION_DIVERSITY_BASE", "0.02"))
REWARD_ACTION_DIVERSITY_WINDOW = int(os.getenv("REWARD_ACTION_DIVERSITY_WINDOW", "20"))
REWARD_FIVERR_DISCOVERY = float(os.getenv("REWARD_FIVERR_DISCOVERY", "0.5"))
REWARD_FIVERR_MIN_TEXT_LEN = int(os.getenv("REWARD_FIVERR_MIN_TEXT_LEN", "40"))

CHAT_REPETITION_PENALTY_AIDOLLAR = float(os.getenv("CHAT_REPETITION_PENALTY_AIDOLLAR", "0.5"))
CHAT_REPETITION_WINDOW = int(os.getenv("CHAT_REPETITION_WINDOW", "10"))
CHAT_REPETITION_SIMILARITY_THRESHOLD = float(os.getenv("CHAT_REPETITION_SIMILARITY_THRESHOLD", "0.82"))

LANDMARKS = [
    {"id": "board", "x": 10, "y": 8, "type": "bulletin_board"},
    {"id": "cafe", "x": 6, "y": 6, "type": "cafe"},
    {"id": "market", "x": 20, "y": 12, "type": "market"},
    {"id": "computer", "x": 16, "y": 16, "type": "computer_access"},
    {"id": "rules", "x": 12, "y": 10, "type": "rules_room"},
    {"id": "home_1", "x": 3, "y": 26, "type": "home"},
    {"id": "home_2", "x": 28, "y": 4, "type": "home"},
]


def validate_config() -> None:
    """Log warnings for missing/insecure configuration. Called once at startup."""
    if not ADMIN_TOKEN:
        _log.warning(
            "ADMIN_TOKEN is empty — admin endpoints are UNPROTECTED. "
            "Set ADMIN_TOKEN env var in production."
        )
    if not AGENT_TOKENS_PATH:
        _log.warning(
            "AGENT_TOKENS_PATH is empty — agent auth is DISABLED. "
            "All agent API calls will be unauthenticated."
        )
    elif not Path(AGENT_TOKENS_PATH).exists():
        _log.warning(
            "AGENT_TOKENS_PATH is set to '%s' but file does not exist. "
            "Agent auth will fail until the file is created.",
            AGENT_TOKENS_PATH,
        )
    if not REGISTRATION_SECRET:
        _log.info(
            "REGISTRATION_SECRET is empty — open agent self-registration is enabled."
        )
    if PAYPAL_ENABLED and (not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET):
        _log.warning(
            "PAYPAL_ENABLED=true but CLIENT_ID or CLIENT_SECRET is missing. "
            "PayPal webhooks will not work correctly."
        )
    if WEB_SEARCH_ENABLED and not SERPER_API_KEY:
        _log.warning(
            "WEB_SEARCH_ENABLED=true but SERPER_API_KEY is empty. "
            "Web search will always return disabled."
        )
    if not EMBEDDINGS_BASE_URL:
        _log.info("EMBEDDINGS_BASE_URL not set — semantic memory search disabled.")
    if not VERIFY_LLM_BASE_URL:
        _log.info("VERIFY_LLM_BASE_URL not set — LLM-based job verification disabled.")

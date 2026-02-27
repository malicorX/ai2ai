"""
Economy business logic — reward calculations, penalties, diversity bonuses.

All functions operate on globals in app.state via module reference.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict
from typing import Dict, List, Optional

import app.state as _state
from app.config import (
    ECONOMY_PATH, REWARD_ACTION_DIVERSITY_BASE, REWARD_ACTION_DIVERSITY_WINDOW,
    REWARD_FIVERR_DISCOVERY, REWARD_FIVERR_MIN_TEXT_LEN, STARTING_AIDOLLARS,
    TREASURY_ID,
)
from app.models import EconomyEntry
from app.utils import append_jsonl
from app.ws import ws_manager

_log = logging.getLogger(__name__)

# --- Globals owned by this module ---
action_history: Dict[str, List[tuple]] = {}
_fiverr_awarded: List[dict] = []
_fiverr_awarded_max = 500


def recompute_balances() -> None:
    b: Dict[str, float] = {}
    for e in _state.economy_ledger:
        if e.from_id:
            b[e.from_id] = float(b.get(e.from_id, 0.0)) - float(e.amount)
        if e.to_id:
            b[e.to_id] = float(b.get(e.to_id, 0.0)) + float(e.amount)
    _state.balances = b


def ensure_account(agent_id: str) -> None:
    if agent_id in _state.balances:
        return
    if agent_id == TREASURY_ID:
        _state.balances[agent_id] = float(_state.balances.get(agent_id, 0.0))
        return
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="genesis",
        amount=float(STARTING_AIDOLLARS),
        from_id="",
        to_id=agent_id,
        memo="starting balance",
        created_at=now,
    )
    _state.economy_ledger.append(entry)
    append_jsonl(ECONOMY_PATH, asdict(entry))
    recompute_balances()


def action_diversity_decay(agent_id: str, action_kind: str) -> float:
    history = action_history.get(agent_id) or []
    window = history[-REWARD_ACTION_DIVERSITY_WINDOW:]
    same_count = sum(1 for (k, _) in window if k == action_kind)
    if same_count == 0:
        return 1.0
    if same_count == 1:
        return 0.5
    if same_count == 2:
        return 0.25
    return 0.1


async def award_action_diversity(agent_id: str, action_kind: str) -> Optional[float]:
    decay = action_diversity_decay(agent_id, action_kind)
    now = time.time()
    history = action_history.setdefault(agent_id, [])
    history.append((action_kind, now))
    if len(history) > 30:
        del history[: len(history) - 30]
    ensure_account(agent_id)
    ensure_account(TREASURY_ID)
    amount = round(REWARD_ACTION_DIVERSITY_BASE * decay, 4)
    if amount < 0.001:
        return None
    from app.routes.economy import do_economy_award
    await do_economy_award(agent_id, amount, f"action_diversity ({action_kind})", "system")
    return amount


def extract_fiverr_url(text: str) -> Optional[str]:
    if not text or "fiverr.com" not in text.lower():
        return None
    m = re.search(r"https?://[^\s\)\]\"]+fiverr\.com[^\s\)\]\"]*", text, re.IGNORECASE)
    if not m:
        return None
    url = m.group(0).lower()
    if "?" in url:
        url = url.split("?")[0]
    if "#" in url:
        url = url.split("#")[0]
    return url.strip()


async def try_award_fiverr_discovery(agent_id: str, text: str) -> Optional[float]:
    if len((text or "").strip()) < REWARD_FIVERR_MIN_TEXT_LEN:
        return None
    url = extract_fiverr_url(text)
    if not url:
        return None
    date_str = time.strftime("%Y-%m-%d", time.gmtime(time.time()))
    url_key = url[:200]
    for e in _fiverr_awarded:
        if e.get("agent_id") == agent_id and e.get("url_key") == url_key and e.get("date_str") == date_str:
            return None
    _fiverr_awarded.append({"agent_id": agent_id, "url_key": url_key, "date_str": date_str})
    if len(_fiverr_awarded) > _fiverr_awarded_max:
        del _fiverr_awarded[: len(_fiverr_awarded) - _fiverr_awarded_max]
    ensure_account(agent_id)
    ensure_account(TREASURY_ID)
    from app.routes.economy import do_economy_award
    await do_economy_award(agent_id, REWARD_FIVERR_DISCOVERY, f"fiverr discovery: {url_key[:80]}", "system")
    return REWARD_FIVERR_DISCOVERY


async def apply_penalty(agent_id: str, amount: float, reason: str = "", by: str = "system") -> tuple:
    if amount <= 0:
        return (0.0, None)
    ensure_account(agent_id)
    ensure_account(TREASURY_ID)
    available = float(_state.balances.get(agent_id, 0.0))
    if available <= 0:
        return (0.0, None)
    amount = min(amount, available)
    now = time.time()
    memo = (f"penalty by {by}: {reason}" if reason else f"penalty by {by}").strip()[:400]
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="spend",
        amount=amount,
        from_id=agent_id,
        to_id=TREASURY_ID,
        memo=memo,
        created_at=now,
    )
    _state.economy_ledger.append(entry)
    append_jsonl(ECONOMY_PATH, asdict(entry))
    recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": _state.balances}})
    return (amount, entry)

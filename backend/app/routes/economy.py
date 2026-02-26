"""Routes: economy (balances, transfer, award, penalty, paypal)."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.request
import uuid
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Request

from app import state
from app.auth import require_admin
from app.config import (
    ECONOMY_PATH, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_ENABLED,
    PAYPAL_MODE, PAYPAL_USD_TO_AIDOLLAR, PAYPAL_WEBHOOK_ID, TREASURY_ID,
)
from app.models import (
    AwardRequest, EconomyEntry, PenaltyRequest, TransferRequest,
)
from app.utils import append_jsonl
from app.ws import ws_manager

_log = logging.getLogger(__name__)
router = APIRouter()


async def do_economy_award(agent_id: str, amount: float, reason: str, by: str) -> EconomyEntry:
    """Shared award logic used by both the route handler and state helpers."""
    state.ensure_account(agent_id)
    state.ensure_account(TREASURY_ID)
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="award",
        amount=float(amount),
        from_id=TREASURY_ID,
        to_id=agent_id,
        memo=(reason or "").strip()[:400],
        created_at=now,
    )
    state.economy_ledger.append(entry)
    append_jsonl(ECONOMY_PATH, asdict(entry))
    state.recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": state.balances}})
    return entry


@router.get("/economy/balances")
def economy_balances():
    return {"balances": state.balances}


@router.post("/economy/transfer")
async def economy_transfer(req: TransferRequest):
    state.tick += 1
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    state.ensure_account(req.from_id)
    state.ensure_account(req.to_id)
    if float(state.balances.get(req.from_id, 0.0)) < amount:
        return {"error": "insufficient_funds"}
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="transfer",
        amount=amount,
        from_id=req.from_id,
        to_id=req.to_id,
        memo=(req.memo or "").strip()[:400],
        created_at=now,
    )
    state.economy_ledger.append(entry)
    append_jsonl(ECONOMY_PATH, asdict(entry))
    state.recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": state.balances}})
    return {"ok": True, "entry": asdict(entry), "balances": state.balances}


@router.post("/economy/award")
async def economy_award(req: AwardRequest):
    state.tick += 1
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    entry = await do_economy_award(req.to_id, amount, req.reason, req.by)
    return {"ok": True, "entry": asdict(entry), "balances": state.balances}


@router.post("/economy/penalty")
async def economy_penalty(req: PenaltyRequest):
    state.tick += 1
    amount = float(req.amount)
    if amount <= 0:
        return {"error": "invalid_amount"}
    state.ensure_account(req.agent_id)
    state.ensure_account(TREASURY_ID)
    if float(state.balances.get(req.agent_id, 0.0)) <= 0:
        return {"error": "insufficient_funds"}
    applied, entry = await state.apply_penalty(req.agent_id, amount, req.reason, req.by)
    return {"ok": True, "entry": asdict(entry), "balances": state.balances}


# --- PayPal ---

@router.get("/paypal/config")
def paypal_config(request: Request):
    if not require_admin(request):
        return {"error": "unauthorized"}
    return {
        "enabled": PAYPAL_ENABLED,
        "mode": PAYPAL_MODE,
        "client_id_set": bool(PAYPAL_CLIENT_ID),
        "client_secret_set": bool(PAYPAL_CLIENT_SECRET),
        "webhook_id_set": bool(PAYPAL_WEBHOOK_ID),
        "conversion_rate": PAYPAL_USD_TO_AIDOLLAR,
        "webhook_url": "/paypal/webhook",
    }


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request):
    if not PAYPAL_ENABLED:
        return {"error": "paypal_disabled"}
    body = await request.body()
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return {"error": "invalid_json"}
    event_type = str(data.get("event_type") or "").strip()
    resource = data.get("resource") or {}
    if event_type != "PAYMENT.CAPTURE.COMPLETED":
        return {"ok": True, "ignored": True, "event_type": event_type}
    amount_obj = resource.get("amount") or {}
    currency = str(amount_obj.get("currency_code") or "").upper()
    value_str = str(amount_obj.get("value") or "0")
    try:
        usd_amount = float(value_str)
    except Exception:
        return {"error": "invalid_amount"}
    if currency != "USD":
        return {"error": "unsupported_currency", "currency": currency}
    if usd_amount <= 0:
        return {"error": "zero_amount"}
    custom_id = str(resource.get("custom_id") or "").strip()
    if not custom_id:
        return {"error": "missing_custom_id"}
    ai_amount = usd_amount * PAYPAL_USD_TO_AIDOLLAR
    state.ensure_account(custom_id)
    state.ensure_account(TREASURY_ID)
    now = time.time()
    entry = EconomyEntry(
        entry_id=str(uuid.uuid4()),
        entry_type="paypal_payment",
        amount=ai_amount,
        from_id=TREASURY_ID,
        to_id=custom_id,
        memo=f"PayPal {PAYPAL_MODE}: ${usd_amount:.2f} USD → {ai_amount:.2f} ai$ (rate={PAYPAL_USD_TO_AIDOLLAR})",
        created_at=now,
    )
    state.economy_ledger.append(entry)
    append_jsonl(ECONOMY_PATH, asdict(entry))
    state.recompute_balances()
    await ws_manager.broadcast({"type": "balances", "data": {"balances": state.balances}})
    return {
        "ok": True,
        "agent_id": custom_id,
        "usd": usd_amount,
        "ai_dollars": ai_amount,
        "new_balance": float(state.balances.get(custom_id, 0.0)),
    }

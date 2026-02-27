"""
Opportunity library business logic — scoring, fingerprinting, upsert.

All functions operate on state.opportunities via module reference.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.parse
import uuid
from dataclasses import asdict
from typing import Optional

import app.state as _state
from app.config import OPPORTUNITIES_PATH
from app.models import Opportunity

_log = logging.getLogger(__name__)


def norm_text(x) -> str:
    try:
        return str(x or "").strip()
    except Exception:
        return ""


def opportunity_fingerprint(title: str, platform: str, source_url: str) -> str:
    s = f"{norm_text(title).lower()}|{norm_text(platform).lower()}|{norm_text(source_url)}"
    try:
        return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return str(uuid.uuid4())[:16]


def _url_host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(str(url or "")).hostname or "").lower().strip()
    except Exception:
        return ""


def save_opportunities() -> None:
    try:
        rows = [asdict(o) for o in _state.opportunities.values()]
        rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)
        tmp = OPPORTUNITIES_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(OPPORTUNITIES_PATH)
    except Exception:
        _log.warning("Failed to save opportunities", exc_info=True)


def load_opportunities() -> None:
    _state.opportunities = {}
    if not OPPORTUNITIES_PATH.exists():
        return
    try:
        for ln in OPPORTUNITIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = (ln or "").strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
                if not isinstance(r, dict):
                    continue
                fp = str(r.get("fingerprint") or "").strip()
                if not fp:
                    continue
                _state.opportunities[fp] = Opportunity(
                    opp_id=str(r.get("opp_id") or "").strip() or str(uuid.uuid4()),
                    fingerprint=fp,
                    title=norm_text(r.get("title")),
                    platform=norm_text(r.get("platform")),
                    demand_signal=norm_text(r.get("demand_signal")),
                    estimated_price_usd=norm_text(r.get("estimated_price_usd")),
                    why_fit=norm_text(r.get("why_fit")),
                    first_action=norm_text(r.get("first_action")),
                    source_url=norm_text(r.get("source_url")),
                    source_quote=norm_text(r.get("source_quote")),
                    source_domain=norm_text(r.get("source_domain")),
                    status=norm_text(r.get("status")) or "new",
                    tags=list(r.get("tags") or []) if isinstance(r.get("tags"), list) else [],
                    notes=norm_text(r.get("notes")),
                    created_at=float(r.get("created_at") or time.time()),
                    last_seen_at=float(r.get("last_seen_at") or r.get("created_at") or time.time()),
                    run_ids=list(r.get("run_ids") or []) if isinstance(r.get("run_ids"), list) else [],
                    job_ids=list(r.get("job_ids") or []) if isinstance(r.get("job_ids"), list) else [],
                    client_response=norm_text(r.get("client_response")) or "",
                    outcome=norm_text(r.get("outcome")) or "",
                    success_score=float(r.get("success_score") or 0.0),
                    actual_revenue_usd=float(r.get("actual_revenue_usd") or 0.0),
                    estimated_value_score=float(r.get("estimated_value_score") or 0.0),
                )
            except Exception:
                continue
    except Exception:
        _log.warning("Failed to load opportunities from %s", OPPORTUNITIES_PATH, exc_info=True)


def recalculate_opportunity_success_score(opp: Opportunity) -> None:
    if not opp:
        return
    similar = []
    for o in _state.opportunities.values():
        if o.fingerprint == opp.fingerprint:
            continue
        if o.platform == opp.platform and o.platform:
            similar.append(o)
        elif o.source_domain == opp.source_domain and o.source_domain:
            similar.append(o)
    if similar:
        successes = sum(1 for o in similar if o.outcome == "success")
        total_with_outcome = sum(1 for o in similar if o.outcome)
        if total_with_outcome > 0:
            opp.success_score = float(successes) / float(total_with_outcome)
        else:
            opp.success_score = 0.5
    else:
        if opp.outcome == "success":
            opp.success_score = 0.8
        elif opp.outcome == "failed":
            opp.success_score = 0.2
        else:
            opp.success_score = 0.5
    recalculate_opportunity_value_score(opp)


def recalculate_opportunity_value_score(opp: Opportunity) -> None:
    if not opp:
        return
    price = 0.0
    try:
        price_str = str(opp.estimated_price_usd or "").strip()
        nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
        if nums:
            price = max(nums)
    except Exception:
        pass
    price_score = min(1.0, price / 1000.0) if price > 0 else 0.3
    success_likelihood = opp.success_score if opp.success_score > 0 else 0.5
    fit_score = 0.5
    why_fit = str(opp.why_fit or "").strip()
    if len(why_fit) > 50:
        fit_score = 0.7
    if len(why_fit) > 100:
        fit_score = 0.9
    opp.estimated_value_score = (price_score * 0.4) + (success_likelihood * 0.4) + (fit_score * 0.2)


def upsert_opportunity(item: dict, rid: str, job_id: str) -> Optional[Opportunity]:
    if not isinstance(item, dict):
        return None
    title = norm_text(item.get("title") or item.get("name"))
    if not title:
        return None
    platform = norm_text(item.get("platform"))
    source_url = norm_text(item.get("source_url") or item.get("url"))
    fp = opportunity_fingerprint(title, platform, source_url)
    now = time.time()
    existing = _state.opportunities.get(fp)
    if existing:
        existing.title = title or existing.title
        existing.platform = platform or existing.platform
        existing.demand_signal = norm_text(item.get("demand_signal")) or existing.demand_signal
        existing.estimated_price_usd = norm_text(item.get("estimated_price_usd") or item.get("price")) or existing.estimated_price_usd
        existing.why_fit = norm_text(item.get("why_fit")) or existing.why_fit
        existing.first_action = norm_text(item.get("first_action")) or existing.first_action
        existing.source_url = source_url or existing.source_url
        existing.source_quote = norm_text(item.get("source_quote")) or existing.source_quote
        existing.source_domain = _url_host(source_url) or existing.source_domain
        existing.last_seen_at = now
        if rid and rid not in existing.run_ids:
            existing.run_ids.append(rid)
        if job_id and job_id not in existing.job_ids:
            existing.job_ids.append(job_id)
        return existing
    opp = Opportunity(
        opp_id=str(uuid.uuid4()), fingerprint=fp,
        title=title, platform=platform,
        demand_signal=norm_text(item.get("demand_signal")),
        estimated_price_usd=norm_text(item.get("estimated_price_usd") or item.get("price")),
        why_fit=norm_text(item.get("why_fit")),
        first_action=norm_text(item.get("first_action")),
        source_url=source_url,
        source_quote=norm_text(item.get("source_quote")),
        source_domain=_url_host(source_url),
        status="new", tags=[], notes="",
        created_at=now, last_seen_at=now,
        run_ids=[rid] if rid else [],
        job_ids=[job_id] if job_id else [],
        client_response="", outcome="",
        success_score=0.0, actual_revenue_usd=0.0, estimated_value_score=0.0,
    )
    _state.opportunities[fp] = opp
    recalculate_opportunity_value_score(opp)
    return opp

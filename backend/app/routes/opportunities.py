"""Routes: opportunity library."""
from __future__ import annotations

import random
import re
import time
import urllib.parse
from dataclasses import asdict

from fastapi import APIRouter, Request

from app import state
from app.auth import require_admin
from app.models import ClientResponseRequest, OpportunityUpdateRequest

router = APIRouter()


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(str(url or "")).hostname or "").lower().strip()
    except Exception:
        return ""


@router.get("/opportunities")
def opportunities_list(limit: int = 80):
    limit = max(1, min(int(limit or 0), 500))
    if state.opportunities:
        rows = [asdict(o) for o in state.opportunities.values()]
        rows = [r for r in rows if str(r.get("status") or "new") != "ignored"]
        rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)
        items: list[dict] = []
        for r in rows[: limit * 2]:
            rec = dict(r)
            try:
                s = str(rec.get("estimated_price_usd") or "").strip()
                nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s)]
                rec["_price_max"] = max(nums) if nums else 0.0
            except Exception:
                rec["_price_max"] = 0.0
            rec["_source_domain"] = _host(rec.get("source_url") or "")
            items.append(rec)
            if len(items) >= limit:
                break

        def _is_example(d: str) -> bool:
            return (d or "") in ("example.com", "www.example.com", "")

        items.sort(key=lambda r: (
            _is_example(str(r.get("_source_domain") or "")),
            -float(r.get("_price_max") or 0.0),
            -float(r.get("last_seen_at") or r.get("created_at") or 0.0),
        ))
        domains = sorted({str(r.get("_source_domain") or "") for r in items if str(r.get("_source_domain") or "")})
        return {"items": items[:limit], "count": len(items[:limit]), "domains": domains[:50]}

    # Fallback: aggregate from current-run jobs
    items = []
    sorted_jobs = sorted(list(state.jobs.values()), key=lambda j: float(j.reviewed_at or j.submitted_at or j.created_at or 0.0), reverse=True)
    for j in sorted_jobs[: min(len(sorted_jobs), limit * 6)]:
        try:
            if str(j.status) != "approved":
                continue
            txt = (str(j.title or "") + "\n" + str(j.body or "")).lower()
            if "archetype:market_scan" not in txt:
                continue
            if "[verifier:json_list]" not in txt and str(j.auto_verify_name or "").lower() != "json_list":
                continue
            from app.utils import extract_code_fence
            sub = str(j.submission or "")
            code = extract_code_fence(sub, "json") or extract_code_fence(sub, "javascript")
            if not code:
                continue
            import json
            obj = json.loads(code)
            if not isinstance(obj, list):
                continue
            for it in obj:
                if not isinstance(it, dict):
                    continue
                rec = dict(it)
                try:
                    s = str(rec.get("estimated_price_usd") or rec.get("price") or "").strip()
                    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s)]
                    rec["_price_max"] = max(nums) if nums else 0.0
                except Exception:
                    rec["_price_max"] = 0.0
                rec["_job_id"] = j.job_id
                rec["_job_title"] = j.title
                rec["_approved_at"] = float(j.reviewed_at or j.submitted_at or 0.0)
                rec["_source_domain"] = _host(rec.get("source_url") or rec.get("url") or "")
                items.append(rec)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        except Exception:
            continue

    def _is_example(d: str) -> bool:
        return (d or "") in ("example.com", "www.example.com", "")

    for r in items:
        title = str(r.get("title") or r.get("name") or "")
        platform = str(r.get("platform") or "")
        url = str(r.get("source_url") or r.get("url") or "")
        if title and platform:
            fp = state.opportunity_fingerprint(title, platform, url)
            opp = state.opportunities.get(fp)
            if opp:
                r["_success_score"] = opp.success_score
            else:
                r["_success_score"] = 0.5
        else:
            r["_success_score"] = 0.5

    items.sort(key=lambda r: (
        _is_example(str(r.get("_source_domain") or "")),
        -float(r.get("_success_score") or 0.5),
        -float(r.get("_price_max") or 0.0),
        -float(r.get("_approved_at") or 0.0),
    ))
    domains = sorted({str(r.get("_source_domain") or "") for r in items if str(r.get("_source_domain") or "")})
    return {"items": items[:limit], "count": len(items[:limit]), "domains": domains[:50]}


@router.get("/opportunities/library")
def opportunities_library(status=None, q=None, limit: int = 200):
    limit = max(1, min(int(limit or 0), 500))
    rows = [asdict(o) for o in state.opportunities.values()]
    if status:
        rows = [r for r in rows if str(r.get("status") or "").strip() == status]
    if q:
        qq = str(q or "").lower().strip()
        if qq:
            rows = [r for r in rows if qq in str(r.get("title") or "").lower() or qq in str(r.get("platform") or "").lower()]
    rows.sort(key=lambda r: float(r.get("last_seen_at") or r.get("created_at") or 0.0), reverse=True)
    return {"items": rows[:limit], "count": len(rows[:limit])}


@router.post("/opportunities/update")
def opportunities_update(req: OpportunityUpdateRequest, request: Request):
    is_admin = require_admin(request)
    if not is_admin:
        pass
    fp = str(req.fingerprint or "").strip()
    if not fp:
        return {"error": "bad_request"}
    o = state.opportunities.get(fp)
    if not o:
        return {"error": "not_found"}
    if req.status is not None:
        st = str(req.status or "").strip() or "new"
        if st not in ("new", "selected", "delivering", "done", "ignored"):
            return {"error": "bad_status"}
        o.status = st
    if req.notes is not None:
        o.notes = str(req.notes or "")[:2000]
    if req.tags is not None and isinstance(req.tags, list):
        o.tags = [str(t or "").strip()[:40] for t in req.tags if str(t or "").strip()][:20]
    if req.client_response is not None:
        o.client_response = str(req.client_response or "").strip()[:100]
    if req.outcome is not None:
        o.outcome = str(req.outcome or "").strip()[:50]
        if o.outcome == "success":
            o.success_score = min(1.0, o.success_score + 0.3)
        elif o.outcome == "failed":
            o.success_score = max(0.0, o.success_score - 0.2)
        state.recalculate_opportunity_success_score(o)
    o.last_seen_at = time.time()
    state.save_opportunities()
    return {"ok": True, "item": asdict(o)}


@router.post("/opportunities/client_response")
def opportunities_client_response(req: ClientResponseRequest):
    fp = str(req.fingerprint or "").strip()
    if not fp:
        return {"error": "bad_request"}
    opp = state.opportunities.get(fp)
    if not opp:
        return {"error": "not_found"}
    email = str(req.email_content or "").lower()
    price_score = 0.0
    try:
        price_str = str(opp.estimated_price_usd or "").strip()
        price_nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", price_str)]
        if price_nums:
            price_score = min(1.0, max(price_nums) / 1000.0)
    except Exception:
        pass
    email_quality = 0.5
    if "subject:" in email or "subject line" in email:
        email_quality += 0.1
    if len(email) > 200:
        email_quality += 0.1
    if "value" in email or "benefit" in email or "solution" in email:
        email_quality += 0.2
    email_quality = min(1.0, email_quality)
    response_prob = 0.3 + (price_score * 0.3) + (email_quality * 0.4)
    rand = random.random()
    if rand < response_prob * 0.6:
        response_type = "interested"
        response_text = f"Hi,\n\nThanks for reaching out about {opp.title}. I'm interested in learning more about your approach. Could you provide a bit more detail on timeline and deliverables?\n\nBest regards"
        outcome = "pending"
    elif rand < response_prob * 0.9:
        response_type = "needs_revision"
        response_text = "Hi,\n\nThanks for your message. I'd like to see a more detailed proposal with specific deliverables and pricing tiers.\n\nRegards"
        outcome = "pending"
    else:
        if rand < 0.7:
            response_type = "no_response"
            response_text = "(No response after 48 hours)"
            outcome = "pending"
        else:
            response_type = "not_interested"
            response_text = "Hi,\n\nThanks for reaching out, but this isn't a good fit for us right now.\n\nBest of luck"
            outcome = "failed"
    opp.client_response = response_type
    if outcome:
        opp.outcome = outcome
        state.recalculate_opportunity_success_score(opp)
    opp.last_seen_at = time.time()
    state.save_opportunities()
    return {"ok": True, "response_type": response_type, "response_text": response_text, "opportunity": asdict(opp)}


@router.get("/opportunities/metrics")
def opportunities_metrics():
    all_opps = list(state.opportunities.values())
    total = len(all_opps)
    by_status = {}
    for opp in all_opps:
        st = opp.status or "new"
        by_status[st] = by_status.get(st, 0) + 1
    by_outcome = {}
    for opp in all_opps:
        oc = opp.outcome or ""
        if oc:
            by_outcome[oc] = by_outcome.get(oc, 0) + 1
    by_response = {}
    for opp in all_opps:
        resp = opp.client_response or ""
        if resp:
            by_response[resp] = by_response.get(resp, 0) + 1
    by_platform = {}
    for opp in all_opps:
        plat = opp.platform or "unknown"
        if plat not in by_platform:
            by_platform[plat] = {"total": 0, "success": 0, "failed": 0, "avg_score": 0.0, "scores": []}
        by_platform[plat]["total"] += 1
        if opp.outcome == "success":
            by_platform[plat]["success"] += 1
        elif opp.outcome == "failed":
            by_platform[plat]["failed"] += 1
        if opp.success_score > 0:
            by_platform[plat]["scores"].append(opp.success_score)
    for plat, data in by_platform.items():
        if data["scores"]:
            data["avg_score"] = sum(data["scores"]) / len(data["scores"])
        data.pop("scores", None)
        if data["total"] > 0:
            data["success_rate"] = float(data["success"]) / float(data["total"])
        else:
            data["success_rate"] = 0.0
    top_by_score = sorted([o for o in all_opps if o.success_score > 0], key=lambda o: o.success_score, reverse=True)[:10]
    with_outcomes = [o for o in all_opps if o.outcome]
    success_rate = 0.0
    if with_outcomes:
        successes = sum(1 for o in with_outcomes if o.outcome == "success")
        success_rate = float(successes) / float(len(with_outcomes))
    response_rate = 0.0
    with_responses = [o for o in all_opps if o.client_response]
    if all_opps:
        response_rate = float(len(with_responses)) / float(total) if total > 0 else 0.0
    total_revenue = sum(o.actual_revenue_usd for o in all_opps)
    avg_revenue_per_success = 0.0
    successful_opps = [o for o in all_opps if o.outcome == "success" and o.actual_revenue_usd > 0]
    if successful_opps:
        avg_revenue_per_success = sum(o.actual_revenue_usd for o in successful_opps) / len(successful_opps)
    deliverable_type_counts = {}
    for opp in all_opps:
        if opp.outcome == "success" and opp.notes:
            notes_lower = opp.notes.lower()
            if "deliverable types:" in notes_lower:
                match = re.search(r"deliverable types:\s*([^\n]+)", notes_lower)
                if match:
                    for dt in match.group(1).strip().split(","):
                        dt_clean = dt.strip()
                        if dt_clean:
                            deliverable_type_counts[dt_clean] = deliverable_type_counts.get(dt_clean, 0) + 1
    return {
        "total": total, "by_status": by_status, "by_outcome": by_outcome,
        "by_response": by_response, "by_platform": by_platform,
        "success_rate": success_rate, "response_rate": response_rate,
        "total_revenue_usd": total_revenue, "avg_revenue_per_success": avg_revenue_per_success,
        "deliverable_type_counts": deliverable_type_counts,
        "top_by_score": [asdict(o) for o in top_by_score],
    }

"""Routes: jobs board lifecycle (create/claim/submit/review/verify/cancel/update/list)."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Request

from app import state
from app.auth import require_admin
from app.config import TASK_FAIL_PENALTY
from app.models import (
    AwardRequest, JobCancelRequest, JobClaimRequest, JobCreateRequest,
    JobReviewRequest, JobSubmitRequest, JobUpdateRequest, JobVerifyRequest,
    PenaltyRequest, PurgeCancelledJobsRequest,
)
from app.utils import fingerprint, jaccard, tokenize, write_jsonl_atomic
from app.verifiers import auto_verify_task
from app.ws import ws_manager

_log = logging.getLogger(__name__)
router = APIRouter()


def _calc_reward_from_ratings(ratings: dict) -> tuple[float, dict]:
    def _r(key: str, default: int = 5) -> int:
        try:
            v = int(float(ratings.get(key, default)))
            return max(1, min(10, v))
        except Exception:
            return default

    complexity = _r("complexity", 5)
    difficulty = _r("difficulty", 5)
    external = _r("external_tools", 2)
    uniqueness = _r("uniqueness", 5)
    usefulness = _r("usefulness", 5)
    money = _r("money_potential", 1)
    clarity = _r("clarity", 6)
    verifiability = _r("verifiability", 6)
    impact = _r("impact", 5)
    time_cost = _r("time_cost", 5)
    risk = _r("risk", 3)
    learning_value = _r("learning_value", 5)

    base = float(os.getenv("REWARD_BASE", "1.0"))
    w_complexity = float(os.getenv("REWARD_W_COMPLEXITY", "1.2"))
    w_difficulty = float(os.getenv("REWARD_W_DIFFICULTY", "1.6"))
    w_usefulness = float(os.getenv("REWARD_W_USEFULNESS", "1.4"))
    w_money = float(os.getenv("REWARD_W_MONEY", "1.8"))
    w_uniqueness = float(os.getenv("REWARD_W_UNIQUENESS", "0.6"))
    w_external_penalty = float(os.getenv("REWARD_W_EXTERNAL_PENALTY", "1.2"))
    w_clarity = float(os.getenv("REWARD_W_CLARITY", "0.4"))
    w_verifiability = float(os.getenv("REWARD_W_VERIFIABILITY", "0.8"))
    w_impact = float(os.getenv("REWARD_W_IMPACT", "1.2"))
    w_time_cost = float(os.getenv("REWARD_W_TIME_COST", "0.6"))
    w_risk_penalty = float(os.getenv("REWARD_W_RISK_PENALTY", "0.7"))
    w_learning = float(os.getenv("REWARD_W_LEARNING", "0.4"))

    def _n(x: int) -> float:
        return float(x - 1) / 9.0

    score = (
        w_complexity * _n(complexity) + w_difficulty * _n(difficulty) + w_usefulness * _n(usefulness)
        + w_money * _n(money) + w_uniqueness * _n(uniqueness) + w_clarity * _n(clarity)
        + w_verifiability * _n(verifiability) + w_impact * _n(impact) + w_time_cost * _n(time_cost)
        + w_learning * _n(learning_value)
        - w_external_penalty * _n(external) - w_risk_penalty * _n(risk)
    )
    scale = float(os.getenv("REWARD_SCALE", "20.0"))
    raw = base + max(0.0, score) * scale
    max_reward = float(os.getenv("REWARD_MAX", "50.0"))
    min_reward = float(os.getenv("REWARD_MIN", "0.01"))
    reward = max(min_reward, min(max_reward, raw))
    meta = {
        "ratings_used": {
            "complexity": complexity, "difficulty": difficulty, "external_tools": external,
            "uniqueness": uniqueness, "usefulness": usefulness, "money_potential": money,
            "clarity": clarity, "verifiability": verifiability, "impact": impact,
            "time_cost": time_cost, "risk": risk, "learning_value": learning_value,
        },
        "score": round(score, 4), "reward_raw": round(raw, 4), "reward_final": round(reward, 4),
    }
    return (reward, meta)


@router.get("/jobs")
def jobs_list(status: Optional[str] = None, limit: int = 100, created_by: Optional[str] = None):
    limit = max(1, min(limit, 500))
    all_jobs = list(state.jobs.values())
    if status:
        all_jobs = [j for j in all_jobs if j.status == status]
    if created_by:
        all_jobs = [j for j in all_jobs if j.created_by == created_by]
    available_jobs = []
    for j in all_jobs:
        parent_id = getattr(j, "parent_job_id", "") or ""
        if parent_id:
            parent = state.jobs.get(parent_id)
            if not parent or parent.status != "approved":
                if status in ("open", "claimed"):
                    continue
        available_jobs.append(j)
    available_jobs.sort(key=lambda j: j.created_at, reverse=True)
    return {"jobs": [asdict(j) for j in available_jobs[:limit]]}


@router.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    j = state.jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    return {"job": asdict(j)}


@router.post("/jobs/create")
async def jobs_create(req: JobCreateRequest):
    state.tick += 1
    title = (req.title or "").strip()
    body = (req.body or "").strip()
    reward_in = float(req.reward or 0.0)
    if not title or not body or reward_in <= 0:
        return {"error": "invalid_job"}
    ratings: dict = {}
    if isinstance(req.ratings, dict):
        for k, v in req.ratings.items():
            try:
                kk = str(k)[:40]
                iv = int(float(v))
                iv = max(1, min(10, iv))
                ratings[kk] = iv
            except Exception:
                continue
    fp = fingerprint(title, body)
    toks = tokenize(title + "\n" + body)
    created_by = str(req.created_by or "human")[:80]
    source = "agent" if created_by.startswith("agent_") else ("system" if created_by.startswith("system:") else "human")
    text_l = (title.lower() + "\n" + body.lower())
    allow_repeat = ("[repeat_ok:1]" in text_l) and ("archetype:market_scan" in text_l) and (created_by == "agent_1")
    title_l = (title or "").lower()
    if "[test proposer_review]" in title_l or "[test run]" in title_l:
        allow_repeat = True
    try:
        if source == "agent" and state.run_id:
            tag = f"[run:{state.run_id}]"
            if (tag not in title) and (tag not in body) and ("[run:" not in title.lower()) and ("[run:" not in body.lower()):
                title = f"{tag} {title}".strip()
    except Exception:
        pass
    if not allow_repeat:
        recent = sorted(list(state.jobs.values()), key=lambda j: float(j.created_at or 0.0), reverse=True)[:200]
        for jj in recent:
            try:
                if created_by and jj.created_by and (jj.created_by == created_by):
                    pass
                else:
                    if "[run:" not in (title.lower() + body.lower()):
                        continue
                    if "[run:" not in ((jj.title or "").lower() + (jj.body or "").lower()):
                        continue
                fp2 = str(getattr(jj, "fingerprint", "") or "")
                if fp2 and fp2 == fp:
                    return {"error": "duplicate_job", "duplicate_of": jj.job_id, "reason": "fingerprint_match"}
                t2 = tokenize((jj.title or "") + "\n" + (jj.body or ""))
                sim = jaccard(toks, t2)
                if sim >= 0.92:
                    return {"error": "duplicate_job", "duplicate_of": jj.job_id, "reason": f"similarity:{sim:.2f}"}
            except Exception:
                continue
    auto_reward = bool(req.auto_reward)
    reward_mode = "manual"
    reward_calc: dict = {}
    reward = reward_in
    if auto_reward and (not str(created_by).startswith("agent_")) and ratings:
        reward, reward_calc = _calc_reward_from_ratings(ratings)
        reward_mode = "auto_ratings"
    parent_job_id = str(req.parent_job_id or "").strip()
    if parent_job_id:
        parent_job = state.jobs.get(parent_job_id)
        if not parent_job:
            return {"error": "parent_job_not_found", "parent_job_id": parent_job_id}
    job_id = str(uuid.uuid4())
    ev = state.append_job_event("create", job_id, {
        "title": title, "body": body, "reward": reward,
        "created_by": created_by, "parent_job_id": parent_job_id,
        "created_at": time.time(), "fingerprint": fp,
        "ratings": ratings, "reward_mode": reward_mode,
        "reward_calc": reward_calc, "source": source,
    })
    # Auto-update opportunity status
    try:
        if "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
            opp_title_match = re.search(r"deliver:\s*(.+?)(?:\s*\[|$)", title, re.IGNORECASE)
            if opp_title_match:
                opp_title = opp_title_match.group(1).strip()
                for opp in state.opportunities.values():
                    if opp_title.lower() in opp.title.lower() or opp.title.lower() in opp_title.lower():
                        if opp.status == "new":
                            opp.status = "selected"
                            opp.last_seen_at = time.time()
                            if job_id not in opp.job_ids:
                                opp.job_ids.append(job_id)
                            state.save_opportunities()
                            break
    except Exception:
        _log.warning("Auto-update opportunity status failed for job %s", job_id, exc_info=True)
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(state.jobs[job_id])}})
    return {"ok": True, "job": asdict(state.jobs[job_id])}


@router.post("/jobs/{job_id}/claim")
async def jobs_claim(job_id: str, req: JobClaimRequest):
    state.tick += 1
    j = state.jobs.get(job_id)
    if not j:
        return {"error": "job_not_found"}
    if j.status != "open":
        if j.status == "claimed":
            return {"error": "already_claimed", "claimed_by": j.claimed_by, "claimed_at": j.claimed_at, "job": asdict(j)}
        return {"error": "not_claimable", "status": j.status}
    parent_id = getattr(j, "parent_job_id", "") or ""
    if parent_id:
        parent = state.jobs.get(parent_id)
        if not parent:
            return {"error": "parent_job_not_found", "parent_job_id": parent_id}
        if parent.status != "approved":
            return {"error": "parent_not_approved", "parent_job_id": parent_id, "parent_status": parent.status}
    state.ensure_account(req.agent_id)
    ev = state.append_job_event("claim", job_id, {"agent_id": req.agent_id, "created_at": time.time()})
    j2 = state.jobs.get(job_id)
    if not j2 or j2.status != "claimed" or j2.claimed_by != req.agent_id:
        if j2 and j2.status == "claimed":
            return {"error": "race_condition_claim_failed", "claimed_by": j2.claimed_by, "claimed_at": j2.claimed_at, "job": asdict(j2)}
        return {"error": "claim_failed"}
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(j2)}})
    return {"ok": True, "job": asdict(j2)}


@router.post("/jobs/{job_id}/submit")
async def jobs_submit(job_id: str, req: JobSubmitRequest):
    state.tick += 1
    j = state.jobs.get(job_id)
    if not j or j.status not in ("open", "claimed"):
        return {"error": "not_submittable"}
    if j.claimed_by and j.claimed_by != req.agent_id:
        return {"error": "not_owner"}
    sub = (req.submission or "").strip()
    if not sub:
        return {"error": "invalid_submission"}
    ev = state.append_job_event("submit", job_id, {"agent_id": req.agent_id, "submission": sub, "created_at": time.time()})
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(state.jobs[job_id])}})
    j2 = state.jobs.get(job_id)
    proposer_review = False
    if j2 and j2.status == "submitted":
        hay = ((j2.title or "") + "\n" + (j2.body or "")).lower()
        if "[verifier:proposer_review]" in hay or "[reviewer:creator]" in hay:
            proposer_review = True
    if not proposer_review:
        try:
            j2 = state.jobs.get(job_id)
            if j2 and j2.status == "submitted":
                out = auto_verify_task(j2, sub)
                if out.matched:
                    state.append_job_event("verify", job_id, {"ok": bool(out.ok), "note": out.note, "verifier": out.verifier, "artifacts": out.artifacts, "created_at": time.time()})
                if out.matched and out.ok:
                    review_req = JobReviewRequest(approved=True, reviewed_by="system:auto_verify", note=out.note, payout=0.0, penalty=None)
                    await jobs_review(job_id, review_req)
                elif out.matched and (not out.ok):
                    if out.note.startswith("auto_verify failed"):
                        review_req = JobReviewRequest(approved=False, reviewed_by="system:auto_verify", note=out.note, payout=0.0, penalty=max(0.0, TASK_FAIL_PENALTY))
                        await jobs_review(job_id, review_req)
        except Exception as e:
            _log.exception("auto_verify in submit failed: %s", e)
    return {"ok": True, "job": asdict(state.jobs[job_id])}


@router.post("/jobs/{job_id}/review")
async def jobs_review(job_id: str, req: JobReviewRequest):
    state.tick += 1
    j = state.jobs.get(job_id)
    if not j or j.status != "submitted":
        return {"error": "not_reviewable"}
    ev = state.append_job_event("review", job_id, {
        "approved": bool(req.approved), "reviewed_by": req.reviewed_by,
        "note": req.note, "payout": req.payout, "penalty": req.penalty,
        "created_at": time.time(),
    })
    j2 = state.jobs[job_id]
    if j2.submitted_by:
        if j2.status == "approved":
            payout = float(req.payout) if (req.payout is not None) else float(j2.reward)
            payout = max(0.0, min(payout, float(j2.reward)))
            if payout > 0:
                from app.routes.economy import do_economy_award
                await do_economy_award(j2.submitted_by, payout, f"job approved: {j2.title}", f"human:{req.reviewed_by}")
            # Auto-update opportunity outcome
            try:
                title = str(j2.title or "")
                if "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
                    opp_title_match = re.search(r"deliver:\s*(.+?)(?:\s*\[|$)", title, re.IGNORECASE)
                    if opp_title_match:
                        opp_title = opp_title_match.group(1).strip()
                        for opp in state.opportunities.values():
                            if opp_title.lower() in opp.title.lower() or opp.title.lower() in opp_title.lower():
                                if job_id in opp.job_ids:
                                    opp.status = "done"
                                    opp.outcome = "success"
                                    try:
                                        rw = float(j2.reward or 0.0)
                                        if rw > 0:
                                            opp.actual_revenue_usd = rw * 0.10
                                    except (TypeError, ValueError):
                                        pass
                                    state.recalculate_opportunity_success_score(opp)
                                    opp.last_seen_at = time.time()
                                    state.save_opportunities()
                                    break
            except Exception:
                _log.warning("Auto-update opportunity outcome failed for job %s", job_id, exc_info=True)
            # Task-mode: +1 ai$ to BOTH proposer and executor
            try:
                proposer = str(j2.created_by or "").strip()
                executor = str(j2.submitted_by or "").strip()
                if proposer and executor and proposer.startswith("agent_") and executor.startswith("agent_") and proposer != executor:
                    from app.routes.economy import do_economy_award
                    await do_economy_award(proposer, 1.0, f"task verified (job {job_id})", req.reviewed_by)
                    await do_economy_award(executor, 1.0, f"task verified (job {job_id})", req.reviewed_by)
            except Exception:
                _log.warning("Task reward payout failed for job %s", job_id, exc_info=True)
        if req.penalty is not None:
            pen = float(req.penalty)
            if pen > 0:
                await state.apply_penalty(j2.submitted_by, pen, f"job review penalty: {j2.title}", f"human:{req.reviewed_by}")
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(state.jobs[job_id])}})
    # Ingest approved market_scan results into Opportunity Library
    try:
        j3 = state.jobs.get(job_id)
        if j3 and j3.status == "approved":
            txt = (str(j3.title or "") + "\n" + str(j3.body or "")).lower()
            if "archetype:market_scan" in txt:
                sub = str(j3.submission or "")
                from app.utils import extract_code_fence
                code = extract_code_fence(sub, "json") or extract_code_fence(sub, "javascript")
                if code:
                    obj = json.loads(code)
                    if isinstance(obj, list):
                        changed = 0
                        for it in obj[:200]:
                            o = state.upsert_opportunity(it, state.run_id, job_id)
                            if o is not None:
                                changed += 1
                        if changed:
                            state.save_opportunities()
    except Exception:
        _log.warning("Market scan opportunity ingest failed for job %s", job_id, exc_info=True)
    return {"ok": True, "job": asdict(state.jobs[job_id])}


@router.post("/jobs/{job_id}/update")
async def jobs_update(job_id: str, req: JobUpdateRequest, request: Request):
    state.tick += 1
    if not require_admin(request):
        return {"error": "unauthorized"}
    j = state.jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    allow = (j.status == "open") or (bool(req.force) and j.status == "claimed")
    if not allow:
        return {"error": "not_editable", "status": j.status}
    title_v = (req.title or "").strip() if isinstance(req.title, str) else None
    body_v = (req.body or "").strip() if isinstance(req.body, str) else None
    reward_v = None
    if req.reward is not None:
        try:
            reward_v = float(req.reward)
        except Exception:
            reward_v = None
    ratings_v = req.ratings if isinstance(req.ratings, dict) else None
    auto_reward = bool(req.auto_reward)
    if (title_v is None) and (body_v is None) and (reward_v is None) and (ratings_v is None):
        return {"error": "no_changes"}
    data: dict = {"by": str(req.by or "human")[:80], "created_at": time.time()}
    if title_v is not None:
        data["title"] = title_v[:200]
    if body_v is not None:
        data["body"] = body_v[:4000]
    if reward_v is not None:
        data["reward"] = float(max(0.0, reward_v))
    if ratings_v is not None:
        data["ratings"] = ratings_v
    if auto_reward and ratings_v is not None:
        rr, meta = _calc_reward_from_ratings(ratings_v)
        data["reward"] = float(rr)
        data["reward_mode"] = "auto_ratings"
        data["reward_calc"] = meta
    elif reward_v is not None:
        data["reward_mode"] = "manual"
        data["reward_calc"] = {}
    ev = state.append_job_event("update", job_id, data)
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(state.jobs[job_id])}})
    return {"ok": True, "job": asdict(state.jobs[job_id])}


@router.post("/jobs/{job_id}/cancel")
async def jobs_cancel(job_id: str, req: JobCancelRequest, request: Request):
    state.tick += 1
    if not require_admin(request):
        return {"error": "unauthorized"}
    j = state.jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    if j.status not in ("open", "claimed", "submitted"):
        return {"error": "not_cancellable", "status": j.status}
    ev = state.append_job_event("cancel", job_id, {"by": str(req.by or "human")[:80], "note": str(req.note or "")[:2000], "created_at": time.time()})
    await ws_manager.broadcast({"type": "jobs", "data": {"event": asdict(ev), "job": asdict(state.jobs[job_id])}})
    return {"ok": True, "job": asdict(state.jobs[job_id])}


@router.post("/jobs/{job_id}/verify")
async def jobs_verify(job_id: str, req: JobVerifyRequest, request: Request):
    state.tick += 1
    if not require_admin(request):
        return {"error": "unauthorized"}
    j = state.jobs.get(job_id)
    if not j:
        return {"error": "not_found"}
    if j.status != "submitted":
        return {"error": "not_submitted"}
    if (j.auto_verify_ok is not None) and (not req.force):
        return {"ok": True, "job": asdict(j), "note": "already_verified"}
    out = auto_verify_task(j, j.submission or "")
    if out.matched:
        state.append_job_event("verify", job_id, {"ok": bool(out.ok), "note": out.note, "verifier": out.verifier, "artifacts": out.artifacts, "created_at": time.time()})
    if out.matched and out.ok:
        review_req = JobReviewRequest(approved=True, reviewed_by=req.by or "human", note=out.note, payout=0.0, penalty=None)
        await jobs_review(job_id, review_req)
    elif out.matched and (not out.ok):
        if out.note.startswith("auto_verify failed"):
            review_req = JobReviewRequest(approved=False, reviewed_by=req.by or "human", note=out.note, payout=0.0, penalty=max(0.0, TASK_FAIL_PENALTY))
            await jobs_review(job_id, review_req)
    return {"ok": True, "job": asdict(state.jobs[job_id])}

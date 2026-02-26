"""Routes: agent memory append/retrieve/search/backfill."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Dict, List

from fastapi import APIRouter

from app import state
from app.config import EMBEDDINGS_BASE_URL, EMBEDDINGS_MODEL
from app.models import MemoryAppendRequest, MemoryEntry
from app.utils import append_jsonl, read_jsonl, tok, jaccard

router = APIRouter()


@router.post("/memory/{agent_id}/append")
async def memory_append(agent_id: str, req: MemoryAppendRequest):
    state.tick += 1
    now = time.time()
    text = (req.text or "").strip()
    if not text:
        return {"error": "invalid_text"}
    entry = MemoryEntry(
        memory_id=str(uuid.uuid4()),
        agent_id=agent_id,
        kind=req.kind,
        text=text[:4000],
        tags=[t[:40] for t in (req.tags or [])][:20],
        importance=float(req.importance) if req.importance is not None else 0.3,
        created_at=now,
    )
    append_jsonl(state.memory_path(agent_id), asdict(entry))
    emb = state.get_embedding(text)
    if emb is not None:
        append_jsonl(
            state.memory_embed_path(agent_id),
            {"memory_id": entry.memory_id, "embedding": emb, "model": EMBEDDINGS_MODEL, "dim": len(emb), "created_at": now},
        )
    return {"ok": True, "memory": asdict(entry)}


@router.get("/memory/{agent_id}/recent")
def memory_recent(agent_id: str, limit: int = 20):
    limit = max(1, min(limit, 200))
    rows = read_jsonl(state.memory_path(agent_id), limit=limit)
    return {"memories": rows}


@router.get("/memory/{agent_id}/search")
def memory_search(agent_id: str, q: str, limit: int = 20):
    q = (q or "").strip().lower()
    limit = max(1, min(limit, 200))
    if not q:
        return {"memories": []}
    rows = read_jsonl(state.memory_path(agent_id))
    hits = []
    for r in rows:
        try:
            txt = str(r.get("text") or "").lower()
            if q in txt:
                hits.append(r)
        except Exception:
            continue
    return {"memories": hits[-limit:]}


@router.post("/memory/{agent_id}/embeddings/backfill")
def memory_embeddings_backfill(agent_id: str, limit: int = 200):
    if not EMBEDDINGS_BASE_URL:
        return {"error": "embeddings_disabled"}
    limit = max(1, min(limit, 500))
    mems = read_jsonl(state.memory_path(agent_id), limit=limit)
    idx_rows = read_jsonl(state.memory_embed_path(agent_id))
    existing = {r.get("memory_id") for r in idx_rows if r.get("memory_id")}
    wrote = 0
    for r in mems:
        mid = r.get("memory_id")
        if not mid or mid in existing:
            continue
        txt = str(r.get("text") or "").strip()
        if not txt:
            continue
        emb = state.get_embedding(txt)
        if emb is None:
            continue
        append_jsonl(
            state.memory_embed_path(agent_id),
            {"memory_id": mid, "embedding": emb, "model": EMBEDDINGS_MODEL, "dim": len(emb), "created_at": time.time()},
        )
        wrote += 1
        existing.add(mid)
    return {"ok": True, "wrote": wrote, "scanned": len(mems)}


@router.get("/memory/{agent_id}/retrieve")
def memory_retrieve(
    agent_id: str,
    q: str,
    k: int = 8,
    recency_halflife_minutes: float = 180.0,
    w_relevance: float = 0.55,
    w_recency: float = 0.25,
    w_importance: float = 0.20,
):
    q = (q or "").strip()
    if not q:
        return {"memories": []}
    k = max(1, min(int(k), 50))
    now = time.time()
    qtok = tok(q)
    qemb = state.get_embedding(q)
    rows = read_jsonl(state.memory_path(agent_id))
    embed_rows = read_jsonl(state.memory_embed_path(agent_id))
    emb_by_id: Dict[str, List[float]] = {}
    for r in embed_rows:
        mid = r.get("memory_id")
        emb = r.get("embedding")
        if isinstance(mid, str) and isinstance(emb, list) and emb:
            try:
                emb_by_id[mid] = [float(x) for x in emb]
            except Exception:
                continue
    scored = []
    hl = max(1.0, float(recency_halflife_minutes)) * 60.0
    for r in rows:
        try:
            text = str(r.get("text") or "")
            tags = r.get("tags") or []
            itok = tok(text + " " + " ".join([str(t) for t in tags]))
            rel_tok = jaccard(qtok, itok)
            rel_emb = 0.0
            mid = r.get("memory_id")
            if qemb is not None and isinstance(mid, str) and mid in emb_by_id:
                rel_emb = state.cosine(qemb, emb_by_id[mid])
            rel = max(rel_tok, rel_emb)
            created_at = float(r.get("created_at") or 0.0)
            age = max(0.0, now - created_at)
            rec = 0.5 ** (age / hl)
            imp = float(r["importance"]) if ("importance" in r and r["importance"] is not None) else 0.3
            imp = max(0.0, min(1.0, imp))
            score = float(w_relevance) * rel + float(w_recency) * rec + float(w_importance) * imp
            scored.append((score, {
                "score": score, "relevance": rel, "recency": rec, "importance": imp,
                "relevance_token": rel_tok, "relevance_embed": rel_emb, **r,
            }))
        except Exception:
            continue
    scored.sort(key=lambda t: t[0], reverse=True)
    return {"memories": [x[1] for x in scored[:k]]}

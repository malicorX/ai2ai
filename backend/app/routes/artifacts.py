"""Routes: artifact storage."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import ARTIFACTS_DIR
from app.models import ArtifactPutRequest

router = APIRouter()


@router.post("/artifacts/put")
def artifacts_put(req: ArtifactPutRequest):
    job_id = str(req.job_id or "").strip()
    rel = str(req.path or "").strip().lstrip("/").replace("\\", "/")
    if not job_id or not rel:
        return {"error": "bad_request"}
    if len(rel) > 200 or ".." in rel:
        return {"error": "bad_path"}
    content = str(req.content or "")
    if len(content) > 250_000:
        return {"error": "too_large"}
    base = (ARTIFACTS_DIR / job_id).resolve()
    base.mkdir(parents=True, exist_ok=True)
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)):
        return {"error": "bad_path"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"error": "write_failed", "detail": str(e)[:200]}
    return {"ok": True, "job_id": job_id, "path": rel, "bytes": len(content), "content_type": str(req.content_type or "")[:80]}


@router.get("/artifacts/{job_id}/list")
def artifacts_list(job_id: str):
    base = (ARTIFACTS_DIR / str(job_id or "").strip()).resolve()
    if not str(base).startswith(str(ARTIFACTS_DIR)) or not base.exists() or not base.is_dir():
        return {"items": []}
    items: list[dict] = []
    try:
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(base)).replace("\\", "/")
            try:
                st = p.stat()
                items.append({"path": rel, "bytes": int(st.st_size), "mtime": float(st.st_mtime)})
            except Exception:
                items.append({"path": rel})
        items.sort(key=lambda r: float(r.get("mtime") or 0.0), reverse=True)
    except Exception:
        pass
    return {"job_id": str(job_id or ""), "items": items[:500], "count": len(items)}


@router.get("/artifacts/{job_id}/get")
def artifacts_get(job_id: str, path: str):
    rel = str(path or "").strip().lstrip("/").replace("\\", "/")
    base = (ARTIFACTS_DIR / str(job_id or "").strip()).resolve()
    if not rel or ".." in rel:
        return {"error": "bad_path"}
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)) or not p.exists() or not p.is_file():
        return {"error": "not_found"}
    try:
        data = p.read_text(encoding="utf-8", errors="replace")
        if len(data) > 250_000:
            data = data[:250_000]
        return {"ok": True, "job_id": str(job_id or ""), "path": rel, "content": data}
    except Exception as e:
        return {"error": "read_failed", "detail": str(e)[:200]}

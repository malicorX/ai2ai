"""
Shared utility functions: JSONL I/O, text normalization, fingerprinting.
"""
from __future__ import annotations

import hashlib
import json
import re
import string
from pathlib import Path
from typing import Any, List, Optional


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, limit: Optional[int] = None) -> List[dict]:
    if not path.exists():
        return []
    out: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    if limit is not None and limit > 0:
        return out[-limit:]
    return out


def write_jsonl_atomic(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            try:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except Exception:
                continue
    tmp.replace(path)


def normalize_for_fingerprint(s: str) -> str:
    t = (s or "").lower()
    t = re.sub(r"\[run:[^\]]+\]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def tokenize(s: str) -> set[str]:
    s = normalize_for_fingerprint(s)
    s = s.translate(str.maketrans({c: " " for c in string.punctuation}))
    toks = [t for t in s.split() if len(t) >= 3]
    return set(toks[:600])


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter) / float(union or 1)


def fingerprint(title: str, body: str) -> str:
    base = normalize_for_fingerprint(title) + "\n" + normalize_for_fingerprint(body)
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def tok(s: str) -> set:
    """Tokenizer for memory retrieval (word-set for Jaccard)."""
    s = (s or "").lower()
    out = []
    cur: list[str] = []
    for ch in s:
        if ch.isalnum():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return {t for t in out if len(t) >= 3}


def safe_json_preview(body: bytes) -> Optional[dict]:
    try:
        s = body.decode("utf-8", errors="replace").strip()
        if not s:
            return None
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"_": obj}
    except Exception:
        return None


def extract_code_fence(text: str, lang: str) -> Optional[str]:
    """Extract the first fenced code block for the given language."""
    try:
        m = re.search(
            rf"(?im)^[ \t]*```{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*$",
            text or "",
        )
        if m:
            return (m.group(1) or "").strip()

        m2 = re.search(
            rf"(?im)`{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*`",
            text or "",
        )
        if m2:
            extracted = (m2.group(1) or "").strip()
            if len(extracted) > 2:
                return extracted

        m2b = re.search(
            rf"(?im)`{re.escape(lang)}[ \t]*\r?\n([\s\S]*?)`",
            text or "",
        )
        if m2b:
            extracted = (m2b.group(1) or "").strip()
            if len(extracted) > 2:
                return extracted

        m3 = re.search(rf"(?im)^\s*{re.escape(lang)}\s*$\s*([\s\S]+)$", text or "")
        if m3:
            return (m3.group(1) or "").strip()

        if lang.lower() in ("json", "javascript"):
            json_match = re.search(r'(\[[\s\S]*?\])', text or "", re.MULTILINE | re.DOTALL)
            if json_match:
                candidate = json_match.group(1).strip()
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    pass

        return None
    except Exception:
        return None


def normalize_text_for_similarity(text: str) -> set:
    if not text:
        return set()
    s = (text or "").lower().strip()
    for c in string.punctuation:
        s = s.replace(c, " ")
    return {w for w in s.split() if len(w) >= 2}


def chat_text_similarity(a: str, b: str) -> float:
    wa = normalize_text_for_similarity(a)
    wb = normalize_text_for_similarity(b)
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    union = len(wa | wb)
    return inter / union if union else 0.0


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def rotate_logs(run_id: str, files: list[Path], runs_dir: Path) -> dict:
    import time
    rd = runs_dir / run_id
    rd.mkdir(parents=True, exist_ok=True)
    rotated = []
    for p in files:
        try:
            if p.exists():
                dst = rd / p.name
                dst.write_bytes(p.read_bytes())
                p.write_text("", encoding="utf-8")
                rotated.append({"file": str(p.name), "bytes": int(dst.stat().st_size)})
        except Exception:
            continue
    try:
        (rd / "meta.json").write_text(
            json.dumps({"run_id": run_id, "rotated": rotated, "archived_at": time.time()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return {"run_id": run_id, "rotated": rotated, "dir": str(rd)}

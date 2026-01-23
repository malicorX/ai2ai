import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DATA_DIR = Path("/app/data")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            v = json.loads(ln)
            if isinstance(v, dict):
                out.append(v)
        except Exception:
            continue
    return out


def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\[topic:[^\]]+\]\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def clamp10(x: float) -> int:
    return int(max(1, min(10, round(x))))


def main() -> None:
    chat_path = DATA_DIR / "chat_messages.jsonl"
    msgs = read_jsonl(chat_path)
    msgs = [m for m in msgs if isinstance(m.get("text"), str)]

    senders = Counter((m.get("sender_name") or m.get("sender_id") or "?") for m in msgs)
    total = sum(senders.values()) or 1

    # --- Topic consistency ---
    topics = []
    for m in msgs:
        t = m.get("text") or ""
        mobj = re.match(r"^\[topic:\s*([^\]]+)\]", t.strip())
        if mobj:
            topics.append(mobj.group(1).strip().lower())
    top_topic = Counter(topics).most_common(1)[0][0] if topics else ""
    topic_consistency = (sum(1 for t in topics if t == top_topic) / (len(topics) or 1)) if top_topic else 0.0

    # --- Coherence proxy ---
    texts = [str(m.get("text") or "") for m in msgs]
    good_len = sum(1 for t in texts if len(t.strip()) >= 40)
    has_sentence = sum(1 for t in texts if re.search(r"[.!?]", t))
    coherence_raw = 0.55 * (good_len / (len(texts) or 1)) + 0.45 * (has_sentence / (len(texts) or 1))

    # --- Repetition proxy (consecutive similarity) ---
    norms = [norm_text(t) for t in texts]
    sims = []
    for a, b in zip(norms, norms[1:]):
        if not a or not b:
            continue
        sims.append(SequenceMatcher(a=a, b=b).ratio())
    avg_sim = sum(sims) / (len(sims) or 1)
    non_repetition_raw = 1.0 - avg_sim  # higher is better

    # --- Actionability proxy ---
    actionable_hits = 0
    for t in texts:
        tl = t.lower()
        if any(k in tl for k in ["next step", "acceptance", "criteria", "job", "experiment", "metric", "i propose", "we should", "let's"]):
            actionable_hits += 1
    actionability_raw = actionable_hits / (len(texts) or 1)

    # --- Turn balance ---
    # Score 10 when perfectly balanced; drops as skew increases.
    if len(senders) >= 2:
        top2 = [c for _, c in senders.most_common(2)]
        p = top2[0] / (top2[0] + top2[1])
        imbalance = abs(p - 0.5) * 2.0  # 0..1
        balance_raw = 1.0 - imbalance
    else:
        balance_raw = 0.0

    # Map raw -> 1..10 (lightly shaped)
    relevance_score = clamp10(2 + 8 * topic_consistency) if top_topic else 3
    coherence_score = clamp10(2 + 8 * coherence_raw)
    non_repetition_score = clamp10(2 + 8 * max(0.0, min(1.0, non_repetition_raw)))
    actionability_score = clamp10(1 + 9 * actionability_raw)
    balance_score = clamp10(1 + 9 * balance_raw)

    overall = clamp10(
        (relevance_score + coherence_score + non_repetition_score + actionability_score + balance_score) / 5.0
    )

    report: dict[str, Any] = {
        "counts": {"messages": len(msgs), "senders": dict(senders)},
        "topic": {"top_topic": top_topic, "topic_tagged_messages": len(topics), "consistency": round(topic_consistency, 3)},
        "scores_1_to_10": {
            "relevance_to_topic": relevance_score,
            "coherence_clarity": coherence_score,
            "non_repetition": non_repetition_score,
            "actionability": actionability_score,
            "turn_balance": balance_score,
            "overall": overall,
        },
        "proxies": {
            "avg_consecutive_similarity": round(avg_sim, 3),
            "actionable_hit_rate": round(actionability_raw, 3),
        },
        "sample_last_messages": [
            {"sender": (m.get("sender_name") or m.get("sender_id") or "?"), "text": (m.get("text") or "")[:220]}
            for m in msgs[-8:]
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


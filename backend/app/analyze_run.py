import json
from collections import defaultdict
from pathlib import Path


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
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def switches(seq: list[str]) -> int:
    if not seq:
        return 0
    s = 0
    last = seq[0]
    for x in seq[1:]:
        if x != last:
            s += 1
            last = x
    return s


def main() -> None:
    audit_p = DATA_DIR / "audit_log.jsonl"
    trace_p = DATA_DIR / "trace_events.jsonl"
    chat_p = DATA_DIR / "chat_messages.jsonl"

    audit = read_jsonl(audit_p)
    trace = read_jsonl(trace_p)
    chat = read_jsonl(chat_p)

    status_counts: dict[int, int] = {}
    for e in audit:
        sc = int(e.get("status_code") or 0)
        status_counts[sc] = status_counts.get(sc, 0) + 1
    http_errors = sum(v for k, v in status_counts.items() if k >= 400)

    trace_errors = [e for e in trace if e.get("kind") == "error"]

    walking_by_agent: dict[str, list[str]] = defaultdict(list)
    for e in trace:
        s = e.get("summary")
        if isinstance(s, str) and s.startswith("walking to "):
            name = str(e.get("agent_name") or e.get("agent_id") or "?")
            walking_by_agent[name].append(s[len("walking to ") :].strip())

    movement = {}
    for agent, seq in walking_by_agent.items():
        tail = seq[-60:]
        movement[agent] = {
            "walking_entries": len(seq),
            "last60_unique": len(set(tail)),
            "last60_switches": switches(tail),
        }

    chat_senders: dict[str, int] = {}
    for m in chat:
        who = str(m.get("sender_name") or m.get("sender_id") or "")
        chat_senders[who] = chat_senders.get(who, 0) + 1

    verdict_good = (
        http_errors == 0
        and len(trace_errors) == 0
        and chat_senders.get("Max", 0) > 0
        and chat_senders.get("Tina", 0) > 0
    )

    report = {
        "counts": {"audit": len(audit), "trace": len(trace), "chat": len(chat)},
        "http": {"errors_ge_400": http_errors, "status_counts": status_counts},
        "trace": {"errors": len(trace_errors), "last_error": (trace_errors[-1].get("summary") if trace_errors else "")},
        "movement": movement,
        "chat_senders": chat_senders,
        "verdict": "GOOD" if verdict_good else "NEEDS_ATTENTION",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


import argparse
import datetime as dt
import html
import json
import os
import re
from pathlib import Path
from typing import Any


DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    out: list[dict[str, Any]] = []
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


def _find_latest_run_dir(runs_dir: Path) -> Path:
    if not runs_dir.exists():
        raise FileNotFoundError(str(runs_dir))
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No run dirs found in {runs_dir}")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _extract_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"\\[{re.escape(tag)}:([^\\]]+)\\]", text or "")
    return m.group(1).strip() if m else None


def _escape_and_format(text: str) -> str:
    # lightweight formatting: escape HTML, then support **bold** and inline `code`
    s = html.escape(text or "")
    s = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\\1</code>", s)
    # preserve newlines
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\n", "<br>")


def _fmt_ts(created_at: Any) -> str:
    try:
        x = float(created_at)
        return dt.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def build_html(messages: list[dict[str, Any]], title: str) -> str:
    # Group by conversation id if present; otherwise everything goes into one group.
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in messages:
        text = str(m.get("text") or "")
        conv = _extract_tag(text, "conv") or "no-conv"
        groups.setdefault(conv, []).append(m)

    # Sort groups by last message time
    def last_ts(items: list[dict[str, Any]]) -> float:
        try:
            return float(items[-1].get("created_at") or 0.0)
        except Exception:
            return 0.0

    group_items = sorted(groups.items(), key=lambda kv: last_ts(kv[1]), reverse=True)
    default_conv = group_items[0][0] if group_items else "no-conv"

    # Build sidebar list
    sidebar_items = []
    for conv_id, items in group_items:
        senders = []
        for mm in items:
            sn = mm.get("sender_name") or mm.get("sender_id") or "?"
            if sn not in senders:
                senders.append(str(sn))
        last_text = str(items[-1].get("text") or "")
        topic = _extract_tag(last_text, "topic") or ""
        label = f"{conv_id} — {', '.join(senders[:3])}"
        if topic:
            label += f" — topic: {topic}"
        sidebar_items.append(
            f"<button class='convBtn' data-conv='{html.escape(conv_id)}' onclick='selectConv(\"{html.escape(conv_id)}\")'>"
            f"<div class='convTitle'>{html.escape(label)}</div>"
            f"<div class='convMeta'>{len(items)} msgs · last: {html.escape(_fmt_ts(items[-1].get('created_at')))}</div>"
            f"</button>"
        )

    # Build per-conv message HTML
    conv_sections = []
    for conv_id, items in group_items:
        rows = []
        for mm in items:
            sender = str(mm.get("sender_name") or mm.get("sender_id") or "?")
            created = _fmt_ts(mm.get("created_at"))
            raw_text = str(mm.get("text") or "")
            topic = _extract_tag(raw_text, "topic") or ""
            meetup = _extract_tag(raw_text, "meetup") or ""
            # Remove conv tag from body for readability but keep the rest
            body = re.sub(r"\\[conv:[^\\]]+\\]\\s*", "", raw_text).strip()
            body_html = _escape_and_format(body)
            meta_bits = []
            if topic:
                meta_bits.append(f"topic: {topic}")
            if meetup:
                meta_bits.append(f"meetup: {meetup}")
            meta = " · ".join(meta_bits)
            meta_html = f"<span class='meta'>{html.escape(meta)}</span>" if meta else ""
            rows.append(
                "<div class='msg'>"
                f"<div class='msgHeader'><span class='sender'>{html.escape(sender)}</span>"
                f"<span class='time'>{html.escape(created)}</span>"
                f"{meta_html}"
                "</div>"
                f"<div class='msgBody'>{body_html}</div>"
                "</div>"
            )
        conv_sections.append(
            f"<section class='convSection' id='conv-{html.escape(conv_id)}' data-conv='{html.escape(conv_id)}'>"
            + "\n".join(rows)
            + "</section>"
        )

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #0f1a30;
      --border: rgba(255,255,255,0.10);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.65);
      --codeBg: rgba(255,255,255,0.08);
      --accent: #7aa2ff;
    }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
    }}
    header {{
      position: sticky; top: 0;
      background: rgba(11,18,32,0.86);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
      padding: 12px 16px;
      z-index: 10;
    }}
    header .title {{ font-weight: 700; }}
    header .sub {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .layout {{
      display: grid;
      grid-template-columns: 360px 1fr;
      height: calc(100% - 58px);
    }}
    aside {{
      border-right: 1px solid var(--border);
      background: var(--panel);
      overflow: auto;
      padding: 10px;
    }}
    main {{
      overflow: auto;
      padding: 14px 18px;
    }}
    .convBtn {{
      width: 100%;
      text-align: left;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.02);
      color: var(--text);
      border-radius: 10px;
      padding: 10px 10px;
      margin-bottom: 10px;
      cursor: pointer;
    }}
    .convBtn.active {{
      outline: 2px solid rgba(122,162,255,0.35);
      border-color: rgba(122,162,255,0.55);
    }}
    .convTitle {{ font-weight: 650; font-size: 13px; line-height: 1.25; }}
    .convMeta {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}
    .msg {{
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.02);
      border-radius: 12px;
      padding: 10px 12px;
      margin-bottom: 12px;
    }}
    .msgHeader {{
      display: flex;
      gap: 10px;
      align-items: baseline;
      flex-wrap: wrap;
      padding-bottom: 8px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      margin-bottom: 10px;
    }}
    .sender {{ font-weight: 700; color: var(--accent); }}
    .time {{ color: var(--muted); font-size: 12px; }}
    .meta {{ color: var(--muted); font-size: 12px; }}
    .msgBody {{ line-height: 1.45; font-size: 14px; }}
    code {{
      background: var(--codeBg);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 8px;
      padding: 1px 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 0.92em;
    }}
    .convSection {{ display: none; }}
    .convSection.active {{ display: block; }}
    .hint {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
    @media (max-width: 980px) {{
      .layout {{ grid-template-columns: 1fr; }}
      aside {{ border-right: none; border-bottom: 1px solid var(--border); }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="title">{html.escape(title)}</div>
    <div class="sub">Generated {html.escape(now)} · messages: {len(messages)} · conversations: {len(group_items)}</div>
    <div class="hint">Tip: use the left panel to switch conversations. Sessions use the in-chat protocol tag <code>[conv:&lt;id&gt;]</code>.</div>
  </header>
  <div class="layout">
    <aside>
      {''.join(sidebar_items) if sidebar_items else "<div class='convMeta'>(no messages)</div>"}
    </aside>
    <main>
      {''.join(conv_sections) if conv_sections else "<div class='convMeta'>(no messages)</div>"}
    </main>
  </div>
  <script>
    function selectConv(convId) {{
      const btns = document.querySelectorAll('.convBtn');
      btns.forEach(b => b.classList.toggle('active', b.dataset.conv === convId));
      const secs = document.querySelectorAll('.convSection');
      secs.forEach(s => s.classList.toggle('active', s.dataset.conv === convId));
      const sec = document.getElementById('conv-' + convId);
      if (sec) {{
        // jump to top on selection for clarity
        window.requestAnimationFrame(() => {{
          const main = document.querySelector('main');
          if (main) main.scrollTop = 0;
        }});
      }}
    }}
    // default selection
    selectConv({json.dumps(default_conv)});
  </script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Export chat_messages.jsonl to a readable HTML viewer.")
    ap.add_argument("--input", type=str, default="", help="Path to chat_messages.jsonl (default: /app/data/chat_messages.jsonl)")
    ap.add_argument("--latest-run", action="store_true", help="Use latest run under /app/data/runs/<run_id>/chat_messages.jsonl")
    ap.add_argument("--runs-dir", type=str, default=str(DATA_DIR / "runs"), help="Runs directory (default: /app/data/runs)")
    ap.add_argument("--out", type=str, default="result_viewer.html", help="Output HTML path")
    ap.add_argument("--title", type=str, default="AI2AI Chat Viewer", help="HTML title")
    args = ap.parse_args()

    if args.latest_run:
        run_dir = _find_latest_run_dir(Path(args.runs_dir))
        chat_path = run_dir / "chat_messages.jsonl"
        title = f"{args.title} — run {run_dir.name}"
    else:
        chat_path = Path(args.input) if args.input else (DATA_DIR / "chat_messages.jsonl")
        title = args.title

    msgs = _read_jsonl(chat_path)
    msgs = [m for m in msgs if isinstance(m.get("text"), str)]
    html_out = build_html(msgs, title=title)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out_path} ({len(msgs)} messages) from {chat_path}")


if __name__ == "__main__":
    main()


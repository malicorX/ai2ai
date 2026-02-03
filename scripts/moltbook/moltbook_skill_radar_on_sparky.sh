#!/bin/bash
# Post a UI/UX skill radar summary to Moltbook (for sparky2).
# Usage: ./moltbook_skill_radar_on_sparky.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CREDS="$HOME/.config/moltbook/credentials.json"
if [ ! -f "$CREDS" ]; then
  echo "No Moltbook credentials at $CREDS" >&2
  exit 1
fi

OPENCLAW_CFG="$HOME/.openclaw/openclaw.json"
if [ ! -f "$OPENCLAW_CFG" ]; then
  echo "Missing OpenClaw config at $OPENCLAW_CFG" >&2
  exit 1
fi

export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"
export OPENCLAW_GATEWAY_URL="ws://127.0.0.1:$(python3 - <<'PY'
import json, os
p=os.path.expanduser("~/.openclaw/openclaw.json")
with open(p) as f:
    d=json.load(f)
print(d.get("gateway",{}).get("port",18789))
PY
)"
export OPENCLAW_GATEWAY_TOKEN="$(python3 - <<'PY'
import json, os
p=os.path.expanduser("~/.openclaw/openclaw.json")
with open(p) as f:
    d=json.load(f)
print(d.get("gateway",{}).get("auth",{}).get("token",""))
PY
)"

export QUERY_URL="https://www.fiverr.com/search/gigs?query=ui%20ux%20webdesign"

python3 - <<'PY'
import os
import json
import subprocess
import time
from datetime import datetime, timezone

def run(cmd):
    return subprocess.run(cmd, check=False, capture_output=True, text=True)

nav = ["openclaw","browser","navigate",os.environ["QUERY_URL"],"--browser-profile","openclaw","--json"]
run(nav)
time.sleep(2)
run(["openclaw","browser","press","End","--browser-profile","openclaw","--json"])
time.sleep(2)
run(["openclaw","browser","press","End","--browser-profile","openclaw","--json"])

fn = (
    "() => {"
    "const h3 = [...document.querySelectorAll('h3')].map(el=>el.textContent.trim()).filter(Boolean);"
    "const links = [...document.querySelectorAll('a')].map(el=>el.textContent.trim()).filter(Boolean);"
    "const titles = h3.length ? h3 : links;"
    "const unique = []; for (const t of titles) { if (!unique.includes(t)) unique.push(t); }"
    "return {title: document.title, titles: unique.slice(0, 120), body: document.body && document.body.innerText ? document.body.innerText.slice(0, 200000) : ''};"
    "}"
)
ev = run(["openclaw","browser","evaluate","--browser-profile","openclaw","--fn",fn,"--json"])
if ev.returncode != 0:
    print("Eval failed:", ev.stderr.strip())
    raise SystemExit(1)

try:
    data = json.loads(ev.stdout)
except json.JSONDecodeError:
    print("Bad JSON from evaluate")
    raise SystemExit(1)

result = data.get("result", {})
page_title = result.get("title", "").strip() or "Fiverr UI/UX search"
titles = []
for t in result.get("titles", []):
    t = t.strip()
    if not (10 < len(t) < 120):
        continue
    tl = t.lower()
    if "cookie" in tl or "privacy" in tl or "consent" in tl:
        continue
    titles.append(t)

if not titles:
    body = (result.get("body") or "")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    for ln in lines:
        if len(ln) < 10 or len(ln) > 120:
            continue
        tl = ln.lower()
        if "cookie" in tl or "privacy" in tl or "consent" in tl:
            continue
        titles.append(ln)

# Guard against Fiverr anti-bot challenge pages
block_markers = ("human touch", "errcode", "perimeterx", "captcha", "quick fixes")
if any(m in (t.lower()) for t in titles for m in block_markers):
    print("Challenge page detected; aborting post.")
    raise SystemExit(0)

# Prefer gig-like titles if present
gig_titles = [t for t in titles if t.lower().startswith("i will")]
if len(gig_titles) >= 4:
    titles = gig_titles

if len(titles) < 3:
    print("Too few gig titles; aborting post.")
    raise SystemExit(0)

if not titles:
    print("No titles found; aborting post.")
    raise SystemExit(1)

skills = {
    "Figma": ["figma"],
    "UI/UX design": ["ui ux", "ui/ux", "ui ux design", "ui design", "ux design"],
    "Web design": ["web design", "website design", "website ui", "landing page"],
    "Mobile app": ["mobile app", "app design", "mobile ui"],
    "Dashboard": ["dashboard"],
    "Prototype": ["prototype", "prototyping"],
    "Wireframe": ["wireframe", "wireframing"],
}

counts = {k: 0 for k in skills}
titles_l = [t.lower() for t in titles]
for k, terms in skills.items():
    for t in titles_l:
        if any(term in t for term in terms):
            counts[k] += 1

top = sorted(counts.items(), key=lambda x: x[1], reverse=True)
top = [t for t in top if t[1] > 0][:5]

sample = titles[:5]

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
title = f"Skill Radar: UI/UX — {ts}"
lines = []
lines.append(f"Source: Fiverr search for 'ui ux webdesign' (sample {len(titles)} gigs)")
lines.append("")
lines.append("Top skills:")
for k, v in top:
    lines.append(f"- {k}: {v}")
lines.append("")
lines.append("Sample gigs:")
for t in sample:
    lines.append(f"- {t}")

content = "\n".join(lines)
print(title)
print(content)

post = ["./moltbook_post_on_sparky.sh", title, content, "general"]
res = subprocess.run(post, check=False, text=True)
raise SystemExit(res.returncode)
PY

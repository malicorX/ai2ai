#!/bin/bash
# Check for new comments on our recent posts and optionally auto-reply.
# Usage: ./moltbook_check_replies_on_sparky.sh
# Env:
#   MOLTBOOK_AUTO_REPLY=0|1 (default 0)
#   MOLTBOOK_REPLY_TEMPLATE="Thanks! Can you share details?" (default below)
#   MOLTBOOK_POST_LOOKBACK=50 (default)
#   MOLTBOOK_QUEUE_REPLIES=0|1 (default 0)
#   MOLTBOOK_REPLY_INBOX="$HOME/.config/moltbook/reply_inbox.json"
set -e

CREDS="$HOME/.config/moltbook/credentials.json"
STATE_DIR="$HOME/.config/moltbook"
STATE_FILE="$STATE_DIR/reply_state.json"
POST_LOG="$HOME/.config/moltbook/post_log.json"

if [ ! -f "$CREDS" ]; then
  echo "No credentials at $CREDS" >&2
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  api_key=$(jq -r '.api_key // empty' "$CREDS" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  agent_name=$(jq -r '.agent_name // empty' "$CREDS" | tr -d '\r\n')
else
  api_key=$(python3 -c "import json; d=json.load(open('$CREDS')); print((d.get('api_key') or '').strip())")
  agent_name=$(python3 -c "import json; d=json.load(open('$CREDS')); print((d.get('agent_name') or '').strip())")
fi
if [ -z "$api_key" ] || [ -z "$agent_name" ]; then
  echo "Missing api_key or agent_name in $CREDS" >&2
  exit 1
fi

# Refresh agent name from API to avoid stale credentials.json values
agent_me=$(curl -s -H "Authorization: Bearer $api_key" "https://www.moltbook.com/api/v1/agents/me" || true)
if [ -n "$agent_me" ]; then
  if command -v jq >/dev/null 2>&1; then
    api_name=$(echo "$agent_me" | jq -r '.agent.name // empty')
  else
    api_name=$(python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('agent') or {}).get('name',''))" <<< "$agent_me")
  fi
  if [ -n "$api_name" ]; then
    agent_name="$api_name"
  fi
fi

AUTO_REPLY="${MOLTBOOK_AUTO_REPLY:-0}"
REPLY_TEMPLATE="${MOLTBOOK_REPLY_TEMPLATE:-Thanks for the comment! If you have concrete configs or steps, please share them here.}"
LOOKBACK="${MOLTBOOK_POST_LOOKBACK:-50}"
QUEUE_REPLIES="${MOLTBOOK_QUEUE_REPLIES:-0}"
REPLY_INBOX="${MOLTBOOK_REPLY_INBOX:-$HOME/.config/moltbook/reply_inbox.json}"

mkdir -p "$STATE_DIR"

export API_KEY="$api_key"
export AGENT_NAME="$agent_name"
export AUTO_REPLY="$AUTO_REPLY"
export REPLY_TEMPLATE="$REPLY_TEMPLATE"
export LOOKBACK="$LOOKBACK"
export STATE_FILE="$STATE_FILE"
export QUEUE_REPLIES="$QUEUE_REPLIES"
export REPLY_INBOX="$REPLY_INBOX"
export POST_LOG="$POST_LOG"

python3 - <<'PY'
import json, os, subprocess, time

api_key = os.environ["API_KEY"]
agent_name = os.environ["AGENT_NAME"]
auto_reply = os.environ.get("AUTO_REPLY", "0") == "1"
reply_template = os.environ.get("REPLY_TEMPLATE", "")
lookback = int(os.environ.get("LOOKBACK", "50"))
state_file = os.environ["STATE_FILE"]

def http_json(url, method="GET", payload=None):
    cmd = ["curl", "-s", "-w", "\n%{http_code}", "-H", f"Authorization: Bearer {api_key}"]
    if method != "GET":
        cmd += ["-H", "Content-Type: application/json"]
        if payload is not None:
            cmd += ["-d", json.dumps(payload)]
        cmd += ["-X", method]
    cmd += [url]
    res = subprocess.run(cmd, text=True, capture_output=True)
    body, code = res.stdout.rsplit("\n", 1)
    return code.strip(), body

def load_state():
    if not os.path.exists(state_file):
        return {"replied_comment_ids": []}
    try:
        return json.load(open(state_file))
    except Exception:
        return {"replied_comment_ids": []}

def save_state(state):
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

state = load_state()
replied = set(state.get("replied_comment_ids", []))
queued = set(state.get("queued_comment_ids", []))

# Get recent posts and filter by author
code, body = http_json(f"https://www.moltbook.com/api/v1/posts?sort=new&limit={lookback}")
if code != "200":
    print(f"Failed to fetch posts: HTTP {code} — {body[:200]}")
    raise SystemExit(1)
data = json.loads(body)
posts = data.get("posts") or []
my_posts = [p for p in posts if isinstance(p, dict) and (p.get("author") or {}).get("name","").lower() == agent_name.lower()]

post_ids = [p.get("id") for p in my_posts if p.get("id")]

if not post_ids:
    # Fallback to local post log when feed does not include our posts
    try:
        log_path = os.environ.get("POST_LOG", "")
        if log_path and os.path.exists(log_path):
            log = json.load(open(log_path))
            if isinstance(log, list):
                post_ids = [e.get("id") for e in log if isinstance(e, dict) and e.get("id")]
    except Exception:
        post_ids = []

if not post_ids:
    print("No recent posts by", agent_name)
    raise SystemExit(0)

new_comments = []
for post_id in post_ids:
    if not post_id:
        continue
    ccode, cbody = http_json(f"https://www.moltbook.com/api/v1/posts/{post_id}/comments?sort=new")
    if ccode != "200":
        continue
    cdata = json.loads(cbody)
    comments = cdata.get("comments") or []
    for c in comments:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        author = (c.get("author") or {}).get("name","")
        if not cid or cid in replied or cid in queued:
            continue
        if author.lower() == agent_name.lower():
            continue
        new_comments.append((post_id, cid, author, c.get("content","")[:200]))

if not new_comments:
    print("No new comments to handle.")
    raise SystemExit(0)

print(f"New comments: {len(new_comments)}")
for post_id, cid, author, snippet in new_comments:
    print(f"- {author} on {post_id}: {snippet}")

if os.environ.get("QUEUE_REPLIES", "0") == "1" and os.environ.get("AUTO_REPLY", "0") != "1":
    qpath = os.environ["REPLY_INBOX"]
    try:
        q = json.load(open(qpath))
        if not isinstance(q, list):
            q = []
    except Exception:
        q = []
    for post_id, cid, author, snippet in new_comments:
        q.append({
            "post_id": post_id,
            "comment_id": cid,
            "author": author,
            "snippet": snippet,
            "queued_at": int(time.time()),
        })
        queued.add(cid)
    with open(qpath, "w") as f:
        json.dump(q, f, indent=2)
    state["queued_comment_ids"] = list(queued)[-1000:]
    save_state(state)
    print(f"Queued replies: {len(new_comments)} (queue={qpath})")
    raise SystemExit(0)

if not auto_reply:
    print("AUTO_REPLY=0, not posting replies.")
    raise SystemExit(0)

for post_id, cid, author, snippet in new_comments:
    # simple reply; no threading (parent_id) to avoid mistakes
    payload = {"content": reply_template}
    rcode, rbody = http_json(f"https://www.moltbook.com/api/v1/posts/{post_id}/comments", method="POST", payload=payload)
    if rcode in ("200","201"):
        replied.add(cid)
        time.sleep(2)

state["replied_comment_ids"] = list(replied)[-500:]
save_state(state)
print("Auto-replies posted.")
PY

#!/usr/bin/env bash
# Solid MoltWorld turn: PULL world/recent_chat in this script, inject into the turn message, then wake the gateway.
# The agent receives the data in the message and only has to call chat_say — no reliance on the model calling world_state first.
#
# Usage: bash run_moltworld_pull_and_wake.sh
# Schedule: system cron every 2 min, e.g.:
#   */2 * * * * /home/user/run_moltworld_pull_and_wake.sh
# Requires: ~/.moltworld.env with WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_API_BASE (optional).
#           OpenClaw gateway running (127.0.0.1:18789) with auth token in ~/.openclaw/openclaw.json.
# The agent must understand questions in recent_chat, solve them, and reply via chat_say (no hardcoded answers in this script).
#
# Optional: MOLTWORLD_SKIP_IF_UNCHANGED=1 — do a cheap GET /chat/recent?limit=1 first; if the last message
#           matches the previous run (stored in ~/.moltworld_last_chat), skip full pull and wake (saves compute).
# Behavior: We only relay what OpenClaw actually said (parse gateway log and POST to theebie). We do NOT post
#           any message from outside (no fixed fallback text, no Ollama substitute). Per openclaw-behavior: agents decide.
set -e

_ts() { date +%H:%M:%S 2>/dev/null || echo "??:??:??"; }
_trace() { if [[ -n "${MOLTWORLD_TRACE_TIMING:-}" ]]; then echo "[$(_ts)] TRACE_$*" >&2; fi; }

ENV_FILE="${HOME}/.moltworld.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Create it with WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"

AGENT_NAME="${DISPLAY_NAME:-${AGENT_NAME:-$AGENT_ID}}"
TOKEN="${WORLD_AGENT_TOKEN:-}"
BASE_URL="${WORLD_API_BASE:-https://www.theebie.de}"

if [[ -z "$TOKEN" || -z "$AGENT_ID" ]]; then
  echo "ERROR: WORLD_AGENT_TOKEN and AGENT_ID must be set in $ENV_FILE" >&2
  exit 1
fi
[[ -z "$AGENT_NAME" ]] && AGENT_NAME="$AGENT_ID"

# Optional: MoltWorld context off = do not inject recent_chat/TASK (so you can chat with agent without MoltWorld).
# Set via: ssh sparky1 'echo off > ~/.moltworld_context'  or  .\scripts\clawd\set_moltworld_context.ps1 -Off
CONTEXT_FILE="${HOME}/.moltworld_context"
if [[ -f "$CONTEXT_FILE" ]]; then
  CONTEXT_VAL="$(cat "$CONTEXT_FILE" 2>/dev/null | tr -d '\r\n' | tr '[:upper:]' '[:lower:]')"
  if [[ "$CONTEXT_VAL" = "off" ]]; then
    echo "200"
    echo '{"ok":true,"skip":"moltworld_context_off"}'
    exit 0
  fi
fi

_trace "script_start"

# Config for gateway token (OpenClaw or Clawdbot)
CONFIG="$HOME/.openclaw/openclaw.json"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="$HOME/.clawdbot/clawdbot.json"
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: No gateway config at ~/.openclaw/openclaw.json or ~/.clawdbot/clawdbot.json." >&2
  exit 1
fi
# When MoltWorld plugin is disabled (OpenClaw only), do not pull/wake. Clawdbot has no plugin key → continue.
if python3 -c "
import json, sys, os
p = os.path.expanduser(sys.argv[1]) if len(sys.argv) > 1 else ''
if not p or not os.path.isfile(p):
    sys.exit(0)   # no config -> continue (e.g. Clawdbot path)
with open(p) as f:
    d = json.load(f)
e = d.get('plugins', {}).get('entries', {}).get('openclaw-moltworld', {})
if not e:
    sys.exit(0)   # no plugin block (Clawdbot) -> continue
if e.get('enabled') is True:
    sys.exit(0)   # enabled -> continue
sys.exit(1)       # explicitly disabled -> skip
" "$CONFIG" 2>/dev/null; then
  : # plugin enabled or N/A, continue
else
  echo "200"
  echo '{"ok":true,"skip":"moltworld_plugin_disabled"}'
  exit 0
fi

# 0) Optional: cheap ping — if last message unchanged, skip full pull and wake
STATE_FILE="${HOME}/.moltworld_last_chat"
if [[ -n "${MOLTWORLD_SKIP_IF_UNCHANGED:-}" ]]; then
  RECENT_JSON=$(curl -s -S -H "Content-Type: application/json" "$BASE_URL/chat/recent?limit=1" 2>/dev/null) || true
  if [[ -n "$RECENT_JSON" ]]; then
    FINGERPRINT=$(python3 -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    msgs = d.get('messages') or []
    if not msgs:
        sys.exit(0)
    m = msgs[-1]
    # stable fingerprint: created_at + sender_id + text
    ts = m.get('created_at') or 0
    sid = (m.get('sender_id') or '').strip()
    txt = (m.get('text') or '').strip()[:500]
    print(f'{ts}|{sid}|{txt}')
except Exception:
    pass
" "$RECENT_JSON" 2>/dev/null) || true
    if [[ -n "$FINGERPRINT" && -f "$STATE_FILE" ]]; then
      PREV=$(cat "$STATE_FILE" 2>/dev/null) || true
      if [[ "$PREV" = "$FINGERPRINT" ]]; then
        echo "200"
        echo '{"ok":true,"skip":"unchanged"}'
        exit 0
      fi
    fi
  fi
fi

# 1) Pull: fetch world from MoltWorld backend (or use test payload for MOLTWORLD_TEST_SPIEGEL=1)
_trace "pull_start"
if [[ -n "${MOLTWORLD_TEST_SPIEGEL:-}" ]]; then
  WORLD_JSON=$(python3 -c '
import json
print(json.dumps({"recent_chat": [{"sender_id": "TestBot", "sender_name": "TestBot", "text": "what is on the frontpage of www.spiegel.de?", "created_at": 0}]}))
')
  _trace "pull_done (test_spiegel)"
else
  WORLD_JSON=$(curl -s -S -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$BASE_URL/world" 2>/dev/null) || true
  _trace "pull_done"
fi
if [[ -z "$WORLD_JSON" || "$WORLD_JSON" =~ ^\{\} ]]; then
  echo "ERROR: Failed to fetch $BASE_URL/world (check token and network)." >&2
  exit 1
fi

# Skip wake if we just posted (prevents double-posting when cron/poll runs twice in quick succession)
if [[ "${MOLTWORLD_SKIP_IF_WE_JUST_POSTED:-1}" = "1" && -n "$AGENT_ID" ]]; then
  export MOLTWORLD_WE_POSTED_COOLDOWN_SEC="${MOLTWORLD_WE_POSTED_COOLDOWN_SEC:-90}"
  WE_JUST_POSTED=$(python3 -c "
import json, sys, os, time
try:
    world = json.loads(sys.argv[1])
    chat = world.get('recent_chat') or []
    if not chat: sys.exit(0)
    m = chat[-1]
    sid = (m.get('sender_id') or '').strip()
    aid = (os.environ.get('AGENT_ID') or '').strip()
    if sid != aid: sys.exit(0)
    created = float(m.get('created_at') or 0)
    if not created: sys.exit(0)
    cooldown = int(os.environ.get('MOLTWORLD_WE_POSTED_COOLDOWN_SEC') or '90')
    if (time.time() - created) < cooldown:
        print('1')
except Exception:
    pass
" "$WORLD_JSON" 2>/dev/null) || true
  if [[ "$WE_JUST_POSTED" = "1" ]]; then
    echo "200"
    echo '{"ok":true,"skip":"we_just_posted"}'
    _trace "skip_we_just_posted"
    exit 0
  fi
fi

# 2) Build message with recent_chat injected (so the agent sees it without calling world_state)
TMP_WORLD=$(mktemp)
TMP_PAYLOAD=$(mktemp)
TMP_V1=$(mktemp)
TMP_WAKE=$(mktemp)
trap 'rm -f "$TMP_WORLD" "$TMP_PAYLOAD" "$TMP_V1" "$TMP_WAKE"' EXIT
echo "$WORLD_JSON" > "$TMP_WORLD"

python3 - "$TMP_WORLD" "$AGENT_NAME" "$TMP_PAYLOAD" "$TMP_V1" "$TMP_WAKE" << 'PY'
import json, os, sys, time
world_path, agent_name, out_path, v1_path, wake_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
with open(world_path, "r", encoding="utf-8") as f:
    world = json.load(f)
chat = world.get("recent_chat") or []
last = chat[-5:]
agent_id = (os.environ.get("AGENT_ID") or "").strip()
now_sec = time.time()
last_msg = last[-1] if last else {}
last_sender = (last_msg.get("sender_id") or last_msg.get("sender_name") or "").strip()
last_text = (last_msg.get("text") or "").strip()
other_bot = "MalicorSparky2" if (agent_id or "").strip() == "Sparky1Agent" else "Sparky1Agent"
def _is_other_bot(s):
    if not s:
        return False
    s = s.strip()
    if s == other_bot:
        return True
    if other_bot == "MalicorSparky2":
        return "MalicorSparky2" in s or ("Malicor" in s and "Sparky2" in s)
    return ("Sparky1" in s and "Agent" in s) or s == "Sparky1Agent"
reply_to_other = _is_other_bot(last_sender) and bool(last_text)
last_from_us = agent_id and (last_msg.get("sender_id") or "").strip() == agent_id

# Direct Ollama prompt: no tool-calling, just generate a conversational reply.
lines = [
    f"You are {agent_name}, an AI agent in MoltWorld — a shared virtual world with other agents.",
    "Reply with ONLY your message text. No JSON, no tool calls, no markdown, no prefixes.",
    "Keep replies 1–3 sentences, natural and varied.",
]
if reply_to_other:
    lines.extend([
        "",
        f"The other agent ({other_bot}) just said: \"{last_text[:280]}\"",
        "Reply directly to what they said. Reference their words or answer their question.",
        "BAD: generic greetings like 'Hello!' or 'Good idea!' that ignore what they said.",
        "GOOD: specific responses that show you read their message.",
    ])
lines.append("")
lines.append("Recent chat (latest last):")
for i, m in enumerate(last):
    sender = m.get("sender_name") or m.get("sender_id") or "?"
    text = (m.get("text") or "").strip()
    suffix = ""
    if i == len(last) - 1:
        try:
            created_at = m.get("created_at")
            created_sec = float(created_at) if created_at else 0
            if created_sec:
                age_min = int((now_sec - created_sec) / 60)
                suffix = f" ({age_min} min ago)" if age_min >= 1 else ""
            if agent_id and (m.get("sender_id") or "").strip() == agent_id:
                suffix = " (from you)" if not suffix else suffix + ", from you"
        except (TypeError, ValueError):
            pass
    lines.append(f"  {sender}: {text}{suffix}")

if last_from_us:
    lines.extend([
        "",
        "The last message is from you — do NOT reply (wait for the other agent). Output exactly: SKIP",
    ])
else:
    if reply_to_other:
        lines.append("")
        lines.append("Now write your reply to the other agent. Just the message text, nothing else.")
    else:
        lines.extend([
            "",
            "Start a new topic or ask an interesting question. Be creative and specific.",
            "Now write your message. Just the text, nothing else.",
        ])
text = "\n".join(lines)
# Payload for /hooks/agent (gateway fallback).
payload = {"message": text, "wakeMode": "now", "name": "MoltWorld", "model": "ollama/llama3.3:latest", "deliver": False, "timeoutSeconds": 120}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
# Payload for direct Ollama /api/chat call (preferred path — no gateway overhead).
ollama_model = os.environ.get("MOLTWORLD_OLLAMA_MODEL", "qwen3.5:35b")
ollama_payload = {"model": ollama_model, "messages": [{"role": "user", "content": text}], "stream": False}
with open(v1_path, "w", encoding="utf-8") as f:
    json.dump(ollama_payload, f, ensure_ascii=False)
# Payload for /hooks/wake (gateway expects "text" and "mode")
wake_payload = {"text": text, "mode": "now"}
with open(wake_path, "w", encoding="utf-8") as f:
    json.dump(wake_payload, f, ensure_ascii=False)
PY

_trace "build_payload_done"

# Optional: emit payload preview for test -Debug
if [[ -n "${MOLTWORLD_DEBUG:-}" ]]; then
  python3 - "$TMP_PAYLOAD" << 'PYDEBUG'
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    t = (d.get("message") or d.get("text") or "")[:1200]
    out = json.dumps({"payload_text_preview": t})
    print("MOLTWORLD_DEBUG_PAYLOAD=" + out)
except Exception:
    pass
PYDEBUG
fi

# 3) Direct Ollama call: bypass gateway entirely for conversation.
#    Call Ollama /api/chat, extract the model's response, post to theebie directly.
OLLAMA_BASE="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
TMP_OLLAMA_RESP=$(mktemp)
trap 'rm -f "$TMP_WORLD" "$TMP_PAYLOAD" "$TMP_V1" "$TMP_WAKE" "$TMP_OLLAMA_RESP"' EXIT

_trace "ollama_chat_start"
OLLAMA_HTTP=$(curl -s -S -X POST "${OLLAMA_BASE}/api/chat" \
  -H "Content-Type: application/json" \
  --data-binary "@$TMP_V1" \
  -o "$TMP_OLLAMA_RESP" -w "%{http_code}" 2>/dev/null) || OLLAMA_HTTP="000"
_trace "ollama_chat_done code=$OLLAMA_HTTP"

CHAT_SAY_TEXT=""
code="$OLLAMA_HTTP"
if [[ "$OLLAMA_HTTP" = "200" ]]; then
  CHAT_SAY_TEXT=$(python3 -c "
import json, sys, re
with open(sys.argv[1]) as f:
    d = json.load(f)
msg = d.get('message', {})
text = (msg.get('content') or '').strip()
if text:
    text = re.sub(r'^(chat_say|reply|response|message)\s*[:：]\s*', '', text, flags=re.IGNORECASE).strip()
    if len(text) > 2 and text[0] == '\"' and text[-1] == '\"':
        text = text[1:-1].strip()
    # SKIP means the model chose not to reply (e.g. last message was from us)
    if text.upper().startswith('SKIP'):
        text = ''
print(text[:1000])
" "$TMP_OLLAMA_RESP" 2>/dev/null) || true
fi

_trace "ollama_response len=${#CHAT_SAY_TEXT}"
echo "${code}"
echo "{\"ok\":true,\"pull\":\"world\",\"mode\":\"direct_ollama\",\"http_code\":\"$code\"}"

# 4) Post the model's response directly to theebie (no relay needed).
if [[ -n "$CHAT_SAY_TEXT" && -n "$TOKEN" && -n "$AGENT_ID" ]]; then
  # Dedup: skip if our last message is identical and recent
  RECENT_FOR_DEDUP=$(curl -s -S -H "Authorization: Bearer $TOKEN" "$BASE_URL/chat/recent?limit=10" 2>/dev/null) || true
  SKIP_POST=0
  DEDUP_MAX_AGE_SEC="${MOLTWORLD_DEDUP_MAX_AGE_SEC:-300}"
  if [[ -n "$RECENT_FOR_DEDUP" ]]; then
    export CHAT_SAY_TEXT AGENT_ID DEDUP_MAX_AGE_SEC
    SKIP_POST=$(python3 -c "
import json, sys, os, time
aid = (os.environ.get('AGENT_ID') or '').strip()
new_text = (os.environ.get('CHAT_SAY_TEXT') or '').strip()
max_age = int(os.environ.get('DEDUP_MAX_AGE_SEC') or '300')
try:
    d = json.loads(sys.argv[1])
    now = time.time()
    for m in (d.get('messages') or [])[::-1]:
        if (m.get('sender_id') or '').strip() == aid:
            last = (m.get('text') or '').strip()
            created = float(m.get('created_at') or 0)
            age_sec = now - created if created else 999999
            if last == new_text and age_sec < max_age:
                print(1)
            else:
                print(0)
            sys.exit(0)
    print(0)
except Exception:
    print(0)
" "$RECENT_FOR_DEDUP" 2>/dev/null) || echo "0"
  fi
  if [[ "$SKIP_POST" = "1" ]]; then
    _trace "post_skip_duplicate len=${#CHAT_SAY_TEXT}"
  else
    POST_BODY=$(CHAT_SAY_TEXT="$CHAT_SAY_TEXT" AGENT_ID="$AGENT_ID" AGENT_NAME="$AGENT_NAME" python3 -c 'import json,os; print(json.dumps({"sender_id":os.environ["AGENT_ID"],"sender_name":os.environ["AGENT_NAME"],"text":os.environ.get("CHAT_SAY_TEXT","")}))' 2>/dev/null)
    if [[ -n "$POST_BODY" ]]; then
      POST_CODE=$(curl -s -S -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/chat/say" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$POST_BODY" 2>/dev/null) || POST_CODE="000"
      _trace "chat_say_post code=$POST_CODE len=${#CHAT_SAY_TEXT}"
      echo "{\"posted\":true,\"code\":\"$POST_CODE\",\"text_len\":${#CHAT_SAY_TEXT}}"
    fi
  fi
fi

# Always remember last message (for cron skip-if-unchanged and for poll loop)
if [[ -n "$WORLD_JSON" ]]; then
  python3 -c "
import json, sys, os
try:
    world = json.loads(sys.argv[1])
    chat = world.get('recent_chat') or []
    if not chat:
        sys.exit(0)
    m = chat[-1]
    ts = m.get('created_at') or 0
    sid = (m.get('sender_id') or '').strip()
    txt = (m.get('text') or '').strip()[:500]
    path = os.path.expanduser('$STATE_FILE')
    with open(path, 'w') as f:
        f.write(f'{ts}|{sid}|{txt}')
except Exception:
    pass
" "$WORLD_JSON" 2>/dev/null || true
fi

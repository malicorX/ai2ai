#!/usr/bin/env bash
# Solid MoltWorld turn: PULL world/recent_chat in this script, inject into the turn message, then wake the gateway.
# The agent receives the data in the message and only has to call chat_say — no reliance on the model calling world_state first.
#
# Usage: CLAW=openclaw bash run_moltworld_pull_and_wake.sh   (or CLAW=clawdbot; default: openclaw)
# Schedule: system cron every 2 min, e.g.:
#   */2 * * * * CLAW=openclaw /home/user/run_moltworld_pull_and_wake.sh
# Requires: ~/.moltworld.env with WORLD_AGENT_TOKEN, AGENT_ID, DISPLAY_NAME (or AGENT_NAME), WORLD_API_BASE (optional).
#           Gateway running (127.0.0.1:18789) with auth token in ~/.openclaw/openclaw.json or ~/.clawdbot/clawdbot.json.
# The agent must understand questions in recent_chat, solve them, and reply via chat_say (no hardcoded answers in this script).
#
# Optional: MOLTWORLD_SKIP_IF_UNCHANGED=1 — do a cheap GET /chat/recent?limit=1 first; if the last message
#           matches the previous run (stored in ~/.moltworld_last_chat), skip full pull and wake (saves compute).
# Optional: MOLTWORLD_FALLBACK_REPLY=1 (default) — if the agent did not post a reply within the wait window,
#           POST a fallback message to theebie: "I don't know how to answer this, sorry." Set to 0 to disable.
# Optional: MOLTWORLD_FALLBACK_REPLY_AFTER_SEC=95 — seconds to wait after wake before checking and maybe sending fallback.
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
CLAW="${CLAW:-openclaw}"

if [[ -z "$TOKEN" || -z "$AGENT_ID" ]]; then
  echo "ERROR: WORLD_AGENT_TOKEN and AGENT_ID must be set in $ENV_FILE" >&2
  exit 1
fi
[[ -z "$AGENT_NAME" ]] && AGENT_NAME="$AGENT_ID"

_trace "script_start"

# Config for gateway token (openclaw or clawdbot)
CONFIG="$HOME/.openclaw/openclaw.json"
[[ "$CLAW" = "clawdbot" ]] && CONFIG="$HOME/.clawdbot/clawdbot.json"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="$HOME/.clawdbot/clawdbot.json"
  [[ -f "$HOME/.openclaw/openclaw.json" ]] && CONFIG="$HOME/.openclaw/openclaw.json"
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: No gateway config found (~/.openclaw or ~/.clawdbot)." >&2
  exit 1
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

# 2) Build message with recent_chat injected (so the agent sees it without calling world_state)
TMP_WORLD=$(mktemp)
TMP_PAYLOAD=$(mktemp)
TMP_V1=$(mktemp)
TMP_WAKE=$(mktemp)
trap 'rm -f "$TMP_WORLD" "$TMP_PAYLOAD" "$TMP_V1" "$TMP_WAKE"' EXIT
echo "$WORLD_JSON" > "$TMP_WORLD"

python3 - "$TMP_WORLD" "$AGENT_NAME" "$TMP_PAYLOAD" "$TMP_V1" "$TMP_WAKE" << 'PY'
import json, sys
world_path, agent_name, out_path, v1_path, wake_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
with open(world_path, "r", encoding="utf-8") as f:
    world = json.load(f)
chat = world.get("recent_chat") or []
last = chat[-5:]
# If last message is a math question, put the task first so the model sees it before other instructions.
last_text = (last[-1].get("text") or "").strip() if last else ""
is_math_question = last_text and ("how much is" in last_text.lower() or ("what is" in last_text.lower() and "+" in last_text) or "plus" in last_text.lower())
if is_math_question:
    lines = [
        "TASK: The last message is a math question. You MUST call chat_say with ONLY the numeric answer (e.g. for 'how much is 1 + 3 ?' call chat_say with text '4'). Do not say 'I don't know' or any other text—just the number.",
        "",
        f"You are {agent_name}. MoltWorld recent_chat (latest message last):",
        ""
    ]
else:
    lines = [
        "You MUST use tools this turn. Do not reply with plain text only.",
        f"You are {agent_name}. MoltWorld recent_chat (latest message last):",
        ""
    ]
for m in last:
    sender = m.get("sender_name") or m.get("sender_id") or "?"
    text = (m.get("text") or "").strip()
    lines.append(f"  {sender}: {text}")

# If the last message is the fallback phrase from the other bot, tell the model to reply with something else.
if last:
    last_text = (last[-1].get("text") or "").strip()
    if last_text == "I don't know how to answer this, sorry." and (last[-1].get("sender_id") or "").strip() in ("Sparky1Agent", "MalicorSparky2"):
        lines.append("")
        lines.append("(The last message above is the other bot's generic fallback. Reply with a short friendly line to keep the conversation going, e.g. a greeting or a new topic. Do not repeat that phrase.)")
    # Math question already handled at top of prompt (TASK first).

# Narrator (sparky1): open or continue conversations; search the web when chat is quiet.
is_narrator = "Sparky1" in agent_name or agent_name == "Sparky1Agent"
if is_narrator:
    lines.extend([
        "",
        "You are the narrator. Call world_state first, then either web_fetch (or fetch_url) then chat_say, or chat_say directly.",
        "If chat is empty or stale: use web_fetch with a real URL (e.g. https://www.spiegel.de or a news site), then call chat_say with a 1–2 sentence summary or question.",
        "If the last message is from MalicorSparky2 or another bot: reply briefly with chat_say to keep the conversation going (e.g. a follow-up question or short comment). Do not say 'I don't know how to answer this' to the other bot.",
        "Always call chat_say with your reply. Use only tools; no plain-text-only output."
    ])
else:
    lines.extend([
        "",
        "Call world_state first. Then: if the last message asks about a webpage or URL, call web_fetch (or fetch_url) with that URL and then call chat_say with a short summary.",
        "If it is a normal question (math, time, etc.), answer in chat_say. If the last message is from Sparky1Agent (e.g. a greeting or topic), reply with chat_say to continue the conversation—do not say 'I don't know how to answer this' to the other bot.",
        "Only if a human asked something you cannot answer, call chat_say with: I don't know how to answer this, sorry. Use only tools; no plain-text-only output."
    ])
text = "\n".join(lines)
# Payload for /hooks/agent (isolated turn)
payload = {"message": text, "wakeMode": "now", "name": "MoltWorld", "model": "ollama/llama3.3:latest", "deliver": False, "timeoutSeconds": 120}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
# Payload for POST /v1/responses (main agent with MoltWorld plugin / chat_say)
v1_payload = {"model": "openclaw:main", "input": text}
with open(v1_path, "w", encoding="utf-8") as f:
    json.dump(v1_payload, f, ensure_ascii=False)
# Payload for /hooks/wake (clawdbot: gateway expects "text" and "mode")
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

# 3) Tokens: gateway.auth.token for /v1/responses; hooks.token or gateway.auth.token for /hooks/agent
WAKE_TOKEN=$(python3 -c "
import json, sys
p = sys.argv[1]
with open(p, 'r') as f:
    d = json.load(f)
h = d.get('hooks', {})
token = h.get('token') if h.get('enabled') else None
if not token:
    gw = d.get('gateway', {})
    auth = gw.get('auth')
    token = gw.get('token')
    if isinstance(auth, dict):
        token = token or auth.get('token')
print(token or '')
" "$CONFIG" 2>/dev/null) || true
GW_TOKEN=$(python3 -c "
import json, sys
p = sys.argv[1]
with open(p, 'r') as f:
    d = json.load(f)
gw = d.get('gateway', {})
auth = gw.get('auth') or {}
token = auth.get('token') or gw.get('token')
print(token or '')
" "$CONFIG" 2>/dev/null) || true
[[ -z "$GW_TOKEN" ]] && GW_TOKEN="$WAKE_TOKEN"

# 4) Run agent turn: prefer POST /v1/responses (main agent with MoltWorld/chat_say); fallback to /hooks/agent
if [[ -z "$WAKE_TOKEN" ]]; then
  echo "WARN: No hooks.token or gateway.auth.token. Run enable_hooks_on_sparky.sh on this host." >&2
fi
code="000"
_trace "post_v1_responses_start"
if [[ -n "$GW_TOKEN" ]]; then
  # Try OpenResponses API first (main agent = has MoltWorld plugin and chat_say)
  code=$(curl -s -S -X POST http://127.0.0.1:18789/v1/responses \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $GW_TOKEN" \
    -H "x-openclaw-agent-id: main" \
    --data-binary "@$TMP_V1" \
    -o /dev/null -w "%{http_code}" 2>/dev/null) || code="000"
  _trace "post_v1_responses_done code=$code"
  if [[ "$code" != "200" && "$code" != "201" ]]; then
    # Fallback: /hooks/agent (isolated turn; may not have plugin)
    _trace "post_hooks_agent_start (fallback)"
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $WAKE_TOKEN" \
      --data-binary "@$TMP_PAYLOAD" \
      -o /dev/null -w "%{http_code}" 2>/dev/null) || code="000"
    _trace "post_hooks_agent_done code=$code"
    # Clawdbot: if still not 200/201 (e.g. 202 from v1), try /hooks/wake with {text, mode} — gateway runs one turn
    if [[ "$CLAW" = "clawdbot" && "$code" != "200" && "$code" != "201" && -n "$WAKE_TOKEN" ]]; then
      _trace "post_hooks_wake_start (clawdbot)"
      code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/wake \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $WAKE_TOKEN" \
        --data-binary "@$TMP_WAKE" \
        -o /dev/null -w "%{http_code}" 2>/dev/null) || code="000"
      _trace "post_hooks_wake_done code=$code"
    fi
  fi
else
  _trace "post_hooks_agent_start (no GW_TOKEN)"
  code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/agent \
    -H "Content-Type: application/json" \
    --data-binary "@$TMP_PAYLOAD" \
    -o /dev/null -w "%{http_code}" 2>/dev/null) || code="000"
  _trace "post_hooks_agent_done code=$code"
  if [[ "$CLAW" = "clawdbot" && "$code" != "200" && "$code" != "201" && -n "$WAKE_TOKEN" ]]; then
    _trace "post_hooks_wake_start (clawdbot)"
    code=$(curl -s -S -X POST http://127.0.0.1:18789/hooks/wake \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $WAKE_TOKEN" \
      --data-binary "@$TMP_WAKE" \
      -o /dev/null -w "%{http_code}" 2>/dev/null) || code="000"
    _trace "post_hooks_wake_done code=$code"
  fi
fi
_trace "script_end"
echo "${code}"
echo '{"ok":true,"pull":"world","wake":"sent"}'

# 5) Fallback: if agent did not reply within the window, POST "I don't know how to answer this, sorry." to theebie
#    Only when the last message was from a human/TestBot — never when it was from our bots (stops fallback ping-pong).
#    When the other bot asked, we rely entirely on the agent (OpenClaw) to reply via chat_say; no scripted reply from here.
FALLBACK_ENABLED="${MOLTWORLD_FALLBACK_REPLY:-1}"
FALLBACK_WAIT="${MOLTWORLD_FALLBACK_REPLY_AFTER_SEC:-95}"
LAST_SENDER_IS_OUR_BOT=$(python3 -c "
import json, sys
try:
    world = json.loads(sys.argv[1])
    chat = world.get('recent_chat') or []
    if not chat:
        sys.exit(0)
    sid = (chat[-1].get('sender_id') or '').strip()
    if sid in ('Sparky1Agent', 'MalicorSparky2'):
        print('1')
except Exception:
    pass
" "$WORLD_JSON" 2>/dev/null) || true
if [[ "$FALLBACK_ENABLED" != "0" && ("$code" = "200" || "$code" = "201") && -n "$WORLD_JSON" && -n "$TOKEN" && -n "$AGENT_ID" && "$LAST_SENDER_IS_OUR_BOT" != "1" ]]; then
  QUESTION_TS=$(python3 -c "
import json, sys
try:
    world = json.loads(sys.argv[1])
    chat = world.get('recent_chat') or []
    if not chat:
        sys.exit(0)
    print(float(chat[-1].get('created_at') or 0))
except Exception:
    pass
" "$WORLD_JSON" 2>/dev/null) || true
  if [[ -n "$QUESTION_TS" ]]; then
    sleep "$FALLBACK_WAIT"
    RECENT_AFTER=$(curl -s -S -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$BASE_URL/chat/recent?limit=25" 2>/dev/null) || true
    AGENT_REPLIED=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    threshold = float(sys.argv[2])
    our_id = (sys.argv[3] or '').strip()
    for m in (data.get('messages') or [])[-25:]:
        if (m.get('sender_id') or '').strip() == our_id and float(m.get('created_at') or 0) > threshold:
            print('1')
            break
except Exception:
    pass
" "$RECENT_AFTER" "$QUESTION_TS" "$AGENT_ID" 2>/dev/null) || true
    if [[ "$AGENT_REPLIED" != "1" ]]; then
      FALLBACK_TEXT="I don't know how to answer this, sorry."
      curl -s -S -X POST "$BASE_URL/chat/say" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"sender_id\":\"$AGENT_ID\",\"sender_name\":\"$AGENT_NAME\",\"text\":\"$FALLBACK_TEXT\"}" \
        -o /dev/null -w "%{http_code}" 2>/dev/null || true
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

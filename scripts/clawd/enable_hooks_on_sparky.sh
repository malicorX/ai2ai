#!/usr/bin/env bash
# Enable hooks on the gateway so POST /hooks/wake is accepted (fixes 405).
# Sets hooks.enabled=true and hooks.token (random if not set). Restart gateway to apply.
# Usage: CLAW=openclaw bash enable_hooks_on_sparky.sh  (or CLAW=clawdbot; run on sparky)
set -e
CONFIG="$HOME/.openclaw/openclaw.json"
[[ "${CLAW:-}" = "clawdbot" ]] && CONFIG="$HOME/.clawdbot/clawdbot.json"
[[ ! -f "$CONFIG" ]] && CONFIG="$HOME/.clawdbot/clawdbot.json"
[[ ! -f "$CONFIG" ]] && CONFIG="$HOME/.openclaw/openclaw.json"
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: No config found." >&2
  exit 1
fi
python3 - "$CONFIG" <<'PY'
import json, sys, secrets
p = sys.argv[1]
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
hooks = data.setdefault("hooks", {})
hooks["enabled"] = True
if not hooks.get("token"):
    hooks["token"] = secrets.token_hex(16)
with open(p, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print("hooks.enabled=True hooks.token set", p)
PY
# Restart gateway
for f in "$HOME/.nvm/nvm.sh" "$HOME/.bashrc"; do [[ -f "$f" ]] && source "$f" 2>/dev/null; done
cmd="${CLAW:-openclaw}"
"$cmd" gateway stop 2>/dev/null || true
sleep 2
logdir="$(dirname "$CONFIG")"
nohup "$cmd" gateway >> "$logdir/gateway.log" 2>&1 &
sleep 3
code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:18789/ 2>/dev/null || echo "0")
echo "Gateway: $code"

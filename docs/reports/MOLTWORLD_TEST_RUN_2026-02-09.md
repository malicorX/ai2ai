*Dated report. For current procedures see [../MOLTWORLD_SPARKY1_VS_SPARKY2.md](../MOLTWORLD_SPARKY1_VS_SPARKY2.md) and [../OPERATIONS.md](../OPERATIONS.md).*

---

# MoltWorld test run report — 2026-02-09

Summary of what was run, what theebie.de shows, and what the logs say.

---

## 1. Scripts run

| Script | Result |
|--------|--------|
| `verify_moltworld_cron.ps1` | Gateways OK (18789). sparky1 cron Status **skipped** (main session). sparky2 cron Status **error**, Last 1m ago. No webhooks (ADMIN_TOKEN not set to list). |
| `run_restart_gateways_on_sparkies.ps1` | Both gateways reported OK after restart. |
| `run_moltworld_chat_now.ps1` | Both sparkies returned `"ok": true, "ran": true`. Waited 75s each. |
| `test_moltworld_math_reply.ps1` | **Not run:** ADMIN_TOKEN not set. Set `$env:ADMIN_TOKEN` or pass `-AdminToken` to run. |

---

## 2. theebie.de (GET /chat/recent)

Last 8 messages (most recent last): Sparky1Agent echo/test messages and math questions. MalicorSparky2 had replied "Hi" earlier but no recent messages — conclusion: backend chat works; replier may need cron/webhook fix.

---

## 3–5. Gateway logs, webhooks, next steps

See git history of this file or [../AGENT_CHAT_DEBUG.md](../AGENT_CHAT_DEBUG.md) and [../OPENCLAW_MOLTWORLD_CHAT_PLAN.md](../OPENCLAW_MOLTWORLD_CHAT_PLAN.md) for current debugging and webhook setup.

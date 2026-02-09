# OpenClaw / MoltWorld — current status report

**Generated:** 2026-02-09 (from live checks)  
**Fixed:** 2026-02-09 — gateways restarted; sparky1 orphan killed, both hosts running.

---

## Summary

| Host    | Gateway      | Port 18789   | MoltWorld cron      | Notes |
|---------|--------------|-------------|---------------------|--------|
| sparky1 | **active**   | in use      | Last run **ok**     | Fixed: orphan killed, single systemd process (PID 2969638) |
| sparky2 | **active**   | in use      | Can run            | Fixed: gateway started (openclaw, PID 3306141) |

**MoltWorld world:** Both agents present at (7,7): Sparky1Agent, MalicorSparky2.

---

## Sparky1

- **Gateway:** systemd reports `active`, port 18789 in use by `clawdbot-gatewa` (pid 2010380).
- **Cron:** "MoltWorld chat turn" exists; Last run ~6m ago, Status **ok**.
- **Issue:** Journal shows repeated failures: *"Gateway failed to start: gateway already running (pid 2010380); lock timeout"* and *"Port 18789 is already in use"*. So an **orphan** gateway process (2010380) is holding the port; each systemd restart tries to start a second process and exits. Restart counter was **3581** — long crash/restart loop. The *working* gateway is the orphan, not the one systemd is managing.

**Fix applied:** Orphan (pid 2010380) was killed; `systemctl --user start clawdbot-gateway.service` started one clean process. If the loop returns: `ssh sparky1 "systemctl --user stop clawdbot-gateway.service; kill \$(ss -tlnp | grep 18789 | grep -oP 'pid=\K[0-9]+') 2>/dev/null; sleep 3; systemctl --user start clawdbot-gateway.service"`.

---

## Sparky2

- **Gateway:** systemd reports **inactive**. No process listening on 18789.
- **Cron:** Cannot list reliably while gateway is down (cron run requires gateway).
- **Issue:** Service was stopped cleanly (SIGTERM) at 09:31 and never started again. No recent start attempts in journal.

**Fix applied:** Gateway started via `run_restart_gateways_on_sparkies.ps1` (unit uses openclaw’s `dist/entry.js`).

---

## MoltWorld (theebie.de)

- **World:** Sparky1Agent and MalicorSparky2 both at (7,7); last_seen present.
- **Chat:** Check https://www.theebie.de/ui/ for recent messages. Useful discussion requires both gateways up and cron runs succeeding (sparky2 currently not running).

---

## Quick actions

1. **Stabilize sparky1:** Stop orphan, then start once:
   ```bash
   ssh sparky1 "clawdbot gateway stop; sleep 3; systemctl --user start clawdbot-gateway.service"
   ```
2. **Bring up sparky2:**
   ```powershell
   .\scripts\clawd\run_restart_gateways_on_sparkies.ps1
   ```
   (Script fixes sparky2 unit path and restarts both; after that, sparky2 should stay up.)
3. **Trigger one chat turn now (after both gateways up):**
   ```powershell
   .\scripts\clawd\run_moltworld_chat_now.ps1
   ```

---

## Scripts reference

| Script | Purpose |
|--------|---------|
| `scripts/clawd/run_restart_gateways_on_sparkies.ps1` | Restart gateways (sparky2 unit fix applied) |
| `scripts/clawd/run_moltworld_chat_now.ps1` | Run MoltWorld chat cron once on both hosts |
| `scripts/clawd/verify_moltworld_cron.ps1` | List crons + world agents |
| `scripts/clawd/add_moltworld_chat_cron.ps1` | Add/refresh MoltWorld chat cron |

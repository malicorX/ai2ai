# Apply jokelord tool-calling patch (Clawd + Ollama tools)

This doc gives the exact steps to get **tool calling** working with Clawd + Ollama on sparky2 using the [jokelord patch](https://github.com/jokelord/openclaw-local-model-tool-calling-patch).

---

## What gets done

1. **Build:** Clone Clawdbot source, copy jokelord’s patched files (4 files), build, install globally on sparky2.
2. **Config:** Add `compat.supportedParameters: ["tools", "tool_choice"]` to every Ollama model in `~/.clawdbot/clawdbot.json`.
3. **Restart:** Restart the gateway so it loads the new binary and config.

After that, the gateway will send tools to Ollama and run tool calls (browser, exec, etc.).

---

## Execute these steps

### Option A — From your Windows PC (recommended)

**Step 1 — Apply patch and build on sparky2** (clone, patch, build, install; can take several minutes):

```powershell
cd M:\Data\Projects\ai_ai2ai
.\scripts\clawd\run_clawd_apply_jokelord.ps1 -Target sparky2
```

If the repo on sparky2 is at `~/ai2ai`, default is correct. If it’s elsewhere:

```powershell
.\scripts\clawd\run_clawd_apply_jokelord.ps1 -Target sparky2 -RemotePath /home/malicor/ai2ai/scripts/clawd
```

**Step 2 — On sparky2: add supportedParameters and restart gateway**

SSH to sparky2, then:

```bash
python3 ~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py
clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &
```

**Step 3 — Test**

Open a new chat (browser or TUI) and ask e.g.:

- *“Use the browser to open https://fiverr.com and list 5 logo design gigs with title and price.”*

If tools run, you’re done.

---

### Option B — All on sparky2 (no Windows)

**Step 1 — Sync repo to sparky2** so these exist:

- `~/ai2ai/scripts/clawd/clawd_apply_jokelord_on_sparky.sh`
- `~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py`

**Step 2 — Apply patch and build** (run on sparky2):

```bash
cd ~/ai2ai/scripts/clawd
bash clawd_apply_jokelord_on_sparky.sh
```

**Step 3 — Add supportedParameters and restart gateway:**

```bash
python3 ~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py
clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &
```

**Step 4 — Test** (new chat, e.g. Fiverr browser prompt above).

---

## If the build fails

- **Wrong tag:** Set the Clawdbot tag before running the apply script, e.g.  
  `export CLAWDBOT_TAG=main`  
  then run `bash clawd_apply_jokelord_on_sparky.sh` again (or clone from a tag that exists in the repo).
- **Missing patched file:** Check that jokelord’s repo has `openclawd-2026.1.24/src/config/zod-schema.core.ts` (and the other 3 files). If paths changed, copy the patched files from [jokelord/openclaw-local-model-tool-calling-patch](https://github.com/jokelord/openclaw-local-model-tool-calling-patch) into your Clawdbot `src/` by hand and run `npm run build` and `sudo npm install -g .` in the Clawdbot clone.
- **Node/npm:** Ensure Node 22+ and npm are installed on sparky2 (`node -v`, `npm -v`).
- **`pnpm: not found`:** The script installs pnpm automatically (via corepack or `npm install -g pnpm`). If it still fails, install manually: `npm install -g pnpm` (or enable corepack: `corepack enable` then `corepack prepare pnpm@latest --activate`).
- **TS errors (resolveClawdbotAgentDir, ToolsLinksSchema, systemPrompt, etc.):** The apply script runs `clawd_jokelord_compat_fixes.sh` after copying the 4 jokelord files. That script aligns the patch with current Clawdbot (OpenClaw naming, `ToolsLinksSchema` in zod-schema.core, compact.ts getter, and removes unsupported `systemPrompt` from session options). Ensure both `clawd_apply_jokelord_on_sparky.sh` and `clawd_jokelord_compat_fixes.sh` are present in `~/ai2ai/scripts/clawd` and re-run.

---

## Summary

| Step | Where | Command |
|------|--------|---------|
| 1. Apply patch + build | From PC | `.\scripts\clawd\run_clawd_apply_jokelord.ps1 -Target sparky2` |
| 1 alt | On sparky2 | `bash ~/ai2ai/scripts/clawd/clawd_apply_jokelord_on_sparky.sh` |
| 2. Add config | On sparky2 | `python3 ~/ai2ai/scripts/clawd/clawd_add_supported_parameters.py` |
| 3. Restart gateway | On sparky2 | `clawdbot gateway stop; sleep 2; nohup clawdbot gateway >> ~/.clawdbot/gateway.log 2>&1 &` |
| 4. Test | Browser/TUI | New chat, ask for browser tool (e.g. Fiverr 5 gigs). |

# Plan: Use Upstream OpenClaw for Ollama Tool Calling (Move Off Jokelord)

## Current state

- **Problem:** With `api: "openai-completions"`, the gateway does not send tool definitions to Ollama → no tool calls. ([clawdbot #1866](https://github.com/clawdbot/clawdbot/issues/1866))
- **What we do today:** We use the **jokelord patch** (community repo that applies a patch to the gateway source and uses `compat.supportedParameters: ["tools", "tool_choice"]`) so tools are sent. See [CLAWD_JOKELORD_STEPS.md](CLAWD_JOKELORD_STEPS.md).

## Upstream status (Feb 2026)

- **OpenClaw PR #4287** (“feat: enhance OpenAI compatibility for tool calling”) was **closed** by the maintainer bot (feature freeze), but a maintainer (**rbur0425**) reported it was **landed via squash on main** (SHA 7911065fb).
- The fix adds an **opt-in** flag: `compat.openaiCompletionsTools: true` on openai-completions model entries. When set, the gateway routes tools through the SDK “built-in tools” path so Ollama (and vLLM, etc.) receive tool definitions and can return `tool_calls`.
- **PR #9339** is the same change **reopened** with a `fix:` prefix (still open as of Feb 2026). So the behavior is either already in `main` from the squash, or will land when #9339 is merged.
- **Clawdbot #1866** is still open; the fix lives in the **openclaw/openclaw** repo (OpenClaw and Clawdbot share the same codebase; “Clawdbot” is the product name, “openclaw” the repo).
- **Checked 2026-02-13:** The **npm release `openclaw@2026.2.12`** does **not** accept `compat.openaiCompletionsTools` (gateway reports “Unknown config keys” and config invalid). So the fix is **not** in the published npm package yet. For tool calling with Ollama you must use the **jokelord patch** until a release that includes the fix is published, or build from `openclaw/openclaw` main.

## Recommendation: Prefer upstream, keep jokelord as fallback

1. **Use upstream OpenClaw** (official npm or build from `openclaw/openclaw` main) so we get the official fix and one less custom patch to maintain.
2. **Config:** On each Ollama model entry in gateway config, set `compat.openaiCompletionsTools: true` (our scripts currently *remove* this key because **stock** builds rejected it; once the gateway build includes the fix, we **add** it back).
3. **Drop jokelord** for new installs and for sparkies once they run a build that includes the squash (or #9339). Keep jokelord in docs and scripts as a **fallback** for older or custom builds that don’t have the fix yet.

## Concrete steps

### Option A — Upgrade to latest OpenClaw (simplest)

1. On each sparky: `npm install -g openclaw@latest` (or `pnpm install -g openclaw@latest`). Use Node 22+.
2. Confirm the installed version includes the fix (e.g. release notes or `openclaw --version` and check if it’s 2026.2.x or later; the squash was early Feb 2026).
3. In `~/.openclaw/openclaw.json` (or `~/.clawdbot/clawdbot.json`), for each Ollama model under `models.providers.ollama.models[]`, add or set:
   ```json
   "compat": { "openaiCompletionsTools": true }
   ```
   You can run **`scripts/clawd/add_openai_completions_tools.py`** on the sparky (or via SSH) to set this in both config files; our apply scripts currently strip this key, so run the add script *after* an apply if you use upstream.
4. Restart the gateway. No jokelord build or `compat.supportedParameters` needed.
5. Test: e.g. “Use the browser to open https://example.com” or run the Spiegel diagnostic. If tools run, you’re on upstream; you can stop applying the jokelord patch on that host.

### Option B — Build from OpenClaw main (if npm release doesn’t include the fix yet)

1. Clone `openclaw/openclaw`, checkout `main`, build and install globally on the sparky (e.g. `pnpm install`, `pnpm build`, `pnpm install -g .` or equivalent).
2. Same config as Option A: `compat.openaiCompletionsTools: true` on Ollama models.
3. Restart and test. No jokelord.

### Keep jokelord when

- You are pinned to an older OpenClaw/Clawdbot version that does **not** include the squash/#9339.
- You can’t upgrade (e.g. corporate constraint). Then continue using [CLAWD_JOKELORD_STEPS.md](CLAWD_JOKELORD_STEPS.md) and `compat.supportedParameters`.

## Script/doc changes we should make

1. **Docs (CLAWD_SPARKY.md, AGENT_CHAT_DEBUG.md):** State that the fix is in OpenClaw main; prefer `openclaw@latest` (or main) + `compat.openaiCompletionsTools: true`; use jokelord only if the installed build doesn’t support that key.
2. **Apply/config scripts:** Add an optional “upstream” path that **sets** `compat.openaiCompletionsTools: true` on Ollama models instead of removing it (and does not require jokelord). Default can stay “no compat” for stock builds that would otherwise fail to start.
3. **PROJECT_OVERVIEW / CURRENT_STATUS:** Short note that we’re moving to upstream OpenClaw for tool calling when possible; jokelord remains the fallback for older builds.

## Summary

| Approach              | When to use                         | Config key                          |
|-----------------------|-------------------------------------|-------------------------------------|
| **Upstream OpenClaw** | New installs; sparkies after upgrade| `compat.openaiCompletionsTools: true` |
| **Jokelord patch**    | Old build or can’t upgrade           | `compat.supportedParameters: ["tools", "tool_choice"]` |

**Yes, we should update the OpenClaw thing and get away from the jokelord patch where possible.** The fix is in OpenClaw main (squash); once an npm release accepts `compat.openaiCompletionsTools`, use that release and the compat flag. Until then, **you still need the jokelord patch** for Ollama tool calling when using the published npm package (verified: `openclaw@2026.2.12` rejects the compat key). Keep jokelord for tool calling until a release that includes the fix is published, or build from `openclaw/openclaw` main.

# Project rules

This repo follows a few rules that Cursor applies automatically (see `.cursor/rules/`) and that we keep in sync here for humans.

## Deploy yourself, test yourself, fix until done

When a task involves deployment, testing, or fixing (e.g. scripts on sparkies, gateways, MoltWorld chat): **do it yourself**. Deploy, run tests, apply fixes, and repeat until the task is done. Don’t stop after one attempt or after documenting—iterate until it works or the blocker is clearly outside what can be changed in this repo.

- **Deploy yourself** — Run deploy steps (scp, ssh, config, restart). Execute them; don’t only suggest.
- **Test yourself** — Run the tests/checks (narrator, poll, chat recent, logs). Run them; don’t only describe.
- **Apply fixes yourself** — On failure, change code/config, redeploy, retest. Do it; don’t stop at suggestions.
- **Repeat until done** — Keep going until the task is achieved or the only blocker is outside this repo; then document.

Cursor rule: `.cursor/rules/deploy-test-fix-until-done.mdc` (always applied).

## OpenClaw-driven behavior only

All agent behavior must be decided by OpenClaw (LLM/tools), not by hardcoded logic in our code. No scripted replies, turn-taking, or “who talks first” in Python.

Do not parse message content in code to branch the prompt (e.g. if math then add TASK); inject raw context only; put behavioral instructions in the SOUL or a single generic prompt.

Cursor rule: `.cursor/rules/openclaw-behavior.mdc` (always applied).

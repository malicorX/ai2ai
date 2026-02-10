# We use Ollama locally on both sparkies

**No cloud API key (no Anthropic, no OpenAI) is required** for the MoltWorld math-reply test or for the OpenClaw/Clawd gateways on sparky1 and sparky2. The gateways call **Ollama** at `http://127.0.0.1:11434` on each host.

---

## Current Ollama models (run `ollama list` on each host)

**sparky1** (as of last check):
```
NAME                       ID              SIZE      MODIFIED
qwen2.5-coder:32b          b92d6a0bd47e    19 GB     ...
nomic-embed-text:latest    0a109f422b47    274 MB    ...
llama3.1:70b               711a9e8463af    42 GB     ...
llama3.1:8b                46e0c10c039e    4.9 GB    ...
```

**sparky2** (as of last check):
```
NAME                   ID              SIZE      MODIFIED
qwen-agentic:latest    eff468c03838    19 GB     ...
qwen2.5-coder:32b      b92d6a0bd47e    19 GB     ...
llama3.3:latest        a6eb4748fd29    42 GB     ...
llava:13b              0d0eb4d7f485    8.0 GB    ...
llama3.1:70b           711a9e8463af    42 GB     ...
llama3.1:8b            46e0c10c039e    4.9 GB    ...
```

**To refresh this list:** Run on your machine:
- `ssh sparky1 "ollama list"`
- `ssh sparky2 "ollama list"`

Primary model for the replier (sparky2) is typically `ollama/llama3.3:latest` or `ollama/qwen2.5-coder:32b` (set in OpenClaw config).

---

## If the gateway asks for "anthropic" or "API key"

The wake/session must use **Ollama**, not a cloud provider. If you see "No API key found for provider anthropic" in the gateway log:

1. **Fix:** Run the Ollama fix so OpenClaw uses local Ollama and does not fall back to anthropic:
   ```powershell
   .\scripts\clawd\run_fix_openclaw_ollama_on_sparky.ps1 -TargetHost sparky2
   ```
   This also sets `gateway.mode=local`, plugin token from `~/.moltworld.env`, and restarts the gateway.
2. **Restart gateway so it loads the new config:** If the gateway was already running, the fix script tries to stop and restart it. If the old process is still bound to port 18789, kill it and start fresh:
   ```bash
   ssh sparky2 "kill \$(lsof -ti :18789 2>/dev/null) 2>/dev/null; sleep 3; bash -lc 'nohup openclaw gateway >> ~/.openclaw/gateway.log 2>&1 &'"
   ```
   Wait ~10s then run the test.
3. Run the test again:
   ```powershell
   .\scripts\testing\test_moltworld_math_reply.ps1 -AdminToken <token> -Debug
   ```
   The first reply can take 60–90s (Ollama inference).

See [AGENT_CHAT_DEBUG.md](AGENT_CHAT_DEBUG.md) §7d for details.

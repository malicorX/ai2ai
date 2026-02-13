# We use Ollama locally on both sparkies

**No cloud API key (no Anthropic, no OpenAI) is required** for the MoltWorld math-reply test or for the OpenClaw/Clawd gateways on sparky1 and sparky2. **Both gateways use local Ollama only**: each host runs Ollama at `http://127.0.0.1:11434` and the gateway on that host talks to localhost.

---

## Current Ollama models (run `ollama list` on each host)

**sparky1:**
```
NAME                       ID              SIZE      MODIFIED
qwen2.5-coder:32b          b92d6a0bd47e    19 GB     5 days ago
nomic-embed-text:latest    0a109f422b47    274 MB    2 weeks ago
llama3.1:70b               711a9e8463af    42 GB     2 months ago
llama3.1:8b                46e0c10c039e    4.9 GB    2 months ago
```

**sparky2:**
```
NAME                   ID              SIZE      MODIFIED
qwen2.5-coder:32b      b92d6a0bd47e    19 GB     9 days ago
qwen-agentic:latest    eff468c03838    19 GB     9 days ago
llama3.3:latest        a6eb4748fd29    42 GB     12 days ago
llama3.1:70b           711a9e8463af    42 GB     2 months ago
llama3.1:8b            46e0c10c039e    4.9 GB    2 months ago
llava:13b              0d0eb4d7f485    8.0 GB    2 months ago
```

**To refresh:** `ssh sparky1 "ollama list"` and `ssh sparky2 "ollama list"`.

---

## Primary model per host (gateway config)

| Host    | Primary model (config)       | Why |
|---------|------------------------------|-----|
| **sparky1** | `ollama/qwen2.5-coder:32b`   | Set in `~/.openclaw/openclaw.json`. Good tool/code support, 19 GB; llama3.3 not installed on sparky1. |
| **sparky2** | `ollama/qwen-agentic:latest` | Set in `~/.openclaw/openclaw.json`. Custom model (Modelfile from qwen2.5-coder:32b) for more tool-friendly behavior; only on sparky2. |

So **we run with local Ollama only**: no cloud provider; each gateway uses the model configured as primary on that host.

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

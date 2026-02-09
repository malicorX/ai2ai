#!/usr/bin/env python3
"""
Run one LangGraph step with stub tools (no backend required).
Verifies the OpenClaw-driven graph builds and runs when deps are installed.
The decide node calls the LLM once; set OPENAI_API_BASE and OPENAI_API_KEY
for a full step, or the script will fail at the LLM call with a clear error.

Usage (from repo root):
    pip install -r agents/agent_template/requirements.txt
    python scripts/testing/test_langgraph_step.py

Or from agents/:
    pip install -r agent_template/requirements.txt
    cd agents && python ../scripts/testing/test_langgraph_step.py
"""

import os
import sys

# Allow importing agent_template from repo root or from agents/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AGENTS = os.path.join(_REPO_ROOT, "agents")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)


def _stub_tools():
    def noop(*a, **k):
        pass

    return {
        "jobs_list": lambda status=None, limit=50: [],
        "jobs_get": lambda jid: None,
        "jobs_create": lambda t, b, r: "",
        "jobs_claim": lambda jid: False,
        "jobs_submit": lambda jid, body: False,
        "jobs_review": lambda jid, ok, reason, aid, penalty=None: False,
        "do_job": lambda j: "",
        "chat_send": noop,
        "chat_recent": lambda limit=20: [],
        "world_move": noop,
        "board_post": lambda t, b: {"ok": False},
        "trace_event": noop,
        "memory_retrieve": lambda q, k=8: [],
        "memory_append": noop,
        "web_fetch": lambda url: {},
        "web_search": lambda q, n: {"results": []},
        "opportunities_list": lambda limit=40: [],
        "opportunities_update": lambda *a: {},
        "email_template_generate": lambda *a: "",
        "client_response_simulate": lambda *a: {},
        "artifact_put": lambda *a: {},
    }


def _minimal_state():
    return {
        "role": "executor",
        "agent_id": "TestAgent",
        "display_name": "Test",
        "persona": "Test persona",
        "run_id": "",
        "world": {
            "agents": [{"agent_id": "TestAgent", "x": 0, "y": 0}],
            "day": 0,
            "minute_of_day": 0,
        },
        "balance": 100.0,
        "chat_recent": [],
        "open_jobs": [],
        "my_claimed_jobs": [],
        "my_submitted_jobs": [],
        "rejected_jobs": [],
        "recent_jobs": [],
    }


def main() -> int:
    os.environ["USE_LANGGRAPH"] = "1"
    print("Testing LangGraph (OpenClaw-driven) one step...")
    try:
        from agent_template.langgraph_agent import run_graph_step
    except ImportError as e:
        print(f"Import error: {e}")
        print("Install deps: pip install -r agents/agent_template/requirements.txt")
        return 1

    print("  Graph built OK")
    st = _minimal_state()
    tools = _stub_tools()
    try:
        out = run_graph_step(st, tools) or {}
    except Exception as e:
        err = str(e).lower()
        if "api_key" in err or "openai" in err or "connection" in err:
            print("  Step ran but LLM call failed (set OPENAI_API_BASE and OPENAI_API_KEY for full test).")
        print(f"  Error: {e}")
        return 1
    kind = (out.get("action") or {}).get("kind", "?")
    print(f"  Step OK, action kind: {kind}")
    print("LangGraph step test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

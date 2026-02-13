#!/usr/bin/env python3
"""
Test that the web_search action is executed and results stored in state.
Does not require LLM or backend; uses stub tools.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AGENTS = os.path.join(_REPO_ROOT, "agents")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)


def main() -> int:
    os.environ["USE_LANGGRAPH"] = "1"
    from agent_template.langgraph_agent import node_act

    # Stub tools: web_search returns fake results
    captured = {"query": None, "num": None}

    def stub_web_search(q: str, n: int):
        captured["query"] = q
        captured["num"] = n
        return {
            "results": [
                {"title": "Example result 1", "snippet": "Snippet one", "url": "https://example.com/1"},
                {"title": "Example result 2", "snippet": "Snippet two", "url": "https://example.com/2"},
            ]
        }

    tools = {
        "jobs_list": lambda status=None, limit=50: [],
        "jobs_get": lambda jid: None,
        "jobs_create": lambda t, b, r: "",
        "jobs_claim": lambda jid: False,
        "jobs_submit": lambda jid, body: False,
        "jobs_review": lambda jid, ok, reason, aid, penalty=None: False,
        "do_job": lambda j: "",
        "chat_send": lambda t: None,
        "chat_recent": lambda limit=20: [],
        "world_move": lambda dx, dy: None,
        "board_post": lambda t, b: {"ok": False},
        "trace_event": lambda *a, **k: None,
        "memory_retrieve": lambda q, k=8: [],
        "memory_append": lambda *a: None,
        "web_search": stub_web_search,
    }

    state = {
        "role": "proposer",
        "agent_id": "TestAgent",
        "world": {},
        "world_model": {"self": {"x": 0, "y": 0, "place_id": ""}},
        "action": {"kind": "web_search", "query": "site:fiverr.com copywriting gig", "num": 5},
        "__tools": tools,
    }

    out = node_act(state, config=None)
    assert out.get("acted") is True, "expected acted=True after web_search"
    assert "last_web_search_result" in out, "expected last_web_search_result in state"
    res = out["last_web_search_result"]
    assert res.get("query") == "site:fiverr.com copywriting gig"
    assert len(res.get("results", [])) == 2
    assert captured["query"] == "site:fiverr.com copywriting gig"
    assert captured["num"] == 5

    print("web_search action test passed: results stored in state, acted=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())

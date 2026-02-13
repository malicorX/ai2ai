# Web-search as LLM-chosen action – implementation and test report

**Date:** 2026-02-09

## What was implemented

- **Action kind `web_search`** added to the LangGraph agent. The LLM can return `{"kind": "web_search", "query": "...", "num": N}`.
- **`node_act`** handles `web_search`: calls `tools["web_search"](query, num)`, stores the result in **`state["last_web_search_result"]`** (query + results or error), sets `acted = True`.
- **Next decide** receives **`last_web_search_result`** in the user prompt (query + up to 8 results with title/snippet/url), so the agent can use search results to propose jobs, reply in chat, or take other actions.
- **Docs:** BEHAVIOR.md updated (Action kinds, decide description, state fields). Backend still requires `WEB_SEARCH_ENABLED=1` and `SERPER_API_KEY` (see ENV.example, TOOLS.md, API.md).

## Tests run

1. **`scripts/testing/test_langgraph_web_search_action.py`**  
   - Calls `node_act` with a stub `web_search` tool and action `{kind: "web_search", query: "...", num: 5}`.  
   - Asserts: `state["acted"] == True`, `state["last_web_search_result"]` has `query` and `results` (list of dicts with title/snippet/url).  
   - **Result:** Passed.

2. **`scripts/testing/test_langgraph_step.py`**  
   - Existing graph-step test (no web_search in this run).  
   - **Result:** Passed (confirms graph still runs).

## New behavior of the agents

- **Proposer (or any role)** can now **choose** to run a web search in a step. The LLM sees the tool description and can output `web_search` when it decides search is useful (e.g. to find Fiverr gigs, facts, or links).
- After a search, **the next decide** gets the search results in the prompt. The agent can then:
  - Propose a job (e.g. Fiverr gig → sparky task),
  - Use the info in `chat_say` or `board_post`,
  - Or do another action (move, noop, etc.).
- **No “from outside” logic:** when to search and how to use results are entirely decided by the LLM; code only executes the chosen action and feeds back `last_web_search_result`.

## What you need for real search

- **Theebie (or backend)** must have:
  - `WEB_SEARCH_ENABLED=1`
  - `SERPER_API_KEY` set (get key at serper.dev)
- Without these, `web_search` will typically return an error; the agent will see that in `last_web_search_result` and can retry or do something else on the next step.

## What was learned from the test

- The **unit test** confirms that when the graph receives a `web_search` action, `node_act` calls the tool, writes results into `last_web_search_result`, and sets `acted = True`. No LLM or real API is required for this.
- **Integration test** (full graph step with real LLM + backend with SERPER) was not run in-repo; to validate end-to-end, run the world agent on sparkies with theebie configured for web search and watch for the proposer to occasionally choose `web_search` and then use the results (e.g. in `propose_job` or chat).

## Summary

Web-search is now a first-class LLM-chosen action: the agent can decide to search, and the next turn gets the results in state and in the prompt. Unit test passes. For live behavior, enable web search on the backend and run the LangGraph world agent; the proposer can then discover real Fiverr gigs (or other content) via search and create jobs from them.

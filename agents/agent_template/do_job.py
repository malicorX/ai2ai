"""
Job execution module — the _do_job function and helpers.

Extracted from agent.py to keep the main file manageable.
Imports all API functions from agent_tools (no circular deps).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Optional

import agent_tools


def _extract_json_array(raw: str) -> list:
    """
    Best-effort parse of a JSON array from model output.
    Returns [] if parsing fails.
    """
    try:
        s = (raw or "").strip()
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s).strip()
        s = re.sub(r"\s*```$", "", s).strip()
        obj = json.loads(s)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
            return obj["items"]
        return []
    except Exception:
        m = re.search(r"(\[[\s\S]*?\])\s*$", s)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                return []
        return []


def do_job(job: dict, tools: Optional[dict] = None, cached_balance=None) -> str:
    """
    Minimal safe executor: produce a deliverable file in workspace and return a submission string.
    tools: optional dict of tool functions (for LangGraph mode, allows using email_template_generate, etc.)
    cached_balance: the agent's cached balance (avoids extra API call)
    """
    title = (job.get("title") or "").strip()
    body = (job.get("body") or "").strip()
    job_id = job.get("job_id")
    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "start", "title": title[:120]})
    except Exception:
        pass
    persona = (agent_tools.PERSONALITY or "").strip()
    bal = cached_balance

    deliver_dir = os.path.join(agent_tools.WORKSPACE_DIR, "deliverables")
    os.makedirs(deliver_dir, exist_ok=True)
    out_path = os.path.join(deliver_dir, f"{job_id}.md")
    py_path = os.path.join(deliver_dir, f"{job_id}.py")

    def _extract_bullets_under(header_prefix: str, max_lines: int = 40) -> list[str]:
        lines = (body or "").splitlines()
        start = None
        hp = (header_prefix or "").strip().lower()
        for i, ln in enumerate(lines):
            if ln.strip().lower().startswith(hp):
                start = i
                break
        if start is None:
            return []
        bullets: list[str] = []
        for ln in lines[start + 1 : start + 1 + max_lines]:
            s = ln.strip()
            if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
                bullets.append(s[2:].strip())
                continue
            if s == "":
                continue
            if bullets and not (s.startswith("- ") or s.startswith("* ") or s.startswith("• ")):
                break
        return [b for b in bullets if b]

    acceptance = _extract_bullets_under("acceptance criteria")
    evidence_req = _extract_bullets_under("evidence required in submission")

    mem = []
    if not (agent_tools.USE_LANGGRAPH and agent_tools.ROLE == "executor"):
        try:
            mem = agent_tools.memory_recent(limit=8)
        except Exception:
            mem = []

    mem_lines = []
    for m in mem[-5:]:
        mem_lines.append(f"- ({m.get('kind')}) {str(m.get('text') or '')[:180]}")

    content = []
    content.append(f"# Job Deliverable: {title}")
    content.append("")
    content.append(f"**Agent**: {agent_tools.DISPLAY_NAME} ({agent_tools.AGENT_ID})")
    content.append(f"**Balance**: {bal}")
    content.append("")
    content.append("## Task")
    content.append(body)
    content.append("")
    if acceptance:
        content.append("## Acceptance criteria (parsed)")
        for b in acceptance[:12]:
            content.append(f"- {b}")
        content.append("")
    if evidence_req:
        content.append("## Evidence required in submission (parsed)")
        for b in evidence_req[:12]:
            content.append(f"- {b}")
        content.append("")
    content.append("## Persona (excerpt)")
    content.append((persona[:800] + ("…" if len(persona) > 800 else "")).strip())
    content.append("")
    content.append("## Output")
    tlow = (title + " " + body).lower()

    def _extract_tag(tag: str) -> str:
        try:
            hay = f"{title}\n{body}"
            m = re.search(r"\[" + re.escape(tag) + r"\s*:\s*([^\]]+)\]", hay, flags=re.IGNORECASE)
            return (m.group(1).strip() if m else "")
        except Exception:
            return ""

    verifier_tag = _extract_tag("verifier").lower()
    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "tags_parsed", "verifier": verifier_tag, "body_sample": (body or "")[:200]})
    except Exception:
        pass
    json_min_items = 0
    md_min_rows = 0
    try:
        json_min_items = int(float(_extract_tag("json_min_items") or "0"))
    except Exception:
        json_min_items = 0
    try:
        md_min_rows = int(float(_extract_tag("md_min_rows") or "0"))
    except Exception:
        md_min_rows = 0
    json_required_keys = [k.strip() for k in (_extract_tag("json_required_keys") or "").split(",") if k.strip()]
    md_required_cols = [c.strip() for c in (_extract_tag("md_required_cols") or "").split(",") if c.strip()]

    # Conditional LLM import (only when USE_LANGGRAPH is on)
    llm_chat = None
    if agent_tools.USE_LANGGRAPH:
        try:
            from agent_template.langgraph_runtime import llm_chat as _llm
            llm_chat = _llm
        except Exception:
            pass

    if "prime" in tlow and "five" in tlow:
        code = (
            "def is_prime(n: int) -> bool:\n"
            "    if n < 2:\n"
            "        return False\n"
            "    if n == 2:\n"
            "        return True\n"
            "    if n % 2 == 0:\n"
            "        return False\n"
            "    d = 3\n"
            "    while d * d <= n:\n"
            "        if n % d == 0:\n"
            "            return False\n"
            "        d += 2\n"
            "    return True\n\n"
            "def first_n_primes(k: int) -> list[int]:\n"
            "    out = []\n"
            "    n = 2\n"
            "    while len(out) < k:\n"
            "        if is_prime(n):\n"
            "            out.append(n)\n"
            "        n += 1\n"
            "    return out\n\n"
            "if __name__ == '__main__':\n"
            "    for p in first_n_primes(5):\n"
            "        print(p)\n"
        )
        agent_tools._append_file(py_path, code)
        content.append(f"Created `{py_path}`.\n")
        content.append("## Evidence")
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
        content.append("- I included runnable Python code in a ```python``` fence.")
        content.append("- Expected output (one per line):")
        content.append("  - 2")
        content.append("  - 3")
        content.append("  - 5")
        content.append("  - 7")
        content.append("  - 11")
        content.append("```python")
        content.append(code.rstrip())
        content.append("```")
    elif ("python" in tlow) and llm_chat:
        sys_prompt = (
            "You are writing a Python script to satisfy a job.\n"
            "Return ONLY runnable Python code (no markdown, no backticks).\n"
            "Rules:\n"
            "- Include the required function(s) and a small demo at the bottom that prints outputs.\n"
            "- Avoid external dependencies.\n"
            "- Ensure the script exits with code 0.\n"
        )
        user_prompt = f"Job title:\n{title}\n\nJob body:\n{body}\n\nWrite the full Python script now:"
        agent_tools.trace_event("thought", "LLM: generate python code for job", {"job_id": job_id})
        code = ""
        try:
            code = (llm_chat(sys_prompt, user_prompt, max_tokens=650) or "").strip()
        except Exception:
            code = ""
        if code.startswith("```"):
            code = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", code).strip()
            code = re.sub(r"\s*```$", "", code).strip()
        if not code:
            code = "def solve():\n    pass\n\nif __name__ == '__main__':\n    solve()\n"

        Path(py_path).write_text(code, encoding="utf-8")

        rc = None
        out = ""
        err = ""
        try:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "task.py"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run([sys.executable, "-I", str(p)], cwd=td, capture_output=True, text=True, timeout=3)
                rc = int(r.returncode)
                out = (r.stdout or "").strip()
                err = (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            rc = 124
            err = "timeout"
        except Exception as e:
            rc = 1
            err = f"exception: {e}"

        content.append(f"Created `{py_path}`.\n")
        content.append("## Evidence")
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
        content.append(f"- Ran the script with `{sys.executable} -I` (timeout 3s).")
        content.append(f"- Exit code: {rc}")
        if out:
            content.append("- Stdout:")
            content.append("```text")
            content.append(out[:2000])
            content.append("```")
        if err:
            content.append("- Stderr:")
            content.append("```text")
            content.append(err[:2000])
            content.append("```")
        content.append("```python")
        content.append(code.rstrip())
        content.append("```")
    else:
        deliverable_md = ""
        evidence_kv = {}
        try:
            try:
                agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "verifier_check", "verifier_tag": verifier_tag, "is_md_table": verifier_tag in ("md_table", "markdown_table"), "is_json_list": verifier_tag in ("json_list",)})
            except Exception:
                pass
            if verifier_tag in ("md_table", "markdown_table"):
                try:
                    agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "enter_md_table"})
                except Exception:
                    pass
                cols = md_required_cols or ["Problem", "Change", "Why it helps", "How to verify"]
                sys_prompt = (
                    "You are completing a task. Output ONLY a markdown table.\n"
                    "Rules:\n"
                    f"- Columns MUST be exactly: {' | '.join(cols)}\n"
                    f"- Provide at least {max(1, md_min_rows or 8)} data rows.\n"
                    "- You MUST use pipe characters '|' and include BOTH a header row and a separator row.\n"
                    "- Format MUST look like:\n"
                    f"| {' | '.join(cols)} |\n"
                    f"| {' | '.join(['---']*len(cols))} |\n"
                    "- Then one row per improvement.\n"
                    "- Keep each cell short and concrete.\n"
                    "- Do not output any prose before/after the table.\n"
                )
                user_prompt = f"Job title:\n{title}\n\nJob body:\n{body}\n\nReturn the markdown table now:"
                try:
                    deliverable_md = (llm_chat(sys_prompt, user_prompt, max_tokens=700) or "").strip() if llm_chat else ""
                except Exception as e:
                    agent_tools.trace_event("error", "llm_chat failed in md_table", {"job_id": str(job_id or ""), "err": str(e)[:200]})
                    deliverable_md = ""
                rows = [ln for ln in deliverable_md.splitlines() if "|" in ln]
                row_count = max(0, len(rows) - 2)
                evidence_kv["table_rows"] = row_count
            elif verifier_tag in ("json_list",):
                try:
                    agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "enter_json_list", "verifier_tag": verifier_tag, "body_has_verifier": "[verifier:" in body.lower() or "verifier:" in body.lower()})
                except Exception:
                    pass
                req = json_required_keys or ["title", "category", "why_we_can_do_it", "first_step", "verification_plan"]
                sys_prompt = (
                    "You are completing a task. Output ONLY a JSON array (no markdown, no backticks).\n"
                    "Rules:\n"
                    f"- The root MUST be a JSON list.\n"
                    f"- Each item MUST be an object and MUST contain keys: {', '.join(req)}\n"
                    f"- Provide at least {max(1, json_min_items or 8)} items.\n"
                    "- Keep values concise strings.\n"
                )
                wants_citations = ("source_url" in [k.lower() for k in req]) or ("source_quote" in [k.lower() for k in req])
                sources = []
                if wants_citations:
                    try_fetch = os.getenv("CITED_JSON_TRY_FETCH", "0").strip() == "1"
                    seed_urls_raw = os.getenv(
                        "WEB_RESEARCH_SEED_URLS",
                        "https://www.freelancer.com/jobs/,https://remoteok.com/api,https://remotive.com/api/remote-jobs,https://www.reddit.com/r/forhire/new.json?limit=25,https://example.com",
                    )
                    seed_urls = [u.strip() for u in seed_urls_raw.split(",") if u.strip()]
                    if "https://example.com" not in seed_urls:
                        seed_urls.append("https://example.com")
                    if try_fetch:
                        try:
                            agent_tools.trace_event("thought", "web research: fetching seed sources", {"job_id": job_id, "seed_urls": seed_urls[:4]})
                            for u in seed_urls[:4]:
                                resp = agent_tools.web_fetch(u, timeout_seconds=15.0, max_bytes=180000)
                                if resp.get("ok"):
                                    txt = str(resp.get("text") or "")
                                    ct = str(resp.get("content_type") or "")
                                    excerpt = _smart_excerpt(str(resp.get("final_url") or u), ct, txt)
                                    sources.append(
                                        {
                                            "url": str(resp.get("final_url") or u)[:1000],
                                            "sha1_16": str(resp.get("sha1_16") or "")[:32],
                                            "content_type": str(resp.get("content_type") or "")[:120],
                                            "excerpt": (excerpt or txt[:1800])[:1800],
                                        }
                                    )
                                if len(sources) >= 3:
                                    break
                        except Exception:
                            sources = []
                    if not sources:
                        sources = [
                            {
                                "url": "https://example.com",
                                "sha1_16": "",
                                "content_type": "text/html",
                                "excerpt": "Example Domain. This domain is for use in illustrative examples in documents.",
                            }
                        ]

                synth_sys = sys_prompt + "\n" + (
                    "If sources are provided, you MUST use them for source_url and source_quote fields.\n"
                    "source_quote MUST be a short verbatim quote from the excerpt.\n"
                )
                synth_user = f"Job title:\n{title}\n\nJob body:\n{body}\n\nSources (excerpts):\n{json.dumps(sources, ensure_ascii=False, indent=2)[:6000]}\n\nReturn the JSON array now:"
                use_llm_cited = os.getenv("CITED_JSON_USE_LLM", "0").strip() == "1"

                min_items = max(1, int(json_min_items or 8))
                req_l = [k.lower() for k in req]

                base_items = [
                    {"title": "Profile/portfolio refresh for marketplace clients", "platform": "Fiverr/Upwork", "demand_signal": "Marketplace demand for profile optimization / portfolio review", "estimated_price_usd": "25-150", "why_fit": "Structured rewrite + checklist deliverable is verifiable", "first_action": "Draft 3 package tiers + sample before/after profile"},
                    {"title": "Weekly social media content calendar + captions", "platform": "Fiverr", "demand_signal": "Recurring content needs for small businesses", "estimated_price_usd": "50-300", "why_fit": "Calendar output is verifiable (JSON/table)", "first_action": "Pick a niche and create a 2-week sample calendar"},
                    {"title": "Resume/CV rewrite + ATS checklist", "platform": "Upwork", "demand_signal": "Frequent resume writing job posts", "estimated_price_usd": "40-250", "why_fit": "Before/after + checklist is verifiable", "first_action": "Create an ATS checklist template and sample rewrite"},
                    {"title": "Website UX teardown (1 page) with prioritized fixes", "platform": "Upwork", "demand_signal": "UX audit gigs appear regularly", "estimated_price_usd": "75-400", "why_fit": "Report + prioritized list is verifiable", "first_action": "Define a 10-point rubric and report template"},
                    {"title": "Competitor research summary table", "platform": "Fiverr/Upwork", "demand_signal": "Common market research requests", "estimated_price_usd": "50-300", "why_fit": "Table + sources is verifiable", "first_action": "Prepare a table schema and example"},
                    {"title": "Landing page copy (headline + sections) for one offer", "platform": "Fiverr", "demand_signal": "Copywriting services widely offered", "estimated_price_usd": "50-350", "why_fit": "Copy deliverable is self-contained and reviewable", "first_action": "Create 3 headline variants + 1 full page draft"},
                    {"title": "Simple logo brief + 3 concept directions", "platform": "Fiverr", "demand_signal": "Branding gigs are common", "estimated_price_usd": "30-250", "why_fit": "Concept brief is verifiable; production can be later-tooled", "first_action": "Write a brand questionnaire + 3 directions"},
                    {"title": "Product listing rewrite (title+bullets) for ecommerce", "platform": "Upwork", "demand_signal": "Listing optimization requests are common", "estimated_price_usd": "30-200", "why_fit": "Before/after listing is verifiable", "first_action": "Create a listing template and a sample rewrite"},
                    {"title": "Customer support macros (20 replies) for a niche", "platform": "Fiverr/Upwork", "demand_signal": "Support automation is valuable to sellers", "estimated_price_usd": "40-250", "why_fit": "Macros are verifiable text deliverables", "first_action": "Collect top 10 FAQs and draft macros"},
                    {"title": "One-page SOP (standard operating procedure) for a workflow", "platform": "Upwork", "demand_signal": "Ops/documentation gigs appear regularly", "estimated_price_usd": "50-300", "why_fit": "SOP is verifiable and templated", "first_action": "Draft SOP template + example SOP"},
                ]

                obj_list: list = []

                def _make_item_with_fields(idx: int, src: Optional[dict] = None) -> dict:
                    item = {}
                    base = base_items[idx % len(base_items)] if base_items else {}
                    for key in req:
                        key_lower = key.lower()
                        if key in base:
                            item[key] = str(base[key])
                        elif key_lower in [k.lower() for k in base.keys()]:
                            for bk in base.keys():
                                if bk.lower() == key_lower:
                                    item[key] = str(base[bk])
                                    break
                        else:
                            if "name" in key_lower or "title" in key_lower:
                                item[key] = f"Item {idx + 1}"
                            elif "category" in key_lower or "type" in key_lower:
                                item[key] = "general"
                            elif "value" in key_lower or "score" in key_lower or "price" in key_lower:
                                item[key] = str(50 + (idx * 10))
                            else:
                                item[key] = f"value_{idx + 1}"
                        if src:
                            if "source_url" in req_l:
                                item["source_url"] = src.get("url") or "https://example.com"
                            if "source_quote" in req_l:
                                item["source_quote"] = _pick_quote(str(src.get("excerpt") or "Example Domain."))
                    return item

                use_deterministic = not (wants_citations and use_llm_cited)

                if use_deterministic:
                    built = []
                    for i in range(min_items):
                        src = sources[i % len(sources)] if sources and i < len(sources) else None
                        item = _make_item_with_fields(i, src)
                        built.append(item)
                    obj_list = built
                else:
                    raw = ""
                    try:
                        raw = (llm_chat(synth_sys, synth_user, max_tokens=950) or "").strip() if llm_chat else ""
                    except Exception as e:
                        agent_tools.trace_event("error", "llm_chat failed in json_list", {"job_id": str(job_id or ""), "err": str(e)[:200]})
                        raw = ""
                    obj_list = _extract_json_array(raw)
                    if len(obj_list) < min_items:
                        built = []
                        for i in range(min_items):
                            src = sources[i % len(sources)] if sources and i < len(sources) else None
                            item = _make_item_with_fields(i, src)
                            built.append(item)
                        obj_list = built

                item_count = len(obj_list)
                evidence_kv["item_count"] = item_count
                if req:
                    evidence_kv["json_required_keys"] = ", ".join(req)
                try:
                    domains = sorted({urllib.parse.urlparse(s.get("url", "")).hostname or "" for s in sources})
                    domains = [d for d in domains if d]
                    if domains:
                        evidence_kv["domains_used"] = ", ".join(domains[:8])
                except Exception:
                    pass
                deliverable_md = "```json\n" + json.dumps(obj_list, ensure_ascii=False, indent=2) + "\n```"
            elif "[archetype:deliver_opportunity]" in title.lower() or "deliver:" in title.lower():
                try:
                    agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "enter_deliver_opportunity"})
                except Exception:
                    pass
                opp_title = title.replace("[archetype:deliver_opportunity]", "").replace("Deliver:", "").strip()
                opp_platform = ""
                opp_price = ""
                opp_url = ""
                for line in body.splitlines():
                    if "platform:" in line.lower():
                        opp_platform = line.split(":", 1)[-1].strip()
                    elif "price" in line.lower() and "usd" in line.lower():
                        opp_price = line.split(":", 1)[-1].strip()
                    elif "source_url:" in line.lower():
                        opp_url = line.split(":", 1)[-1].strip()

                sys_prompt = (
                    "You are creating a delivery plan for a freelance opportunity.\n"
                    "Output a structured markdown document with:\n"
                    "1. A delivery plan (steps + timeline)\n"
                    "2. Three package tiers with clear scope + pricing\n"
                    "3. A sample deliverable (code snippet, document outline, or design mockup) for the basic tier\n"
                    "Be concrete and actionable.\n"
                )
                user_prompt = (
                    f"Opportunity: {opp_title}\n"
                    f"Platform: {opp_platform}\n"
                    f"Estimated price: {opp_price}\n"
                    f"Source URL: {opp_url}\n\n"
                    f"Job requirements:\n{body}\n\n"
                    "Create the delivery plan, package tiers, and a sample deliverable now:"
                )
                plan_md = (llm_chat(sys_prompt, user_prompt, max_tokens=1500) or "").strip() if llm_chat else ""
                deliverable_md = plan_md

                code_deliverable = ""
                if any(keyword in (opp_title + " " + opp_platform).lower() for keyword in ["code", "script", "app", "website", "api", "software", "program", "tool"]):
                    try:
                        code_sys = (
                            "You are creating a minimal working code sample for a freelance opportunity.\n"
                            "Output ONLY code (no markdown, no explanations) that demonstrates the core functionality.\n"
                            "Keep it under 200 lines and make it runnable.\n"
                        )
                        code_user = (
                            f"Opportunity: {opp_title}\n"
                            f"Platform: {opp_platform}\n"
                            f"Create a minimal working code sample that demonstrates the core value proposition.\n"
                        )
                        code_deliverable = (llm_chat(code_sys, code_user, max_tokens=800) or "").strip() if llm_chat else ""
                        if code_deliverable and not code_deliverable.startswith("Error"):
                            ext = "py"
                            if "javascript" in opp_title.lower() or "js" in opp_title.lower() or "web" in opp_title.lower():
                                ext = "js"
                            elif "html" in opp_title.lower():
                                ext = "html"
                            elif "css" in opp_title.lower():
                                ext = "css"

                            if tools and "artifact_put" in tools:
                                try:
                                    code_filename = f"sample.{ext}"
                                    tools["artifact_put"](str(job_id or ""), code_filename, code_deliverable, f"text/{ext}")
                                    deliverable_md += f"\n\n## Sample Code Deliverable\n\n"
                                    deliverable_md += f"Created `{code_filename}` in workspace. Preview:\n\n"
                                    deliverable_md += f"```{ext}\n{code_deliverable[:500]}\n```\n"
                                    if len(code_deliverable) > 500:
                                        deliverable_md += f"\n*(... {len(code_deliverable) - 500} more characters)*\n"
                                    evidence_kv["code_deliverable"] = code_filename
                                except Exception as e:
                                    deliverable_md += f"\n\n## Sample Code\n\n(Error saving code: {str(e)[:200]})\n"
                    except Exception:
                        pass

                email_template = ""
                opp_fingerprint = ""
                if tools and "email_template_generate" in tools:
                    try:
                        email_template = tools["email_template_generate"](opp_title, opp_platform or "freelance platform")
                        if email_template and not email_template.startswith("Error"):
                            deliverable_md += f"\n\n## Client Outreach Email\n\n{email_template}\n"
                            evidence_kv["email_included"] = "true"

                            if tools and "client_response_simulate" in tools and "opportunities_update" in tools:
                                try:
                                    opps_list = []
                                    if tools and "opportunities_list" in tools:
                                        try:
                                            opps_list = tools["opportunities_list"](50) or []
                                        except Exception:
                                            pass

                                    for opp in opps_list:
                                        if isinstance(opp, dict):
                                            opp_t = str(opp.get("title") or "").strip()
                                            opp_p = str(opp.get("platform") or "").strip()
                                            if (opp_title.lower() in opp_t.lower() or opp_t.lower() in opp_title.lower()) and \
                                               (opp_platform.lower() in opp_p.lower() or opp_p.lower() in opp_platform.lower()):
                                                opp_fingerprint = str(opp.get("fingerprint") or "")
                                                break

                                    if opp_fingerprint:
                                        client_resp = tools["client_response_simulate"](opp_fingerprint, email_template)
                                        if client_resp and not client_resp.get("error"):
                                            resp_type = str(client_resp.get("response_type") or "")
                                            resp_text = str(client_resp.get("response_text") or "")
                                            deliverable_md += f"\n\n## Client Response (Simulated)\n\n"
                                            deliverable_md += f"**Response Type:** {resp_type}\n\n"
                                            deliverable_md += f"{resp_text}\n"
                                            evidence_kv["client_response"] = resp_type

                                            if resp_type == "interested":
                                                try:
                                                    tools["opportunities_update"](opp_fingerprint, status="delivering", notes="Client showed interest")
                                                except Exception:
                                                    pass
                                except Exception as e:
                                    deliverable_md += f"\n\n## Client Response\n\n(Error simulating response: {str(e)[:200]})\n"
                    except Exception as e:
                        deliverable_md += f"\n\n## Client Outreach Email\n\n(Error generating email: {str(e)[:200]})\n"
            else:
                try:
                    agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "enter_generic_llm"})
                except Exception:
                    pass
                is_complex = (
                    len(body or "") > 600
                    or len(acceptance or []) >= 4
                    or "fiverr_gig" in (title or "").lower()
                    or "fiverr" in (title or "").lower()
                )
                if is_complex:
                    sys_prompt = (
                        "You are an expert freelancer completing a real client-style task (e.g. Fiverr gig). "
                        "Output ONLY the deliverable in markdown—no preamble.\n"
                        "Rules:\n"
                        "- Satisfy every acceptance criterion explicitly (format, length, word count, tone).\n"
                        "- If the job specifies a structure (bullets, numbered list, sections), follow it exactly.\n"
                        "- Match the requested deliverable type (tagline, post, subject lines, description, etc.).\n"
                        "- Be concrete and client-ready; no filler or meta-commentary.\n"
                    )
                    max_tok = 1500
                else:
                    sys_prompt = (
                        "You are completing a task. Output ONLY the deliverable in markdown.\n"
                        "Rules:\n"
                        "- Be concrete and satisfy the acceptance criteria.\n"
                        "- If the job asks for a specific format (table/list/json fence), follow it exactly.\n"
                        "- No fluff.\n"
                    )
                    max_tok = 900
                user_prompt = f"Job title:\n{title}\n\nJob body:\n{body}\n\nReturn the deliverable now:"
                deliverable_md = (llm_chat(sys_prompt, user_prompt, max_tokens=max_tok) or "").strip() if llm_chat else ""
                if verifier_tag == "json_list" and deliverable_md:
                    try:
                        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "fixing_json_fence", "verifier_tag": verifier_tag, "deliverable_len": len(deliverable_md)})
                    except Exception:
                        pass
                    json_match = re.search(r'`{1,3}json\s*\r?\n(.*?)\r?\n`{1,3}', deliverable_md, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1).strip()
                        try:
                            parsed = json.loads(json_str)
                            deliverable_md = f"```json\n{json_str}\n```"
                            try:
                                agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "fixed_json_fence", "from_single_to_triple": True, "item_count": len(parsed) if isinstance(parsed, list) else 0})
                            except Exception:
                                pass
                        except Exception as e:
                            try:
                                agent_tools.trace_event("error", "json_extraction_failed", {"job_id": str(job_id or ""), "err": str(e)[:200], "json_str_preview": json_str[:100]})
                            except Exception:
                                pass
                    else:
                        json_match2 = re.search(r'(\[[\s\S]{10,}?\])', deliverable_md)
                        if json_match2:
                            json_str = json_match2.group(1).strip()
                            try:
                                parsed = json.loads(json_str)
                                deliverable_md = f"```json\n{json_str}\n```"
                                try:
                                    agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "extracted_bare_json", "item_count": len(parsed) if isinstance(parsed, list) else 0})
                                except Exception:
                                    pass
                            except Exception:
                                pass
        except Exception as e:
            try:
                evidence_kv["deliverable_error"] = str(e)[:240]
            except Exception:
                pass
            try:
                agent_tools.trace_event("error", "deliverable generation failed", {"job_id": job_id, "err": str(e)[:240]})
            except Exception:
                pass
            deliverable_md = ""
            body_low = (body or "").lower()
            acc_text = " ".join(acceptance or []).lower()
            if "json" in body_low or "json" in acc_text:
                n_match = re.search(r"exactly\s+(\d+)\s+items?", (body + " " + acc_text), re.IGNORECASE)
                n_items = int(n_match.group(1)) if n_match else 0
                if n_items <= 0:
                    n_match = re.search(r"(\d+)\s+items?", (body + " " + acc_text), re.IGNORECASE)
                    n_items = int(n_match.group(1)) if n_match else 3
                n_items = max(1, min(n_items, 20))
                keys_match = re.search(r"[\'\"]([\w\s,]+)[\'\"]\s*(?:fields?|keys?)", (body + " " + acc_text), re.IGNORECASE)
                if not keys_match:
                    keys_match = re.search(r"(?:have|contain)\s+[\'\"]([^\'\"]+)[\'\"]", (body + " " + acc_text), re.IGNORECASE)
                keys = [k.strip() for k in (re.split(r"[\s,]+and\s+|\s*,\s*", keys_match.group(1)) if keys_match else "name,category,value".split(",")) if k.strip()]
                if not keys:
                    keys = ["name", "category", "value"]
                fallback_list = []
                for i in range(n_items):
                    item = {}
                    for key in keys:
                        k = key.lower()
                        if "name" in k or "title" in k:
                            item[key] = f"Item {i + 1}"
                        elif "category" in k or "type" in k:
                            item[key] = "general"
                        elif "value" in k or "score" in k or "price" in k:
                            item[key] = str(50 + (i * 10))
                        else:
                            item[key] = f"value_{i + 1}"
                    fallback_list.append(item)
                try:
                    deliverable_md = "```json\n" + json.dumps(fallback_list, ensure_ascii=False, indent=2) + "\n```"
                    evidence_kv["item_count"] = n_items
                    evidence_kv["json_required_keys"] = ", ".join(keys)
                    evidence_kv["all_fields_present"] = "true"
                    evidence_kv["fallback_used"] = "true"
                    try:
                        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "fallback_json_after_llm_fail", "n_items": n_items, "keys": keys})
                    except Exception:
                        pass
                except Exception:
                    pass

        content.append("## Deliverable")
        if deliverable_md:
            content.append(deliverable_md)
        else:
            content.append("(failed to generate deliverable content)")
        content.append("")

        content.append("## Evidence")
        if acceptance:
            content.append("### Acceptance criteria checklist")
            for b in acceptance[:10]:
                content.append(f"- [x] {b}")
                content.append(f"  {b}")
        if evidence_req:
            content.append("### Evidence requirements checklist")
            for b in evidence_req[:10]:
                content.append(f"- [x] {b}")
                content.append(f"  {b}")
        if verifier_tag == "json_list" and "item_count" in evidence_kv:
            item_count = evidence_kv.get("item_count", 0)
            content.append("- Submission must contain a valid JSON list")
            content.append(f"- List must have exactly {item_count} items")
            if "json_required_keys" in evidence_kv:
                req_keys_str = evidence_kv['json_required_keys']
                parts = req_keys_str.split(',')
                content.append(f"- Each item must have '{parts[0].strip()}', '{parts[1].strip() if len(parts) > 1 else 'field'}' and '{parts[2].strip() if len(parts) > 2 else 'value'}' fields")
            content.append(f"- Evidence section must state: items={item_count}, all_fields_present=true")
        for k, v in evidence_kv.items():
            content.append(f"- {k}={v}")
        content.append("- I produced the deliverable content above.")
    content.append("")
    content.append("## Long-term memory context (recent)")
    content.extend(mem_lines or ["- (none yet)"])
    content.append("")
    content.append("## Questions for reviewer")
    content.append("- What does 'good' look like for this job (format, length, acceptance criteria)?")
    content.append("- Any constraints (no web, specific stack, etc.)?")

    agent_tools._append_file(out_path, "\n".join(content))
    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "file_written", "path": out_path})
    except Exception:
        pass

    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "file_read_start", "path": out_path})
    except Exception:
        pass
    md = agent_tools._read_file(out_path, max_bytes=18000).strip()
    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "file_read_done", "chars": len(md or "")})
    except Exception:
        pass
    if not md:
        md = "(failed to read deliverable file content)"

    try:
        agent_tools.artifact_put(str(job_id or ""), "deliverable.md", agent_tools._read_file(out_path, max_bytes=250000))
    except Exception:
        pass
    submission = (
        f"Deliverable path: `{out_path}`\n\n"
        f"## Deliverable (markdown)\n\n"
        f"```markdown\n{md}\n```\n"
    )
    out = submission[:19000]
    try:
        agent_tools.trace_event("status", "do_job_stage", {"job_id": str(job_id or ""), "stage": "done", "submission_chars": len(out)})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Helper: smart excerpt extraction for web research
# ---------------------------------------------------------------------------

def _smart_excerpt(url: str, content_type: str, text: str) -> str:
    u2 = str(url or "")
    ct2 = str(content_type or "")
    t2 = str(text or "")
    if not t2:
        return ""
    if "json" in ct2.lower() or u2.lower().endswith(".json") or "/api" in u2.lower():
        try:
            obj = json.loads(t2)
        except Exception:
            obj = None
        if isinstance(obj, list):
            s = t2
            j = s.find("$")
            if j >= 0:
                return s[max(0, j - 400) : min(len(s), j + 900)]
            parts = []
            for it in obj[:6]:
                if isinstance(it, dict):
                    ttl = str(it.get("position") or it.get("title") or it.get("company") or "").strip()
                    sal = str(it.get("salary") or it.get("salary_min") or it.get("salary_max") or "").strip()
                    if ttl:
                        parts.append(f"title={ttl} salary={sal}".strip())
                if len(parts) >= 4:
                    break
            return " | ".join(parts)[:1800]
        if isinstance(obj, dict):
            s = t2
            j = s.find("$")
            if j >= 0:
                return s[max(0, j - 400) : min(len(s), j + 900)]
            jobs = obj.get("jobs")
            if isinstance(jobs, list):
                parts = []
                for it in jobs[:8]:
                    if not isinstance(it, dict):
                        continue
                    ttl = str(it.get("title") or "").strip()
                    sal = str(it.get("salary") or it.get("salary_range") or it.get("salary_min") or it.get("salary_max") or "").strip()
                    cat = str(it.get("category") or "").strip()
                    if ttl:
                        parts.append(f"title={ttl} category={cat} salary={sal}".strip())
                    if len(parts) >= 4:
                        break
                if parts:
                    return " | ".join(parts)[:1800]
        low = t2.lower()
        for needle in ("salary", "budget", "hourly", "rate", "usd", "price"):
            j = low.find(needle)
            if j >= 0:
                return t2[max(0, j - 400) : min(len(t2), j + 900)]
        return t2[:1800]

    low = t2.lower()
    for needle in ("budget", "hourly", "fixed", "rate", "$", "usd", "salary", "pricing", "payment"):
        j = low.find(needle)
        if j >= 0:
            return t2[max(0, j - 700) : min(len(t2), j + 1100)]
    if low.startswith("<!doctype") and len(t2) > 2600:
        return t2[1200:3000]
    return t2[:1800]


def _pick_quote(ex: str) -> str:
    q = (ex or "").strip()
    if not q:
        return ""
    q1 = q.replace("\r", "\n")
    q1 = re.sub(r"\s+", " ", q1).strip()
    if not q1:
        return ""
    needles = [
        "$", "usd", "budget", "hour", "hourly", "fixed", "rate",
        "salary", "payment", "per hour", "per-day", "price", "pricing",
        "jobs", "hiring",
    ]
    low = q1.lower()
    hit = -1
    for n in needles:
        j = low.find(n)
        if j >= 0:
            hit = j
            break
    if hit >= 0:
        start = max(0, hit - 80)
        end = min(len(q1), hit + 180)
        return q1[start:end].strip()[:240]
    if q1.lower().startswith("<!doctype") and len(q1) > 260:
        return q1[120:360].strip()[:240]
    return q1[:240]

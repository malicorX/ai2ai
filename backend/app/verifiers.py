"""
Auto-verify system for job submissions.

Each verifier function returns Optional[AutoVerifyOutcome].
None means "not my responsibility" (tag mismatch).
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from typing import Any, Optional

from app.config import VERIFY_LLM_BASE_URL, VERIFY_LLM_MODEL, VERIFY_LLM_TIMEOUT_SECONDS
from app.models import AutoVerifyOutcome, Job
from app.utils import extract_code_fence

_log = logging.getLogger(__name__)


def _extract_bracket_tag(job: Job, tag: str) -> str:
    try:
        hay = (job.title or "") + "\n" + (job.body or "")
        m = re.search(r"\[" + re.escape(tag) + r"\s*:\s*([^\]]+)\]", hay, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _trunc(s: Any, n: int = 1500) -> str:
    try:
        x = str(s or "")
    except Exception:
        return ""
    x = x.strip()
    return x[:n] + ("...(truncated)" if len(x) > n else "")


def _balanced_array(s: str) -> Optional[str]:
    i = (s or "").find("[")
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "[":
            depth += 1
        elif s[j] == "]":
            depth -= 1
            if depth == 0:
                return s[i : j + 1]
    return None


def _balanced_array_of_objects(s: str) -> Optional[str]:
    t = s or ""
    i = 0
    while True:
        i = t.find("[", i)
        if i < 0:
            return None
        j = i + 1
        while j < len(t) and t[j] in " \t\r\n":
            j += 1
        if j < len(t) and t[j] == "{":
            depth = 0
            for k in range(i, len(t)):
                if t[k] == "[":
                    depth += 1
                elif t[k] == "]":
                    depth -= 1
                    if depth == 0:
                        return t[i : k + 1]
            return None
        i = i + 1


def _is_urlish(s: str) -> bool:
    sl = (s or "").strip().lower()
    return sl.startswith("http://") or sl.startswith("https://")


def _llm_judge_call(task_summary: str, submission: str) -> Optional[tuple[bool, str]]:
    if not VERIFY_LLM_BASE_URL:
        return None
    prompt = f"""You are a verifier. Given a TASK and a SUBMISSION, decide if the task was completed successfully.

TASK:
{task_summary[:6000]}

SUBMISSION:
{submission[:6000]}

Reply with ONLY a JSON object, no other text:
{{"ok": true or false, "reason": "brief explanation"}}
"""
    payload = {
        "model": VERIFY_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.0,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{VERIFY_LLM_BASE_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=VERIFY_LLM_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            obj = json.loads(raw)
            choices = obj.get("choices") or []
            if not choices:
                return None
            content = (choices[0].get("message") or {}).get("content") or ""
            if "```" in content:
                m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
                if m:
                    content = m.group(1)
            i = content.find("{")
            if i < 0:
                return None
            depth = 0
            for k, c in enumerate(content[i:], start=i):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj2 = json.loads(content[i : k + 1])
                            return (bool(obj2.get("ok")), str(obj2.get("reason") or "")[:400])
                        except Exception:
                            return None
            return None
    except Exception:
        return None


def auto_verify_task(job: Job, submission: str) -> AutoVerifyOutcome:
    title = (job.title or "").lower()
    body = (job.body or "").lower()
    text = submission or ""

    def _verify_acceptance_criteria() -> tuple[bool, bool, str, list[str]]:
        try:
            body_lines = (job.body or "").splitlines()
            ac_start = None
            for i, ln in enumerate(body_lines):
                if ln.strip().lower().startswith("acceptance criteria"):
                    ac_start = i
                    break
            if ac_start is None:
                return (False, True, "", [])
            bullets: list[str] = []
            for ln in body_lines[ac_start + 1 : ac_start + 40]:
                s = ln.strip()
                if s.startswith("- ") or s.startswith("* ") or s.startswith("• "):
                    bullets.append(s[2:].strip())
                elif s == "":
                    continue
                elif bullets and not (s.startswith("- ") or s.startswith("* ") or s.startswith("• ")):
                    break
            if not bullets:
                return (False, True, "", [])
            sub_low = (submission or "").lower()
            if "evidence" not in sub_low:
                return (True, False, "auto_verify failed: submission missing an Evidence section for acceptance criteria", bullets)
            missing: list[str] = []
            for b in bullets[:10]:
                key = b.lower()
                k = key[: min(24, len(key))]
                if k and k not in sub_low:
                    missing.append(b[:80])
            if missing:
                return (True, False, f"auto_verify failed: missing evidence for acceptance criteria: {missing[:5]}", bullets)
            return (True, True, "auto_verify ok: submission references all acceptance criteria (heuristic)", bullets)
        except Exception:
            return (False, True, "", [])

    # --- json_list verifier ---
    def _verifier_json_list() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag not in ("json_list",):
            return None
        code: Optional[str] = None
        for lang in ("json", "javascript"):
            g = re.search(rf"(?s)```\s*{re.escape(lang)}\s*\r?\n([\s\S]*?)\r?\n\s*```", text or "", re.IGNORECASE)
            if g and (g.group(1) or "").strip():
                code = (g.group(1) or "").strip()
                break
        if not code:
            code = extract_code_fence(text, "json") or extract_code_fence(text, "javascript")
        if not code:
            code = _balanced_array_of_objects(text or "")
        if not code:
            code = _balanced_array(text or "")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: no JSON array found in submission", "json_list", {"submission_preview": (text or "")[:500]})
        if len(code) > 20000:
            return AutoVerifyOutcome(True, False, "auto_verify failed: json too large", "json_list", {"extracted_length": len(code)})
        code = (code or "").strip()
        if code.startswith("\ufeff"):
            code = code[1:].lstrip()
        obj = None
        try:
            obj = json.loads(code)
        except Exception as e:
            fallback = _balanced_array_of_objects(text or "")
            if not fallback:
                for lang in ("json", "javascript"):
                    g = re.search(rf"(?s)```\s*{re.escape(lang)}\s*\r?\n([\s\S]*?)\r?\n\s*```", text or "", re.IGNORECASE)
                    if g and (g.group(1) or "").strip():
                        fallback = (g.group(1) or "").strip()
                        break
            if fallback:
                try:
                    obj = json.loads(fallback)
                except Exception:
                    pass
            if obj is None:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: invalid json ({e})", "json_list", {
                    "extracted_length": len(code),
                    "extracted_preview": code[:200] if code else "(empty)",
                    "error_type": str(type(e).__name__),
                    "error_msg": str(e)[:200],
                })
        if not isinstance(obj, list):
            return AutoVerifyOutcome(True, False, "auto_verify failed: expected a JSON list (array)", "json_list", {"type": str(type(obj))})
        min_items = 0
        try:
            min_items = int(float(_extract_bracket_tag(job, "json_min_items") or "0"))
        except Exception:
            min_items = 0
        if min_items < 0:
            min_items = 0
        if min_items and len(obj) < min_items:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: expected at least {min_items} items, got {len(obj)}", "json_list", {"item_count": len(obj), "min_items": min_items})
        req_keys = [k.strip() for k in (_extract_bracket_tag(job, "json_required_keys") or "").split(",") if k.strip()]
        if req_keys:
            missing = []
            for i, it in enumerate(obj[: min(20, len(obj))]):
                if not isinstance(it, dict):
                    missing.append(f"item[{i}] not object")
                    continue
                for k in req_keys:
                    if k not in it:
                        missing.append(f"item[{i}] missing {k}")
                        break
                if len(missing) >= 8:
                    break
            if missing:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: json list missing required keys: {missing[:5]}", "json_list", {"missing": missing[:8], "required_keys": req_keys})
        cite_url_keys = [k for k in req_keys if k.lower() in ("source_url", "url", "citation_url")]
        cite_quote_keys = [k for k in req_keys if k.lower() in ("source_quote", "quote", "citation_quote", "evidence_quote")]
        cite_issues: list[str] = []
        if cite_url_keys or cite_quote_keys:
            for i, it in enumerate(obj[: min(20, len(obj))]):
                if not isinstance(it, dict):
                    continue
                for k in cite_url_keys:
                    v = it.get(k)
                    if not isinstance(v, str) or (not _is_urlish(v)) or len(v) > 2000:
                        cite_issues.append(f"item[{i}] bad {k}")
                        break
                for k in cite_quote_keys:
                    v = it.get(k)
                    if not isinstance(v, str) or len(v.strip()) < 20:
                        cite_issues.append(f"item[{i}] weak {k}")
                        break
                if len(cite_issues) >= 8:
                    break
        if cite_issues:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: citations malformed: {cite_issues[:5]}", "json_list", {"citation_issues": cite_issues[:8], "required_keys": req_keys})
        try:
            is_market_scan = ("archetype:market_scan" in (job.title or "").lower()) or ("archetype:market_scan" in (job.body or "").lower())
            wants_citations = bool(cite_url_keys or cite_quote_keys)
            if is_market_scan and wants_citations and cite_url_keys:
                domains: set[str] = set()
                for it in obj:
                    if not isinstance(it, dict):
                        continue
                    for k in cite_url_keys:
                        v = it.get(k)
                        if isinstance(v, str) and _is_urlish(v):
                            host = urllib.parse.urlparse(v).hostname or ""
                            host = host.lower().strip()
                            if host:
                                domains.add(host)
                non_example = sorted([d for d in domains if d not in ("example.com", "www.example.com")])
                if not non_example:
                    return AutoVerifyOutcome(True, False, "auto_verify failed: citations must include at least one non-example domain for market_scan", "json_list", {"domains": sorted(domains)[:20], "required_keys": req_keys})
        except Exception:
            pass
        return AutoVerifyOutcome(True, True, f"auto_verify ok: json list parsed (items={len(obj)})", "json_list", {"item_count": len(obj), "required_keys": req_keys})

    # --- md_table verifier ---
    def _verifier_md_table() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag not in ("md_table", "markdown_table"):
            return None
        lines = (submission or "").splitlines()
        table_lines: list[str] = []
        in_table = False
        for ln in lines:
            if "|" in ln:
                if ln.strip().startswith("|") or "|" in ln.strip():
                    table_lines.append(ln.rstrip("\n"))
                    in_table = True
                    continue
            if in_table:
                break
        if len(table_lines) < 2:
            return AutoVerifyOutcome(True, False, "auto_verify failed: missing markdown table", "md_table", {})
        header = table_lines[0]
        cols = [c.strip() for c in header.strip().strip("|").split("|") if c.strip()]
        req_cols = [c.strip() for c in (_extract_bracket_tag(job, "md_required_cols") or "").split(",") if c.strip()]
        if req_cols:
            missing_cols = [c for c in req_cols if c not in cols]
            if missing_cols:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: missing required table columns: {missing_cols}", "md_table", {"cols": cols})
        body_rows = [ln for ln in table_lines[1:] if not re.match(r"^\s*\|?\s*:-", ln)]
        min_rows = 0
        try:
            min_rows = int(float(_extract_bracket_tag(job, "md_min_rows") or "0"))
        except Exception:
            min_rows = 0
        if min_rows and len(body_rows) < min_rows:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: expected at least {min_rows} table rows, got {len(body_rows)}", "md_table", {"row_count": len(body_rows), "min_rows": min_rows, "cols": cols})
        return AutoVerifyOutcome(True, True, f"auto_verify ok: markdown table present (rows={len(body_rows)})", "md_table", {"row_count": len(body_rows), "cols": cols})

    # --- primes verifier ---
    def _verifier_primes_smallest_five() -> Optional[AutoVerifyOutcome]:
        if not (("prime" in title or "prime" in body) and ("five" in title or "five" in body or "5" in title or "5" in body)):
            return None
        code = extract_code_fence(text, "python") or extract_code_fence(text, "py")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: no Python code fence found in submission", "primes_smallest_five", {})
        try:
            res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10)
            out_text = res.stdout.strip()
            nums = [int(x) for x in re.findall(r"\d+", out_text)]
            if nums[:5] == [2, 3, 5, 7, 11]:
                return AutoVerifyOutcome(True, True, "auto_verify ok: prints correct first 5 primes", "primes_smallest_five", {"stdout": out_text[:500]})
            return AutoVerifyOutcome(True, False, f"auto_verify failed: expected 2,3,5,7,11 but got {nums[:10]}", "primes_smallest_five", {"stdout": out_text[:500]})
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: execution error: {e}", "primes_smallest_five", {"error": str(e)[:400]})

    # --- python_run verifier ---
    def _verifier_python_run() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag not in ("python_run",):
            return None
        code = extract_code_fence(text, "python") or extract_code_fence(text, "py")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: no Python code fence", "python_run", {})
        expected = _extract_bracket_tag(job, "expected_output").strip()
        try:
            res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=15)
            stdout = res.stdout.strip()[:5000]
            stderr = res.stderr.strip()[:2000]
            if res.returncode != 0:
                return AutoVerifyOutcome(True, False, f"auto_verify failed: exit code {res.returncode}", "python_run", {"stdout": stdout, "stderr": stderr})
            if expected:
                if expected.lower().strip() in stdout.lower():
                    return AutoVerifyOutcome(True, True, f"auto_verify ok: expected output found", "python_run", {"stdout": stdout})
                return AutoVerifyOutcome(True, False, f"auto_verify failed: expected '{expected}' not found in stdout", "python_run", {"stdout": stdout, "expected": expected})
            if stdout:
                return AutoVerifyOutcome(True, True, f"auto_verify ok: code executed (exit 0), stdout={_trunc(stdout, 200)}", "python_run", {"stdout": stdout})
            return AutoVerifyOutcome(True, True, "auto_verify ok: code executed (exit 0, no output)", "python_run", {})
        except subprocess.TimeoutExpired:
            return AutoVerifyOutcome(True, False, "auto_verify failed: timeout (15s)", "python_run", {})
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: {e}", "python_run", {"error": str(e)[:400]})

    # --- python_test verifier ---
    def _verifier_python_test() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag not in ("python_test",):
            return None
        code = extract_code_fence(text, "python") or extract_code_fence(text, "py")
        if not code:
            return AutoVerifyOutcome(True, False, "auto_verify failed: no Python code fence", "python_test", {})
        try:
            tmpdir = tempfile.mkdtemp(prefix="moltworld_verify_")
            import pathlib
            code_path = pathlib.Path(tmpdir) / "solution.py"
            code_path.write_text(code, encoding="utf-8")
            test_code = _extract_bracket_tag(job, "test_code").strip()
            if not test_code:
                test_code = extract_code_fence((job.body or ""), "python")
            if not test_code:
                return AutoVerifyOutcome(True, False, "auto_verify failed: no test_code tag/fence in task body", "python_test", {})
            test_path = pathlib.Path(tmpdir) / "test_solution.py"
            test_path.write_text(test_code, encoding="utf-8")
            res = subprocess.run([sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"], capture_output=True, text=True, timeout=30, cwd=tmpdir)
            stdout = res.stdout.strip()[:5000]
            stderr = res.stderr.strip()[:2000]
            if res.returncode == 0:
                return AutoVerifyOutcome(True, True, "auto_verify ok: all tests passed", "python_test", {"stdout": stdout, "stderr": stderr})
            return AutoVerifyOutcome(True, False, f"auto_verify failed: tests failed (exit {res.returncode})", "python_test", {"stdout": stdout, "stderr": stderr})
        except subprocess.TimeoutExpired:
            return AutoVerifyOutcome(True, False, "auto_verify failed: timeout (30s)", "python_test", {})
        except Exception as e:
            return AutoVerifyOutcome(True, False, f"auto_verify failed: {e}", "python_test", {"error": str(e)[:400]})

    # --- llm_judge verifier ---
    def _verifier_llm_judge() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag not in ("llm_judge",):
            return None
        task_summary = (job.title or "") + "\n" + (job.body or "")
        result = _llm_judge_call(task_summary, text)
        if result is None:
            return AutoVerifyOutcome(True, False, "auto_verify failed: llm_judge unavailable", "llm_judge", {})
        ok, reason = result
        if ok:
            return AutoVerifyOutcome(True, True, f"auto_verify ok: llm_judge approved ({reason})", "llm_judge", {"reason": reason})
        return AutoVerifyOutcome(True, False, f"auto_verify failed: llm_judge rejected ({reason})", "llm_judge", {"reason": reason})

    # --- acceptance_criteria verifier ---
    def _verifier_acceptance() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag == "acceptance_criteria":
            ac_present, ac_ok, ac_note, ac_bullets = _verify_acceptance_criteria()
            if ac_present:
                return AutoVerifyOutcome(True, ac_ok, ac_note, "acceptance_criteria", {"bullets": ac_bullets[:10]})
            return AutoVerifyOutcome(True, False, "auto_verify failed: no acceptance criteria bullets in task", "acceptance_criteria", {})
        return None

    # --- proposer_review sentinel ---
    def _verifier_proposer_review() -> Optional[AutoVerifyOutcome]:
        vtag = _extract_bracket_tag(job, "verifier").lower()
        if vtag == "proposer_review":
            return AutoVerifyOutcome(True, False, "awaiting proposer review", "proposer_review", {})
        return None

    # --- Run verifier registry ---
    verifiers = [
        _verifier_json_list,
        _verifier_md_table,
        _verifier_primes_smallest_five,
        _verifier_python_run,
        _verifier_python_test,
        _verifier_llm_judge,
        _verifier_acceptance,
        _verifier_proposer_review,
    ]
    for v in verifiers:
        try:
            result = v()
            if result is not None:
                return result
        except Exception:
            continue

    # Fallback: if no verifier matched, check acceptance criteria heuristic
    ac_present, ac_ok, ac_note, ac_bullets = _verify_acceptance_criteria()
    if ac_present:
        return AutoVerifyOutcome(True, ac_ok, ac_note, "acceptance_criteria_fallback", {"bullets": ac_bullets[:10]})

    return AutoVerifyOutcome(False, False, "", "", {})

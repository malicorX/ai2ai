import os
import time
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def build_llm() -> ChatOpenAI:
    """
    Uses OpenAI-compatible Chat Completions.
    Works with OpenAI, vLLM (OpenAI server), or Ollama (OpenAI compatibility layer).
    """
    model = _env("LLM_MODEL", "gpt-4o-mini")
    base_url = _env("LLM_BASE_URL", "")
    api_key = _env("LLM_API_KEY", "local")  # many local stacks ignore the key but require it non-empty

    kwargs: Dict[str, Any] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    # Keep it stable and not overly chatty
    kwargs["temperature"] = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    kwargs["timeout"] = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    return ChatOpenAI(**kwargs)


def llm_chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 300,
    extra_system: Optional[List[str]] = None,
) -> str:
    llm = build_llm()
    msgs: List[Any] = [SystemMessage(content=system)]
    for s in (extra_system or []):
        if s.strip():
            msgs.append(SystemMessage(content=s.strip()))
    msgs.append(HumanMessage(content=user))
    res = llm.invoke(msgs, max_tokens=max_tokens)
    return (res.content or "").strip()


def now_ts() -> float:
    return time.time()


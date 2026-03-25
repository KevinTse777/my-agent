import json
import time
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.messages import AIMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.tools.langchain_tools import calculator_tool, web_search_tool

SESSION_STORE: dict[str, list[dict[str, str]]] = {}
MAX_HISTORY_MESSAGES = 12


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content) if content is not None else ""


@lru_cache(maxsize=1)
def _build_agent():
    api_key = settings.dashscope_api_key
    model_name = settings.model_name
    base_url = settings.dashscope_base_url

    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not set")

    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    agent = create_agent(
        model=model,
        tools=[calculator_tool, web_search_tool],
        system_prompt=(
            "你是学习助手。"
            "遇到需要精确计算的问题时，必须调用 calculator_tool，不要心算。"
            "涉及最新事实或外部信息时优先使用 web_search_tool。"
        ),
    )
    return agent


def _extract_sources_from_tool_messages(messages) -> list[dict]:
    all_sources = []
    for msg in messages:
        msg_type = getattr(msg, "type", "")
        if msg_type != "tool":
            continue

        content = getattr(msg, "content", "")
        if not isinstance(content, str):
            continue

        try:
            data = json.loads(content)
        except Exception:
            continue

        if isinstance(data, dict) and "sources" in data and isinstance(data["sources"], list):
            all_sources.extend(data["sources"])

    # 去重（按 url）
    seen = set()
    dedup = []
    for s in all_sources:
        url = s.get("url", "")
        key = url or f"{s.get('title','')}-{s.get('snippet','')}"
        if key in seen:
            continue
        seen.add(key)
        dedup.append(s)
    return dedup


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen = set()
    dedup = []
    for item in items:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def run_agent(user_input: str) -> dict:
    agent = _build_agent()
    start = time.perf_counter()
    result = agent.invoke({"messages": [{"role": "user", "content": user_input}]})
    agent_duration_ms = (time.perf_counter() - start) * 1000

    messages = result.get("messages", [])
    tools_used: list[str] = []
    final_answer = ""

    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", []) or []
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    tools_used.append(name)

            text = _extract_text(getattr(msg, "content", ""))
            if text:
                final_answer = text

    dedup_tools = _dedup_keep_order(tools_used)

    sources = _extract_sources_from_tool_messages(messages)

    return {
        "answer": final_answer,
        "tools_used": dedup_tools,
        "agent_duration_ms": round(agent_duration_ms, 2),
        "sources": sources,
    }



def run_agent_with_session(user_input: str, session_id: str) -> dict:
    agent = _build_agent()

    history = SESSION_STORE.get(session_id, [])
    messages = history + [{"role": "user", "content": user_input}]

    result = agent.invoke({"messages": messages})

    result_messages = result.get("messages", [])
    tools_used: list[str] = []
    final_answer = ""

    for msg in result_messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", []) or []
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name:
                    tools_used.append(name)

            text = _extract_text(getattr(msg, "content", ""))
            if text:
                final_answer = text


    updated = history + [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": final_answer},
    ]
    SESSION_STORE[session_id] = updated[-MAX_HISTORY_MESSAGES:]

    dedup_tools = _dedup_keep_order(tools_used)

    return {
        "session_id": session_id,
        "answer": final_answer,
        "tools_used": dedup_tools,
    }

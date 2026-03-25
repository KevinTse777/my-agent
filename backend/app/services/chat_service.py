from app.agent_service import run_agent, run_agent_with_session
from app.llm_chain import build_basic_chain
from app.tools.calculator import calculate
from app.tool_calling import chat_with_auto_tool
from app.tools.search_web import search_web_structured


def chain_chat(message: str) -> dict:
    chain = build_basic_chain()
    answer = chain.invoke({"user_input": message})
    return {"answer": answer}


def agent_chat(message: str) -> dict:
    return run_agent(message)


def manual_chat(mode: str, message: str) -> dict:
    if mode == "chat":
        return {
            "mode": "chat",
            "answer": chain_chat(message)["answer"],
            "tools_used": [],
        }
    
    result = calculate(message)
    return {
        "mode": "calculator",
        "answer": f"计算结果是{result}",
        "tools_used": ["calculator"],
    }


def auto_tool_chat(message: str) -> dict:
    return chat_with_auto_tool(message)


def agent_session_chat(session_id: str, message: str) -> dict:
    return run_agent_with_session(message, session_id)

def web_search_debug(query: str) -> dict:
    return search_web_structured(query=query, max_results=5)

def agent_chat_with_sources(message: str) -> dict:
    # 1) 先做真实搜索，拿结构化来源
    search_data = search_web_structured(query=message, max_results=3)
    sources = search_data.get("sources", [])

    # 2) 把来源片段拼到上下文，让 agent 基于来源回答
    context_lines = []
    for i, s in enumerate(sources, start=1):
        context_lines.append(
            f"[{i}] {s.get('title', '')}\nURL: {s.get('url', '')}\nSnippet: {s.get('snippet', '')}"
        )
    context_text = "\n\n".join(context_lines) if context_lines else "No sources found."

    augmented_message = (
        f"用户问题：{message}\n\n"
        f"可用参考来源：\n{context_text}\n\n"
        "请基于来源回答，并尽量简洁。"
    )

    # 3) 复用现有 agent 能力
    agent_result = agent_chat(augmented_message)

    return {
        "answer": agent_result.get("answer", ""),
        "tools_used": agent_result.get("tools_used", []),
        "sources": sources,
    }
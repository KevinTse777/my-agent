from openai import OpenAI

from app.core.config import settings
from app.tools.calculator import calculate
from app.tools.search_web import search_web_structured


def _build_openai_client() -> OpenAI:
    api_key = settings.dashscope_api_key
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not set")
    return OpenAI(api_key=api_key, base_url=settings.dashscope_base_url)


def simple_chat(message: str) -> dict:
    client = _build_openai_client()
    completion = client.chat.completions.create(
        model=settings.model_name,
        messages=[{"role": "user", "content": message}],
    )
    answer = completion.choices[0].message.content
    return {"answer": answer}


def chain_chat(message: str) -> dict:
    from app.llm_chain import build_basic_chain

    chain = build_basic_chain()
    answer = chain.invoke({"user_input": message})
    return {"answer": answer}


def calculate_chat(expression: str) -> dict:
    result = calculate(expression)
    return {"tool": "calculator", "expression": expression, "result": result}


def manual_chat(mode: str, message: str) -> dict:
    if mode == "chat":
        answer = chain_chat(message)["answer"]
        return {"mode": "chat", "answer": answer, "tools_used": []}

    result = calculate(message)
    return {
        "mode": "calculator",
        "answer": f"计算结果是 {result}",
        "tools_used": ["calculator"],
    }


def auto_tool_chat(message: str) -> dict:
    from app.tool_calling import chat_with_auto_tool

    return chat_with_auto_tool(message)


def agent_chat(message: str) -> dict:
    from app.agent_service import run_agent

    return run_agent(message)


def agent_session_chat(session_id: str, message: str) -> dict:
    from app.agent_service import run_agent_with_session

    return run_agent_with_session(message, session_id)


def web_search_debug(query: str) -> dict:
    return search_web_structured(query=query, max_results=5)

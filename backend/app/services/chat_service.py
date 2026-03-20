from app.agent_service import run_agent, run_agent_with_session
from app.llm_chain import build_basic_chain
from app.tools.calculator import calculate
from app.tool_calling import chat_with_auto_tool

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
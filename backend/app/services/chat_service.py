from app.agent_service import run_agent
from app.llm_chain import build_basic_chain


def chain_chat(message: str) -> dict:
    chain = build_basic_chain()
    answer = chain.invoke({"user_input": message})
    return {"answer": answer}


def agent_chat(message: str) -> dict:
    return run_agent(message)

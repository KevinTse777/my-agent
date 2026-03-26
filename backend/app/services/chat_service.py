from app.services.agent_service import run_agent, run_agent_with_session


def agent_chat(message: str) -> dict:
    return run_agent(message)


def agent_session_chat(session_id: str, message: str) -> dict:
    return run_agent_with_session(message, session_id)

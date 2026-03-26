from app.services.agent_service import run_agent, run_agent_with_session, stream_agent_with_session


def agent_chat(message: str) -> dict:
    return run_agent(message)


def agent_session_chat(session_id: str, message: str) -> dict:
    return run_agent_with_session(message, session_id)


async def agent_session_chat_stream(session_id: str, message: str):
    async for event in stream_agent_with_session(message, session_id):
        yield event

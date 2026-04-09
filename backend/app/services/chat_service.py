from fastapi import HTTPException, status

from app.core.config import settings
from app.services.agent_service import run_agent, run_agent_with_session, stream_agent_with_session
from app.services.audit_service import record_audit_event
from app.services.chat_store import get_chat_store
from app.services.task_broker import ChatTaskJob, get_task_broker
from app.services.task_store import get_task_store


def list_chat_sessions(user_id: str) -> list[dict]:
    return get_chat_store().list_sessions(user_id=user_id)


def create_chat_session(user_id: str, title: str | None = None) -> dict:
    return get_chat_store().create_session(user_id=user_id, title=title)


def list_chat_messages(user_id: str, session_id: str) -> list[dict]:
    try:
        return get_chat_store().list_messages(
            user_id=user_id,
            session_id=session_id,
            limit=settings.business_chat_history_limit,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden session access") from exc


def delete_chat_session(user_id: str, session_id: str) -> bool:
    try:
        return get_chat_store().delete_session(user_id=user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden session access") from exc


def create_chat_task(user_id: str, session_id: str, message: str, request_id: str | None = None) -> dict:
    chat_store = get_chat_store()
    task_store = get_task_store()
    try:
        chat_store.ensure_session(user_id=user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden session access") from exc

    active_task_limit = max(1, settings.user_active_task_limit)
    active_task_count = task_store.count_active_chat_tasks_for_user(user_id=user_id)
    if active_task_count >= active_task_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"User already has too many active tasks active={active_task_count} "
                f"limit={active_task_limit}"
            ),
        )

    active_task = task_store.get_active_chat_task_for_session(user_id=user_id, session_id=session_id)
    if active_task is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Session already has an active task task_id={active_task['id']} "
                f"status={active_task['status']}"
            ),
        )

    task = task_store.create_chat_task(
        user_id=user_id,
        session_id=session_id,
        input_text=message,
        request_id=request_id,
    )
    get_task_broker().publish_chat_task(
        ChatTaskJob(
            task_id=task["id"],
            user_id=user_id,
            session_id=session_id,
            message=message,
            request_id=request_id,
        )
    )
    record_audit_event(
        event_type="chat.task.create",
        user_id=user_id,
        request_id=request_id,
        event_payload={"task_id": task["id"], "session_id": session_id},
    )
    return task


def get_chat_task(user_id: str, task_id: str) -> dict:
    task = get_task_store().get_chat_task(user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def get_chat_task_result(user_id: str, task_id: str) -> dict:
    task = get_chat_task(user_id=user_id, task_id=task_id)
    if task["status"] != "succeeded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is not ready, current status={task['status']}",
        )
    return {
        "task_id": task["id"],
        "status": task["status"],
        "result": task["result"],
        "session_id": task["session_id"],
    }


def agent_chat(message: str) -> dict:
    return run_agent(message)


def agent_session_chat(user_id: str, session_id: str, message: str) -> dict:
    chat_store = get_chat_store()
    try:
        chat_store.ensure_session(user_id=user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden session access") from exc

    data = run_agent_with_session(message, session_id)
    chat_store.append_message(user_id=user_id, session_id=session_id, role="user", content=message)
    chat_store.append_message(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=data.get("answer", ""),
        tools_used=data.get("tools_used", []),
        sources=data.get("sources", []),
    )
    return data


async def agent_session_chat_stream(user_id: str, session_id: str, message: str):
    chat_store = get_chat_store()
    try:
        chat_store.ensure_session(user_id=user_id, session_id=session_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden session access") from exc

    final_event = None
    async for event in stream_agent_with_session(message, session_id):
        final_event = event
        yield event

    if isinstance(final_event, dict) and final_event.get("type") == "end":
        chat_store.append_message(user_id=user_id, session_id=session_id, role="user", content=message)
        chat_store.append_message(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=final_event.get("answer", ""),
            tools_used=final_event.get("tools_used", []),
            sources=final_event.get("sources", []),
        )

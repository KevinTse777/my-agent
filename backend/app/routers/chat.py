import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies.auth import get_current_user
from app.schemas.api_response import ApiResponse
from app.services.chat_service import (
    agent_chat,
    agent_session_chat,
    agent_session_chat_stream,
    create_chat_task,
    create_chat_session,
    delete_chat_session,
    get_chat_task,
    get_chat_task_result,
    list_chat_messages,
    list_chat_sessions,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SessionChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class CreateSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class CreateChatTaskRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


@router.get("/chat/sessions", response_model=ApiResponse)
def get_chat_sessions(current_user: dict = Depends(get_current_user)):
    return ApiResponse(data={"sessions": list_chat_sessions(current_user["id"])})


@router.post("/chat/sessions", response_model=ApiResponse)
def post_chat_sessions(req: CreateSessionRequest, current_user: dict = Depends(get_current_user)):
    return ApiResponse(data=create_chat_session(user_id=current_user["id"], title=req.title))


@router.get("/chat/sessions/{session_id}/messages", response_model=ApiResponse)
def get_chat_session_messages(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return ApiResponse(data={"messages": list_chat_messages(current_user["id"], session_id)})
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/chat/sessions/{session_id}", response_model=ApiResponse)
def delete_chat_session_route(session_id: str, current_user: dict = Depends(get_current_user)):
    deleted = delete_chat_session(current_user["id"], session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return ApiResponse(data={"deleted": True, "session_id": session_id})


@router.post("/chat/tasks", response_model=ApiResponse)
def post_chat_tasks(
    req: CreateChatTaskRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    task = create_chat_task(
        user_id=current_user["id"],
        session_id=req.session_id,
        message=req.message,
        request_id=getattr(request.state, "request_id", None),
    )
    return ApiResponse(data=task)


@router.get("/chat/tasks/{task_id}", response_model=ApiResponse)
def get_chat_task_route(task_id: str, current_user: dict = Depends(get_current_user)):
    return ApiResponse(data=get_chat_task(user_id=current_user["id"], task_id=task_id))


@router.get("/chat/tasks/{task_id}/result", response_model=ApiResponse)
def get_chat_task_result_route(task_id: str, current_user: dict = Depends(get_current_user)):
    return ApiResponse(data=get_chat_task_result(user_id=current_user["id"], task_id=task_id))


@router.post("/chat/agent", response_model=ApiResponse)
def chat_agent(req: ChatRequest, request: Request):
    start = time.perf_counter()
    try:
        data = agent_chat(req.message)
        data["request_id"] = getattr(request.state, "request_id", None)
        data["route_duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/agent/session", response_model=ApiResponse)
def chat_agent_session(req: SessionChatRequest, current_user: dict = Depends(get_current_user)):
    try:
        data = agent_session_chat(current_user["id"], req.session_id, req.message)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/agent/session/stream")
async def chat_agent_session_stream(
    req: SessionChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", None)

    async def event_generator():
        start = time.perf_counter()
        start_event = {"type": "start", "session_id": req.session_id, "request_id": request_id}
        yield json.dumps(start_event, ensure_ascii=False) + "\n"

        try:
            async for event in agent_session_chat_stream(current_user["id"], req.session_id, req.message):
                if isinstance(event, dict):
                    event["request_id"] = request_id
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except ValueError as e:
            error_event = {"type": "error", "message": str(e), "request_id": request_id}
            yield json.dumps(error_event, ensure_ascii=False) + "\n"
        except Exception as e:
            error_event = {"type": "error", "message": str(e), "request_id": request_id}
            yield json.dumps(error_event, ensure_ascii=False) + "\n"
        finally:
            done_event = {
                "type": "done",
                "route_duration_ms": round((time.perf_counter() - start) * 1000, 2),
                "request_id": request_id,
            }
            yield json.dumps(done_event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

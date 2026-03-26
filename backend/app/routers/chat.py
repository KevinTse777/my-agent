import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.schemas.api_response import ApiResponse
from app.services.chat_service import agent_chat, agent_session_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SessionChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


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
def chat_agent_session(req: SessionChatRequest):
    try:
        data = agent_session_chat(req.session_id, req.message)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

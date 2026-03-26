import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


from app.schemas.api_response import ApiResponse
from app.services.chat_service import (
    agent_chat,
    agent_session_chat,
    auto_tool_chat,
    calculate_chat,
    chain_chat,
    manual_chat,
    simple_chat,
    web_search_debug,
)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class CalcRequest(BaseModel):
    expression: str


class ManualChatRequest(BaseModel):
    mode: Literal["chat", "calculator"]
    message: str


class SessionChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class WebSearchRequest(BaseModel):
    query: str


@router.post("/chat/simple", response_model=ApiResponse)
def chat_simple(req: ChatRequest):
    try:
        data = simple_chat(req.message)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/chain", response_model=ApiResponse)
def chat_chain(req: ChatRequest):
    try:
        data = chain_chat(req.message)
        return ApiResponse(data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/calculate", response_model=ApiResponse)
def calculate_api(req: CalcRequest):
    try:
        data = calculate_chat(req.expression)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/chat/manual", response_model=ApiResponse)
def chat_manual(req: ManualChatRequest):
    try:
        data = manual_chat(req.mode, req.message)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/auto-tool", response_model=ApiResponse)
def chat_auto_tool(req: ChatRequest):
    try:
        data = auto_tool_chat(req.message)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/tools/web-search", response_model=ApiResponse)
def web_search_api(req: WebSearchRequest):
    try:
        data = web_search_debug(req.query)
        return ApiResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

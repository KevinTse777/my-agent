import time
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.schemas.api_response import ApiResponse
from app.services.chat_service import agent_chat, agent_session_chat, agent_session_chat_stream

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


@router.post("/chat/agent/session/stream")
async def chat_agent_session_stream(req: SessionChatRequest, request: Request):
    request_id = getattr(request.state, "request_id", None)

    async def event_generator():
        start = time.perf_counter()
        start_event = {"type": "start", "session_id": req.session_id, "request_id": request_id}
        yield json.dumps(start_event, ensure_ascii=False) + "\n"

        try:
            async for event in agent_session_chat_stream(req.session_id, req.message):
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

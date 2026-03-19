from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.agent_service import run_agent, run_agent_with_session
from app.llm_chain import build_basic_chain
from app.tool_calling import chat_with_auto_tool
from app.tools.calculator import calculate
from app.core.config import settings
from app.services.chat_service import agent_chat, chain_chat


api_key = settings.dashscope_api_key
model_name = settings.model_name
base_url = settings.dashscope_base_url
client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
class ChatRequest(BaseModel):
    message: str
router = APIRouter()

@router.post("/chat/simple")
def chat_simple(req: ChatRequest):
    if client is None:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY is not set")
    
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role":"user", "content": req.message}],
        )
        answer = completion.choices[0].message.content
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.post("/chat/chain")
def chat_chain(req: ChatRequest):
    try:
        return chain_chat(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


class CalcRequest(BaseModel):
    expression: str


@router.post("/tools/calculate")
def calculate_api(req: CalcRequest):
    try:
        result = calculate(req.expression)
        return {"tool": "calculator", "expression": req.expression, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ManualChatRequest(BaseModel):
    mode: Literal["chat", "calculator"]
    message: str


@router.post("/chat/manual")
def chat_manual(req: ManualChatRequest):
    try:
        if req.mode == "chat":
            chain = build_basic_chain()
            answer = chain.invoke({"user_input": req.message})
            return {
                "mode": "chat",
                "answer": answer,
                "tools_used": [],
            }

        # mode == "calculator"
        result = calculate(req.message)
        return {
            "mode": "calculator",
            "answer": f"计算结果是 {result}",
            "tools_used": ["calculator"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/auto-tool")
def chat_auto_tool(req: ChatRequest):
    try:
        result = chat_with_auto_tool(req.message)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/agent")
def chat_agent(req: ChatRequest):
    try:
        return agent_chat(req.message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class SessionChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("/chat/agent/session")
def chat_agent_session(req: SessionChatRequest):
    try:
        return run_agent_with_session(req.message, req.session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel
from app.llm_chain import build_basic_chain
from app.tools.calculator import calculate
from typing import Literal
from app.tool_calling import chat_with_auto_tool



load_dotenv()
app = FastAPI(title="StudyMate Agent API", version="0.1.0")

api_key = os.getenv("DASHSCOPE_API_KEY")
model_name = os.getenv("MODEL_NAME", "qwen3-vl-235b-a22b-thinking")
base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None


class ChatRequest(BaseModel):
    message: str



@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/chat/simple")
def chat_simple(req: ChatRequest):
    if client is None:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set")
    
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role":"user", "content": req.message}],
        )
        answer = completion.choices[0].message.content
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/chat/chain")
def chat_chain(req: ChatRequest):
    try:
        chain = build_basic_chain()
        answer = chain.invoke({"user_input": req.message})
        return {"ans": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


class CalcRequest(BaseModel):
    expression: str


@app.post("/tools/calculate")
def calculate_api(req: CalcRequest):
    try:
        result = calculate(req.expression)
        return {"tool": "calculator", "expression": req.expression, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ManualChatRequest(BaseModel):
    mode: Literal["chat", "calculator"]
    message: str


@app.post("/chat/manual")
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


@app.post("/chat/auto-tool")
def chat_auto_tool(req: ChatRequest):
    try:
        result = chat_with_auto_tool(req.message)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

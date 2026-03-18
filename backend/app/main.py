import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel
from app.llm_chain import build_basic_chain


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
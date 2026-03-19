from fastapi import FastAPI

from app.routers.chat import router as chat_router
from app.routers.system import router as system_router

app = FastAPI(title="StudyMate Agent API", version="0.1.0")

app.include_router(system_router)
app.include_router(chat_router)

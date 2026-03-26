import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    dashscope_api_key: str | None
    model_name: str
    dashscope_base_url: str
    redis_url: str | None
    postgres_url: str | None
    memory_context_window: int
    memory_context_ttl_seconds: int


settings = Settings(
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
    model_name=os.getenv("MODEL_NAME", "qwen-plus"),
    dashscope_base_url=os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    redis_url=os.getenv("REDIS_URL"),
    postgres_url=os.getenv("POSTGRES_URL"),
    memory_context_window=int(os.getenv("MEMORY_CONTEXT_WINDOW", "12")),
    memory_context_ttl_seconds=int(os.getenv("MEMORY_CONTEXT_TTL_SECONDS", "1800")),
)

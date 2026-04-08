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
    business_chat_history_limit: int
    auth_secret_key: str
    auth_access_token_ttl_seconds: int
    auth_refresh_token_ttl_seconds: int


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
    business_chat_history_limit=int(os.getenv("BUSINESS_CHAT_HISTORY_LIMIT", "100")),
    auth_secret_key=os.getenv("AUTH_SECRET_KEY", "dev-secret-change-me"),
    auth_access_token_ttl_seconds=int(os.getenv("AUTH_ACCESS_TOKEN_TTL_SECONDS", "3600")),
    auth_refresh_token_ttl_seconds=int(os.getenv("AUTH_REFRESH_TOKEN_TTL_SECONDS", "1209600")),
)

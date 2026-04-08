import os
from importlib.util import find_spec
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
    task_broker_backend: str
    kafka_bootstrap_servers: str | None
    kafka_chat_task_topic: str
    kafka_chat_task_dlq_topic: str
    kafka_chat_task_consumer_group: str
    task_worker_max_retries: int
    api_rate_limit_enabled: bool
    api_rate_limit_window_seconds: int
    api_rate_limit_auth_max_requests: int
    api_rate_limit_chat_max_requests: int
    api_rate_limit_task_create_max_requests: int


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
    task_broker_backend=os.getenv("TASK_BROKER_BACKEND", "inmemory").strip().lower(),
    kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS"),
    kafka_chat_task_topic=os.getenv("KAFKA_CHAT_TASK_TOPIC", "chat.request"),
    kafka_chat_task_dlq_topic=os.getenv("KAFKA_CHAT_TASK_DLQ_TOPIC", "chat.request.dlq"),
    kafka_chat_task_consumer_group=os.getenv("KAFKA_CHAT_TASK_CONSUMER_GROUP", "studymate-chat-worker"),
    task_worker_max_retries=int(os.getenv("TASK_WORKER_MAX_RETRIES", "1")),
    api_rate_limit_enabled=os.getenv("API_RATE_LIMIT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
    api_rate_limit_window_seconds=int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60")),
    api_rate_limit_auth_max_requests=int(os.getenv("API_RATE_LIMIT_AUTH_MAX_REQUESTS", "5")),
    api_rate_limit_chat_max_requests=int(os.getenv("API_RATE_LIMIT_CHAT_MAX_REQUESTS", "10")),
    api_rate_limit_task_create_max_requests=int(os.getenv("API_RATE_LIMIT_TASK_CREATE_MAX_REQUESTS", "10")),
)


def validate_runtime_configuration() -> None:
    if settings.task_broker_backend != "kafka":
        return

    if not settings.kafka_bootstrap_servers:
        raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is required when TASK_BROKER_BACKEND=kafka")

    if not settings.postgres_url:
        raise RuntimeError(
            "POSTGRES_URL is required when TASK_BROKER_BACKEND=kafka so API and worker can share auth/chat/task/memory storage."
        )

    if find_spec("kafka") is None:
        raise RuntimeError(
            "kafka-python is required when TASK_BROKER_BACKEND=kafka. Please install it before starting API or worker."
        )

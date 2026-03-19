import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    dashscope_api_key: str | None
    model_name: str
    dashscope_base_url: str


settings = Settings(
    dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),
    model_name=os.getenv("MODEL_NAME", "qwen-plus"),
    dashscope_base_url=os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
)

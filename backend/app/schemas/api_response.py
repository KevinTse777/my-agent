from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Any = None

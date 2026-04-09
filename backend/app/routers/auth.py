from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.dependencies.auth import get_current_user
from app.schemas.api_response import ApiResponse
from app.services.auth_service import (
    login_user,
    logout_user,
    refresh_user_token,
    register_user,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=4096)


@router.post("/auth/register", response_model=ApiResponse)
def register(req: RegisterRequest, request: Request):
    return ApiResponse(data=register_user(req.email, req.username, req.password, request_id=getattr(request.state, "request_id", None)))


@router.post("/auth/login", response_model=ApiResponse)
def login(req: LoginRequest, request: Request):
    return ApiResponse(data=login_user(req.email, req.password, request_id=getattr(request.state, "request_id", None)))


@router.post("/auth/refresh", response_model=ApiResponse)
def refresh(req: RefreshRequest, request: Request):
    return ApiResponse(data=refresh_user_token(req.refresh_token, request_id=getattr(request.state, "request_id", None)))


@router.post("/auth/logout", response_model=ApiResponse)
def logout(req: RefreshRequest, request: Request):
    return ApiResponse(data=logout_user(req.refresh_token, request_id=getattr(request.state, "request_id", None)))


@router.get("/me", response_model=ApiResponse)
def me(current_user: dict = Depends(get_current_user)):
    return ApiResponse(data=current_user)

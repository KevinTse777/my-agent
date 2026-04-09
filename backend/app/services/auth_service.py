from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.audit_service import record_audit_event
from app.services.auth_security_service import get_auth_login_security_service
from app.services.auth_store import UserRecord, get_auth_store, hash_token


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _encode_token(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def _decode_token(token: str) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual = _b64url_decode(signature_b64)

    if not hmac.compare_digest(expected, actual):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(_utc_now().timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return payload


def _build_password_hash(password: str, salt: str | None = None) -> str:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt.encode("utf-8"),
        100000,
    ).hex()
    return f"{actual_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_build_password_hash(password, salt), stored_hash)


def _access_payload(user: UserRecord) -> dict:
    now = _utc_now()
    return {
        "sub": user.id,
        "email": user.email,
        "username": user.username,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.auth_access_token_ttl_seconds)).timestamp()),
    }


def _refresh_payload(user: UserRecord, session_id: str) -> dict:
    now = _utc_now()
    return {
        "sub": user.id,
        "sid": session_id,
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.auth_refresh_token_ttl_seconds)).timestamp()),
    }


def _require_active_user(user: UserRecord | None) -> UserRecord:
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _normalize_email(email: str) -> str:
    cleaned = email.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
    return cleaned


def register_user(email: str, username: str, password: str, request_id: str | None = None) -> dict:
    store = get_auth_store()
    email = _normalize_email(email)
    if store.get_user_by_email(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = store.create_user(email=email, username=username, password_hash=_build_password_hash(password))
    public_user = user.public_dict()
    record_audit_event(
        event_type="auth.register",
        user_id=user.id,
        request_id=request_id,
        event_payload={"username": user.username},
    )
    return public_user


def login_user(email: str, password: str, request_id: str | None = None) -> dict:
    store = get_auth_store()
    email = _normalize_email(email)
    security = get_auth_login_security_service()
    security.ensure_login_allowed(email)

    user = store.get_user_by_email(email)
    if user is None or user.status != "active":
        security.record_failed_login(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not verify_password(password, user.password_hash):
        security.record_failed_login(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    security.reset_failed_logins(email)

    expires_at = _utc_now() + timedelta(seconds=settings.auth_refresh_token_ttl_seconds)
    refresh_session = store.create_refresh_session(
        user_id=user.id,
        refresh_token_hash="pending",
        expires_at=expires_at,
    )
    refresh_token = _encode_token(_refresh_payload(user, refresh_session.id))
    store.update_refresh_session_hash(refresh_session.id, hash_token(refresh_token))
    access_token = _encode_token(_access_payload(user))
    record_audit_event(
        event_type="auth.login",
        user_id=user.id,
        request_id=request_id,
        event_payload={"refresh_session_id": refresh_session.id},
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.auth_access_token_ttl_seconds,
        "user": user.public_dict(),
    }


def refresh_user_token(refresh_token: str, request_id: str | None = None) -> dict:
    store = get_auth_store()
    payload = _decode_token(refresh_token)
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    session_id = payload.get("sid")
    user_id = payload.get("sub")
    if not isinstance(session_id, str) or not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    record = store.get_refresh_session(session_id)
    if record is None or record.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session invalid")
    if record.expires_at <= _utc_now():
        store.revoke_refresh_session(session_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    if not hmac.compare_digest(record.refresh_token_hash, hash_token(refresh_token)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token invalid")

    user = _require_active_user(store.get_user_by_id(user_id))
    store.revoke_refresh_session(session_id)

    expires_at = _utc_now() + timedelta(seconds=settings.auth_refresh_token_ttl_seconds)
    new_session = store.create_refresh_session(
        user_id=user.id,
        refresh_token_hash="pending",
        expires_at=expires_at,
    )
    new_refresh_token = _encode_token(_refresh_payload(user, new_session.id))
    store.update_refresh_session_hash(new_session.id, hash_token(new_refresh_token))
    access_token = _encode_token(_access_payload(user))
    record_audit_event(
        event_type="auth.refresh",
        user_id=user.id,
        request_id=request_id,
        event_payload={"refresh_session_id": new_session.id},
    )
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.auth_access_token_ttl_seconds,
        "user": user.public_dict(),
    }


def logout_user(refresh_token: str, request_id: str | None = None) -> dict:
    payload = _decode_token(refresh_token)
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    session_id = payload.get("sid")
    user_id = payload.get("sub")
    if not isinstance(session_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    get_auth_store().revoke_refresh_session(session_id)
    record_audit_event(
        event_type="auth.logout",
        user_id=user_id if isinstance(user_id, str) else None,
        request_id=request_id,
        event_payload={"refresh_session_id": session_id},
    )
    return {"logged_out": True}


def get_current_user_from_token(access_token: str) -> dict:
    payload = _decode_token(access_token)
    if payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = _require_active_user(get_auth_store().get_user_by_id(user_id))
    return user.public_dict()

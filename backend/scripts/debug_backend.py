#!/usr/bin/env python3
"""
Lightweight backend diagnostics for my-agent.

Usage:
  python backend/scripts/debug_backend.py
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
import traceback

from dotenv import load_dotenv


REQUIRED_MODULES = [
    "fastapi",
    "uvicorn",
    "openai",
    "langchain",
    "langchain_openai",
    "dotenv",
    "tavily",
    "psycopg_pool",
    "redis",
]

IMPORTANT_ENVS = [
    "DASHSCOPE_API_KEY",
    "MODEL_NAME",
    "DASHSCOPE_BASE_URL",
    "TAVILY_API_KEY",
    "POSTGRES_URL",
    "REDIS_URL",
    "MEMORY_CONTEXT_WINDOW",
    "MEMORY_CONTEXT_TTL_SECONDS",
]


def title(text: str) -> None:
    print(f"\n=== {text} ===")


def ok(text: str) -> None:
    print(f"[OK] {text}")


def fail(text: str) -> None:
    print(f"[FAIL] {text}")


def warn(text: str) -> None:
    print(f"[WARN] {text}")


def check_python() -> None:
    title("Python")
    ok(f"python={sys.version.split()[0]}")
    ok(f"platform={platform.platform()}")
    ok(f"executable={sys.executable}")


def check_modules() -> bool:
    title("Dependencies")
    all_ok = True
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            ok(f"import {mod}")
        except Exception as e:
            all_ok = False
            fail(f"import {mod} -> {e.__class__.__name__}: {e}")
    return all_ok


def masked(value: str | None) -> str:
    if not value:
        return "NOT_SET"
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def check_envs() -> None:
    title("Environment Variables")
    for key in IMPORTANT_ENVS:
        value = os.getenv(key)
        if value:
            ok(f"{key}={masked(value)}")
        else:
            warn(f"{key}=NOT_SET")


def check_app_import() -> bool:
    title("App Import")
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    try:
        from app.main import app  # pylint: disable=import-outside-toplevel

        ok(f"import app.main:app ({type(app).__name__})")
        return True
    except Exception:
        fail("import app.main:app failed")
        traceback.print_exc()
        return False


def check_routes() -> bool:
    title("Route Smoke Test")
    try:
        from fastapi.testclient import TestClient  # pylint: disable=import-outside-toplevel
        from app.main import app  # pylint: disable=import-outside-toplevel

        client = TestClient(app)

        health = client.get("/health")
        if health.status_code == 200:
            ok("GET /health -> 200")
        else:
            warn(f"GET /health -> {health.status_code}")

        resp = client.post(
            "/chat/agent/session",
            json={"session_id": "debug_session", "message": "hello"},
        )
        if resp.status_code in (200, 400, 500):
            ok(f"POST /chat/agent/session reachable -> {resp.status_code}")
        else:
            warn(f"POST /chat/agent/session unexpected -> {resp.status_code}")

        return True
    except Exception:
        fail("route smoke test failed")
        traceback.print_exc()
        return False


def main() -> int:
    load_dotenv()
    check_python()
    deps_ok = check_modules()
    check_envs()
    app_ok = check_app_import()
    route_ok = check_routes() if app_ok else False

    title("Summary")
    if deps_ok and app_ok and route_ok:
        ok("backend diagnostics passed")
        return 0

    fail("backend diagnostics found issues")
    print("\nSuggested first fix:")
    print(
        "  pip install fastapi 'uvicorn[standard]' openai python-dotenv "
        "langchain langchain-openai langgraph tavily-python psycopg[binary] "
        "psycopg-pool redis"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

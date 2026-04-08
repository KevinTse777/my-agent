from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4


def request_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
    access_token: str | None = None,
) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method} {url} failed: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {url} returned non-JSON body: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test API -> Kafka -> worker -> Postgres chat task flow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Task polling interval in seconds")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Task result timeout in seconds")
    parser.add_argument("--message", default="请用一句话确认 Kafka consumer group 异步链路已经恢复。", help="Task input message")
    args = parser.parse_args()

    suffix = uuid4().hex[:8]
    email = f"smoke_{suffix}@example.com"
    username = f"smoke_{suffix}"
    password = "password123"

    print("==> register")
    register_resp = request_json(
        "POST",
        f"{args.base_url}/auth/register",
        payload={"email": email, "username": username, "password": password},
    )
    user = register_resp["data"]
    print(f"registered user_id={user['id']} email={user['email']}")

    print("==> login")
    login_resp = request_json(
        "POST",
        f"{args.base_url}/auth/login",
        payload={"email": email, "password": password},
    )
    auth_data = login_resp["data"]
    access_token = auth_data["access_token"]
    print("login ok")

    print("==> create session")
    session_resp = request_json(
        "POST",
        f"{args.base_url}/chat/sessions",
        payload={"title": "Kafka smoke session"},
        access_token=access_token,
    )
    session = session_resp["data"]
    session_id = session["id"]
    print(f"session_id={session_id}")

    print("==> create task")
    task_resp = request_json(
        "POST",
        f"{args.base_url}/chat/tasks",
        payload={"session_id": session_id, "message": args.message},
        access_token=access_token,
    )
    task = task_resp["data"]
    task_id = task["id"]
    print(f"task_id={task_id} status={task['status']}")

    print("==> poll task")
    deadline = time.time() + args.timeout_seconds
    latest_status = task["status"]
    while time.time() < deadline:
        status_resp = request_json(
            "GET",
            f"{args.base_url}/chat/tasks/{task_id}",
            access_token=access_token,
        )
        status_data = status_resp["data"]
        latest_status = status_data["status"]
        print(f"task status={latest_status}")
        if latest_status in {"succeeded", "failed"}:
            break
        time.sleep(args.poll_interval)

    if latest_status != "succeeded":
        raise RuntimeError(f"task did not succeed before timeout, latest_status={latest_status}")

    print("==> get task result")
    result_resp = request_json(
        "GET",
        f"{args.base_url}/chat/tasks/{task_id}/result",
        access_token=access_token,
    )
    result = result_resp["data"]["result"]
    answer = result.get("answer", "")
    print(f"task answer={answer}")

    print("==> get session messages")
    messages_resp = request_json(
        "GET",
        f"{args.base_url}/chat/sessions/{session_id}/messages",
        access_token=access_token,
    )
    messages = messages_resp["data"]["messages"]
    print(f"messages_count={len(messages)}")

    if len(messages) < 2:
        raise RuntimeError(f"expected at least 2 messages in session history, got {len(messages)}")

    print("==> smoke flow passed")
    print(
        json.dumps(
            {
                "session_id": session_id,
                "task_id": task_id,
                "final_status": latest_status,
                "messages_count": len(messages),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"smoke flow failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings, validate_runtime_configuration
from app.services.task_broker import ChatTaskJob, get_task_broker


def load_kafka_consumer():
    try:
        from kafka import KafkaConsumer
    except ImportError as exc:
        raise RuntimeError("kafka-python is required to run DLQ smoke flow.") from exc
    return KafkaConsumer


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test chat task DLQ publish/read flow.")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="Consumer timeout in milliseconds")
    args = parser.parse_args()

    validate_runtime_configuration()
    broker = get_task_broker()
    kafka_consumer_cls = load_kafka_consumer()

    suffix = uuid4().hex[:8]
    job = ChatTaskJob(
        task_id=f"task_dlq_smoke_{suffix}",
        user_id=f"user_dlq_smoke_{suffix}",
        session_id=f"sess_dlq_smoke_{suffix}",
        message="dlq smoke message",
        request_id=f"req_dlq_smoke_{suffix}",
    )
    error_message = f"dlq smoke error {suffix}"
    retry_count = 99

    print("==> publish dlq message")
    broker.publish_chat_task_dlq(job, error_message, retry_count)

    print("==> read dlq message")
    consumer = kafka_consumer_cls(
        settings.kafka_chat_task_dlq_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=args.timeout_ms,
        auto_offset_reset="earliest",
        group_id=None,
    )
    try:
        for message in consumer:
            payload = message.value
            if payload.get("task_id") != job.task_id:
                continue

            print(json.dumps(payload, ensure_ascii=False))
            if payload.get("error_message") != error_message:
                raise RuntimeError("DLQ message found but error_message mismatch.")
            if payload.get("retry_count") != retry_count:
                raise RuntimeError("DLQ message found but retry_count mismatch.")
            print("==> dlq smoke flow passed")
            return 0
    finally:
        consumer.close()

    raise RuntimeError("DLQ smoke message not found before timeout.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"dlq smoke flow failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

from __future__ import annotations

import argparse
import json
import sys

CURRENT_DIR = __import__("pathlib").Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings, validate_runtime_configuration


def load_kafka_consumer():
    try:
        from kafka import KafkaConsumer
    except ImportError as exc:
        raise RuntimeError("kafka-python is required to read DLQ messages.") from exc
    return KafkaConsumer


def main() -> int:
    parser = argparse.ArgumentParser(description="Read messages from chat task DLQ topic.")
    parser.add_argument("--max-messages", type=int, default=5, help="Maximum number of DLQ messages to print")
    parser.add_argument("--timeout-ms", type=int, default=3000, help="Consumer timeout in milliseconds")
    parser.add_argument("--from-beginning", action="store_true", help="Read from earliest offset")
    args = parser.parse_args()

    validate_runtime_configuration()
    kafka_consumer_cls = load_kafka_consumer()

    consumer = kafka_consumer_cls(
        settings.kafka_chat_task_dlq_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=args.timeout_ms,
        auto_offset_reset="earliest" if args.from_beginning else "latest",
        group_id=None,
    )

    printed = 0
    try:
        for message in consumer:
            printed += 1
            print(json.dumps(message.value, ensure_ascii=False))
            if printed >= args.max_messages:
                break
    finally:
        consumer.close()

    if printed == 0:
        print("No DLQ messages found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

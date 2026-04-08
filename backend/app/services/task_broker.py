from __future__ import annotations

import json
import queue
from dataclasses import asdict, dataclass
from functools import lru_cache
from threading import Event
from typing import Callable, Protocol

from app.core.config import settings


@dataclass
class ChatTaskJob:
    task_id: str
    user_id: str
    session_id: str
    message: str
    request_id: str | None


ChatTaskHandler = Callable[[ChatTaskJob], None]


class TaskBroker(Protocol):
    def publish_chat_task(self, job: ChatTaskJob) -> None:
        ...

    def consume_chat_tasks(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        ...

    def close(self) -> None:
        ...


class InMemoryTaskBroker:
    def __init__(self) -> None:
        self._queue: queue.Queue[ChatTaskJob] = queue.Queue()

    def publish_chat_task(self, job: ChatTaskJob) -> None:
        self._queue.put(job)

    def consume_chat_tasks(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        while not stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                handler(job)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        return None


class KafkaTaskBroker:
    def __init__(self, bootstrap_servers: str, topic: str, consumer_group: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._consumer_group = consumer_group
        self._producer = None

    def _load_kafka(self):
        try:
            from kafka import KafkaConsumer, KafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "Kafka broker backend requires kafka-python. Please install it before enabling TASK_BROKER_BACKEND=kafka."
            ) from exc
        return KafkaConsumer, KafkaProducer

    def _get_producer(self):
        if self._producer is None:
            _, kafka_producer_cls = self._load_kafka()
            self._producer = kafka_producer_cls(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
        return self._producer

    def publish_chat_task(self, job: ChatTaskJob) -> None:
        producer = self._get_producer()
        producer.send(self._topic, asdict(job))
        producer.flush()

    def consume_chat_tasks(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        kafka_consumer_cls, _ = self._load_kafka()
        consumer = kafka_consumer_cls(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._consumer_group,
            enable_auto_commit=False,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            consumer_timeout_ms=1000,
            auto_offset_reset="earliest",
        )
        try:
            while not stop_event.is_set():
                for message in consumer:
                    if stop_event.is_set():
                        break
                    handler(ChatTaskJob(**message.value))
                    consumer.commit()
        finally:
            consumer.close()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()
            self._producer = None


@lru_cache(maxsize=1)
def get_task_broker() -> TaskBroker:
    if settings.task_broker_backend == "kafka":
        if not settings.kafka_bootstrap_servers:
            raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is required when TASK_BROKER_BACKEND=kafka")
        return KafkaTaskBroker(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_chat_task_topic,
            consumer_group=settings.kafka_chat_task_consumer_group,
        )
    return InMemoryTaskBroker()

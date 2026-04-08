from __future__ import annotations

import json
import logging
import queue
from dataclasses import asdict, dataclass
from functools import lru_cache
from threading import Event
from typing import Callable, Protocol

from app.core.config import settings

logger = logging.getLogger("app.task_broker")


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

    def publish_chat_task_dlq(self, job: ChatTaskJob, error_message: str, retry_count: int) -> None:
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

    def publish_chat_task_dlq(self, job: ChatTaskJob, error_message: str, retry_count: int) -> None:
        logger.warning(
            "InMemory broker DLQ event task_id=%s retry_count=%s error=%s",
            job.task_id,
            retry_count,
            error_message,
        )

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
    def __init__(self, bootstrap_servers: str, topic: str, dlq_topic: str, consumer_group: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._dlq_topic = dlq_topic
        self._consumer_group = consumer_group
        self._producer = None

    def _load_kafka(self):
        try:
            from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer, TopicPartition
        except ImportError as exc:
            raise RuntimeError(
                "Kafka broker backend requires kafka-python. Please install it before enabling TASK_BROKER_BACKEND=kafka."
            ) from exc
        return KafkaAdminClient, KafkaConsumer, KafkaProducer, TopicPartition

    def _get_producer(self):
        if self._producer is None:
            _, _, kafka_producer_cls, _ = self._load_kafka()
            self._producer = kafka_producer_cls(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
        return self._producer

    def publish_chat_task(self, job: ChatTaskJob) -> None:
        producer = self._get_producer()
        producer.send(self._topic, asdict(job))
        producer.flush()

    def publish_chat_task_dlq(self, job: ChatTaskJob, error_message: str, retry_count: int) -> None:
        producer = self._get_producer()
        producer.send(
            self._dlq_topic,
            {
                **asdict(job),
                "error_message": error_message,
                "retry_count": retry_count,
            },
        )
        producer.flush()

    def _consume_with_group(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        _, kafka_consumer_cls, _, _ = self._load_kafka()
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

    def _consume_without_group(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        _, kafka_consumer_cls, _, topic_partition_cls = self._load_kafka()
        consumer = kafka_consumer_cls(
            bootstrap_servers=self._bootstrap_servers,
            enable_auto_commit=False,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            consumer_timeout_ms=1000,
            auto_offset_reset="earliest",
        )
        try:
            partitions = consumer.partitions_for_topic(self._topic)
            if not partitions:
                logger.warning("Kafka topic has no partitions yet topic=%s", self._topic)
                return

            topic_partitions = [topic_partition_cls(self._topic, partition) for partition in sorted(partitions)]
            consumer.assign(topic_partitions)
            consumer.seek_to_beginning(*topic_partitions)

            while not stop_event.is_set():
                for message in consumer:
                    if stop_event.is_set():
                        break
                    handler(ChatTaskJob(**message.value))
        finally:
            consumer.close()

    def _consumer_group_ready(self) -> bool:
        kafka_admin_cls, _, _, _ = self._load_kafka()
        admin = kafka_admin_cls(bootstrap_servers=self._bootstrap_servers, client_id="studymate-task-worker")
        try:
            admin.describe_consumer_groups([self._consumer_group])
            return True
        except Exception as exc:
            if exc.__class__.__name__ == "CoordinatorNotAvailableError":
                logger.warning(
                    "Kafka consumer group coordinator unavailable, direct partition fallback will be used. "
                    "topic=%s group=%s error=%s",
                    self._topic,
                    self._consumer_group,
                    str(exc),
                )
                return False
            raise
        finally:
            admin.close()

    def inspect_detailed_runtime(self) -> dict[str, str]:
        _, kafka_consumer_cls, _, _ = self._load_kafka()
        runtime = self.inspect_runtime()

        consumer = kafka_consumer_cls(
            bootstrap_servers=self._bootstrap_servers,
            enable_auto_commit=False,
            consumer_timeout_ms=1000,
            auto_offset_reset="earliest",
        )
        try:
            runtime["bootstrap_connected"] = "yes" if consumer.bootstrap_connected() else "no"

            try:
                partitions = consumer.partitions_for_topic(self._topic)
                if partitions:
                    runtime["topic_exists"] = "yes"
                    runtime["topic_partitions"] = ",".join(str(partition) for partition in sorted(partitions))
                else:
                    runtime["topic_exists"] = "no"
                    runtime["topic_partitions"] = ""
            except Exception as exc:
                runtime["topic_exists"] = "unknown"
                runtime["topic_partitions"] = ""
                runtime["topic_error"] = f"{exc.__class__.__name__}: {exc}"

            try:
                # Newer kafka-python versions support exclude_internal_topics.
                # Older versions do not, so we gracefully degrade instead of
                # reporting a misleading "no" for __consumer_offsets visibility.
                try:
                    topics = sorted(consumer.topics(exclude_internal_topics=False))
                    runtime["consumer_offsets_topic_visible"] = "yes" if "__consumer_offsets" in topics else "no"
                except TypeError:
                    topics = sorted(consumer.topics())
                    if "__consumer_offsets" in topics:
                        runtime["consumer_offsets_topic_visible"] = "yes"
                    else:
                        runtime["consumer_offsets_topic_visible"] = "unknown"
                        runtime["consumer_offsets_note"] = (
                            "Current kafka-python version does not support include-internal-topics inspection."
                        )
            except Exception as exc:
                runtime["consumer_offsets_topic_visible"] = "unknown"
                runtime["topics_error"] = f"{exc.__class__.__name__}: {exc}"
        finally:
            consumer.close()

        return runtime

    def consume_chat_tasks(self, handler: ChatTaskHandler, stop_event: Event) -> None:
        if not self._consumer_group_ready():
            self._consume_without_group(handler, stop_event)
            return
        try:
            self._consume_with_group(handler, stop_event)
        except Exception as exc:
            if exc.__class__.__name__ != "CoordinatorNotAvailableError":
                raise
            logger.warning(
                "Kafka consumer group coordinator unavailable, fallback to direct partition consumption. "
                "topic=%s group=%s error=%s",
                self._topic,
                self._consumer_group,
                str(exc),
            )
            self._consume_without_group(handler, stop_event)

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()
            self._producer = None

    def inspect_runtime(self) -> dict[str, str]:
        consumer_mode = "consumer_group"
        note = "Kafka consumer group coordinator is available."
        if not self._consumer_group_ready():
            consumer_mode = "direct_partition_fallback"
            note = "Kafka consumer group coordinator is unavailable, worker will fallback to direct partition consumption."
        return {
            "broker_backend": "kafka",
            "bootstrap_servers": self._bootstrap_servers,
            "topic": self._topic,
            "dlq_topic": self._dlq_topic,
            "consumer_group": self._consumer_group,
            "consumer_mode": consumer_mode,
            "note": note,
        }


@lru_cache(maxsize=1)
def get_task_broker() -> TaskBroker:
    if settings.task_broker_backend == "kafka":
        if not settings.kafka_bootstrap_servers:
            raise RuntimeError("KAFKA_BOOTSTRAP_SERVERS is required when TASK_BROKER_BACKEND=kafka")
        return KafkaTaskBroker(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.kafka_chat_task_topic,
            dlq_topic=settings.kafka_chat_task_dlq_topic,
            consumer_group=settings.kafka_chat_task_consumer_group,
        )
    return InMemoryTaskBroker()


def inspect_task_broker_runtime() -> dict[str, str]:
    broker = get_task_broker()
    if isinstance(broker, KafkaTaskBroker):
        return broker.inspect_runtime()
    return {
        "broker_backend": "inmemory",
        "consumer_mode": "embedded_worker",
        "note": "InMemory mode uses the embedded API worker and does not require a standalone worker process.",
    }


def inspect_task_broker_runtime_detailed() -> dict[str, str]:
    broker = get_task_broker()
    if isinstance(broker, KafkaTaskBroker):
        return broker.inspect_detailed_runtime()
    return inspect_task_broker_runtime()

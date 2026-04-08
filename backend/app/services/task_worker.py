from __future__ import annotations

import logging
import threading
from functools import lru_cache

from app.services.task_broker import ChatTaskJob, get_task_broker
from app.services.task_store import get_task_store

logger = logging.getLogger("app.task_worker")


class TaskWorker:
    def __init__(self) -> None:
        self._broker = get_task_broker()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, name="chat-task-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._broker.close()

    def enqueue(self, job: ChatTaskJob) -> None:
        self._broker.publish_chat_task(job)

    def process_job(self, job: ChatTaskJob) -> None:
        from app.services.chat_service import agent_session_chat

        task_store = get_task_store()
        task_store.mark_chat_task_running(job.task_id)
        try:
            result = agent_session_chat(job.user_id, job.session_id, job.message)
            task_store.mark_chat_task_succeeded(job.task_id, result)
        except Exception as exc:
            logger.exception(
                "chat task failed task_id=%s user_id=%s session_id=%s request_id=%s error=%s",
                job.task_id,
                job.user_id,
                job.session_id,
                job.request_id,
                str(exc),
            )
            task_store.mark_chat_task_failed(job.task_id, str(exc))

    def run_forever(self) -> None:
        self._broker.consume_chat_tasks(self.process_job, self._stop_event)


@lru_cache(maxsize=1)
def get_task_worker() -> TaskWorker:
    return TaskWorker()

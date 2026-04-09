from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar


T = TypeVar("T")


class ToolTimeoutError(RuntimeError):
    pass


def run_with_timeout(
    func: Callable[..., T],
    *args,
    timeout_seconds: float,
    timeout_message: str,
    **kwargs,
) -> T:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tool-timeout")
    try:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ToolTimeoutError(timeout_message) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

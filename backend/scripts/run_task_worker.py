from pathlib import Path
import signal
import sys

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings, validate_runtime_configuration
from app.services.task_broker import inspect_task_broker_runtime, inspect_task_broker_runtime_detailed
from app.services.task_worker import get_task_worker


def _print_runtime_check() -> None:
    runtime = inspect_task_broker_runtime()
    print("Task worker runtime check")
    for key in sorted(runtime):
        print(f"- {key}: {runtime[key]}")


def _print_runtime_diagnose() -> None:
    runtime = inspect_task_broker_runtime_detailed()
    print("Task worker runtime diagnose")
    for key in sorted(runtime):
        print(f"- {key}: {runtime[key]}")


def main() -> int:
    validate_runtime_configuration()

    if "--check" in sys.argv[1:]:
        _print_runtime_check()
        return 0

    if "--diagnose" in sys.argv[1:]:
        _print_runtime_diagnose()
        return 0

    if settings.task_broker_backend == "inmemory":
        print("TASK_BROKER_BACKEND=inmemory uses the embedded API worker. Switch to kafka before starting a standalone worker.")
        return 1

    worker = get_task_worker()

    def handle_shutdown(signum, frame):
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

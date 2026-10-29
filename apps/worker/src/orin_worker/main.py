import logging
import os
import signal
import threading
from orin_worker.client import worker_loop


def main() -> None:
    """Run the authenticated worker gateway loop after explicit device enrollment."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.getLogger(__name__).info("Worker process started")
    try:
        worker_loop(stopping)
    except RuntimeError as error:
        logging.getLogger(__name__).error("Worker configuration is incomplete: %s", error)
        while not stopping.is_set():
            stopping.wait(30)
    logging.getLogger(__name__).info("Worker foundation stopped")


if __name__ == "__main__":
    main()

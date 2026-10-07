import logging
import os
import signal
import time


def main() -> None:
    """Run an idle worker process until the platform worker is designed."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.getLogger(__name__).info("Worker foundation started; no jobs are configured")
    while not stopping:
        time.sleep(1)
    logging.getLogger(__name__).info("Worker foundation stopped")


if __name__ == "__main__":
    main()

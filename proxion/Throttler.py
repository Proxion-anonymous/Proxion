import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiprocessing.managers import ValueProxy
    from threading import Lock


_logger = logging.getLogger(__name__)


class Throttler:
    def __init__(self, request_per_second: float, last_refill: "ValueProxy[float]", lock: "Lock"):
        self.rate = request_per_second
        self.last_refill = last_refill
        self.lock = lock

    def __enter__(self):
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_refill.value
                _logger.debug(
                    "Acquired lock: refill=%s elapsed=%s", self.last_refill.value, elapsed
                )

                if self.rate * elapsed >= 1:
                    self.last_refill.value = now
                    _logger.debug("Grants: elapsed=%s refill=%s", elapsed, now)
                    return

                _logger.debug("Sleeping")
                time.sleep(1 / self.rate)
                _logger.debug("Waked up")

    def __exit__(self, exc_type, exc, tb):
        return


def example_usage(task_id):
    from random import random

    with rate_limiter:
        print(f"Task {task_id}: Executing at {time.time() - start}")
        # if task_id % 5 == 0:
        #     raise Exception("test")
        time.sleep(random())
        print(f"Task {task_id}: Finish at {time.time() - start}")


def example_usage_wrapped(args):
    import logging

    try:
        return example_usage(args)
    except Exception:
        logging.error("", exc_info=True, stack_info=True)


def initialize(_rate_limiter):
    global rate_limiter
    rate_limiter = _rate_limiter


def main():
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

    logging.basicConfig(format="%(asctime)s %(processName)s %(message)s", level=logging.DEBUG)
    _logger.setLevel(logging.DEBUG)

    global start
    start = time.time()

    with multiprocessing.Manager() as manager:
        rate_limiter = Throttler(
            request_per_second=0.25, last_refill=manager.Value("d", 0.0), lock=manager.Lock()
        )

        with ProcessPoolExecutor(
            max_workers=5, initializer=initialize, initargs=(rate_limiter,)
        ) as executor:
            for _ in executor.map(example_usage_wrapped, range(50)):
                pass


if __name__ == "__main__":
    main()

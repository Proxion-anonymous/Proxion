import logging
import multiprocessing
import re
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import cast

import psycopg

import __main__

# -- Constants ---

LATEST_BLOCK = 18473542  # 2023-10-31 23:59:59 UTC

# --- Logging ---


class ProcessPoolLoggingFormatter(logging.Formatter):
    """Process pool workers are named "ForkPoolWorker-#" and "ForkProcess-#" by default, which is
    too long when the limit of comm in Linux is 15 characters."""

    DEFAULT_FORMAT = "%(asctime)s %(processName)-8s %(levelname)-8s %(name)s %(pathname)s:%(lineno)d:%(funcName)s: %(message)s"

    def __init__(self, fmt=DEFAULT_FORMAT, **kwargs):
        super().__init__(fmt=fmt, **kwargs)

    def format(self, record):
        record.processName = f"worker{record.processName.partition('-')[-1]}"
        return super().format(record)

    @classmethod
    def get_default_handler(cls, level=logging.INFO):
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(cls())
        return handler


# --- Database ---


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=str(Path.home() / "Documents/ProxyChecker/.postgres-socket"),
        dbname="proxychecker",
        user="proxychecker",
        password="proxychecker",
        autocommit=True,
    )


def copy_to(query: str, filename: str):
    with (
        cast(psycopg.Connection, __main__.db_connection).cursor() as cur,
        cur.copy(f"COPY ({query}) TO STDOUT (FORMAT CSV, HEADER)") as copy,
        open(filename, "wb") as f,
    ):
        for raw_row in copy:
            f.write(raw_row)


class QueryNoResultError(RuntimeError):
    pass


def fetchone(query, *params):
    row = cast(psycopg.Connection, __main__.db_connection).execute(query, params).fetchone()
    if row is None:
        raise QueryNoResultError(f'query="{query}" params={params}')
    return row[0] if len(row) == 1 else row


def get_today_tag() -> str:
    return datetime.today().strftime("%Y%m%d")


# -- Process Pool ---


def initialize_worker():
    set_process_name()
    signal.signal(signal.SIGALRM, timeout_handler)


def set_process_name():
    open("/proc/self/comm", "w").write(
        f"worker{multiprocessing.current_process().name.partition('-')[-1]}"[-15:]
    )


def timeout_handler(signum, frame):
    signal.alarm(0)
    raise TimeoutError()


def run_with_timeout(func, timeout=60, *args, **kwargs):
    signal.alarm(timeout)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)


# --- Ethereum Node ---


def get_rpc_host() -> str:
    return (
        subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                "erigon-rpcdaemon-1",
            ],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip("\n")
    )


# --- Solidity Compliation ---


def find_contract(dir: Path, name: str) -> Path:
    try:
        return next(dir.rglob(f"{name}.sol", case_sensitive=False))
    except StopIteration:
        pass

    for path in dir.rglob("*"):
        if path.is_file() and re.search(
            rf"(contract|library)\s+{re.escape(name)}", path.read_text()
        ):
            return path

    # if dir.exists():
    #     import logging
    #     import os
    #     logging.error(f"Failed to find {name} in {dir}, killing process tree {__main__._pid}")
    #     os.killpg(__main__._pid, signal.SIGTERM)

    raise FileNotFoundError(f"Cannot find {name} in {dir}")


# --- Study collisions ---


def right_align_strings(str1, str2):
    if str1 is None or str2 is None:
        return (str1, str2)
    max_length = max(len(str1), len(str2))
    aligned_str1 = f"{str1:>{max_length}}"
    aligned_str2 = f"{str2:>{max_length}}"
    return aligned_str1, aligned_str2

#!/usr/bin/env -S poetry run python3
import logging
import multiprocessing
import subprocess
import time
from pathlib import Path

import psycopg
from tqdm import tqdm

from tools.utils import connect, find_contract, initialize_worker

db_connection: psycopg.Connection


def select():
    with (
        connect() as conn,
        conn.execute(
            """
            SELECT address, name, compiler
            FROM verified_contracts a
            WHERE NOT EXISTS (SELECT 1 FROM uschunt_proxy_info WHERE address = a.address)
            """
        ) as cur,
    ):
        return cur.fetchall()


def process_row(row):
    addr, name, compiler = row
    try:
        process_row_unsafe(addr, name, compiler)

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.exception(f"Error processing {addr}", exc_info=True, stack_info=True)


def process_row_unsafe(addr, name, compiler):
    cwd = Path.home() / "Documents/ProxyChecker/.results/source/{addr[2:4]}/{addr}"
    contract_path = find_contract(cwd, name)
    output = error = None
    if compiler is None:
        compiler = "0.8.23,0.8.22,0.8.21,0.8.20,0.8.19,0.8.18,0.8.17,0.8.16,0.8.15,0.8.14,0.8.13,0.8.12,0.8.11,0.8.10,0.8.9,0.8.8,0.8.7,0.8.6,0.8.5,0.8.4,0.8.3,0.8.2,0.8.1,0.8.0,0.7.6,0.7.5,0.7.4,0.7.3,0.7.2,0.7.1,0.7.0,0.6.12,0.6.11,0.6.10,0.6.9,0.6.8,0.6.7,0.6.6,0.6.5,0.6.4,0.6.3,0.6.2,0.6.1,0.6.0,0.5.17,0.5.16,0.5.15,0.5.14,0.5.13,0.5.12,0.5.11,0.5.10,0.5.9,0.5.8,0.5.7,0.5.6,0.5.5,0.5.4,0.5.3,0.5.2,0.5.1,0.5.0,0.4.26,0.4.25,0.4.24,0.4.23,0.4.22,0.4.21,0.4.20,0.4.19,0.4.18,0.4.17,0.4.16,0.4.15,0.4.14,0.4.13,0.4.12,0.4.11,0.4.10,0.4.9,0.4.8,0.4.7,0.4.6,0.4.5,0.4.4,0.4.3,0.4.2,0.4.1,0.4.0"
    try:
        proc = subprocess.run(
            [
                Path.home() / "Documents/ProxyChecker/USCHunt/.venv/bin/slither",
                "--no-fail-pedantic",
                "--detect",
                "proxy-patterns",
                "--solc-solcs-select",
                compiler,
                contract_path,
            ],
            cwd=cwd,
            check=True,
            capture_output=True,
            timeout=60,
        )
        output = proc.stderr.decode()

    except subprocess.TimeoutExpired:
        error = "timeout"

    except subprocess.CalledProcessError as e:
        error = f"cd '{cwd}'; " + " ".join(f"'{x}'" for x in e.cmd) + "\n" + e.stderr.decode()

    is_proxy = is_upgradeable = None
    if output:
        is_upgradeable = (
            "is an upgradeable proxy" in output or "may be an upgradeable proxy" in output
        )
        is_proxy = "is a proxy" in output or is_upgradeable

    db_connection.execute(
        """
        INSERT INTO uschunt_proxy_info
        (address, is_proxy, is_upgradeable, output, error)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (address) DO NOTHING
        """,
        (addr, is_proxy, is_upgradeable, output, error),
    )


def initialize():
    initialize_worker()

    global db_connection
    db_connection = connect()


def main():
    tm = time.time()
    rows = select()
    print(f"Found {len(rows)} addresses after {time.time() - tm:.2f}s")

    with multiprocessing.Pool(processes=24, initializer=initialize) as pool:
        for _ in tqdm(
            pool.imap_unordered(process_row, rows),
            total=len(rows),
            mininterval=5,
        ):
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env -S poetry run python3
import logging
import multiprocessing
import pickle
import time
from pathlib import Path

import psycopg
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
from tqdm import tqdm

from proxion.AdvCheck import find_selectors
from tools.utils import (
    LATEST_BLOCK,
    QueryNoResultError,
    connect,
    fetchone,
    get_rpc_host,
    initialize_worker,
)

TIMEOUT = 30

db_connection: psycopg.Connection
explorer: EthereumExplorerRPC


def select():
    CACHE_FILE = Path("proxy-info.pickle")
    if CACHE_FILE.exists():
        return pickle.load(open(CACHE_FILE, "rb"))

    with connect() as conn:
        with conn.execute(
            """
            SELECT
                address,
                CASE WHEN current_implementation IS NOT NULL
                    THEN old_implementations || current_implementation
                    ELSE old_implementations
                END AS impls
            FROM contracts_all_latest a
            JOIN proxy_info b USING (address, block_number)
            """,
        ) as cur:
            return cur.fetchall()


def process(row):
    addr, impls = row
    try:
        process_unsafe(addr, impls)

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s", addr, exc_info=True, stack_info=True)


def process_unsafe(addr, impls):
    hash1 = get_bytecode_hash(addr)
    if hash1 is None:
        return
    sigs = get_signatures(addr, hash1)
    for impl in impls:
        try:
            hash2 = get_bytecode_hash(impl)
        except QueryNoResultError:
            # logic address newer than 2023-10-31, ignore
            continue
        if hash2 is None:
            continue
        sigs2 = get_signatures(impl, hash2)
        colliding = sigs & sigs2
        db_connection.execute(
            """
            INSERT INTO function_collisions (address1, address2, colliding_signatures)
            VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
            """,
            (addr, impl, list(colliding)),
        )


def get_signatures(addr: str, bytecode_hash: str) -> set[str]:
    try:
        sigs = set(
            fetchone(
                "SELECT signatures FROM function_signatures WHERE bytecode_hash = %s",
                bytecode_hash,
            )
        )
    except QueryNoResultError:
        sigs = find_selectors(addr, explorer, LATEST_BLOCK)
        db_connection.execute(
            "INSERT INTO function_signatures (bytecode_hash, signatures, address) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (bytecode_hash, list(sigs), addr),
        )
    return sigs


def get_bytecode_hash(addr) -> str | None:
    return fetchone("SELECT bytecode_hash FROM bytecode_hash_latest WHERE address = %s", addr)


def initialize():
    initialize_worker()

    global db_connection, explorer
    db_connection = connect()
    explorer = EthereumExplorerRPC(get_rpc_host())


def main():
    tm = time.time()
    rows = select()
    print(f"Found {len(rows)} addresses after {time.time() - tm:.2f}s")

    with multiprocessing.Pool(12, initializer=initialize) as pool:
        for _ in tqdm(
            pool.imap_unordered(process, rows, chunksize=10000),
            total=len(rows),
            mininterval=5,
        ):
            pass


if __name__ == "__main__":
    main()

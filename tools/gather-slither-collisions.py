#!/usr/bin/env -S poetry run python3
import logging
import multiprocessing.pool
import pickle
import time
from itertools import zip_longest
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from tqdm import tqdm

from tools.utils import QueryNoResultError, connect, fetchone

db_connection: psycopg.Connection


def select():
    CACHE_FILE = Path("proxy-info.pickle")
    if CACHE_FILE.exists():
        return pickle.load(open(CACHE_FILE, "rb"))


def process_row(row):
    addr, impls = row
    try:
        process_unsafe(addr, impls)

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.exception(f"Error processing {addr}", stack_info=True, exc_info=True)


def process_unsafe(addr, impls):
    hash1 = get_bytecode_hash(addr)
    if hash1 is None:
        return

    try:
        sigs1 = get_signatures(hash1)
        vars1 = get_var_order(hash1)
    except QueryNoResultError:
        return

    for impl in impls:
        try:
            hash2 = get_bytecode_hash(impl)
        except QueryNoResultError:
            # logic address newer than 2023-10-31, ignore
            continue
        if hash2 is None:
            continue

        db_connection.execute(
            """INSERT INTO bytecode_pairs (bytecode_hash1, bytecode_hash2)
            VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (hash1, hash2),
        )

        try:
            sigs2 = get_signatures(hash2)
            vars2 = get_var_order(hash2)
        except QueryNoResultError:
            continue

        colliding = {k: (sigs1[k], sigs2[k]) for k in sigs1.keys() & sigs2.keys()}
        db_connection.execute(
            """
            INSERT INTO slither_function_collisions (bytecode_hash1, bytecode_hash2, colliding_signatures)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (hash1, hash2, Jsonb(colliding)),
        )

        colliding = [
            (i, x, y)
            for i, (x, y) in enumerate(zip_longest(vars1, vars2))
            if x is not None and y is not None and x.partition(".")[-1] != y.partition(".")[-1]
        ]
        db_connection.execute(
            """
            INSERT INTO slither_storage_collisions (bytecode_hash1, bytecode_hash2, colliding_vars)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (hash1, hash2, Jsonb(colliding)),
        )


def right_align_strings(str1, str2):
    if str1 is None or str2 is None:
        return (str1, str2)
    max_length = max(len(str1), len(str2))
    aligned_str1 = f"{str1:>{max_length}}"
    aligned_str2 = f"{str2:>{max_length}}"
    return aligned_str1, aligned_str2


def get_signatures(bytecode_hash) -> dict:
    return fetchone(
        "SELECT signatures FROM slither_signatures WHERE bytecode_hash = %s", bytecode_hash
    )


def get_var_order(bytecode_hash) -> list:
    return fetchone(
        "SELECT var_order FROM slither_var_order WHERE bytecode_hash = %s", bytecode_hash
    )


def get_bytecode_hash(addr) -> str | None:
    return fetchone("SELECT bytecode_hash FROM bytecode_hash_latest WHERE address = %s", addr)


def initialize():
    global db_connection
    db_connection = connect()


def main():
    tm = time.time()
    rows = select()
    print(f"Found {len(rows)} addresses after {time.time() - tm:.2f}s")

    with multiprocessing.Pool(12, initializer=initialize) as pool:
        for _ in tqdm(
            pool.imap_unordered(process_row, rows, chunksize=10000),
            total=len(rows),
            mininterval=5,
        ):
            pass


if __name__ == "__main__":
    main()

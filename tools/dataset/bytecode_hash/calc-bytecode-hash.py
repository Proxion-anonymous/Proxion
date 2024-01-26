#!/usr/bin/env -S poetry run python3
from __future__ import annotations

import pickle
import subprocess
import time
from multiprocessing.pool import Pool
from pathlib import Path
from typing import TYPE_CHECKING, cast

import psycopg
from hexbytes import HexBytes
from tqdm import tqdm
from web3 import HTTPProvider, Web3
from web3.types import Address

from tools.utils import connect, initialize_worker

if TYPE_CHECKING:
    from web3.eth import Eth


LATEST_BLOCK = 18473542  # 2023-10-31 23:59:59 UTC

NULL_HASH = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
assert NULL_HASH == Web3.keccak(b"").hex()


db_connection: psycopg.Connection
w3_client: Eth


def select() -> list[tuple[Address, int]]:
    CACHE_FILE = Path("contracts_all_unique.pickle")
    if CACHE_FILE.exists():
        return pickle.load(open(CACHE_FILE, "rb"))

    with connect() as conn:
        with conn.execute(
            """
            SELECT address, block_number FROM contracts_all_unique a
            WHERE NOT EXISTS
            (SELECT 1 FROM bytecode_hash WHERE address = a.address AND block_number = a.block_number)
            OR NOT EXISTS
            (SELECT 1 FROM bytecode_hash_latest WHERE address = a.address)
            """
        ) as cur:
            return cur.fetchall()


def process_row(row: tuple[Address, int]):
    addr, block_number = row
    if (
        db_connection.execute(
            "SELECT 1 FROM bytecode_hash WHERE address = %s AND block_number = %s",
            (addr, block_number),
        ).fetchone()
        and db_connection.execute(
            "SELECT 1 FROM bytecode_hash_latest WHERE address = %s", (addr,)
        ).fetchone()
    ):
        return

    match code := w3_client.get_code(cast(Address, HexBytes(addr)), block_number):
        case b"":
            code_hash = None
        case _:
            code_hash = Web3.keccak(code).hex()

    match code_latest := w3_client.get_code(cast(Address, HexBytes(addr)), LATEST_BLOCK):
        case b"":
            code_hash_latest = None
        case _ if code_latest == code:
            code_hash_latest = code_hash
        case _:
            code_hash_latest = Web3.keccak(code_latest).hex()

    db_connection.execute(
        """
        INSERT INTO bytecode_hash
        (address, block_number, bytecode_hash)
        VALUES (%s, %s, %s)
        ON CONFLICT (address, block_number) DO NOTHING
        """,
        (addr, block_number, code_hash),
    )
    db_connection.execute(
        """
        INSERT INTO bytecode_hash_latest
        (address, bytecode_hash)
        VALUES (%s, %s)
        ON CONFLICT (address) DO NOTHING
        """,
        (addr, code_hash_latest),
    )


def initialize():
    initialize_worker()

    global db_connection, w3_client
    db_connection = connect()
    proc = subprocess.run(
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
    rpc_address = proc.stdout.decode().strip("\n")
    w3_client = Web3(HTTPProvider(f"http://{rpc_address}:8545"), middlewares=[]).eth


def main():
    tm = time.time()
    rows = select()
    print(f"Found {len(rows)} contracts after {time.time() - tm:.2f} seconds")

    with Pool(initializer=initialize) as pool:
        for _ in tqdm(
            pool.imap_unordered(process_row, rows, chunksize=100),
            total=len(rows),
            mininterval=5,
        ):
            pass


if __name__ == "__main__":
    main()

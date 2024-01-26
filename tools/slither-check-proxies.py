#!/usr/bin/env -S poetry run python3
from __future__ import annotations

import json
import logging.handlers
import multiprocessing
import pickle
import re
import signal
import time
from argparse import ArgumentParser, Namespace
from ctypes import c_double
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import psycopg
from psycopg.types.json import Jsonb
from tqdm import tqdm

from proxion.Check import SlitherCheckerLogic, SlitherCheckerProxy, SlitherResult
from proxion.Config import ETHERSCAN_APIKEY
from proxion.SourceCrawler import (
    ContractSourceMeta,
    SourceCrawler,
    SourceManager,
    extract_compiler_version,
)
from proxion.Throttler import Throttler
from tools.utils import (
    ProcessPoolLoggingFormatter,
    QueryNoResultError,
    connect,
    fetchone,
    find_contract,
    get_today_tag,
    initialize_worker,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from multiprocessing.managers import ValueProxy
    from threading import Lock


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

db_connection: psycopg.Connection
source_prefix: Path
crawler: SourceCrawler
_logger: Logger


def select() -> tuple[Iterable[tuple[str, list[str]]], int]:
    PROXY_INFO_FILENAME = Path("proxy-info.pickle")
    if PROXY_INFO_FILENAME.exists():
        proxy_info = pickle.load(open(PROXY_INFO_FILENAME, "rb"))
        return (proxy_info, len(proxy_info))
    cur = db_connection.execute(
        """
        SELECT
            address,
            CASE WHEN current_implementation IS NOT NULL
                THEN old_implementations || current_implementation
                ELSE old_implementations
            END AS impls
        FROM proxy_info
        WHERE is_proxy
        """
        # "SELECT address, ARRAY[]::text[] FROM contracts"
    )
    return (cur, cur.rowcount)


def process_row(row: tuple[str, list[str]]):
    addr, impls = row
    try:
        signal.alarm(600)
        process_proxy_pairs(addr, impls)

    except SystemExit:
        exit()

    except:  # noqa: E722 # pylint: disable=bare-except
        _logger.error("error for %s", addr, exc_info=True, stack_info=True)


def process_proxy_pairs(addr: str, impls: list[str]):
    proxy_src = get_source(addr)
    if proxy_src is None:
        return

    logic_srcs: list[Optional[ContractSourceMeta]] = [get_source(impl) for impl in impls]

    check(addr, impls, SourceManager(proxy=proxy_src, logics=logic_srcs))


def get_source(addr: str) -> Optional[ContractSourceMeta]:
    try:
        bytecode_hash = get_bytecode_hash(addr)
    except QueryNoResultError:
        # logic contract that is deployed after 2023-10-31, ignore it
        return None
    if bytecode_hash is None:
        return None

    if is_no_source(bytecode_hash):
        return None

    try:
        return get_source_meta_by_hash(bytecode_hash)
    except QueryNoResultError:
        if is_minimal_proxy(addr):
            set_no_source(bytecode_hash)
            return None
        src = crawler.download(addr, SourceManager.get_source_dir(source_prefix, addr))
        if src is None:
            set_no_source(bytecode_hash)
            return None
        set_source_meta(bytecode_hash, src.address, src.name, src.compiler_version)
        return src


def get_bytecode_hash(addr: str) -> str:
    bytecode_hash = fetchone(
        """SELECT bytecode_hash FROM bytecode_hash WHERE address = %s ORDER BY block_number DESC""",
        addr,
    )
    # assert bytecode_hash is not None
    return bytecode_hash


def is_minimal_proxy(addr: str) -> bool:
    is_minimal = fetchone(
        """SELECT erc_1167 FROM proxy_info WHERE address = %s ORDER BY block_number DESC""", addr
    )
    # None is considered as False
    return bool(is_minimal)


def get_source_meta_by_hash(bytecode_hash: str) -> Optional[ContractSourceMeta]:
    addr_s, name, compiler = fetchone(
        """
        SELECT address, name, compiler
        FROM verified_contracts
        WHERE bytecode_hash = %s
        """,
        bytecode_hash,
    )
    _logger.debug("hash=%s addr=%s name=%s compiler=%s", bytecode_hash, addr_s, name, compiler)
    srcdir = SourceManager.get_source_dir(source_prefix, addr_s)
    try:
        _logger.debug("Finding source for %s", addr_s)
        src = ContractSourceMeta(
            addr_s,
            name,
            find_contract(srcdir, name).relative_to(srcdir),
            srcdir,
            extract_compiler_version(compiler),
        )
        _logger.debug("Found source for %s: %s", addr_s, src)
        return src
    except FileNotFoundError:
        return crawler.download(addr_s, srcdir)


def set_source_meta(bytecode_hash: str, addr: str, name: str, compiler: Optional[str]) -> None:
    _logger.debug(
        "bytecode_hash=%s addr=%s name=%s compiler=%s", bytecode_hash, addr, name, compiler
    )
    db_connection.execute(
        """
        INSERT INTO verified_contracts
        (bytecode_hash, address, name, compiler, date_added)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (bytecode_hash, addr, name, compiler, get_today_tag()),
    )

    # then insert into source_address through:
    """
    INSERT INTO source_address
    (address, source_address, kind)
    SELECT t.address, s.address, 20231218
    FROM contracts_all_latest t
    JOIN bytecode_hash h USING (address, block_number)
    JOIN contract_sanctuary_by_hash s
    ON h.bytecode_hash = s.bytecode_hash
    AND h.bytecode_hash != '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470' -- empty bytecode
    AND s.id = 20231218
    ON CONFLICT (address) DO NOTHING
    """


def is_no_source(bytecode_hash: str) -> bool:
    try:
        fetchone("""SELECT 1 FROM no_source WHERE bytecode_hash = %s""", bytecode_hash)
        _logger.debug("hash %s no source", bytecode_hash)
        return True
    except QueryNoResultError:
        return False


def set_no_source(bytecode_hash: str) -> None:
    db_connection.execute(
        """
        INSERT INTO no_source (bytecode_hash) VALUES (%s)
        ON CONFLICT DO NOTHING
        """,
        (bytecode_hash,),
    )


def check(addr: str, impls: list[str], srcmgr: SourceManager) -> None:
    # addr and impls are the addresses to check
    # while srcmgr.proxy and srcmgr.logics are their sources
    # srcmgr.proxy.address may be different from addr
    # similarly, srcmgr.logics[i].address may be different from impls[i]
    proxy = srcmgr.proxy
    logics = srcmgr.logics

    hash1 = get_bytecode_hash(addr)

    if not proxy:
        return

    for impl, logic in zip(impls, logics):
        if not logic:
            continue

        hash2 = get_bytecode_hash(impl)

        try:
            vars1 = get_vars(hash1)
            sigs1 = get_signatures(hash1)
            vars2 = get_vars(hash2)
            sigs2 = get_signatures(hash2)

        except QueryNoResultError:
            _logger.debug(
                "Checking proxy %s(%s) and logic %s(%s)", addr, proxy.address, impl, logic.address
            )
            set_slither_result(SlitherCheckerProxy(proxy, logic).check(timeout=180), hash1, hash2)
            vars1 = get_vars(hash1)
            sigs1 = get_signatures(hash1)
            vars2 = get_vars(hash2)
            sigs2 = get_signatures(hash2)

        if vars1 is None or vars2 is None or sigs1 is None or sigs2 is None:
            continue

        colliding_vars = [
            (i, x, y)
            for i, (x, y) in enumerate(zip(vars1, vars2))
            if x is not None and y is not None and x.partition(".")[-1] != y.partition(".")[-1]
        ]
        db_connection.execute(
            """
            INSERT INTO slither_storage_collisions
            (bytecode_hash1, bytecode_hash2, colliding_vars)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (hash1, hash2, Jsonb(colliding_vars)),
        )

        colliding_sigs = {k: (sigs1[k], sigs2[k]) for k in sigs1.keys() & sigs2.keys()}
        db_connection.execute(
            """
            INSERT INTO slither_function_collisions
            (bytecode_hash1, bytecode_hash2, colliding_signatures)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (hash1, hash2, Jsonb(colliding_sigs)),
        )


def get_vars(bytecode_hash: str) -> list[str]:
    return fetchone(
        """SELECT vars FROM slither_vars WHERE bytecode_hash = %s""",
        bytecode_hash,
    )


def get_signatures(bytecode_hash: str) -> dict[str, str]:
    return fetchone(
        """SELECT signatures FROM slither_signatures WHERE bytecode_hash = %s""",
        bytecode_hash,
    )


def set_slither_result(sr: SlitherResult, hash1, hash2):
    _logger.debug("%s, %s", sr.address1, sr.address2)
    var_order = extract_var_order(sr.output)
    signatures = extract_signatures(sr.output)
    db_connection.execute(
        """
        INSERT INTO slither_result
        (bytecode_hash1, bytecode_hash2, example_address1, example_address2,
         vars, signatures, collisions, error, output_text, output_json, type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            hash1,
            hash2,
            sr.address1,
            sr.address2,
            Jsonb(var_order) if var_order is not None else None,
            Jsonb(signatures) if signatures is not None else None,
            sr.collisions,
            sr.error,
            sr.output,
            sr.json if sr.json else None,
            sr.type == SlitherCheckerLogic.__name__,
        ),
    )
    db_connection.execute(
        """
        INSERT INTO slither_signatures
        (bytecode_hash, example_address, signatures)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            hash1,
            sr.address1,
            Jsonb(signatures["proxy"]) if signatures else None,
        ),
    )
    db_connection.execute(
        """
        INSERT INTO slither_signatures
        (bytecode_hash, example_address, signatures)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            hash2,
            sr.address2,
            Jsonb(signatures["implem"]) if signatures else None,
        ),
    )
    db_connection.execute(
        """
        INSERT INTO slither_vars
        (bytecode_hash, example_address, vars)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            hash1,
            sr.address1,
            Jsonb(var_order["order2"]) if var_order else None,
        ),
    )
    db_connection.execute(
        """
        INSERT INTO slither_vars
        (bytecode_hash, example_address, vars)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            hash2,
            sr.address2,
            Jsonb(var_order["order1"]) if var_order else None,
        ),
    )


def extract_var_order(output: Optional[str]) -> Optional[dict]:
    return extract_any("var_order", output)


def extract_signatures(output: Optional[str]) -> Optional[dict]:
    return extract_any("signatures", output)


def extract_any(what: str, output: Optional[str]) -> Optional[dict]:
    if not output:
        return None
    m = re.search(rf"^{what}: (.*)$", output, re.MULTILINE)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def initialize(args: Namespace, last_refill: "ValueProxy[float]", lock: "Lock"):
    initialize_worker()

    global db_connection, source_prefix, crawler, _logger
    db_connection = connect()
    source_prefix = args.source_prefix
    crawler = SourceCrawler(
        args,
        api_key=ETHERSCAN_APIKEY,
        throttler=Throttler(
            request_per_second=5,
            last_refill=last_refill,
            lock=lock,
        ),
    )
    _logger = logging.getLogger(__name__)
    _logger.addHandler(ProcessPoolLoggingFormatter.get_default_handler(logging.INFO))


def interactive():
    from IPython.terminal.embed import InteractiveShellEmbed

    global db_connection, source_prefix, crawler, _logger
    db_connection = connect()
    source_prefix = Path("source")
    crawler = SourceCrawler(
        Namespace(fetch_source_timeout=5, fetch_source_retry=3),
        api_key=ETHERSCAN_APIKEY,
        throttler=Throttler(
            request_per_second=5,
            last_refill=multiprocessing.Value(c_double, 0.0),
            lock=multiprocessing.Lock(),
        ),
    )
    _logger = logging.getLogger(__name__)
    shell = InteractiveShellEmbed()
    shell()
    exit()


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger(__name__).addHandler(
        ProcessPoolLoggingFormatter.get_default_handler(logging.INFO)
    )
    logging.getLogger("proxy_checker").addHandler(
        ProcessPoolLoggingFormatter.get_default_handler(logging.INFO)
    )

    # interactive()

    parser = ArgumentParser()
    parser.add_argument("source_prefix", type=Path)
    parser.add_argument("--fetch-source-timeout", type=int, default=20)
    parser.add_argument("--fetch-source-retry", type=int, default=3)
    args = parser.parse_args()

    global db_connection
    db_connection = connect()

    tm = time.time()
    rows, nrows = select()
    print(f"Found {nrows} addresses after {time.time() - tm:.2f}s")

    with (
        multiprocessing.Manager() as manager,
        multiprocessing.Pool(
            24,
            initializer=initialize,
            initargs=(
                args,
                manager.Value(c_double, 0.0),
                manager.Lock(),
            ),
        ) as pool,
    ):
        for _ in tqdm(
            pool.imap_unordered(process_row, rows, chunksize=100),
            total=nrows,
            mininterval=5,
        ):
            pass


if __name__ == "__main__":
    main()

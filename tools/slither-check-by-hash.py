#!/usr/bin/env -S poetry run python3
import logging
import multiprocessing
import pickle
from itertools import pairwise
from pathlib import Path

from tqdm import tqdm

from tools.utils import connect

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def select():
    PROXY_INFO_FILENAME = Path("proxy-info.pickle")
    if PROXY_INFO_FILENAME.exists():
        return pickle.load(open(PROXY_INFO_FILENAME, "rb"))
    with connect() as conn:
        with conn.execute(
            """
            SELECT address, implementations, current_implementation
            FROM contracts_all_latest a
            JOIN proxy_info b USING (address, block_number)
            WHERE is_proxy
            """,
            # WITH t AS (
            #     SELECT DISTINCT address, UNNEST(implementations || current_implementation) AS laddr
            #     FROM contracts_all_latest a
            #     JOIN proxy_info b USING (address, block_number)
            #     WHERE is_proxy
            # )
            # SELECT t.address, s1.address, s1.name, s1.compiler,
            #     ARRAY_AGG(t.laddr) AS laddr,
            #     ARRAY_AGG(s2.address) AS laddr,
            #     ARRAY_AGG(s2.name) AS lname,
            #     ARRAY_AGG(s2.compiler) AS lcompiler
            # FROM t
            # JOIN bytecode_hash_latest h1 ON t.address = h1.address
            # JOIN contract_sanctuary_by_hash s1 ON h1.bytecode_hash = s1.bytecode_hash
            # JOIN bytecode_hash_latest h2 ON t.laddr = h2.address
            # JOIN contract_sanctuary_by_hash s2 ON h2.bytecode_hash = s2.bytecode_hash
            # GROUP BY t.address, s1.address, s1.name, s1.compiler
            # ---
            # AND (
            #     NOT EXISTS
            #     (SELECT 1 FROM slither_result_all_var WHERE address1 = a.address)
            #     OR NOT EXISTS
            #     (SELECT 1 FROM slither_result_all_func WHERE address1 = a.address)
            # )
        ) as cur:
            return cur.fetchall()


def process(row):
    addr, impls = row
    impls = list(set(impls))
    try:
        logging.debug("Processing %s and implementations %s", addr, impls)

        addr_s = get_source_address(addr)
        if addr_s is None:
            address_have_no_source_both(addr)
            return

        var_order_proxy = get_var_order_proxy(addr_s)
        if not var_order_proxy:
            address_have_no_source_var(addr)

        signatures_proxy = get_signatures_proxy(addr_s)
        if not signatures_proxy:
            address_have_no_source_func(addr)

        var_order_impls = {}
        signatures_impls = {}
        for impl in impls:
            impl_s = get_source_address(impl)
            if not impl_s:
                address_have_no_source_both(addr, impl)
                continue

            var_order_impls[impl] = get_var_order_impl(impl_s)
            if not var_order_impls[impl]:
                address_have_no_source_var(addr, impl)

            signatures_impls[impl] = get_signatures_impl(impl_s)
            if not signatures_impls[impl]:
                address_have_no_source_func(addr, impl)

        for impl in impls:
            storage_collision = check_storage_collision(var_order_proxy, var_order_impls.get(impl))
            function_collision = check_function_collision(
                signatures_proxy, signatures_impls.get(impl)
            )
            db_connection.execute(
                """
                INSERT INTO slither_result_all_var
                (address1, address2, type, storage_collision)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (address1, address2) DO NOTHING
                """,
                (addr, impl, False, storage_collision),
            )
            db_connection.execute(
                """
                INSERT INTO slither_result_all_func
                (address1, address2, function_collision)
                VALUES (%s, %s, %s)
                ON CONFLICT (address1, address2) DO NOTHING
                """,
                (addr, impl, function_collision),
            )

        for impl1, impl2 in pairwise(impls):
            storage_collision = check_storage_collision(
                var_order_impls.get(impl1), var_order_impls.get(impl2)
            )
            db_connection.execute(
                """
                INSERT INTO slither_result_all_var
                (address1, address2, type, storage_collision)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (address1, address2) DO NOTHING
                """,
                (impl1, impl2, True, storage_collision),
            )

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s", addr, exc_info=True, stack_info=True)


def get_var_order_proxy(addr_s):
    row = db_connection.execute(
        """SELECT var_order FROM slither_result WHERE address1 = %s""", (addr_s,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]["order2"]


def get_var_order_impl(impl_s):
    row = db_connection.execute(
        """SELECT var_order FROM slither_result WHERE address2 = %s""", (impl_s,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]["order1"]


def get_signatures_proxy(addr_s):
    row = db_connection.execute(
        """SELECT signatures FROM slither_result_func WHERE address1 = %s""", (addr_s,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]["proxy"]


def get_signatures_impl(impl_s):
    row = db_connection.execute(
        """SELECT signatures FROM slither_result_func WHERE address2 = %s""", (impl_s,)
    ).fetchone()
    if not row or not row[0]:
        return None
    return row[0]["implem"]


def address_have_no_source_both(addr, addr2=ZERO_ADDRESS):
    address_have_no_source_var(addr, addr2)
    address_have_no_source_func(addr, addr2)


def address_have_no_source_var(addr, addr2=ZERO_ADDRESS):
    return
    db_connection.execute(
        """
        INSERT INTO slither_result_all_var
        (address1, address2, type, storage_collision)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (address1, address2) DO NOTHING
        """,
        (addr, addr2, None, None),
    )


def address_have_no_source_func(addr, addr2=ZERO_ADDRESS):
    return
    db_connection.execute(
        """
        INSERT INTO slither_result_all_func
        (address1, address2, function_collision)
        VALUES (%s, %s, %s)
        ON CONFLICT (address1, address2) DO NOTHING
        """,
        (addr, addr2, None),
    )


def check_storage_collision(var_order1, var_order2):
    if not var_order1 or not var_order2:
        return None
    return any(a.partition(".")[-1] != b.partition(".")[-1] for a, b in zip(var_order1, var_order2))


def check_function_collision(signatures1, signatures2):
    if not signatures1 or not signatures2:
        return None
    return bool(set(signatures1) & set(signatures2))


def get_source_address(address):
    res = db_connection.execute(
        """
        SELECT b.address
        FROM bytecode_hash_latest a
        JOIN contract_sanctuary_by_hash b USING (bytecode_hash)
        WHERE a.address = %s
        AND a.bytecode_hash != %s
        """,
        (address, "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
    ).fetchone()
    logging.debug("Source address for %s is %s", address, res)
    if not res:
        return None
    return res[0]


def initializer():
    global db_connection
    db_connection = connect()


def main():
    with multiprocessing.Pool(
        int(multiprocessing.cpu_count() * 1.1), initializer=initializer
    ) as pool:
        rows = select()
        print(f"Found {len(rows)} addresses to check")

        for _ in tqdm(pool.imap_unordered(process, rows), total=len(rows), mininterval=5):
            pass


if __name__ == "__main__":
    main()

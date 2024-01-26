import logging
import multiprocessing
import os.path
import signal
import traceback
from typing import Optional

import psycopg
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
from tqdm import tqdm

from proxion.AdvCheck import BackwardAnalyzer
from tools.utils import LATEST_BLOCK, run_with_timeout

TIMEOUT = 30


def connect():
    return psycopg.connect(
        dbname="proxychecker",
        user="proxychecker",
        password="proxychecker",
        host=os.path.join(os.getcwd(), "../.postgres-socket"),
        autocommit=True,
    )


def select():
    with connect() as conn:
        with conn.execute(
            """
            SELECT address, impl
            FROM (
                SELECT DISTINCT address, UNNEST(implementations || current_implementation) AS impl
                FROM contracts_all_latest a
                JOIN proxy_info_latest b USING (address)
                WHERE is_proxy
            ) c
            WHERE (
                NOT EXISTS
                (SELECT 1 FROM storage_access_latest WHERE address = c.address)
                OR NOT EXISTS
                (SELECT 1 FROM storage_access_latest WHERE address = c.impl)
            )
            """,
        ) as cur:
            return cur.fetchall()


def process(row):
    addr, impl = row
    try:
        slots_r, slots_w = run_with_timeout(
            BackwardAnalyzer(addr, explorer, LATEST_BLOCK).find_storage_access
        )
        error = None
    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s proxy", addr, exc_info=True, stack_info=True)
        slots_r = slots_w = None
        error = traceback.format_exc()

    try:
        l_slots_r, l_slots_w = run_with_timeout(
            BackwardAnalyzer(impl, explorer, LATEST_BLOCK).find_storage_access
        )
        l_error = None
    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s logic", addr, exc_info=True, stack_info=True)
        l_slots_r = l_slots_w = None
        l_error = traceback.format_exc()

    def intersect(a: Optional[set], b: Optional[set]) -> Optional[list]:
        return list(a & b) if a is not None and b is not None else None

    def to_list(a: Optional[set]) -> Optional[list]:
        return list(a) if a is not None else None

    try:
        slots_rr = intersect(slots_r, l_slots_r)
        slots_rw = intersect(slots_r, l_slots_w)
        slots_wr = intersect(slots_w, l_slots_r)
        slots_ww = intersect(slots_w, l_slots_w)
        slots_r = to_list(slots_r)
        slots_w = to_list(slots_w)
        l_slots_r = to_list(l_slots_r)
        l_slots_w = to_list(l_slots_w)

        with db_connection.transaction():
            db_connection.execute(
                """
                INSERT INTO storage_access_latest
                (address, slots_read, slots_write, error)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (address) DO NOTHING
                """,
                (addr, slots_r, slots_w, error),
            )
            db_connection.execute(
                """
                INSERT INTO storage_access_latest
                (address, slots_read, slots_write, error)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (address) DO NOTHING
                """,
                (impl, l_slots_r, l_slots_w, l_error),
            )
            if error or l_error:
                return
            db_connection.execute(
                """
                INSERT INTO storage_collision_latest
                (address1, address2, slots_rr, slots_rw, slots_wr, slots_ww)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (address1, address2) DO NOTHING
                """,
                (addr, impl, slots_rr, slots_rw, slots_wr, slots_ww),
            )

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s", addr, exc_info=True, stack_info=True)


def initializer():
    global db_connection, explorer
    db_connection = connect()

    # Run following to discover the address of the local RPC node container:
    # docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' erigon-rpcdaemon-1
    explorer = EthereumExplorerRPC("172.22.0.6")

    signal.signal(signal.SIGALRM, timeout_handler)


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

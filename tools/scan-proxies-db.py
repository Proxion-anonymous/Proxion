import json
import logging
import multiprocessing
import os.path

import psycopg
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
from tqdm import tqdm

from proxion.__main__ import proxy_check
from tools.utils import LATEST_BLOCK, connect, get_rpc_host, initialize_worker, run_with_timeout

TIMEOUT = 30

# Number of processes as a multiple of the number of CPU cores
PARALLEL_FACTOR = 1.1


def select(year):
    with connect() as conn:
        with conn.execute(
            """
            SELECT a.address, a.block_number FROM contracts_all_unique a
            LEFT JOIN proxy_info b
            ON a.address = b.address AND a.block_number = b.block_number
            WHERE b.address IS NULL
            OR error LIKE '%%RPC connection Error%%'
            OR error LIKE '%%Read timed out%%'
            OR error LIKE '%%KeyboardInterrupt%%'
            """
            # AND error != 'No bytecode!'
            # AND error != 'multi_delegatecall'
            # AND error NOT LIKE '%Contain inconcrete_opcode%'
            # AND error NOT LIKE '%TimeoutError%'
            # AND error NOT LIKE '%maximum recursion%'
            # AND error NOT LIKE '%KeyError%'
            # AND error NOT LIKE '%IndexError%'
            # AND error NOT LIKE '%OverflowError%'
            # AND error NOT LIKE '%StopIteration%'
            # AND error NOT LIKE '%NoneType%'
            # AND error NOT LIKE '%non-hexadecimal number%'
            # AND error NOT LIKE '%BytecodeEmptyException%'
        ) as cur:
            return cur.fetchall()


def process(row):
    addr, block = row
    try:
        result = run_with_timeout(proxy_check, addr, explorer, block)
        db_connection.execute(
            """
            INSERT INTO proxy_info
            (address, block_number, success, error, is_proxy, erc_1167, erc_1822, erc_1967,
             erc_2535, reason, implementation_slot, standard_implementation_slots,
             current_implementation, implementations)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (address, block_number) DO UPDATE SET
            address = EXCLUDED.address, block_number = EXCLUDED.block_number,
            success = EXCLUDED.success, error = EXCLUDED.error, is_proxy = EXCLUDED.is_proxy,
            erc_1167 = EXCLUDED.erc_1167, erc_1822 = EXCLUDED.erc_1822, erc_1967 = EXCLUDED.erc_1967,
            erc_2535 = EXCLUDED.erc_2535, reason = EXCLUDED.reason,
            implementation_slot = EXCLUDED.implementation_slot,
            standard_implementation_slots = EXCLUDED.standard_implementation_slots,
            current_implementation = EXCLUDED.current_implementation,
            implementations = EXCLUDED.implementations
            """,
            (
                addr,
                block,
                result.success,
                result.error,
                result.is_proxy,
                result.erc_1167,
                result.erc_1822,
                result.erc_1967,
                result.erc_2535,
                result.reason,
                result.implementation_slot,
                json.dumps(result.standard_implementation_slots),
                result.current_implementation,
                result.old_implementations,
            ),
        )

    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("Error on %s", addr, exc_info=True, stack_info=True)


def initializer():
    initialize_worker()

    global db_connection, explorer
    db_connection = connect()
    explorer = EthereumExplorerRPC(get_rpc_host())


def main():
    with multiprocessing.Pool(
        int(multiprocessing.cpu_count() * PARALLEL_FACTOR), initializer=initializer
    ) as pool:
        for year in range(2023, 2014, -1):
            addrs = select(year)
            print(f"Found {len(addrs)} addresses to check in {year}")

            for _ in tqdm(pool.imap_unordered(process, addrs), total=len(addrs), mininterval=5):
                pass
            break


if __name__ == "__main__":
    main()

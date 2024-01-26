#!/usr/bin/env -S poetry run python3
import time

from tools.utils import connect

conn = connect()


def create_table():
    conn.execute(
        """
        DROP TABLE IF EXISTS contracts_new;

        CREATE TABLE contracts_new (
            id SERIAL PRIMARY KEY,
            address character(42) NOT NULL,
            block integer NOT NULL,
            year smallint NOT NULL,
            bytecode_hash character(66),
            self_destructed boolean NOT NULL,
            UNIQUE (address, block)
        );
        """
    )


def timeit(func, *args, **kwargs):
    start = time.time()
    ret = func(*args, **kwargs)
    print(f"{func.__name__} took {time.time() - start:.2f}s")
    return ret


with timeit(
    conn.execute,
    """
    SELECT
        a.address,
        a.block_number,
        a.year,
        c.bytecode_hash,
        a.block_number != b.block_number OR c.bytecode_hash IS NULL OR d.bytecode_hash IS NULL AS self_destructed
    FROM contracts a
        JOIN bytecode_hash c USING (address, block_number)
        JOIN bytecode_hash_latest d USING (address)
        LEFT JOIN contracts_latest b USING (address)
    WHERE
        NOT EXISTS (SELECT 1 FROM contracts_new WHERE address = a.address AND block = a.block_number)
    """,
) as cur:
    while True:
        rows = timeit(cur.fetchmany, 100000)
        if not rows:
            break

        with conn.cursor() as cur_w:
            timeit(
                cur_w.executemany,
                """
                INSERT INTO contracts_new (address, block, year, bytecode_hash, self_destructed)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                rows,
            )

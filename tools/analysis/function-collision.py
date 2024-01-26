#!/usr/bin/env -S poetry run python3
import json
import sys

import psycopg

from tools.utils import connect

db_connection: psycopg.Connection


def select():
    with db_connection.execute(
        """
        SELECT a.address1, a.address2, b.signatures
        FROM slither_result_all_func a
        JOIN source_address s1 ON a.address1 = s1.address
        JOIN source_address s2 ON a.address2 = s2.address
        JOIN slither_result_func b ON b.address1 = s1.source_address AND b.address2 = s2.source_address
        WHERE a.function_collision = true
        """
    ) as cur:
        return cur.fetchall()


def main():
    global db_connection
    db_connection = connect()

    result = []
    for row in select():
        addr1, addr2, signatures = row
        result.append(
            {
                "contract1": get_etherscan_url(addr1),
                "contract2": get_etherscan_url(addr2),
                "signatures": outer_join_dict(signatures["proxy"], signatures["implem"]),
            }
        )
    print(f"Found {len(result)} collisions", file=sys.stderr)
    json.dump(result, sys.stdout, indent=2)


def get_etherscan_url(addr: str) -> str:
    return f"https://etherscan.io/address/{addr}#code"


def outer_join_dict(d1: dict, d2: dict) -> dict:
    return {key: (d1.get(key), d2.get(key)) for key in set(d1) | set(d2)}


if __name__ == "__main__":
    main()

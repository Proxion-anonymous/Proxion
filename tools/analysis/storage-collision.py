#!/usr/bin/env -S poetry run python3
import json
import sys
from itertools import zip_longest

import psycopg

from tools.utils import connect

db_connection: psycopg.Connection


def select():
    with db_connection.execute(
        """
        WITH t AS (
            SELECT address, UNNEST(old_implementations || current_implementation) AS impl, year
            FROM contracts_all_latest a
            JOIN proxy_info b USING (address, block_number)
            WHERE is_proxy
        )
        SELECT t.address, t.impl, t.year, h1.bytecode_hash, h2.bytecode_hash, a.storage_collision, b.var_order, (
            ARRAY_LENGTH(c.slots_rr, 1) IS NOT NULL
            OR ARRAY_LENGTH(c.slots_rw, 1) IS NOT NULL
            OR ARRAY_LENGTH(c.slots_wr, 1) IS NOT NULL
            OR ARRAY_LENGTH(c.slots_ww, 1) IS NOT NULL
        ) AS slot_collide
        FROM t
        JOIN slither_result_all_var a ON a.address1 = t.address AND a.address2 = t.impl
        JOIN bytecode_hash_latest h1 ON h1.address = t.address
        JOIN contract_sanctuary_by_hash s1 ON s1.bytecode_hash = h1.bytecode_hash
        JOIN bytecode_hash_latest h2 ON h2.address = t.impl
        JOIN contract_sanctuary_by_hash s2 ON s2.bytecode_hash = h2.bytecode_hash
        JOIN slither_result b ON b.address1 = s1.address AND b.address2 = s2.address
        JOIN storage_collision_latest c ON c.address1 = t.address AND c.address2 = t.impl
        """
    ) as cur:
        return cur.fetchall()


def main():
    global db_connection
    db_connection = connect()

    result = []
    result_by_hash = {}
    data = []
    for row in select():
        addr1, addr2, year, hash1, hash2, storage_collide, var_order, slot_collide = row
        # if (
        #     var_order["order2"]
        #     and (
        #         "masterCopy" in var_order["order2"][0] or "Doubler.owner" in var_order["order2"][0]
        #     )
        # ) or (var_order["order1"] and "ComptrollerLib" in var_order["order1"][0]):
        #     # exclude GnosisSafe wallets
        #     # exclude Doubler (empty bytecode, which is FP)
        #     continue

        result.append(
            {
                "contract1": get_etherscan_url(addr1),
                "contract2": get_etherscan_url(addr2),
                "year": year,
                "storage_collide_slither": storage_collide,
                "slot_collide_proxion": slot_collide,
                "vars": [
                    right_align_strings(x, y)
                    for x, y in zip_longest(var_order["order2"], var_order["order1"])
                ]
                if var_order
                else None,
            }
        )
        result_by_hash[(hash1, hash2)] = result[-1]
        data.append((addr1, addr2, str(year)))

    n_collisions = sum(
        1 for x in result if x["storage_collide_slither"] or x["slot_collide_proxion"]
    )
    print(f"Found {n_collisions} collisions out of {len(data)} pairs", file=sys.stderr)
    json.dump(result, open(f"b1-storage-and-slot-collisions-{len(result)}.json", "w"), indent=2)

    result_by_hash = list(result_by_hash.values())
    json.dump(
        result_by_hash,
        open(f"b1-storage-and-slot-collisions-groupby-hash-{len(result_by_hash)}.json", "w"),
        indent=2,
    )

    with open(f"b1-proxy-logic-pairs-{len(data)}.csv", "w") as f:
        f.write("address1,address2,year\n")
        for row in data:
            f.write(",".join(row) + "\n")


def right_align_strings(str1, str2):
    if str1 is None or str2 is None:
        return (str1, str2)
    max_length = max(len(str1), len(str2))
    aligned_str1 = f"{str1:>{max_length}}"
    aligned_str2 = f"{str2:>{max_length}}"
    return aligned_str1, aligned_str2


def get_etherscan_url(addr: str) -> str:
    return f"https://etherscan.io/address/{addr}#code"


if __name__ == "__main__":
    main()

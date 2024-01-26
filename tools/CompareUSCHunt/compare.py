#!/usr/bin/env -S poetry run python3
"""
Execute in python console:
c = importlib.reload(importlib.import_module('compare'))
Then access c.proxychecker and c.uschunt
"""
import json
from collections import defaultdict
from itertools import zip_longest

import psycopg
from semver import Version

from tools.utils import connect

# mapping from USCHunt result tag to ProxyChecker result tag
MAPPING = {
    "missing-variables": "missing-variables",
    "order-vars-proxy": "incorrect-variables-with-the-proxy",
    "order-vars-contracts": "incorrect-variables-with-the-v2",
    "extra-vars-proxy": "extra-variables-in-the-proxy",
    "extra-vars-v2": "extra-variables-in-the-v2",
    "function-shadowing": "functions-shadowing",
    "function-id-collision": "functions-ids-collisions",
}


def right_align_strings(str1, str2):
    if str1 is None or str2 is None:
        return (str1, str2)
    max_length = max(len(str1), len(str2))
    aligned_str1 = f"{str1:>{max_length}}"
    aligned_str2 = f"{str2:>{max_length}}"
    return aligned_str1, aligned_str2


def get_etherscan_url(addr: str) -> str:
    return f"https://etherscan.io/address/{addr}#code"


def outer_join_dict(d1: dict, d2: dict) -> dict:
    return {key: (d1.get(key, None), d2.get(key, None)) for key in set(d1) | set(d2)}


# ---

print("compare USCHunt")

var_collision = defaultdict(list)
func_collision = defaultdict(list)
with connect() as conn:
    with conn.execute(
        """
        SELECT address1, address2, year, compiler, collisions, var_order, signatures
        FROM contract_sanctuary_by_hash a
        JOIN slither_result b ON a.address = b.address1
        JOIN slither_result_func USING (address1, address2)
        JOIN proxy_info c USING (address, block_number)
        JOIN contracts_all_latest d USING (address, block_number)
        WHERE is_proxy AND compiler IS NOT NULL AND a.id < 20230000
        """
    ) as cur:
        for row in cur.fetchall():
            addr, addr2, year, compiler, collisions, var_order, signatures = row
            if Version.parse(compiler.removeprefix("v")) >= Version.parse("0.8.9"):
                continue

            var_collision[addr].append(
                {
                    "contract1": get_etherscan_url(addr),
                    "contract2": get_etherscan_url(addr2),
                    "year": year,
                    "is_collided_proxion": "incorrect-variables-with-the-proxy" in collisions,
                    "is_collided_uschunt": False,
                    "vars": [
                        right_align_strings(x, y)
                        for x, y in zip_longest(var_order["order2"], var_order["order1"])
                    ]
                    if var_order
                    else None,
                }
            )

            func_collision[addr].append(
                {
                    "contract1": get_etherscan_url(addr),
                    "contract2": get_etherscan_url(addr2),
                    "year": year,
                    "is_collided_proxion": "functions-shadowing" in collisions,
                    "is_collided_uschunt": False,
                    "signatures": outer_join_dict(signatures["proxy"], signatures["implem"])
                    if signatures
                    else None,
                }
            )

    with conn.execute(
        """
        SELECT address, vulns
        FROM uschunt_result
        """
    ) as cur:
        for row in cur.fetchall():
            addr, collisions = row
            if "order-vars-proxy" in collisions:
                for x in var_collision[addr]:
                    x["is_collided_uschunt"] = True
            if "function-shadowing" in collisions:
                for x in func_collision[addr]:
                    x["is_collided_uschunt"] = True

var_collision_flat = [y for x in var_collision.values() for y in x]
json.dump(
    var_collision_flat,
    open(f"a-compare-storage-collisions-{len(var_collision_flat)}.json", "w"),
    indent=2,
)

func_collision_flat = [y for x in func_collision.values() for y in x]
json.dump(
    func_collision_flat,
    open(f"a-compare-function-collisions-{len(func_collision_flat)}.json", "w"),
    indent=2,
)

print(
    f"(var) Both: {sum(x['is_collided_uschunt'] and x['is_collided_proxion'] for x in var_collision_flat)}"
)
print(
    f"(var) USCHunt - Proxion: {sum(x['is_collided_uschunt'] and not x['is_collided_proxion'] for x in var_collision_flat)}"
)
print(
    f"(var) Proxion - USCHunt: {sum(x['is_collided_proxion'] and not x['is_collided_uschunt'] for x in var_collision_flat)}"
)
print(
    f"(func) Both: {sum(x['is_collided_uschunt'] and x['is_collided_proxion'] for x in func_collision_flat)}"
)
print(
    f"(func) USCHunt - Proxion: {sum(x['is_collided_uschunt'] and not x['is_collided_proxion'] for x in func_collision_flat)}"
)
print(
    f"(func) Proxion - USCHunt: {sum(x['is_collided_proxion'] and not x['is_collided_uschunt'] for x in func_collision_flat)}"
)

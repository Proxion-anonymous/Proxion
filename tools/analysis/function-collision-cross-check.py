#!/usr/bin/env -S poetry run python3
import json

import pandas as pd

from tools.utils import connect


def ternary_logic(obj):
    return None if obj is None else bool(obj)


conn = connect()
res_json = []
res_csv = []
for (
    bytecode_hash1,
    bytecode_hash2,
    addr1,
    addr2,
    sigs1,
    sigs2,
    collision_proxion,
    collision_slither,
) in conn.execute(
    """
    SELECT
        year,
        bytecode_hash1, bytecode_hash2,
        c1.address, c2.address,
        s1.signatures, s2.signatures,
        a.colliding_signatures, b.colliding_signatures
    FROM function_collisions_by_hash a
    JOIN contract_sanctuary_by_hash c1 ON c1.bytecode_hash = a.bytecode_hash1
    JOIN contract_sanctuary_by_hash c2 ON c2.bytecode_hash = a.bytecode_hash2
    JOIN slither_signatures s1 ON s1.bytecode_hash = a.bytecode_hash1
    JOIN slither_signatures s2 ON s2.bytecode_hash = a.bytecode_hash2
    FULL JOIN slither_function_collisions b USING (bytecode_hash1, bytecode_hash2)
    """
).fetchall():
    res_json.append(
        {
            "bytecode_hash1": bytecode_hash1,
            "bytecode_hash2": bytecode_hash2,
            "example_contract1": f"https://etherscan.io/address/{addr1}#code",
            "example_contract2": f"https://etherscan.io/address/{addr2}#code",
            "colliding_signatures_slither": collision_slither,
            "colliding_signatures_proxion": collision_proxion,
            "functions1": sigs1,
            "functions2": sigs2,
        }
    )
    res_csv.append(
        (
            bytecode_hash1,
            bytecode_hash2,
            ternary_logic(collision_slither),
            ternary_logic(collision_proxion),
        )
    )
json.dump(res_json, open("b1-function-collision-cross-check.json", "w"), indent=2)
pd.DataFrame(
    res_csv,
    columns=["bytecode_hash1", "bytecode_hash2", "is_collision_slither", "is_collision_proxion"],
).replace({True: "t", False: "f"}).to_csv("b1-function-collision-cross-check.csv", index=False)

#!/usr/bin/env -S poetry run python3
import json
import sys
from itertools import zip_longest

from tools.utils import connect, right_align_strings

conn = connect()
res = [
    {
        "bytecode_hash1": bytecode_hash1,
        "bytecode_hash2": bytecode_hash2,
        "example_contract1": contract1,
        "example_contract2": contract2,
        "colliding_vars": colliding_vars,
        "vars": [right_align_strings(x, y) for x, y in zip_longest(vars1, vars2)],
    }
    for (
        contract1,
        contract2,
        bytecode_hash1,
        bytecode_hash2,
        colliding_vars,
        vars1,
        vars2,
    ) in conn.execute(
        """
        SELECT
            'https://etherscan.io/address/' || c1.address || '#code' AS contract1,
            'https://etherscan.io/address/' || c2.address || '#code' AS contract2,
            bytecode_hash1, bytecode_hash2,
            colliding_vars,
            s1.var_order, s2.var_order
        FROM "slither_storage_collisions" a
        JOIN contract_sanctuary_by_hash c1 ON c1.bytecode_hash = a.bytecode_hash1
        JOIN contract_sanctuary_by_hash c2 ON c2.bytecode_hash = a.bytecode_hash2
        JOIN slither_var_order s1 ON s1.bytecode_hash = a.bytecode_hash1
        JOIN slither_var_order s2 ON s2.bytecode_hash = a.bytecode_hash2
        WHERE jsonb_array_length(colliding_vars) > 0
        """
    ).fetchall()
]
json.dump(res, open(f"b1-storage-collisions-by-hash-{len(res)}.json", "w"), indent=2)

#!/usr/bin/env -S poetry run python3
import pandas as pd

from tools.utils import connect

conn = connect()
res = [
    (addr1, addr2, year, bytecode_hash1, bytecode_hash2, "t")
    for addr1, addr2, year, bytecode_hash1, bytecode_hash2 in conn.execute(
        """
        WITH t AS (
            SELECT address, UNNEST(old_implementations || current_implementation) AS impl, year
            FROM contracts_all_latest a
            JOIN proxy_info b USING (address, block_number)
        )
        SELECT t.address, t.impl, year, bytecode_hash1, bytecode_hash2
        FROM t
        JOIN bytecode_hash_latest h1 ON h1.address = t.address
        JOIN bytecode_hash_latest h2 ON h2.address = t.impl
        JOIN slither_storage_collisions a ON a.bytecode_hash1 = h1.bytecode_hash AND a.bytecode_hash2 = h2.bytecode_hash
        WHERE jsonb_array_length(colliding_vars) > 0
        """
    ).fetchall()
]
pd.DataFrame(
    res,
    columns=[
        "address1",
        "address2",
        "year",
        "bytecode_hash1",
        "bytecode_hash2",
        "is_storage_collision",
    ],
).to_csv(f"b1-storage-collisions-{len(res)}.csv", index=False)

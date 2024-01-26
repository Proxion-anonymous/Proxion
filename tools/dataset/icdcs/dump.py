#!/usr/bin/env -S poetry run python3
import psycopg

from tools.utils import connect, copy_to

conn = connect()

# copy_to(
#     """
#     WITH t AS (
#         SELECT address, UNNEST(old_implementations || current_implementation) AS impl
#         FROM contracts_all_latest a
#         JOIN proxy_info b USING (address, block_number)
#         WHERE is_proxy = 't'
#     )
#     SELECT
#         t.address AS address1,
#         h1.bytecode_hash AS bytecode_hash1,
#         t.impl AS address2,
#         h2.bytecode_hash AS bytecode_hash2,
#         a.colliding_signatures
#     FROM t
#     JOIN bytecode_hash_latest h1 ON h1.address = t.address
#     JOIN bytecode_hash_latest h2 ON h2.address = t.impl
#     JOIN function_collisions_by_hash a ON a.bytecode_hash1 = h1.bytecode_hash AND a.bytecode_hash2 = h2.bytecode_hash
#     WHERE ARRAY_LENGTH(a.colliding_signatures, 1) IS NOT NULL
#     """,
#     "b12-signature-collisions.csv",
# )

copy_to(
    """
    SELECT
        a.address,
        year,
        b.block_number as block,
        is_proxy,
        CASE
            WHEN current_implementation IS NOT NULL
            THEN old_implementations || current_implementation
            ELSE old_implementations
        END as implementations,
        erc_1167 as erc1167_minimal,
        erc_1822 as erc1822_UUPS,
        erc_1967 as erc1967_proxy_slots,
        erc_2535 as erc2535_diamond,
        implementation_slot,
        reason
    FROM contract_sanctuary_by_hash a
    JOIN contracts_all_latest b USING (address)
    JOIN proxy_info c ON c.address = b.address AND c.block_number = b.block_number
    """,
    "a.csv",
)

SELECT_PROXY_INFO = """
    SELECT
        address,
        year,
        block_number as block,
        is_proxy,
        CASE
            WHEN current_implementation IS NOT NULL
            THEN old_implementations || current_implementation
            ELSE old_implementations
        END as implementations,
        erc_1167 as erc1167_minimal,
        erc_1822 as erc1822_UUPS,
        erc_1967 as erc1967_proxy_slots,
        erc_2535 as erc2535_diamond,
        implementation_slot,
        reason
    FROM contracts_all_latest a
    JOIN proxy_info b USING (address, block_number)
    JOIN bytecode_hash_latest c USING (address)
"""

copy_to(
    f"""
    {SELECT_PROXY_INFO}
    JOIN source_address d USING (address)
    --WHERE bytecode_hash IS NOT NULL
    """,
    "b1a.csv",
)

copy_to(
    f"""
    {SELECT_PROXY_INFO}
    --WHERE bytecode_hash IS NOT NULL
    WHERE NOT EXISTS (SELECT 1 FROM source_address WHERE address = a.address)
    """,
    "b2a.csv",
)

copy_to(
    """
    SELECT address1, address2, slots_rr, slots_rw, slots_wr, slots_ww
    FROM storage_collision_latest
    WHERE ARRAY_LENGTH(slots_rr, 1) IS NOT NULL
    OR ARRAY_LENGTH(slots_rw, 1) IS NOT NULL
    OR ARRAY_LENGTH(slots_wr, 1) IS NOT NULL
    OR ARRAY_LENGTH(slots_ww, 1) IS NOT NULL
    """,
    "b2-slot-collisions.csv",
)

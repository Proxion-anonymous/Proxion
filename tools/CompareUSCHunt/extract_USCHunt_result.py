import json
from collections import defaultdict
from pathlib import Path

import psycopg


def connect():
    return psycopg.connect(
        dbname="proxychecker",
        user="proxychecker",
        password="proxychecker",
        host=Path(__file__).parent.parent.parent.joinpath(".postgres-socket").as_posix(),
        autocommit=True,
    )


data = json.load(
    open(
        Path(__file__).parent.parent.parent.joinpath(
            "USCHunt/study/data/slither-check-upgradeability_results/slither_check_upgradeability_results.json"
        )
    )
)["ethereum"]

rows = defaultdict(list)
for check_type, c in data.items():
    for contract in c["contracts"]:
        addr, _, name = contract.partition("_")
        addr = "0x" + addr.lower()
        name = name.removesuffix(".sol")
        rows[addr].append(check_type)

with connect() as conn:
    with conn.transaction():
        for addr, check_types in rows.items():
            conn.execute(
                """
                INSERT INTO USCHunt_result
                (address, vulns)
                VALUES (%s, %s)
                """,
                (addr, check_types),
            )

#!/usr/bin/env python3
import csv
import json

data = []
for line in open("smart-contract-sanctuary-ethereum/contracts/mainnet/contracts.json"):
    j = json.loads(line)
    month, day, year = map(int, j["date"].split("/"))
    data.append(
        {
            "name": j["name"],
            "balance": j["balance"],
            "compiler": j["compiler"],
            "address": j["address"].lower(),
            "block": None,
            "deploy_year": year,
            "settings": j["settings"],
            "txcount": j["txcount"],
            "dataset": "tintin",
        }
    )

for year in range(2017, 2023 + 1):
    with open(f"2017-2023_contract_data_feb/{year}.csv") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            data.append(
                {
                    "name": None,
                    "balance": None,
                    "compiler": None,
                    "address": row["address"].lower(),
                    "block": int(row["block_number"]),
                    "deploy_year": year,
                    "settings": None,
                    "txcount": None,
                    "dataset": "sampled",
                }
            )

with open("dataset.json", "w") as f:
    f.write("[")
    for d in data:
        f.write(json.dumps(d) + ",\n")
    f.seek(f.tell() - 2)  # remove last comma
    f.write("]")

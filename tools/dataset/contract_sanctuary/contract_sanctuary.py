"""Convert the Smart Contract Sanctuary dataset from JSON to CSV"""
import csv
import json
import re
import subprocess

j = [
    json.loads(l)
    for l in open("smart-contract-sanctuary-ethereum/contracts/mainnet/contracts.json")
    .read()
    .splitlines()
]
for x in j:
    x["address"] = x["address"].lower()

files = subprocess.run(
    "find smart-contract-sanctuary-ethereum/contracts/mainnet/ -mindepth 2 -type f",
    capture_output=True,
)
contracts: dict[str, str] = {}
for f in files.stdout.decode().splitlines():
    m = re.search(r"([0-9a-fA-F]{40})_(\w+)", f)
    if m:
        addr = "0x" + m.group(1).lower()
        name = m.group(2)
        if contracts.get(addr) in (None, "None"):
            contracts[addr] = name

with open("./contracts.csv", "w", newline="") as csv_file:
    csv_writer = csv.DictWriter(csv_file, fieldnames=list(j[0].keys()) + ["err"])
    csv_writer.writeheader()
    csv_writer.writerows(j)
    csv_writer.writerows([{"address": k, "name": v} for k, v in contracts.items()])

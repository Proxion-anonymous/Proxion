#!/usr/bin/env python3
import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass

avail_keys = (os.environ.get("KEYS") or "0 1 2 3 4 5 6 7").split(" ")


@dataclass
class Address:
    id: int
    year: int
    address: str


def get_output_name(year, address):
    return f"results/{year}/output/{address}"


async def process_address(id_, year, address, sem):
    async with sem:
        if not avail_keys:
            print("All keys run out of daily quota")
            exit(429)

        key = avail_keys[id_ % len(avail_keys)]
        print(f"{id_:>6}  {year}  {address}  {key}")

        output_name = get_output_name(year, address)
        with open(output_name, "w") as output_file:
            proc = await asyncio.create_subprocess_exec(
                "timeout",
                "-v",
                "30s",
                "poetry",
                "run",
                "python3",
                "usenix-second/ProxyChecker.py",
                address,
                env={"KEY": str(key)},
                stdout=output_file,
                stderr=output_file,
            )
            await proc.wait()

    result = open(output_name).read()
    process_result(result, year, address, key)


def process_result(result, year, address, key):
    f_not_proxy = f"results/{year}/data_not_proxy"
    f_collision = f"results/{year}/data_collision"
    f_minimal = f"results/{year}/data_minimal"
    f_proxy = f"results/{year}/data_proxy"
    f_no_bytecode = f"results/{year}/data_no_bytecode"
    f_0_error = f"results/{year}/data_zero_error"
    f_invalid = f"results/{year}/data_invalid"
    f_other = f"results/{year}/data_other"

    checks = []
    for check in [
        "functions-shadowing",
        "functions-ids-collisions",
        "incorrect-variables-with-the-v2",
        "incorrect-variables-with-the-proxy",
        "missing-variables",
    ]:
        if check in result:
            checks.append(check)

    if len(checks) > 0:
        with open(f_collision, "a") as f:
            f.write(address + " " + ",".join(checks) + "\n")

    elif "Not a proxy" in result:
        with open(f_not_proxy, "a") as f:
            f.write(address + "\n")

    elif "minimal proxy contract" in result:
        with open(f_minimal, "a") as f:
            f.write(address + "\n")

    elif "This is a proxy contract" in result:
        with open(f_proxy, "a") as f:
            f.write(address + "\n")

    elif "No bytecode!" in result:
        with open(f_no_bytecode, "a") as f:
            f.write(address + "\n")

    elif "KeyError:" in result:
        with open(f_0_error, "a") as f:
            f.write(address + "\n")

    elif "Error: invalid literal for int() with base 16:" in result:
        with open(f_invalid, "a") as f:
            f.write(address + "\n")

    else:
        print(result)
        if "RPC connection failure: 429 Too Many Requests" in result:
            try:
                avail_keys.remove(key)
                print(f"Depleted key {key} removed. Available: {avail_keys}")
            except ValueError:
                pass


async def main():
    data_name = sys.argv[1]
    if data_name.endswith(".csv"):
        addresses = [
            Address(id=int(row["id"]), year=int(row["year"]), address=row["address"])
            for row in csv.DictReader(open(data_name))
        ]

    elif data_name.endswith(".json"):
        addresses = [
            Address(id=i, year=int(x["date"].split("/")[-1]), address=x["address"])
            for i, x in enumerate(json.load(open(data_name)))
        ]

    else:
        print("Unknown data format")
        exit(1)

    tasks = []
    sem = asyncio.Semaphore(16)
    for addr in addresses:
        try:
            existing_output = open(get_output_name(addr.year, addr.address)).read()
        except FileNotFoundError:
            existing_output = ""

        if existing_output and (
            "RPC connection failure: 429 Too Many Requests" not in existing_output
            #  "error" not in existing_output.lower()
            #  or "KeyError" in existing_output
            #  or "Error: invalid literal for int() with base 16:" in existing_output
            #  or "timeout: sending signal TERM to command " in existing_output
            #  or "RPC connection failure: 403 Forbidden" in existing_output
            #  or "StopIteration" in existing_output
            #  or "TypeError: string indices must be integers" in existing_output
            #  or "OverflowError: cannot fit 'int' into an index-sized integer" in existing_output
            and "IndexError" not in existing_output
            #  or "slither compile error" in existing_output
        ):
            continue

        tasks.append(asyncio.create_task(process_address(addr.id, addr.year, addr.address, sem)))
    await asyncio.gather(*tasks)


asyncio.run(main())

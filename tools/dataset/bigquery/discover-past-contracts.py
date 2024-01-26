import asyncio
import json
import logging
import sys
from typing import Awaitable, Callable, TypeVar

from aiohttp import ClientSession, ClientTimeout
from google.cloud import bigquery
from more_itertools import batched
from web3 import AsyncHTTPProvider, AsyncWeb3, Web3

RPC_URL = "http://localhost:8545"

T = TypeVar("T")
U = TypeVar("U")


async def fmap_async(fn: Callable[[T], U], arg: Awaitable[T]):
    return fn(await arg)


async def main():
    logging.basicConfig(level=logging.DEBUG)

    # Require setting up Application Default Credentials for Google Cloud:
    # https://cloud.google.com/docs/authentication/provide-credentials-adc
    # Run Google Cloud CLI to setup: `gcloud auth application-default login`
    with bigquery.Client() as client:
        # Count contracts before 2023-10-31
        # query_job = client.query()
        # result = next(query_job.result())[0]
        # json.dump(json.loads(result), sys.stdout, indent=2)

        # Get all contract addresses before 2023-10-31
        query_job = client.query(
            """
            SELECT address, EXTRACT(YEAR FROM block_timestamp) as year, block_number
            FROM `bigquery-public-data.crypto_ethereum.contracts`
            WHERE bytecode IS NOT NULL
                AND bytecode != "0x"
                AND TIMESTAMP_TRUNC(block_timestamp, DAY) <= TIMESTAMP("2023-10-31")
            """
        )
        addrs = []
        for addr, year in query_job.result():
            addrs.append(
                {
                    "address": addr,
                    "year": year,
                }
            )

    # w3 = AsyncWeb3(AsyncHTTPProvider(RPC_URL))
    # latest_block_number = await w3.eth.block_number
    # for block_numbers in batched(range(latest_block_number), 16):
    #     tasks = []
    #     for block_number in block_numbers:
    #         tasks.append(asyncio.create_task(fmap_async(Web3.to_json, w3.eth.get_block(block_number))))
    #     results = await asyncio.gather(*tasks)
    #     json.dump(list(map(json.loads, results)), sys.stdout, indent=2)
    #     break


if __name__ == "__main__":
    asyncio.run(main())

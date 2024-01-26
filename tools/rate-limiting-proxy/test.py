#!/usr/bin/env python3
import logging
import multiprocessing

import requests

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)-5s %(message)s")


def get_etherscan(i):
    r = requests.get(
        "http://172.20.0.4",
        params={
            "module": "contract",
            "action": "getsourcecode",
            "address": "0x42bb6d1bb09959a61cc1d1d98ccc7902dfde3e92",
            "apiKey": "HZTCZR4GP8WXNADISZ9TWSPS3U71KC3C1S",
        },
        timeout=100,
    )
    logging.debug(f"{i} {r.status_code}")


with multiprocessing.Pool() as pool:
    for _ in pool.imap_unordered(get_etherscan, range(100)):
        pass

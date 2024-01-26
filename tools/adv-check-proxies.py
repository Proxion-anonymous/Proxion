#!/usr/bin/env python3
import argparse
import json
import logging
import multiprocessing
import os.path

from octopus.platforms.ETH.explorer import EthereumExplorerRPC

from proxion import Check, Config


def thread(proxy_addr, logic_addrs, dest):
    try:
        explorer = EthereumExplorerRPC(Config.RPC_HOST, Config.RPC_PORT, Config.RPC_TLS)
        results = Check.check_advanced(proxy_addr, logic_addrs, explorer)
        dest_file = os.path.join(dest, proxy_addr[2:4], f"{proxy_addr}.json")
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        json.dump(results, open(dest_file, "w"), indent=2)
    except:  # noqa: E722 # pylint: disable=bare-except
        logging.error("error for %s", proxy_addr, exc_info=True, stack_info=True)


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("address_file")
    parser.add_argument("proxy_info")
    parser.add_argument("destination")
    args = parser.parse_args()

    addresses = open(args.address_file).read().splitlines()
    proxy_info = json.load(open(args.proxy_info))
    with multiprocessing.Pool() as pool:
        pool.starmap(
            thread,
            (
                (
                    addr,
                    proxy_info[addr]["implementations"] if addr in proxy_info else [],
                    args.destination,
                )
                for addr in addresses
            ),
        )


if __name__ == "__main__":
    main()

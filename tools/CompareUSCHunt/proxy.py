#!/usr/bin/env -S poetry run python3
# fmt: off
import os

import pandas

from tools.utils import connect


def select(query):
    with conn.execute(query) as cur:
        return cur.fetchall()


df = pandas.read_csv(f"{os.getenv('HOME')}/Documents/ProxyChecker/.results/icdcs-data/a-smart-contract-sanctuary-329674.csv")
addrs = set(df["address"].tolist())
proxion_proxy = addrs & set(df[df["is_proxy"] == "t"]["address"].tolist())
proxion_nonproxy = addrs & set(df[df["is_proxy"] == "f"]["address"].tolist())

conn = connect()

uschunt_result = pandas.DataFrame(
    select("SELECT address, year, is_proxy, is_upgradeable FROM uschunt_proxy_info JOIN contracts_latest USING (address)"),
    columns=["address", "year", "is_proxy", "is_upgradeable"]
)
uschunt_result.replace({True: 't', False: 'f'}, inplace=True)

uschunt_proxy = addrs & set(uschunt_result[uschunt_result["is_proxy"] == "t"]["address"].tolist())
uschunt_nonproxy = addrs & set(uschunt_result[uschunt_result["is_proxy"] == "f"]["address"].tolist())

print(f"Proxion (+) {len(proxion_proxy)} (-) {len(proxion_nonproxy)}")
print(f"USCHunt (+) {len(uschunt_proxy)} (-) {len(uschunt_nonproxy)}")

both = uschunt_proxy & proxion_proxy
only_proxion = proxion_proxy & uschunt_nonproxy
only_uschunt = uschunt_proxy & proxion_nonproxy
both_nonproxy = uschunt_nonproxy & proxion_nonproxy

# import IPython; IPython.embed()
# exit()

uschunt_result.to_csv(f"a-proxies-uschunt-{len(uschunt_result)}.csv", index=False)
open(f"a-proxies-both-{len(both)}.txt", "w").write("\n".join(sorted(both)))
open(f"a-proxies-only-proxion-{len(only_proxion)}.txt", "w").write("\n".join(sorted(only_proxion)))
open(f"a-proxies-only-uschunt-{len(only_uschunt)}.txt", "w").write("\n".join(sorted(only_uschunt)))
open(f"a-proxies-neither-{len(both_nonproxy)}.txt", "w").write("\n".join(sorted(both_nonproxy)))

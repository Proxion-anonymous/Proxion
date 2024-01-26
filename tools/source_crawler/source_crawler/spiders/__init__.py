# This package will contain the spiders of your Scrapy project
#
# Please refer to the documentation for information on how to create and manage
# your spiders.

import re
from typing import Iterable, Optional

import psycopg
import scrapy
from scrapy.http import HtmlResponse
from source_crawler.items import ContractItem


class ContractsSpider(scrapy.Spider):
    name = "contracts_spider"
    # start_urls = ['https://etherscan.io/contractsVerified']

    def start_requests(self):
        # Loop for all pages in the table of verified smart contracts in EtherScan
        # urls = ['https://etherscan.io/contractsVerified/' + format(i) + "?filter=opensourcelicense"
        #        for i in range(1, 400, 1)]  # 1685
        # urls = ['https://etherscan.io/searchcontractlist?q=function&a=all&ps=100&p=' + format(i)
        #     for i in range(1, 500, 1)] # contract search for "function" (appears in all contracts) 1585 pages 100 each
        # Loop over all upgradeable proxies (including "maybe" cases) to compile a list of addresses to query
        # for proxy_dir in self.proxy_dirs:

        # for i in range (1, len(self.chain_names)):

        year = 2023
        addrs = self.get_addresses(year)
        self.logger.info(f"Found {len(addrs)} contracts to crawl in {year}")

        for addr in addrs:
            yield scrapy.Request(
                url=f"https://etherscan.io/address/{addr}",
                callback=self.parse,
                meta={"address": addr},
            )

    def get_addresses(self, year: int) -> list[str]:
        with psycopg.connect(
            host=self.settings["POSTGRES_HOST"],
            dbname=self.settings["POSTGRES_DATABASE"],
            user=self.settings["POSTGRES_USER"],
            password=self.settings["POSTGRES_PASSWORD"],
        ) as conn:
            cur = conn.execute(
                "SELECT address FROM contracts_all_unique a "
                "WHERE year = %s "
                "AND EXISTS "
                "(SELECT 1 FROM proxy_info WHERE address = a.address AND is_proxy) "
                "AND NOT EXISTS "
                "(SELECT 1 FROM source_code WHERE bytecode_hash = a.bytecode_hash) ",
                (year,),
            )
            return [x[0] for x in cur.fetchall()]

        # return [
        #     "0xa444caa3e6002265dfadc405c75d14826efee1a3",  # max recursion depht
        #     "0xfced578b60e00dc488d21a2d04982375cb5258cc",  # verified is none
        #     "0x5b2b0d0f50b03451633604e7524f2d4adc61cc09",
        #     "0x00a5df0b73f553c40e5c6acb4eeaff0deff267a7",
        #     "0x52ea46506b9cc5ef470c5bf89f17dc28bb35d85c",
        #     "0x25a867342e45a28b9cb42f7a1417d9e29feb1cc4",
        # ]

    def parse(self, response: HtmlResponse, **kwargs):
        item = ContractItem(address=response.meta["address"])

        item.public_name_tag = response.xpath(
            '//*[@id="ContentPlaceHolder1_divSummary"]/div[1]/div[1]/a/div/span/text()'
        ).get()

        item.labels = response.xpath(
            '//*[@id="ContentPlaceHolder1_divLabels"]//*[contains(@class, "hash-tag")]/text()'
        ).getall()

        item.verified = (
            "Contract Source Code Verified" in x
            if (x := response.css("#ContentPlaceHolder1_contractCodeDiv").get())
            else False
        )

        if (
            x := response.css("#ContentPlaceHolder1_contractCodeDiv").get()
        ) and "Similar Match Source Code" in x:
            item.similar_contract = (
                x.lower()
                if (
                    x := response.xpath(
                        '//*[@id="ContentPlaceHolder1_contractCodeDiv"]/div[1]/div/h3/span[1]/div/a/text()'
                    ).get()
                )
                else None
            )

        item.contract_name = response.xpath(
            '//*[@id="ContentPlaceHolder1_contractCodeDiv"]/div[2]/div[1]/div[1]/div[2]/span/text()'
        ).get()

        def extract_solc_version(v: Optional[str]) -> Optional[str]:
            if not v:
                return None
            m = re.match(r"v(\d+\.\d+\.\d+)\+commit\.[a-f0-9]+", v)
            return m.group(1) if m else v

        item.compiler_version = extract_solc_version(
            response.xpath(
                '//*[@id="ContentPlaceHolder1_contractCodeDiv"]/div[2]/div[1]/div[2]/div[2]/span/text()'
            ).get()
        )

        item.abi = response.css("#js-copytextarea2::text").get()

        if response.css("#editor1").get():
            # multiple source files
            i = 1
            while True:
                content = response.css(f"#editor{i}::text").get()
                if not content:
                    break

                # the filename is right before the content, and is like:
                # "File 3 of 5 : UpgradeableProxy.sol"
                filename = response.xpath(
                    f'//*[@id="editor{i}"]/preceding-sibling::*[1]/span[1]/text()'
                ).get()
                if not filename:
                    break
                filename = filename.partition(":")[-1].strip()

                item.source_files[filename] = content
                i += 1
        else:
            # single source file
            content = response.css("#editor::text").get()
            if content:
                item.source_code = content

        return item

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

from __future__ import annotations

import asyncio
import json
import logging
import os.path
import re
import subprocess
from typing import TYPE_CHECKING, Optional

import pymongo.collection
from psycopg_pool import AsyncConnectionPool
from solc_select.constants import ARTIFACTS_DIR

if TYPE_CHECKING:
    from scrapy import Spider
    from source_crawler.items import ContractItem


class SourceCombinePipeline:
    """Combine a package of source files into a single file by expanding imports."""

    def process_item(self, item: ContractItem, _spider: Spider):
        if item.source_code:
            return item

        try:
            # assume that the first source file is the main file
            item.source_code = self.combine(item.source_files, next(iter(item.source_files)))
        except StopIteration:
            item.errors.append({"stage": self.__class__.__name__, "message": "No main file"})
        except RecursionError:
            item.errors.append(
                {
                    "stage": self.__class__.__name__,
                    "message": "Too many levels of imports",
                }
            )
        return item

    def combine(
        self,
        source_files: dict[str, str],
        filename: str,
        depth: int = 0,
        used: Optional[set[str]] = None,
    ) -> str:
        if depth > 32:
            raise RecursionError("Too many levels of imports")

        if used is None:
            used = set()
        used.add(filename)

        content = source_files.get(filename, "")

        # recursively expand imports
        for match in re.finditer(r"^import (.*from )?[\"']([^\"']+)[\"'];", content, re.MULTILINE):
            import_filename = os.path.basename(match.group(2))
            if import_filename in used:
                content = content.replace(match.group(0), "// import skipped: " + match.group(0))
                continue
            import_content = self.combine(source_files, import_filename, depth + 1, used)
            if import_content:
                # remove SPDX License Identifier as it cannot be duplicated in the same file
                import_content = re.sub(r"// SPDX-License-Identifier:.*", "", import_content)
                content = content.replace(match.group(0), import_content)

        return content


class SourceValidatePipeline:
    """Validate that contract source code is compilable with solc."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    async def process_item(self, item: ContractItem, _spider: Spider):
        source_code = item.source_code
        if not source_code:
            item.errors.append({"stage": self.__class__.__name__, "message": "No source code"})
            return item

        version = item.compiler_version
        if not version:
            item.errors.append({"stage": self.__class__.__name__, "message": "No compiler version"})
            return item

        errmsg, stdout, stderr = await self.compile(source_code, version)
        if errmsg:
            item.errors.append(
                {
                    "stage": self.__class__.__name__,
                    "message": errmsg,
                    "stdout": stdout,
                    "stderr": stderr,
                }
            )

        return item

    async def compile(
        self, source_code: str, version: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        solc_path = ARTIFACTS_DIR.joinpath(f"solc-{version}", f"solc-{version}")
        if not solc_path.exists():
            self.logger.error("Compiler version %s not found", version)
            return f"Compiler version {version} not found", None, None

        proc = await asyncio.create_subprocess_exec(
            solc_path,
            "-",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=source_code.encode())
        if proc.returncode != 0:
            return (
                f"Compilation failed with return code {proc.returncode}",
                stdout.decode(),
                stderr.decode(),
            )

        return None, None, None


class MongoDBPipeline:
    """Store contract source code & relevant information in MongoDB."""

    collection_name = "source_code"

    mongodb_uri: str
    mongodb_db: str
    client: pymongo.MongoClient
    collection: pymongo.collection.Collection

    def __init__(self, mongodb_uri, mongodb_db):
        self.mongodb_uri = mongodb_uri
        self.mongodb_db = mongodb_db

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongodb_uri=crawler.settings["MONGODB_URI"],
            mongodb_db=crawler.settings["MONGODB_DATABASE"],
        )

    def open_spider(self, _spider: Spider):
        self.client = pymongo.MongoClient(self.mongodb_uri)
        self.collection = self.client[self.mongodb_db][self.collection_name]

    def close_spider(self, _spider: Spider):
        self.client.close()

    def process_item(self, item: ContractItem, _spider: Spider):
        self.collection.find_one_and_replace(
            {"bytecode_hash": item.bytecode_hash},
            item.asdict(),
            upsert=True,
        )
        return item


class PostgresPipeline:
    """Store contract source code & relevant information in PostgreSQL."""

    table_name = "source_code"

    postgres_host: str
    postgres_user: str
    postgres_database: str
    postgres_password: str
    pool: Optional[AsyncConnectionPool]
    logger: logging.Logger

    def __init__(self, postgres_host, postgres_user, postgres_database, postgres_password):
        self.postgres_host = postgres_host
        self.postgres_user = postgres_user
        self.postgres_database = postgres_database
        self.postgres_password = postgres_password
        self.pool = None
        self.logger = logging.getLogger(self.__class__.__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            postgres_host=crawler.settings["POSTGRES_HOST"],
            postgres_user=crawler.settings["POSTGRES_USER"],
            postgres_database=crawler.settings["POSTGRES_DATABASE"],
            postgres_password=crawler.settings["POSTGRES_PASSWORD"],
        )

    def close_spider(self, _spider: Spider):
        if self.pool:
            asyncio.run_coroutine_threadsafe(self.pool.close(), asyncio.get_event_loop())
            self.pool = None

    async def process_item(self, item: ContractItem, _spider: Spider):
        if not self.pool:
            self.pool = AsyncConnectionPool(
                f"host={self.postgres_host} "
                f"user={self.postgres_user} "
                f"dbname={self.postgres_database} "
                f"password={self.postgres_password} ",
                max_size=24,
            )
            await self.pool.open()

        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT bytecode_hash FROM contracts_all_unique WHERE address = %s",
                (item.address,),
            )
            if r := await cur.fetchone():
                code_hash = r[0]
            else:
                self.logger.error("No bytecode hash found for %s", item.address)
                return item

            await conn.execute(
                f"INSERT INTO {self.table_name}"
                "(bytecode_hash, public_name_tag, labels, verified, similar_contract, contract_name, "
                " compiler_version, abi, source_files, source_code, errors)"
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                "ON CONFLICT (bytecode_hash) DO UPDATE SET"
                "(bytecode_hash, public_name_tag, labels, verified, similar_contract, contract_name, "
                " compiler_version, abi, source_files, source_code, errors)"
                "= (EXCLUDED.bytecode_hash, EXCLUDED.public_name_tag, EXCLUDED.labels, EXCLUDED.verified,"
                "   EXCLUDED.similar_contract, EXCLUDED.contract_name, EXCLUDED.compiler_version,"
                "   EXCLUDED.abi, EXCLUDED.source_files, EXCLUDED.source_code, EXCLUDED.errors)",
                (
                    code_hash,
                    item.public_name_tag,
                    item.labels,
                    item.verified,
                    item.similar_contract,
                    item.contract_name,
                    item.compiler_version,
                    item.abi,
                    json.dumps(item.source_files),
                    item.source_code,
                    json.dumps(item.errors),
                ),
            )
            await conn.commit()
        return item

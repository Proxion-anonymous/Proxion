import json
import logging
import os
import re
import shutil
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TypeAlias, Union, cast

import requests

from proxion.Throttler import Throttler

_logger = logging.getLogger(__name__)


class FetchSourceError(RuntimeError):
    pass


class InvalidStatusError(FetchSourceError):
    pass


class UnexpectedResponseError(FetchSourceError):
    pass


class DummyThrottler:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# The raw JSON response from Etherscan API for the `getsourcecode` query
EtherscanGetSourceCodeResponse: TypeAlias = dict


@dataclass
class _ContractSource:
    # contract name
    name: Optional[str] = None

    # main contract path relative to the directory that stores the source code
    path: Optional[str] = None

    compiler_version: Optional[str] = None

    # source code of each file
    sources: dict[str, str] = field(default_factory=dict)

    # path remappings
    remappings: dict[str, str] = field(default_factory=dict)


@dataclass
class ContractSourceMeta:
    address: str

    # contract name
    name: str

    # main contract path relative to the directory that stores the source code
    path: Path

    # directory that stores the source code
    directory: Path

    compiler_version: Optional[str] = None


class SourceCrawler:
    def __init__(self, args: Namespace, api_key: str, throttler: Optional[Throttler] = None):
        self.args = args
        self.api_key = api_key
        self.throttler = throttler or DummyThrottler()

    def download(self, address: str, destination: Union[str, Path]) -> Optional[ContractSourceMeta]:
        """Download and save the source code of the contract at the given address.
        Returns the main contract name and main contract relative path in the filesystem.
        """
        response = self.get_source_code_etherscan(address)
        contract_source = self.extract_source_code(response)
        if not contract_source or not contract_source.name or not contract_source.path:
            return None

        self.save_source(contract_source, destination)
        return ContractSourceMeta(
            address=address,
            name=contract_source.name,
            path=Path(contract_source.path),
            directory=Path(destination),
            compiler_version=contract_source.compiler_version,
        )

    def get_source_code_etherscan(self, address: str) -> EtherscanGetSourceCodeResponse:
        """Download verified source code including metadata from Etherscan.io.

        Since Etherscan free-tier API has a rate limit of 5 requests per second,
        we have to throttle request rate.

        Returns the raw JSON response in dict from Etherscan API.
        """
        res = None
        for _ in range(self.args.fetch_source_retry):
            try:
                with self.throttler, requests.Session() as session:
                    res = self.get_source_code_etherscan_once(address, session)
                    break
            except (
                requests.exceptions.Timeout,
                requests.exceptions.HTTPError,
                FetchSourceError,
            ) as e:
                _logger.error("request source retry: %s: %s", address, e)

        if res is None:
            raise FetchSourceError(
                f"getting {address} source failed with timeout {self.args.fetch_source_timeout} "
                f"and {self.args.fetch_source_retry} retries"
            )

        return res

    def get_source_code_etherscan_once(
        self, address: str, session: requests.Session
    ) -> EtherscanGetSourceCodeResponse:
        _logger.info("requesting source: %s", address)
        with session.get(
            "https://api.etherscan.io/api",
            params={
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apiKey": self.api_key,
            },
            timeout=self.args.fetch_source_timeout,
        ) as r:
            _logger.debug("responded source: %s", address)

            r.raise_for_status()
            j = r.json()

            if j["status"] != "1":
                raise InvalidStatusError(f"request {address} source failed: {j['result']}")

            res = j["result"][0]
            if not isinstance(res, dict):
                # When max rate limit is reached, Etherscan returns a string "M" instead of a dict
                raise UnexpectedResponseError(f"unexpected response: {address}: {res}")

            _logger.debug("got source: %s", address)
            return res

    @staticmethod
    def extract_source_code(
        etherscan_response: EtherscanGetSourceCodeResponse,
    ) -> Optional[_ContractSource]:
        """Parse the response returned by Etherscan API, remove metadata and return only the source
        code (single or multiple files), main contract name and main contract path.
        If the source code is not verified, return None.
        """
        result = _ContractSource()

        name = etherscan_response.get("ContractName")
        if not name:
            return None
        result.name = name

        code = etherscan_response.get("SourceCode")
        if not code:
            return None

        result.compiler_version = extract_compiler_version(
            etherscan_response.get("CompilerVersion")
        )

        if code.startswith("{{"):
            dic = json.loads(code[1:-1])
            sources = dic["sources"]

        elif code.startswith("{"):
            dic = {}
            sources = json.loads(code)

        if code.startswith("{"):
            # multi-file source: either start with { or {{
            for f_path, f_content in sources.items():
                # avoid absolute path
                f_path = cast(str, f_path).removeprefix("/")

                if not f_path.endswith(".sol"):
                    f_path += ".sol"

                for remapping in dic.get("settings", {}).get("remappings", []):
                    remapping = cast(str, remapping)
                    from_, _, to = remapping.partition("=")
                    if from_ == to:
                        continue

                    # avoid nested remapping
                    # e.g. both @openzeppelin=node_modules/openzeppelin and
                    # @openzeppelin/contracts=node_modules/openzeppelin/contracts
                    p = Path(from_)
                    nested = False
                    while p != Path(".") and p != Path("/"):
                        p = p.parent
                        if str(p) + "/" in result.remappings:
                            nested = True
                            break
                    if nested:
                        continue

                    # avoid absolute path
                    if from_ == "/":
                        continue
                    result.remappings[from_.removeprefix("/")] = to.removeprefix("/")

                # guess first one is contract path
                if result.path is None:
                    result.path = f_path

                # override contract path if there is a more suitable one
                if result.name and f_path.split("/")[-1] == result.name + ".sol":
                    result.path = f_path

                result.sources[f_path] = f_content["content"]

        else:
            # single-file source
            if result.name:
                result.path = result.name + ".sol"
                result.sources[result.path] = code

        return result

    @staticmethod
    def save_source(contract_source: _ContractSource, destination: Union[str, Path]):
        dest = ensure_clean_dir(destination)
        for _path, content in contract_source.sources.items():
            path = Path(_path)
            if path.is_absolute():
                raise ValueError(f"absolute path in source code: {path}")

            full_path = ensure_file(dest / path)
            full_path.write_text(content)

        for from_, to in contract_source.remappings.items():
            if from_ == to or not from_:
                continue

            # symlink full_from -> full_to
            full_from = dest / from_
            full_to = dest / to

            if not full_to.is_dir():
                # avoid dangling symlink
                continue

            ensure_file(full_from)
            full_from.symlink_to(
                os.path.relpath(full_to, full_from.parent), target_is_directory=True
            )


@dataclass
class SourceManager:
    """Fetch source code from Etherscan and save to local filesystem.
    The directory structure is like:
    17/0x172a9be5ea7f8602d6b9a97a914d23859053790a/
        @openzeppelin/contracts-upgradeable/proxy/ERC1967/ERC1967Proxy.sol
        contracts/Proxy.sol
        logic0 -> ../../5d/0x5d9fb7f5a349177af70890abb21b9461554f24b6  # symlink
    """

    proxy: Optional[ContractSourceMeta]
    logics: list[Optional[ContractSourceMeta]]

    @classmethod
    def download_proxy_and_logics(
        cls, crawler: SourceCrawler, proxy_addr: str, logic_addrs: list[str], dest: Union[str, Path]
    ) -> "SourceManager":
        proxy_dir = cls.get_source_dir(dest, proxy_addr)
        try:
            proxy_source_meta = crawler.download(proxy_addr, proxy_dir)
        except FetchSourceError as e:
            _logger.error("fetch proxy source failed: %s", e)
            proxy_source_meta = None

        logic_source_meta: list[Optional[ContractSourceMeta]] = []
        for i, logic_addr in enumerate(logic_addrs):
            logic_dir = cls.get_source_dir(dest, logic_addr)
            try:
                logic_source_meta.append(crawler.download(logic_addr, logic_dir))
            except FetchSourceError as e:
                _logger.error("fetch logic source failed: %s", e)
                logic_source_meta.append(None)

            if logic_source_meta[i] and proxy_source_meta:
                # create symlink to logic contracts in proxy dir
                proxy_dir.joinpath(f"logic{i}").symlink_to(
                    os.path.relpath(logic_dir, proxy_dir),
                    target_is_directory=True,
                )
        return cls(proxy_source_meta, logic_source_meta)

    @staticmethod
    def get_source_dir(prefix: Union[str, Path], address: str) -> Path:
        return Path(prefix).joinpath(address[2:4]).joinpath(address)


def extract_compiler_version(version_string: Optional[str]) -> Optional[str]:
    if not version_string:
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", version_string)
    return m.group(1) if m else None


def ensure_clean_dir(path: Union[str, Path]) -> Path:
    """Ensure the directory exists and is empty."""
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)

    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_file(path: Union[str, Path]) -> Path:
    """Ensure the parent dir of the file exists."""
    path = Path(path)
    parent = path.parent
    if parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)
    return path

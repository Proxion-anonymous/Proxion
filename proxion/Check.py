from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Optional

from solc_select.solc_select import ARTIFACTS_DIR

from proxion.SourceCrawler import ContractSourceMeta, SourceManager

_logger = logging.getLogger(__name__)


# fmt: off
solc_versions = [f"0.8.{i}" for i in range(23, -1, -1)] + [
    "0.7.6", "0.7.5", "0.7.4", "0.7.3", "0.7.2", "0.7.1", "0.7.0",
    "0.6.12", "0.6.11", "0.6.10", "0.6.9", "0.6.8", "0.6.7", "0.6.6", "0.6.5", "0.6.4", "0.6.3", "0.6.2", "0.6.1", "0.6.0",
    "0.5.17", "0.5.16", "0.5.15", "0.5.14", "0.5.13", "0.5.12", "0.5.11", "0.5.10", "0.5.9", "0.5.8", "0.5.7", "0.5.6", "0.5.5", "0.5.4", "0.5.3", "0.5.2", "0.5.1", "0.5.0",
    "0.4.26", "0.4.25", "0.4.24", "0.4.23", "0.4.22", "0.4.21", "0.4.20", "0.4.19", "0.4.18", "0.4.17", "0.4.16", "0.4.15", "0.4.14", "0.4.13", "0.4.12", "0.4.11", "0.4.10", "0.4.9", "0.4.8", "0.4.7", "0.4.6", "0.4.5", "0.4.4", "0.4.3", "0.4.2", "0.4.1", "0.4.0",
]
# fmt: on
solcs = ",".join(solc_versions)


def check_slither(source_manager: SourceManager) -> list[SlitherResult]:
    checks = []
    proxy = source_manager.proxy

    # check proxy and current logic
    for logic in source_manager.logics[-1:]:
        if not proxy or not logic:
            continue
        _logger.info("Checking proxy %s and logic %s", proxy.address, logic.address)
        checks.append(SlitherCheckerProxy(proxy, logic).check())

    # check old logic and new logic
    for logic1, logic2 in pairwise(source_manager.logics):
        if not logic1 or not logic2:
            continue
        _logger.info("Checking logic %s and logic %s", logic1.address, logic2.address)
        checks.append(SlitherCheckerLogic(logic1, logic2).check())

    return checks


@dataclass
class SlitherResult:
    type: str
    address1: str
    address2: str
    error: Optional[str] = None
    output: Optional[str] = None
    json: Optional[str] = None
    collisions: list[str] = field(default_factory=list)

    def asdict(self):
        return asdict(self)


class SlitherError(RuntimeError):
    pass


class SlitherChecker(ABC):
    """Base class for slither-check-upgradeability checkers."""

    @property
    @abstractmethod
    def contract1(self) -> ContractSourceMeta:
        ...

    @property
    @abstractmethod
    def contract2(self) -> ContractSourceMeta:
        ...

    def check(self, timeout: float = 60.0, **kwargs) -> SlitherResult:
        # setup env so that solc-select & solc artifacts from the virtualenv are used
        venv_bin = Path(sys.executable).parent
        venv_dir = venv_bin.parent
        env = {
            "PATH": f"{venv_bin}:{os.environ['PATH']}",
            "VIRTUAL_ENV": f"{venv_dir}",
        }
        cmd = self.get_command(timeout=timeout, **kwargs)
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        ) as proc:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as e:
                proc.kill()
                proc.wait()
                raise SlitherError(f"Timeout after {timeout} seconds") from e

        out_json = stdout.decode()
        out_msg = stderr.decode()
        cmd_and_msg = (
            f"PATH={venv_bin}:$PATH VIRTUAL_ENV={venv_dir} "
            + " ".join(f"'{x}'" for x in cmd)
            + "\n"
            + out_msg
        )

        try:
            collisions = self.parse_slither_output(out_json, out_msg)
        except SlitherError as e:
            return SlitherResult(
                type=self.__class__.__name__,
                address1=self.contract1.address,
                address2=self.contract2.address,
                output=cmd_and_msg,
                json=out_json,
                error=str(e),
            )

        return SlitherResult(
            type=self.__class__.__name__,
            address1=self.contract1.address,
            address2=self.contract2.address,
            output=cmd_and_msg,
            json=out_json,
            collisions=collisions,
        )

    @abstractmethod
    def get_command(self, timeout: float, **kwargs) -> list[str]:
        ...

    def parse_slither_output(self, output_json: str, output_message: str) -> list[str]:
        """Parse the output of slither-check-upgradeability.
        Returns a list of collision types.
        """
        if not output_json:
            raise SlitherError("No output from slither-check-upgradeability")

        j = json.loads(output_json)
        if not j["success"]:
            raise SlitherError(j["error"])

        v = set()
        for line in output_message.split("\n"):
            if line.startswith("Reference"):
                for check in [
                    "functions-shadowing",
                    "functions-ids-collisions",
                    "incorrect-variables-with-the-v2",
                    "incorrect-variables-with-the-proxy",
                    "missing-variables",
                ]:
                    if check in line:
                        v.add(check)

        return list(v)


@dataclass
class SlitherCheckerProxy(SlitherChecker):
    """Check proxy and logic."""

    proxy: ContractSourceMeta
    logic: ContractSourceMeta

    @property
    def contract1(self) -> ContractSourceMeta:
        return self.proxy

    @property
    def contract2(self) -> ContractSourceMeta:
        return self.logic

    def get_command(self, timeout: float, **kwargs) -> list[str]:
        # run slither-check-upgradeability in virtualenv
        # so that our modified slither is used
        return [
            "timeout",
            "-v",
            f"{timeout}",
            sys.executable,
            "-c",
            "from slither.tools.upgradeability.__main__ import main; main()",
            *self._get_compiler_args(),
            "--solc-working-dir",
            str(self.logic.directory),
            str(self.logic.path),
            self.logic.name,
            "--proxy-solc-working-dir",
            str(self.proxy.directory),
            "--proxy-filename",
            str(self.proxy.path),
            "--proxy-name",
            self.proxy.name,
            "--json",
            "-",
        ]

    def _get_compiler_args(self) -> list[str]:
        if not self.proxy.compiler_version or not self.logic.compiler_version:
            # select all solc versions
            return ["--solc-solcs-select", solcs]

        return [
            "--solc-solcs-bin",
            ARTIFACTS_DIR.joinpath(
                f"solc-{self.logic.compiler_version}", f"solc-{self.logic.compiler_version}"
            ).as_posix(),
            "--proxy-solc-solcs-bin",
            ARTIFACTS_DIR.joinpath(
                f"solc-{self.proxy.compiler_version}", f"solc-{self.proxy.compiler_version}"
            ).as_posix(),
        ]


@dataclass
class SlitherCheckerLogic(SlitherChecker):
    """Check old and new logic."""

    old_logic: ContractSourceMeta
    new_logic: ContractSourceMeta

    @property
    def contract1(self) -> ContractSourceMeta:
        return self.old_logic

    @property
    def contract2(self) -> ContractSourceMeta:
        return self.new_logic

    def get_command(self, timeout: float, **kwargs) -> list[str]:
        # run slither-check-upgradeability in virtualenv
        # so that our modified slither is used
        return [
            "timeout",
            "-v",
            f"{timeout}",
            sys.executable,
            "-c",
            "from slither.tools.upgradeability.__main__ import main; main()",
            *self._get_compiler_args(),
            "--solc-working-dir",
            str(self.old_logic.directory),
            str(self.old_logic.path),
            self.old_logic.name,
            "--new-contract-solc-working-dir",
            str(self.new_logic.directory),
            "--new-contract-filename",
            str(self.new_logic.path),
            "--new-contract-name",
            self.new_logic.name,
            "--json",
            "-",
        ]

    def _get_compiler_args(self) -> list[str]:
        if not self.old_logic.compiler_version or not self.new_logic.compiler_version:
            # select all solc versions
            return ["--solc-solcs-select", solcs]

        return [
            "--solc-solcs-bin",
            ARTIFACTS_DIR.joinpath(
                f"solc-{self.old_logic.compiler_version}", f"solc-{self.old_logic.compiler_version}"
            ).as_posix(),
            "--new-contract-solc-solcs-bin",
            ARTIFACTS_DIR.joinpath(
                f"solc-{self.new_logic.compiler_version}", f"solc-{self.new_logic.compiler_version}"
            ).as_posix(),
        ]

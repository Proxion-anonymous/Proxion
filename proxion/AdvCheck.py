import logging
from collections import defaultdict
from typing import NamedTuple, Optional, TypeAlias, Union

from evm_cfg_builder.cfg import CFG
from evm_cfg_builder.cfg.basic_block import BasicBlock
from hexbytes import HexBytes
from octopus.platforms.ETH.constants import BLOCK_TAG_LATEST
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
from pyevmasm import Instruction, disassemble_all

_logger = logging.getLogger(__name__)


class ConcreteWord(NamedTuple):
    """a normal 256-bit value"""

    value: HexBytes


class HashedWord(NamedTuple):
    """a keccak256 digest of some data, such as \"eip1967.proxy.implementation\"
    data is set to None if not available
    """

    data: Optional[str]


Word = ConcreteWord | HashedWord


class BackwardAnalyzer:
    PC: TypeAlias = int
    ForwardCFG: TypeAlias = dict[PC, Word]
    BackwardCFG: TypeAlias = dict[PC, set[PC]]

    def __init__(
        self, address: str, explorer: EthereumExplorerRPC, block: Union[str, int] = BLOCK_TAG_LATEST
    ):
        self.address = address
        self.bytecode = explorer.eth_getCode(address, block)
        self._cfg = CFG(self.bytecode, optimization_enabled=False)
        self._cfg_back: BackwardAnalyzer.BackwardCFG = defaultdict(set)

        bb: BasicBlock
        bbo: BasicBlock
        for bb in self._cfg.basic_blocks:
            for bbo in bb.all_outgoing_basic_blocks:
                self._cfg_back[bbo.start.pc].add(bb.start.pc)

    @property
    def instructions(self) -> dict[PC, Instruction]:
        return self._cfg._instructions

    def trace_op_input(self, stack_index: int, pc: PC, visited: set[PC]) -> Optional[Word]:
        if pc in visited:
            return None
        visited.add(pc)

        while pc >= 0:
            inst = self.instructions[pc]

            _logger.debug("trace: %x stack=%s %s %s", inst.pc, stack_index, inst.name, inst.operand)

            if inst._name == "PUSH" and stack_index == 1:
                return ConcreteWord(HexBytes(inst.operand))

            if inst._name == "SHA3" and stack_index == 1:
                # if the storage is accessed by a key of keccak256,
                # we say that collisions are unlikely, and exclude it from our result
                # TODO: trace the data that is hashed
                return HashedWord(None)

            if inst._name == "DUP":
                stack_index = inst._pops + 1

            elif inst._name == "SWAP":
                swap_index = inst._pops
                if stack_index == 1:
                    stack_index = swap_index
                elif stack_index == swap_index:
                    stack_index = 1

            elif inst._name == "JUMPDEST":
                if not self._cfg_back[inst.pc]:
                    _logger.debug("Incoming basic block to %x not found", inst.pc)
                    return None

                for incoming in self._cfg_back[inst.pc]:
                    if res := self.trace_op_input(stack_index, incoming, visited):
                        return res

            stack_index += inst.pops - inst.pushes
            pc -= 1
            while pc >= 0 and not self.instructions.get(pc):
                pc -= 1

        return None

    def find_storage_access(self) -> tuple[set[str], set[str]]:
        _logger.debug("Finding slots that %s accesses", self.address)
        read_slots = set()
        written_slots = set()
        for inst in self.instructions.values():
            if inst._name in ("SLOAD", "SSTORE"):
                slot = self.trace_op_input(stack_index=1, pc=inst.pc, visited=set())
                _logger.debug("0x%x: %s accessed slot %s", inst.pc, inst.name, slot)
                if isinstance(slot, ConcreteWord):
                    if inst._name == "SLOAD":
                        read_slots.add(slot.value.hex())
                    else:
                        written_slots.add(slot.value.hex())
        return read_slots, written_slots


def hexbytes_to_int(h: HexBytes) -> int:
    return int.from_bytes(h, "big")


def find_selectors(
    address: str, explorer: EthereumExplorerRPC, block: Union[str, int] = BLOCK_TAG_LATEST
) -> set[str]:
    """Find all function selectors of a contract."""
    bytecode = HexBytes(explorer.eth_getCode(address, block))
    return {
        "0x" + inst.operand.to_bytes(4, "big").hex()
        for inst in disassemble_all(bytecode)
        if inst._name == "PUSH" and inst.operand_size == 4 and inst.operand != 0xFFFFFFFF
    }


def check_advanced(
    proxy_address: str,
    logic_addresses: list[str],
    explorer: EthereumExplorerRPC,
    block: Union[str, int] = BLOCK_TAG_LATEST,
):
    _logger.info(
        "Bytecode-based check for slot collisions: proxy %s and logic %s",
        proxy_address,
        logic_addresses,
    )

    proxy_slots_r, proxy_slots_w = BackwardAnalyzer(
        proxy_address, explorer, block
    ).find_storage_access()
    logic_slots = [
        BackwardAnalyzer(logic_addr, explorer, block).find_storage_access()
        for logic_addr in logic_addresses
    ]

    proxy_signatures = find_selectors(proxy_address, explorer, block)
    logic_signatures = [
        find_selectors(logic_addr, explorer, block) for logic_addr in logic_addresses
    ]

    return {
        "address": proxy_address,
        "slots": {
            "proxy": {
                "read": list(proxy_slots_r),
                "write": list(proxy_slots_w),
            },
            "logics": [
                {
                    "read": list(r),
                    "write": list(w),
                }
                for r, w in logic_slots
            ],
        },
        "signatures": {
            "proxy": list(proxy_signatures),
            "logics": [list(sigs) for sigs in logic_signatures],
        },
        # read by proxy, read by logic
        "slots_rr": list(proxy_slots_r & logic_slots[-1][0]) if logic_slots else None,
        # read by proxy, written by logic
        "slots_rw": list(proxy_slots_r & logic_slots[-1][1]) if logic_slots else None,
        # written by proxy, read by logic
        "slots_wr": list(proxy_slots_w & logic_slots[-1][0]) if logic_slots else None,
        # written by proxy, written by logic
        "slots_ww": list(proxy_slots_w & logic_slots[-1][1]) if logic_slots else None,
        # signatures that are used by both proxy and logic
        "colliding_signatures": [list(proxy_signatures & sigs) for sigs in logic_signatures],
    }

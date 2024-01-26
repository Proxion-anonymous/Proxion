# fmt: off
import argparse
import json
import logging
import sys
import traceback
from dataclasses import asdict, dataclass, field
from typing import Optional, Union
from urllib.parse import urlsplit

from octopus.platforms.ETH.constants import BLOCK_TAG_LATEST
from octopus.platforms.ETH.disassembler import EthereumDisassembler
from octopus.platforms.ETH.emulator import EthereumSSAEngine
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
from octopus.platforms.ETH.vmstate import EthereumVMstate

from proxion.Config import ETHERSCAN_APIKEY, RPC_URL

SLOTS: dict[str, int] = {}
SLOTS['EIP1822_IMPLEMENT_SLOT'] = 0xc5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7
SLOTS['ERC1967_IMPLEMENT_SLOT'] = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc
SLOTS['ERC1967_BEACON_SLOT'] = 0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50
SLOTS['ERC1967_ADMIN_SLOT'] = 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103
SLOTS['EIP2535_DIAMOND_SLOT'] = 0xc8fcad8db84d3cc18b4c41d551ea0ee66dd599cde068d998e57d5e09332c131c
SLOTS['EIP2535_DIAMOND1_OWNER_SLOT'] = SLOTS['EIP2535_DIAMOND_SLOT'] + 3
SLOTS['EIP2535_DIAMOND23_OWNER_SLOT'] = SLOTS['EIP2535_DIAMOND_SLOT'] + 4

ZERO_VALUE = '0x0000000000000000000000000000000000000000000000000000000000000000'


def word_to_address(word: str) -> str:
    """Convert a 256-bit word to an 20-byte address.
    Example input: 0x000000000000000000000000017674bd734f120a60b43965fb76fbcd0a89cd24
    Example output: 0x017674bd734f120a60b43965fb76fbcd0a89cd24
    """
    return f"0x{word[-40:]}"


def int_to_word(val: int) -> str:
    """Convert an integer to a 256-bit word.
    Example input: 1234
    Example output: 0x00000000000000000000000000000000000000000000000000000000000004d2
    """
    return f"{val:#066x}"


def binary_search(addr: str, slot: int, explorer: EthereumExplorerRPC, right: Union[int, str] = BLOCK_TAG_LATEST):
    left = 1
    if right == BLOCK_TAG_LATEST:
        right = explorer.eth_blockNumber()
    table: dict[int, int] = {}

    def get_val(block,addr):
        if block in table:
            return table[block]
        val = explorer.eth_getStorageAt(addr, slot, block)
        if val == "0x" or val == ZERO_VALUE:
            val = 0
        else:
            val = int(val,16)
        table[block] = val
        return table[block]

    def search_diff(l,r,addr):
        if get_val(l,addr) == get_val(r,addr) or r - l <= 1:
            return
        mid = (l+r) // 2
        if get_val(mid,addr) != get_val(l,addr):
            search_diff(l,mid,addr)
        if get_val(mid,addr) != get_val(r,addr):
            search_diff(mid,r,addr)

    search_diff(left,right,addr)
    logic_contracts = [0]
    for k in sorted(table):
        if table[k] != logic_contracts[-1]:
            logic_contracts.append(table[k])
    return [f"{logic:#0{42}x}" for logic in logic_contracts[1:]]



def get_func_sigs(code) -> set:
    res = set()
    disasm = EthereumDisassembler(code)
    instrs = disasm.disassemble()
    has_delegate = False
    for instr in instrs:
        if(instr.name == 'PUSH4'):
            res.add(f"{instr.operand_interpretation:#0{10}x}")
    if('0xffffffff' in res):
        res.remove('0xffffffff')
    return res


@dataclass
class ProxyCheckResult:
    address: str

    success: bool = True
    error: Optional[str] = None

    is_proxy: Optional[bool] = None
    erc_1167: bool = False  # minimal proxy
    erc_1822: bool = False  # UUPS proxy
    erc_1967: bool = False  # standard proxy storage slots are used
    erc_2535: bool = False  # diamond proxy
    multi_delegatecall: bool = False  # may be a diamond proxy
    reason: Optional[str] = None

    implementation_slot: Optional[str] = None
    standard_implementation_slots: dict[str, str] = field(default_factory=dict)
    current_implementation: Optional[str] = None
    old_implementations: list[str] = field(default_factory=list)

    def asdict(self):
        return asdict(self)


def proxy_check(
    addr: str, explorer: EthereumExplorerRPC, block: Union[int, str] = BLOCK_TAG_LATEST, debug: bool = False
) -> ProxyCheckResult:
    result = ProxyCheckResult(addr)
    try:
        addr = f"{int(addr,16):#0{42}x}"
        code = explorer.eth_getCode(addr, block)
        if(code == '0x'):
            result.success = False
            result.error = "No bytecode!"
            return result
        func_sigs = get_func_sigs(code)
        code_size = len(code[2:]) // 2
        test_sig = "0xaabbccdd"
        while(test_sig in func_sigs):
            tmp = int(test_sig,16) + 1
            test_sig = f"{tmp:#0{10}x}"

        callinfo = {'calldata':bytes.fromhex(test_sig[2:]+"ee"*32), 'callvalue':0, 'address': addr, 'codesize':code_size}
        callinfo['storage_address'] = addr
        callinfo['caller'] = "0x"+"cc" * 20
        callinfo['origin'] = "0x"+"cc" * 20
        # check storage value
        for slot_name, slot_key in SLOTS.items():
            val = explorer.eth_getStorageAt(addr, slot_key)
            if val != ZERO_VALUE and val != "0x":
                result.standard_implementation_slots[slot_name] = val
                result.current_implementation = word_to_address(val)
                if slot_name.startswith("ERC1167_"):
                    result.erc_1167 = True
                if slot_name.startswith("EIP1822_"):
                    result.erc_1822 = True
                if slot_name.startswith("ERC1967_"):
                    result.erc_1967 = True
                if slot_name.startswith("EIP2535_"):
                    result.erc_2535 = True

        state = EthereumVMstate(explorer)
        emul = EthereumSSAEngine(code, explorer)
        # emulate will modify callinfo so pass copy
        emul.emulate(callinfo.copy(), state, debug)
        info = emul.get_delegate_info()
        if emul.contains_inconcrete_opcode():
            result.success = False
            result.error = f"Contain inconcrete_opcode: {emul.meet_inconcrete_opcode}"
        if(len(info) == 0):  # no delegate call
            result.is_proxy = False
            result.reason = "no delegatecall in fallback function"
        else:  # at least one delegate call
            if(len(info) > 1):
                result.multi_delegatecall = True  # TODO: check if it is a diamond
            # Takes last one as logic contract.
            logic_address = info[-1]['address']
            if(callinfo['calldata'] != info[-1]['calldata']):
                result.is_proxy = False
                result.reason = "Calldata different"
                return result
            result.is_proxy = True
            result.current_implementation = logic_address
            result.old_implementations = []
            storage_slot = None
            storage: dict[int, int] = state.storage
            for slot in storage:
                if storage[slot] == int(logic_address, 16):
                    storage_slot = slot
                    break
            if storage_slot is None:
                if info[-1]['address'][2:] in code: # minimal proxy
                    result.erc_1167 = True
                else:
                    # non-trivial implementation slot,
                    # or logic contract stored in another (beacon) contract
                    result.implementation_slot = None
            else:
                result.implementation_slot = int_to_word(storage_slot)
                # get all historical logic contracts
                result.old_implementations = binary_search(addr, storage_slot, explorer, block)
                if result.old_implementations[-1] == result.current_implementation:
                    result.old_implementations.pop()

        return result

    except:  # noqa: E722 # pylint: disable=bare-except
        result.success = False
        result.error = traceback.format_exc()
        return result


def int_or_str(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address", help="Input an Ethereum smart contract address.")
    parser.add_argument("--no-slither", help="Disable slither-check-upgradeability.",
                        action="store_true")
    parser.add_argument("--no-advanced-check", help="Disable bytecode-based advanced check.",
                        action="store_true")
    parser.add_argument("--log-level", help="Log level", default="INFO")
    parser.add_argument("--source-prefix", help="The directory to save/load the source files.",
                        required="--no-slither" not in sys.argv)
    parser.add_argument("--compiler-version", help="The version of solc to use.", default=None)
    parser.add_argument("--slither-verbose", help="Show slither's output", action="store_true")
    parser.add_argument("--fetch-source",
                        help="Always fetch source code from etherscan.io even if it exists locally.",
                        action="store_true", default=False)
    parser.add_argument("--fetch-source-timeout",
                        help="Timeout for fetching source code from Etherscan.", default=3)
    parser.add_argument("--fetch-source-retry",
                        help="Retry times for fetching source code from Etherscan.", default=3)
    parser.add_argument("--rpc-url", help="RPC URL", default=RPC_URL)
    parser.add_argument("--debug", help="Debug mode", action="store_true")
    parser.add_argument("--block", help="Block number", type=int_or_str,
                        default=BLOCK_TAG_LATEST)
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)
    result = {}

    urlparts = urlsplit(args.rpc_url)
    explorer = EthereumExplorerRPC(
        host=f"{urlparts.hostname}{urlparts.path}",
        port=urlparts.port or 8545,
        tls=(urlparts.scheme == "https")
    )
    proxy_info = proxy_check(args.address, explorer, debug=args.debug, block=args.block)
    result["proxy_info"] = proxy_info.asdict()

    if not args.no_slither:
        from proxion.Check import check_slither
        from proxion.SourceCrawler import SourceCrawler, SourceManager

        # run slither-check-upgradeability
        # save all source code if provided
        crawler = SourceCrawler(args, api_key=ETHERSCAN_APIKEY)
        srcmgr = SourceManager.download_proxy_and_logics(
            crawler,
            args.address,
            proxy_info.old_implementations + [proxy_info.current_implementation]
            if proxy_info.current_implementation is not None
            else proxy_info.old_implementations,
            args.source_prefix,
        )
        result["slither"] = [x.asdict() for x in check_slither(srcmgr)]
        for x in result["slither"]:
            del x["json"]

    if not args.no_advanced_check:
        from proxion.AdvCheck import check_advanced

        result["adv_check"] = check_advanced(
            args.address,
            proxy_info.old_implementations + [proxy_info.current_implementation]
            if proxy_info.current_implementation is not None
            else proxy_info.old_implementations,
            explorer,
            block=args.block,
        )

    json.dump(result, sys.stdout, indent=2)


if __name__ == '__main__':
    main()

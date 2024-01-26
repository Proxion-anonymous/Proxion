from octopus.arch.evm.disassembler import EvmDisassembler

# Etherem smart contract == EVM bytecode
class EthereumDisassembler(object):
    def __new__(cls, bytecode=None, arch='evm'):
        #if arch == 'evm':
        return EvmDisassembler(bytecode)
        #else:  # eWasm
        #    return WasmDisassembler(bytecode)

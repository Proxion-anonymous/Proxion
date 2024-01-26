import copy
import time
from logging import getLogger

from eth_hash.auto import keccak
from octopus.core.ssa import SSA, SSA_TYPE_CONSTANT, SSA_TYPE_FUNCTION
from octopus.engine.emulator import EmulatorEngine
from octopus.engine.helper import helper as hlp
from octopus.platforms.ETH.contract import EthereumContract
from octopus.platforms.ETH.disassembler import EthereumDisassembler
from octopus.platforms.ETH.explorer import INFURA_MAINNET, EthereumInfuraExplorer
from octopus.platforms.ETH.ssa import EthereumSSASimplifier
from octopus.platforms.ETH.vmstate import EthereumVMstate

logging = getLogger(__name__)
INFURA_KEY = "d449de4b0a0c4c2ca8d60fcd0fc544d9"


def int_to_address(value: int) -> str:
    """Convert an integer to an Ethereum address."""
    return "0x" + f"{value:0{40}x}"[-40:]

class EthereumEmulatorEngine(EmulatorEngine):

    def __init__(self, bytecode, explorer):

        self.bytecode = bytecode

        # retrive instructions, basicblocks & functions statically
        disasm = EthereumDisassembler(bytecode)
        # pass runtime code no need to analysis
        self.instructions = disasm.disassemble(analysis=False)
        self.reverse_instructions = {k: v for k, v in enumerate(self.instructions)}

        self.states = dict()
        self.states_total = 0

        self.bytecode = disasm.bytecode  # get the run time bytecode from disasm

        self.result = {} # record the last opcode and info
        self.handler = Handler(explorer)  # handle info outside contract
        self.delegate_info = []  # record delegate call info
        self.meet_inconcrete_opcode = set() # check if meet inconcrete opcode like block number or basefee

    def emulate(self, callinfo, state=None, debug = False):
        state = state or EthereumVMstate(self.handler.explorer)
        self.meet_inconcrete_opcode = set()
        self.result = {}
        self.delegate_info = []  # record delegate call info
        # handle call return data
        self.has_call = False
        self.return_buffer = b''

        # callinfo check
        try:
            for i in ['address','caller','origin','codesize','storage_address']:
                if(callinfo.get(i) == None):
                    raise Exception("callinfo error: need "+i)
        except Exception as e:
            print(e)
            return
        #pre process calldata
        #convert calldata to bytes
        if(callinfo.get('calldata') != None):
            if type(callinfo['calldata']) == str:
                if(callinfo['calldata'][:2] == '0x'):
                    callinfo['calldata'] = callinfo['calldata'][2:]
                callinfo['calldata'] = bytes.fromhex(callinfo['calldata'])
        else:
            callinfo['calldata'] = b''

        if(callinfo.get('gas') != None):
            state.gas = callinfo.get('gas')

        # get current instruction
        instr = self.reverse_instructions[state.pc]

        # halt variable use to catch ending branch
        halt = False
        while not halt:

            # get current instruction
            instr = self.reverse_instructions[state.pc]

            # Save instruction and state
            state.instr = instr
            self.states[self.states_total] = state
            self.states_total += 1
            state.pc += 1

            # execute single instruction
            halt = self.emulate_one_instruction(callinfo, instr, state, debug)

    def get_result(self):
        return self.result

    def get_delegate_info(self):
        return self.delegate_info

    #return bool
    def contains_inconcrete_opcode(self):
        return len(self.meet_inconcrete_opcode) > 0

    def emulate_one_instruction(self, callinfo, instr, state, debug):
        if(debug):
            if instr.operand_interpretation:
                print ('\033[1;32m Instr \033[0m',hex(state.pc-1), instr.name, hex(instr.operand_interpretation))
            else:
                print ('\033[1;32m Instr \033[0m', hex(state.pc-1), instr.name)
        state.gas -= instr.fee
        halt = False

        #
        #  0s: Stop and Arithmetic Operations
        #
        if instr.name == 'STOP':
            halt = True

        elif instr.is_arithmetic:
            self.emul_arithmetic_instruction(instr, state)
        #
        #  10s: Comparison & Bitwise Logic Operations
        #
        elif instr.is_comparaison_logic:
            self.emul_comparaison_logic_instruction(instr, state)
        #
        #  20s: SHA3
        #
        elif instr.is_sha3:
            self.emul_sha3_instruction(instr, state)
        #
        #  30s: Environment Information
        #
        elif instr.is_environmental:
            self.ssa_environmental_instruction(callinfo, instr, state)
            if instr.name in ("ORIGIN","GASPRICE","BALANCE"):
                self.meet_inconcrete_opcode.add(instr.name)

        #
        #  40s: Block Information
        #
        elif instr.uses_block_info:
            self.ssa_block_instruction(callinfo, instr, state)
            self.meet_inconcrete_opcode.add(instr.name)
            #halt = True
        #
        #  50s: Stack, Memory, Storage, and Flow Information
        #
        elif instr.uses_stack_block_storage_info:
            halt = self.ssa_stack_memory_storage_flow_instruction(callinfo, instr, state)
        #
        #  60s & 70s: Push Operations
        #
        elif instr.name.startswith("PUSH"):
            state._stack.append(instr.operand_interpretation)
        #
        #  80s: Duplication Operations
        #
        elif instr.name.startswith('DUP'):
            # DUPn (eg. DUP1: a b c -> a b c c, DUP3: a b c -> a b c a)
            position = instr.pops  # == XX from DUPXX
            state._stack.append(state._stack[- position])
        #
        #  90s: Swap Operations
        #
        elif instr.name.startswith('SWAP'):
            # SWAPn (eg. SWAP1: a b c d -> a b d c, SWAP3: a b c d -> d b c a)
            position = instr.pops - 1  # == XX from SWAPXX
            temp = state._stack[-position - 1]
            state._stack[-position - 1] = state._stack[-1]
            state._stack[-1] = temp
        #
        #  a0s: Logging Operations
        #
        elif instr.name.startswith('LOG'):
            # only stack operations emulated
            arg = [state._stack.pop() for x in range(instr.pops)]
        #
        #  f0s: System Operations
        #
        elif instr.is_system:
            halt = self.ssa_system_instruction(callinfo, instr, state, debug)
            if instr.name in ("CREATE","CREATE2"):
                self.meet_inconcrete_opcode.add(instr.name)

        # UNKNOWN INSTRUCTION
        else:
            logging.warning('UNKNOWN = ' + instr.name)
            halt = True
        if(debug == True):
            print ('stack: ',list(map(lambda x: x if(type(x)==str) else hex(x),state._stack)))
            print ('storage: ', list(map(lambda x: (hex(x),hex(state.storage[x])),state.storage)))
            print ('memory: ', state.memory)
        # save last opcode to result
        self.result['opcode'] = str(instr.name)
        return halt

    def emul_arithmetic_instruction(self, instr, state):
        op = instr.name

        if op == 'ADD':
            s0 = state._stack.pop()
            s1 = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(s0 + s1)))
        elif op == 'SUB':
            s0 = state._stack.pop()
            s1 = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(s0 - s1)))
        elif op == 'MUL':
            s0 = state._stack.pop()
            s1 = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(s0 * s1)))
        elif op == 'DIV':
            x = state._stack.pop()
            y = state._stack.pop()
            if y == 0:
                state._stack.append(0)
            else:
                state._stack.append(hlp.get_concrete_int(x//y))
        elif op == 'MOD':
            x = state._stack.pop()
            y = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(0 if y == 0 else x % y))
        elif op == 'SDIV':
            x = hlp.to_signed(state._stack.pop())
            y = hlp.to_signed(state._stack.pop())
            sign = 1 if(x*y) >= 0 else -1
            computed = sign*(abs(x)//abs(y)) if(y!=0) else 0
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(computed)))
        elif op == 'SMOD':
            x = hlp.to_signed(state._stack.pop())
            y = hlp.to_signed(state._stack.pop())
            sign = -1 if x < 0 else 1
            computed = sign * (abs(x) % abs(y))
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(computed)))
        elif op == 'EXP':
            x = state._stack.pop()
            y = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(pow(x, y))))
        elif op == 'SIGNEXTEND':
            i = state._stack.pop()
            x = state._stack.pop()
            mask = 2**(8*(i+1))
            sign_max_plus_one = mask >> 1
            x &= mask - 1
            x = x if(x < sign_max_plus_one) else x - mask
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(x)))
        elif op == 'ADDMOD':
            x = state._stack.pop()
            y = state._stack.pop()
            m = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec((x+y)%m)))
        elif op == 'MULMOD':
            x = state._stack.pop()
            y = state._stack.pop()
            m = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec((x*y)%m)))

    def emul_comparaison_logic_instruction(self, instr, state):
        op = instr.name

        if op == 'LT':
            x = state._stack.pop()
            y = state._stack.pop()
            if x < y:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'GT':
            x = state._stack.pop()
            y = state._stack.pop()
            if x > y:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'SLT':
            x = state._stack.pop()
            y = state._stack.pop()
            x = hlp.to_signed(x)
            y = hlp.to_signed(y)
            if x < y:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'SGT':
            x = state._stack.pop()
            y = state._stack.pop()
            x = hlp.to_signed(x)
            y = hlp.to_signed(y)
            if x > y:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'EQ':
            x = state._stack.pop()
            y = state._stack.pop()
            if x == y:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'AND':
            x = state._stack.pop()
            y = state._stack.pop()
            state._stack.append(x&y)
        elif op == 'OR':
            x = state._stack.pop()
            y = state._stack.pop()
            state._stack.append(x|y)
        elif op == 'XOR':
            x = state._stack.pop()
            y = state._stack.pop()
            state._stack.append(x^y)
        elif op == 'BYTE':
            n = state._stack.pop()
            x = state._stack.pop()
            state._stack.append(int((x).to_bytes(32, byteorder="big")[n]))
        elif op == 'ISZERO':
            x = state._stack.pop()
            if x == 0:
                state._stack.append(1)
            else:
                state._stack.append(0)
        elif op == 'NOT':
            x = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(~x)))
        elif op == 'SHL':
            shift = state._stack.pop()
            x = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(x << shift)))
        elif op == 'SHR':
            shift = state._stack.pop()
            x = state._stack.pop()
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(x >> shift)))
        elif op == 'SAR':
            shift = state._stack.pop()
            x = state._stack.pop()
            x = hlp.to_signed(x)
            state._stack.append(hlp.get_concrete_int(hlp.convert_to_bitvec(x >> shift)))

    def emul_sha3_instruction(self, instr, state):
        pos = state._stack.pop()
        n = state._stack.pop()
        sha3 = int(keccak(state.memory[pos:pos+n]).hex(),16)
        state._stack.append(sha3)

    def ssa_environmental_instruction(self, callinfo, instr, state):

        if instr.name in ['ADDRESS', 'ORIGIN', 'CALLER', 'CALLVALUE', 'CALLDATASIZE', 'CODESIZE', 'RETURNDATASIZE', 'GASPRICE']:
            op = instr.name
            if op == 'CALLDATASIZE':
                v = len(callinfo["calldata"]) if(callinfo['calldata']) else 0
                state._stack.append(v)
            elif op == 'CALLVALUE':
                v = callinfo.get('callvalue', 0)
                state._stack.append(v)
            elif op == 'ADDRESS':
                v = callinfo.get('address')
                # = "ADDRESS" if(v == None) else v
                state._stack.append(int(v,16))
            elif op == 'RETURNDATASIZE':
                if(self.has_call):
                    state._stack.append(len(self.return_buffer))
                else:
                    state._stack.append(0)
            elif op == "CODESIZE":
                state._stack.append(callinfo['codesize'])
            elif op == "CALLER":
                caller = callinfo['caller']
                caller = int(caller, 16)
                state._stack.append(caller)
            elif op == "ORIGIN":
                origin = callinfo['origin']
                origin = int(origin, 16)
                state._stack.append(origin)
            elif op == "GASPRICE":
                state._stack.append(self.handler.get_gas_price())

        elif instr.name in ['BALANCE', 'CALLDATALOAD', 'EXTCODESIZE', 'EXTCODEHASH']:
            if instr.name == 'CALLDATALOAD':
                pos = state._stack.pop()
                pos_end = pos + 0x20
                tmp = callinfo['calldata'][pos:pos_end]
                if(len(tmp) < 0x20):
                    tmp += bytes(0x20 - len(tmp))
                v = int(tmp.hex(),16)
                state._stack.append(v)
            elif instr.name == 'EXTCODESIZE':
                ext_addr = int_to_address(state._stack.pop())
                ret = self.handler.get_extCodeSize(ext_addr)
                state._stack.append(ret)
            elif instr.name == 'EXTCODEHASH':
                ext_addr = int_to_address(state._stack.pop())
                ret = self.handler.get_extCodeHash(ext_addr)
                state._stack.append(ret)
            elif instr.name == 'BALANCE':
                ext_addr = int_to_address(state._stack.pop())
                bal = self.handler.get_balance(ext_addr)
                state._stack.append(bal)

        elif instr.name in ['CALLDATACOPY', 'CODECOPY', 'RETURNDATACOPY']:
            dst_offset = state._stack.pop()
            offset = state._stack.pop()
            length = state._stack.pop()
            if(len(state.memory) < dst_offset + length):
                state.memory.mextend( dst_offset + length)
            if( instr.name == 'CALLDATACOPY'):
                if(length > 0):
                    v = callinfo["calldata"][offset:offset+length]
                    state.memory[dst_offset:dst_offset+length] = v
            elif( instr.name == 'CODECOPY'):
                v = self.bytecode[ offset : offset+length]
                state.memory[ dst_offset : dst_offset+length] = v
            elif( instr.name == 'RETURNDATACOPY'):
                state.memory[dst_offset:dst_offset+length] = self.return_buffer[offset:offset+length]


        elif instr.name == 'EXTCODECOPY':
            addr = int_to_address(state._stack.pop())
            dst_offset = state._stack.pop()
            offset = state._stack.pop()
            length = state._stack.pop()
            ext_code = self.handler.get_extCode(addr)
            state.memory[dst_offset:dst_offset+length] = ext_code[offset:offset+length]

    def ssa_block_instruction(self, callinfo, instr, state):

        if instr.name == 'BLOCKHASH':
            blocknumber = state._stack.pop()
            b = self.handler.get_block_by_number(blocknumber)
            state._stack.append(int(b['hash'],16))
        elif instr.name == 'DIFFICULTY':
            state._stack.append(self.handler.get_difficulty())
        elif instr.name == 'CHAINID':
            state._stack.append(1)
        elif instr.name == 'GASLIMIT':
            state._stack.append(self.handler.get_gas_limit())
        elif instr.name == 'BASEFEE':
            state._stack.append(50*10**9) #50 Gwei
        elif instr.name == 'TIMESTAMP':
            state._stack.append(int(time.time()))
        elif instr.name == 'COINBASE':
            state._stack.append(0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb)
        elif instr.name == 'NUMBER':
            state._stack.append(self.handler.get_block_number())
        elif instr.name == 'SELFBALANCE':
            state._stack.append(self.handler.get_balance(callinfo['address']))

    def ssa_stack_memory_storage_flow_instruction(self, callinfo, instr, state):

        halt = False
        op = instr.name

        if op == 'POP':
            state._stack.pop()

        elif op in ['MLOAD', 'SLOAD']:
            if op == 'MLOAD':
                mem_pos = state._stack.pop()
                #mem_end = mem_pos + 0x20
                #mem_val = int(state.memory[mem_pos:mem_end].hex(),16)
                mem_val = state.memory.mload(mem_pos)
                state._stack.append(mem_val)

            if op == 'SLOAD':
                storage_pos = state._stack.pop()
                #storage_val = state.storage[storage_pos]
                storage_val = state.storage.sload(callinfo.get('storage_address'),storage_pos)
                state._stack.append(storage_val)


        elif op in ['MSTORE', 'MSTORE8', 'SSTORE']:
            if op == 'MSTORE':
                pos = state._stack.pop()
                val = state._stack.pop()
                state.memory.mstore(pos,val)
            elif op == 'MSTORE8':
                pos = state._stack.pop()
                val = state._stack.pop()
                state.memory.mstore8(pos,val)

            elif op == 'SSTORE':
                pos = state._stack.pop()
                val = state._stack.pop()
                state.storage.sstore(pos,val)

        elif op == 'JUMP':
            jump_addr = state._stack.pop()
            target = next(filter(lambda element: element.offset == jump_addr, self.instructions))
            if target.name != "JUMPDEST":
                logging.info('[X] Bad JUMP to 0x%x' % jump_addr)
                halt = True
            state.pc = self.instructions.index(target)

        elif op == 'JUMPI':
            jump_addr = state._stack.pop()
            con = state._stack.pop()
            target = next(filter(lambda element: element.offset == jump_addr, self.instructions))
            if target.name != "JUMPDEST":
                logging.info('[X] Bad JUMP to 0x%x' % jump_addr)
                halt = True
            if con:
                state.pc = self.instructions.index(target)

        elif op in ['PC', 'MSIZE', 'GAS']:
            if(op == 'PC'):
                state._stack.append(state.pc-1)
            elif(op == 'GAS'):
                state._stack.append(state.gas)
            elif(op == 'MSIZE'):
                state._stack.append(len(state.memory))

        elif op == 'JUMPDEST':
            pass

        return halt

    def ssa_system_instruction(self, callinfo, instr, state, debug=False):

        halt = False

        if instr.name == 'CREATE':
            value = state._stack.pop()
            offset = state._stack.pop()
            length = state._stack.pop()
            (create_success, create_address) = self.handler.create( callinfo.copy(), state.memory[offset:offset+length], debug)
            state._stack.append(create_address)
            if not create_success:
                halt = True
            #halt = True

        elif instr.name in ('CALL', 'CALLCODE', 'DELEGATECALL', 'STATICCALL'):
            self.has_call = True
            if instr.name in ('CALL', 'CALLCODE'):
                gas = state._stack.pop()
                addr = int_to_address(state._stack.pop())
                value = state._stack.pop()
                arg_offset = state._stack.pop()
                arg_length = state._stack.pop()
                ret_offset = state._stack.pop()
                ret_length = state._stack.pop()
                pass_callinfo = callinfo.copy()
                pass_callinfo['calldata'] = state.memory[arg_offset:arg_offset+arg_length]
                pass_callinfo['address'] = addr
                if(instr.name == 'CALL'):
                    pass_callinfo['storage_address'] = addr
                pass_callinfo['gas'] = gas
                pass_callinfo['value'] = value
                pass_callinfo['caller'] = callinfo['address']
                (call_result,_) = self.handler.call(pass_callinfo.copy(), debug)
                if(call_result.get('opcode','ERROR') in ['RETURN, REVERT']):
                    state._stack.append(call_result['success'])
                    self.return_buffer = call_result['return_data']
                    state.memory[ret_offset:ret_offset+ret_length] = self.return_buffer[:ret_length]
                else:
                    self.result['callinfo'] = pass_callinfo
                    self.result['call_result'] = call_result
                    halt = True

            else:
                gas = state._stack.pop()
                addr = int_to_address(state._stack.pop())
                arg_offset = state._stack.pop()
                arg_length = state._stack.pop()
                ret_offset = state._stack.pop()
                ret_length = state._stack.pop()
                #halt = True
                #save the result
                pass_callinfo = callinfo.copy()
                pass_callinfo['calldata'] = state.memory[arg_offset:arg_offset+arg_length]
                pass_callinfo['address'] = addr
                pass_callinfo['gas'] = gas
                if instr.name != 'DELEGATECALL':
                    pass_callinfo['storage_address'] = addr
                (call_result, delegate_info) = self.handler.call(pass_callinfo.copy(), debug)
                if(call_result.get('opcode','ERROR') in ['RETURN', 'REVERT']):
                    state._stack.append(call_result['success'])
                    self.return_buffer = call_result['return_data']
                    state.memory[ret_offset:ret_offset+ret_length] = self.return_buffer[:ret_length]
                else:
                    self.result['callinfo'] = pass_callinfo
                    self.result['call_result'] = call_result
                    halt = True
                if(instr.name == 'DELEGATECALL'):
                    tmp = pass_callinfo.copy()
                    tmp["arg_offset"] = arg_offset
                    tmp["arg_length"] = arg_length
                    tmp['call_result'] = call_result
                    tmp['delegate_info'] = delegate_info
                    self.delegate_info.append(tmp)

        elif instr.name == 'CREATE2':
            value = state._stack.pop()
            offset = state._stack.pop()
            length = state._stack.pop()
            salt = state._stack.pop()
            (create_success, create_address) = self.handler.create( callinfo.copy(), state.memory[offset:offset+length], debug)
            state._stack.append(create_address)
            if not create_success:
                halt = True
            #halt = True

        elif instr.name in ['RETURN', 'REVERT']:
            offset = state._stack.pop()
            length = state._stack.pop()
            self.result["opcode"] = str(instr.name)
            self.result["return_data"] = state.memory[offset:offset+length]
            self.result["success"] = 1 if(instr.name == 'RETURN') else 0
            halt = True

        elif instr.name in ['INVALID', 'SELFDESTRUCT']:
            halt = True

        return halt


class EthereumSSAEngine(EthereumEmulatorEngine):

    def __init__(self, bytecode=None, explorer=None):
        EthereumEmulatorEngine.__init__(self, bytecode, explorer)

class Handler():
    def __init__(self, explorer):
        self.explorer = explorer
        # fetch the latest block
        self.b = self.get_block_by_number(self.get_block_number())
        #if create any contract, address start from 0xdddddddddddddddddddddddddddddddddddddddd
        self.create_address = 0xdddddddddddddddddddddddddddddddddddddddd
        self.create_code = {}
    # return result
    def call(self, callinfo, debug=False) -> (dict,list):
        addr = callinfo['address']
        code = None
        code_size = 0
        if addr in self.create_code:
            code = self.create_code[addr]
            code_size = len(code)
        else:
            code = self.explorer.eth_getCode(addr)
            code_size = len(code[2:]) // 2
        callinfo['codesize'] = code_size
        state = EthereumVMstate(self.explorer)
        emul = EthereumSSAEngine(code, self.explorer)
        emul.emulate(callinfo.copy(), state, debug)
        return (emul.get_result(), emul.get_delegate_info())

    def get_extCodeSize(self, addr) -> int:
        code = None
        code_size = 0
        if addr in self.create_code:
            code = self.create_code[addr]
            code_size = len(code)
        else:
            code = self.explorer.eth_getCode(addr)
            code_size = len(code[2:]) // 2
        return code_size

    def get_extCodeHash(self, addr) -> int:
        code = None
        if addr in self.create_code:
            code = self.create_code[addr]
        else:
            code = self.explorer.eth_getCode(addr)
            code = bytes.fromhex(code[2:])
        code_hash = int(keccak(code).hex(),16)
        return code_hash

    def get_balance(self, addr) -> int:
        bal = self.explorer.eth_getBalance(addr)
        return bal

    def get_extCode(self, addr) -> bytes:
        code = None
        if addr in self.create_code:
            code = self.create_code[addr]
        else:
            code = self.explorer.eth_getCode(addr)
            code = bytes.fromhex(code[2:])
        return code

    def get_block_number(self) -> int:
        return self.explorer.eth_blockNumber()

    def get_block_by_number(self, num) -> dict:
        return self.explorer.get_block_by_number(num)

    def get_difficulty(self) -> int:
        return int(self.b['difficulty'],16)

    def get_gas_limit(self) -> int:
        return int(self.b['gasLimit'],16)

    def get_gas_price(self) -> int:
        return self.explorer.eth_gasPrice()

    def create(self, callinfo,  init_bytecode, debug=False):
        callinfo['codesize'] = len(init_bytecode)
        state = EthereumVMstate(self.explorer)
        emul = EthereumSSAEngine(init_bytecode, self.explorer)
        emul.emulate(callinfo.copy(), state, debug)
        result = emul.get_result()
        if result['opcode'] == "RETURN":
            address = self.create_address
            self.create_address += 1
            self.create_code[int_to_address(address)] = result["return_data"]
            return (True, address)
        else:
            return (False, 0)

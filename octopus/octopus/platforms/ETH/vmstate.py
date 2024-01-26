from octopus.core.memory import Memory
from octopus.core.storage import Storage
from octopus.engine.engine import VMstate


class EthereumVMstate(VMstate):

    def __init__(self, explorer, gas=1000000):
        self.storage = Storage(explorer)
        self.memory = Memory()
        self._stack = []
        self.gas = gas
        self.pc = 0
        self.instr = None

        self.instructions_visited = list()

    def details(self):

        return {'storage': self.storage,
                'memory': self.memory,
                'stack': self._stack,
                'gas': self.gas,
                'pc': self.pc}

    def mem_extend(self, start, sz):

        if (start < 4096 and sz < 4096):

            if sz and start + sz > len(self.memory):

                n_append = start + sz - len(self.memory)

                while n_append > 0:
                    self.memory.append(0)
                    n_append -= 1

        else:
            raise Exception

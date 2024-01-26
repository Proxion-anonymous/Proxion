#rpc

class  Storage(dict):
    """docstring for  Memory"""
    def __init__(self, explorer):
        super()
        #rpc
        self.explorer = explorer

    def sstore(self, p, v):
        self[p] = v

    def sload(self, addr, p):
        if not self.get(p):
            if(addr):
                self[p] = int(self.explorer.eth_getStorageAt(addr, p),16)
            else:
                self[p] = 0
        v = self[p]
        return v

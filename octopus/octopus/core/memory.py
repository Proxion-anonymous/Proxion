class  Memory(bytearray):
    """docstring for  Memory"""
    def __init__(self, l=0):
        super(Memory, self).__init__(l)
        
    def mstore(self, p,v):
        if len(self) < p+0x20:
            self.mextend(p+0x20)
        self[p:p+0x20] = (v).to_bytes(32, byteorder="big")

    def mstore8(self,p,v):
        if len(self) < p:
            self.mextend(p)
        self[p:p] = (v).to_bytes(1, byteorder="big")

    def mload(self,p):
        if len(self) < p+0x20:
            self.mextend(p+0x20)
        v = int(self[p:p+0x20].hex(),16)
        return v

    def mextend(self,p):
        self.extend(bytearray(p))
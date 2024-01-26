import sys
sys.path.append('..')

from octopus.platforms.ETH.disassembler import EthereumDisassembler
from octopus.platforms.ETH.explorer import EthereumInfuraExplorer
from octopus.platforms.ETH.explorer import INFURA_MAINNET
from octopus.platforms.ETH.explorer import EthereumExplorerRPC
import json


INFURA_KEY = "d449de4b0a0c4c2ca8d60fcd0fc544d9"
#INFURA_KEY = "9d821f5839de4d79a55f5e140c858998"
explorer = EthereumInfuraExplorer(INFURA_KEY,network=INFURA_MAINNET)
#explorer = EthereumExplorerRPC(host="api.archivenode.io/011d01c6-2d76-4b54-8232-6594feedcdc6",port=443,tls=True)
bytecode_map = {}
#with open('data/bytecode_map2019','r') as f:
#    bytecode_map = json.load(f)

start = 0
with open('proxy_addresses','r') as lines:
    for i in range(start): # start from {start} line
        next(lines)

    for i in lines:
        addr = i.strip()
        print(start)
        print(addr)
        try:
            if(bytecode_map.get(addr) != None):
                #log.write(addr + " duplicate \n")
                print("duplicate")
                continue
            bytecode = explorer.eth_getCode(addr)
            bytecode_map[addr] = bytecode
        except Exception as e:
            print(e)
            #print("start:",start)
            break
        start += 1
with open('proxy_addr_map','w') as f:
    json.dump(bytecode_map, f)

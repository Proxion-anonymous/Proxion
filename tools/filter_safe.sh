#!/bin/sh
# Filter out Safe wallets from the results of proxy contracts.
ag -li '(0x8942595A2dC5181Df0465AF0D7be08c8f23C93af)|(0xb6029EA3B2c51D09a50B53CA8012FeEB05bDa35A)|(0xaE32496491b53841efb51829d6f886387708F99B)|(0x34CfAC646f301356fAa8B21e94227e3583Fe3F5F)|(0x6851D6fDFAfD08c0295C392436245E5bc78B0185)|(0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552)' "$@"

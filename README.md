# Proxion - ICDCS 2024 Submission

This is the repo for reviewing our submission “Uncovering All Proxy Smart Contracts in Ethereum”
in ICDCS 2024.

The raw data of our studies elaborated in our submission is available at:
https://drive.google.com/drive/folders/1FHCxSYq5jNnBRo7sWKAmWZkypFRGMlww?usp=sharing

## Description

Proxion is a tool for inspecting proxy smart contracts in Ethereum. Its features include:
- Determine if a smart contract is a proxy smart contract, and if it follows any proxy standards
  (e.g. ERC-1167, ERC-1822, ERC-1967, ERC-2535).
- Identifying the current and previous logic (a.k.a. implementation) contracts.
- Checking for potential function collision and storage collision problems in a proxy smart
  contract and its logic smart contracts
  - Based on [slither-check-upgradeability](https://github.com/crytic/slither/wiki/Upgradeability-Checks),
    which requires the smart contract's source code be verified on [Etherscan](https://etherscan.io/contractsVerified).
  - If the source code is not available, a bytecode-based analysis is conducted, though at a lower accuracy.

## Requirements

- An Ethereum archive node to obtain the bytecode for analysis
- An Etherscan API key to obtain the source code for analysis
- Python 3.10 with pip

An Etherscan API key and an Infura archive node API key is included by default, and can be
changed in `proxion/Config.py`.

## Setup Guide

Run `./setup.sh` to complete the setup. It does the following:
1. Install `poetry` via `pip` if not exists
2. Create a virtual environment and install the dependent packages
3. Install *all versions* of solc compilers via `solc-select`
4. Spawn a shell inside the poetry virtual environment

## Execution Guide

Run the tool by:
```shell
python3 -m proxion --source-prefix dir_to_keep_source_code 0x95a3946104132973b00ec0a2f00f7cc2b67e751f
```

The output has 3 sections in JSON format:
```json
{
  "proxy_info": { /* the proxy information ... */ },
  "slither": { /* function collision & storage collision check via Slither ... */ },
  "adv_check": { /* bytecode-based function/storage collision analysis in
                    case source code is not available ... */ }
}

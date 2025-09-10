import os
import argparse
import time
import ipfshttpclient
from web3 import Web3
from solcx import compile_source, install_solc


CONTRACT_SOURCE = '''
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract IPFSStorage {
    struct Record { string ipfsHash; uint256 timestamp; address uploader; }
    event RecordAdded(string ipfsHash, uint256 timestamp, address uploader);
    mapping(uint256 => Record) public records; uint256 public recordCount;
    function addRecord(string memory _ipfsHash) public {
        records[recordCount] = Record(_ipfsHash, block.timestamp, msg.sender);
        emit RecordAdded(_ipfsHash, block.timestamp, msg.sender);
        recordCount++;
    }
    function getRecord(uint256 _id) public view returns (string memory, uint256, address) {
        require(_id < recordCount, "Record does not exist.");
        Record memory r = records[_id];
        return (r.ipfsHash, r.timestamp, r.uploader);
    }
}
'''


def connect_ipfs(addr: str):
    return ipfshttpclient.connect(addr)


def deploy_contract(w3: Web3):
    install_solc('0.8.0')
    compiled = compile_source(CONTRACT_SOURCE, output_values=['abi', 'bin'], solc_version='0.8.0')
    _, iface = compiled.popitem()
    contract = w3.eth.contract(abi=iface['abi'], bytecode=iface['bin'])
    tx_hash = contract.constructor().transact()
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.eth.contract(address=rcpt.contractAddress, abi=iface['abi'])


def upload_file(client, path: str) -> str:
    res = client.add(path)
    return res['Hash']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=str, default=os.path.join(os.path.dirname(__file__), '..', 'outputs'))
    p.add_argument('--ipfs-address', type=str, default='/ip4/127.0.0.1/tcp/5001/http')
    p.add_argument('--ganache-url', type=str, default='http://127.0.0.1:7545')
    args = p.parse_args()

    # Connect IPFS
    client = connect_ipfs(args.ipfs_address)

    # Connect chain
    w3 = Web3(Web3.HTTPProvider(args.ganache_url))
    if not w3.is_connected():
        raise RuntimeError('Cannot connect to Ganache. Make sure it runs at 7545.')
    if not w3.eth.accounts:
        raise RuntimeError('No accounts from Ganache.')
    w3.eth.default_account = w3.eth.accounts[0]

    # Deploy contract
    print('[+] Deploying IPFSStorage...')
    contract = deploy_contract(w3)
    print(f'[OK] Contract at {contract.address}')

    # Upload all files under inputs
    files = [os.path.join(args.inputs, f) for f in os.listdir(args.inputs) if os.path.isfile(os.path.join(args.inputs, f))]
    files.sort()
    for f in files:
        print(f'[*] Uploading {os.path.basename(f)} to IPFS...')
        t0 = time.time()
        cid = upload_file(client, f)
        t1 = time.time()
        print(f'    CID={cid}, upload_time={t1 - t0:.2f}s')

        txh = contract.functions.addRecord(cid).transact()
        w3.eth.wait_for_transaction_receipt(txh)
        rid = contract.functions.recordCount().call() - 1
        stored, ts, who = contract.functions.getRecord(rid).call()
        ok = (stored == cid)
        print(f'    on-chain verify: id={rid}, ok={ok}')


if __name__ == '__main__':
    main()


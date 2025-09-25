// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract RecordCID {
    event CIDRecorded(address indexed sender, string cid, string path);
    struct Entry { string cid; string path; uint256 blockTime; }
    Entry[] public entries;
    function record(string calldata cid, string calldata path) external {
        entries.push(Entry({cid: cid, path: path, blockTime: block.timestamp}));
        emit CIDRecorded(msg.sender, cid, path);
    }
    function count() external view returns (uint256) { return entries.length; }
    function get(uint256 i) external view returns (string memory, string memory, uint256) {
        Entry storage e = entries[i];
        return (e.cid, e.path, e.blockTime);
    }
}

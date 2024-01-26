-- Associate contracts with their source code
CREATE TABLE source_address AS
SELECT t.address, s.address, 0::smallint AS kind as source_address
FROM contracts_all_latest t
JOIN bytecode_hash h USING (address, block_number)
JOIN contract_sanctuary_by_hash s
ON h.bytecode_hash = s.bytecode_hash
AND h.bytecode_hash != '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470' -- empty bytecode

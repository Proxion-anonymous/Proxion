CREATE TABLE "b1-past-contracts-with-source-5951198" AS
SELECT address, year, block_number, is_proxy, implementations || current_implementation
FROM contracts_all_latest
JOIN source_address USING (address)
JOIN bytecode_hash_latest USING (address)
JOIN proxy_info USING (address, block_number)
WHERE bytecode_hash != '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470'
;

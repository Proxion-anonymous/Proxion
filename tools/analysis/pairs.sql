WITH t AS (
    SELECT DISTINCT address, UNNEST(implementations || current_implementation) AS impl
    FROM contract_sanctuary_by_hash a
    JOIN proxy_info b USING (address, block_number)
    WHERE is_proxy
)
SELECT t.address, s1.address, s1.name, s1.compiler, t.impl, s2.address, s2.name, s2.compiler
FROM t
JOIN bytecode_hash_latest h1 ON t.address = h1.address
JOIN contract_sanctuary_by_hash s1 ON h1.bytecode_hash = s1.bytecode_hash
JOIN bytecode_hash_latest h2 ON t.impl = h2.address
JOIN contract_sanctuary_by_hash s2 ON h2.bytecode_hash = s2.bytecode_hash

---

WITH t AS (
    SELECT DISTINCT address, UNNEST(implementations || current_implementation) AS impl
    FROM contracts_all_latest a
    JOIN proxy_info b USING (address, block_number)
    WHERE is_proxy
)
SELECT t.address, s1.address AS addr_s, t.impl, s2.address AS impl_s FROM t
JOIN source_address s1 ON t.address = s1.address
JOIN source_address s2 ON t.impl = s2.address

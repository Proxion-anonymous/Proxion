-- https://console.cloud.google.com/marketplace/product/ethereum/crypto-ethereum-blockchain
-- Count contracts before 2023-10-31
WITH SubQuery AS (
    SELECT EXTRACT(YEAR FROM block_timestamp) as year, COUNT(*) as count
    FROM `bigquery-public-data.crypto_ethereum.contracts`
    WHERE TIMESTAMP_TRUNC(block_timestamp, DAY) <= TIMESTAMP("2023-10-31")
    GROUP BY ROLLUP(year)
    ORDER BY year
)
SELECT TO_JSON(ARRAY_AGG(SubQuery))
FROM SubQuery

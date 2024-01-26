SELECT COUNT(*)
FROM slither_result a
JOIN contracts_all_latest b ON a.address1 = b.address
WHERE collisions && ARRAY['incorrect-variables-with-the-proxy', 'incorrect-variables-with-the-v2']::character varying[]

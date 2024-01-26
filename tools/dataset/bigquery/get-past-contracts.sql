-- Get all contract addresses before 2023-10-31 from BigQuery:
-- https://console.cloud.google.com/marketplace/product/ethereum/crypto-ethereum-blockchain
SELECT address, EXTRACT(YEAR FROM block_timestamp) as year, block_number
    FROM `bigquery-public-data.crypto_ethereum.contracts`
    WHERE TIMESTAMP_TRUNC(block_timestamp, DAY) <= TIMESTAMP("2023-10-31")


-- Create a local table storing the results exported from BigQuery
CREATE TABLE contracts_all (
    id integer NOT NULL,
    address character(42) NOT NULL,
    year smallint NOT NULL,
    block_number integer NOT NULL
);
CREATE SEQUENCE contracts_all_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
COPY contracts_all (address, year, block_number)
    FROM 'contracts.csv' CSV DELIMITER ',' HEADER QUOTE '"';


-- Create a table with unique (address, block_number) pairs
-- So that every version of a contract is a unique row in the table
CREATE TABLE contracts_all_unique AS
    SELECT DISTINCT ON (address, block_number)
           address, block_number, year, id
    FROM contracts_all
    ORDER BY address, block_number;

ALTER TABLE ONLY contracts_all_unique
    ADD CONSTRAINT contracts_all_unique_address_block_number PRIMARY KEY (address, block_number);


-- Create a table with the latest version of each contract
CREATE TABLE contracts_all_latest AS
    SELECT DISTINCT ON (address)
           address, block_number, year, id
    FROM contracts_all
    ORDER BY address, block_number DESC;

ALTER TABLE ONLY contracts_all_latest
    ADD CONSTRAINT contracts_all_latest_address PRIMARY KEY (address);

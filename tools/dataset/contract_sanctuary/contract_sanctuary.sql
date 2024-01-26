-- Import from Smart Contract Sanctuary:
-- https://github.com/tintinweb/smart-contract-sanctuary-ethereum/blob/master/contracts/mainnet/contracts.json
CREATE TABLE public.contract_sanctuary (
    id integer NOT NULL,
    name character varying(128),
    balance character varying(64),
    compiler character varying(16),
    address character(42) NOT NULL,
    date character varying(16) NOT NULL,
    settings character(1),
    txcount integer NOT NULL,
    err character varying(128)
);

CREATE SEQUENCE public.contract_sanctuary_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.contract_sanctuary_id_seq OWNED BY public.contract_sanctuary.id;

ALTER TABLE ONLY public.contract_sanctuary
    ADD CONSTRAINT contract_sanctuary_pkey PRIMARY KEY (id);

COPY contract_sanctuary (name,balance,compiler,address,date,settings,txcount,err)
    FROM 'contracts.csv' CSV DELIMITER ',' HEADER QUOTE '"';


-- Index the contract sanctuary table by SHA3 hash of bytecode
CREATE TABLE contract_sanctuary_by_hash AS
    SELECT DISTINCT ON (bytecode_hash)
           bytecode_hash, b.address, block_number, name, compiler, a.id
    FROM contract_sanctuary a
    LEFT JOIN bytecode_hash_latest b ON LOWER(a.address) = b.address
    ORDER BY bytecode_hash;

ALTER TABLE ONLY public.contract_sanctuary_by_hash
    ADD CONSTRAINT contract_sanctuary_by_hash_bytecode_hash PRIMARY KEY (bytecode_hash);

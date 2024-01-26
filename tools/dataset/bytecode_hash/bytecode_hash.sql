CREATE TABLE public.bytecode_hash (
    address character(42) NOT NULL,
    block_number integer NOT NULL,
    bytecode_hash character(66) NOT NULL
);

CREATE TABLE public.bytecode_hash_latest (
    address character(42) NOT NULL,
    block_number integer NOT NULL,
    bytecode_hash character(66) NOT NULL
);

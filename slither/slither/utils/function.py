from hashlib import sha3_256


def get_function_id(sig: str) -> int:
    """'
        Return the function id of the given signature
    Args:
        sig (str)
    Return:
        (int)
    """
    s = sha3_256()
    s.update(sig.encode("utf-8"))
    return int("0x" + s.hexdigest()[:8], 16)

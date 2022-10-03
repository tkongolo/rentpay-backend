from random import randrange

CHARSET = 'ABCDEFGHJKLMNPQRSTUVWXYZ123456789'


def generate_code(existing: list, size: int = 5, max_tries: int = 32,
                  prefix: str = '', charset: str = CHARSET) -> str:
    iteration = 0
    unique = False
    code = prefix

    while not unique:
        if iteration < max_tries:
            for i in range(size):
                code += charset[randrange(0, len(charset))]
                if code not in existing:
                    unique = True
                iteration += 1
        else:
            raise ValueError("Couldn't generate a unique code")

    return code

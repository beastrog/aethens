# Converted by bench/external/convert.py from HumanEval (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/31. Do not edit by hand; re-run the converter.


def is_prime(n):
    """Return true if a given number is prime, and false otherwise.
    >>> is_prime(6)
    False
    >>> is_prime(101)
    True
    >>> is_prime(11)
    True
    >>> is_prime(13441)
    True
    >>> is_prime(61)
    True
    >>> is_prime(4)
    False
    >>> is_prime(1)
    False
    """
    if n < 2:
        return False
    for k in range(2, n - 1):
        if n % k == 0:
            return False
    return True

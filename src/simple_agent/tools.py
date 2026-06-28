"""Arithmetic tools available to SimpleAgent."""

from langchain_core.tools import tool


@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First integer.
        b: Second integer.
    """
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiplies `a` and `b`.

    Args:
        a: First integer.
        b: Second integer.
    """
    return a * b


@tool
def divide(a: int, b: int) -> float:
    """Divides `a` by `b`.

    Args:
        a: Numerator.
        b: Denominator (must not be zero).
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


DEFAULT_TOOLS = [add, multiply, divide]

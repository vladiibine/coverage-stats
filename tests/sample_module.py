"""Sample module used by tests to verify coverage-stats tracking."""


class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b

    def multiply(self, a: int, b: int) -> int:
        return a * b


def standalone_function(x: int) -> int:
    if x > 0:
        return x * 2
    return 0

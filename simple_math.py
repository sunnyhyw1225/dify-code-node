def main(a: float, b: float) -> dict:
    result = a + b

    return {
        "a": a,
        "b": b,
        "operation": "addition",
        "result": result
    }
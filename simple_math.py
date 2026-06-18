def main(a: float, b: float) -> dict:
    result = a + b

    return {
        "a": str(a),
        "b": str(b),
        "operation": "addition",
        "result": str(result)
    }
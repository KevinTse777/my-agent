def calculate(expression: str) -> float:
    """
    仅支持四则运算
    学习阶段简化实现
    """
    allowed_chars = set("0123456789+-*/(). ")
    if not expression or any(ch not in allowed_chars for ch in expression):
        raise ValueError("Expression contains invalid characters")

    try:
        result = eval(expression, {"__builtins__": {}}, {})
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}") from e

    if not isinstance(result, (int, float)):
        raise ValueError("Expression did not return a number")

    return float(result)
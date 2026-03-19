from langchain.tools import tool

from app.tools.calculator import calculate


@tool
def calculator_tool(expression: str) -> str:
    """计算数学表达式，例如: (2+3)*4。"""
    result = calculate(expression)
    return str(result)

from langchain.tools import tool

from app.tools.calculator import calculate
from app.tools.search_mock import search_mock


@tool
def calculator_tool(expression: str) -> str:
    """计算数学表达式，例如: (2+3)*4。"""
    result = calculate(expression)
    return str(result)

@tool
def search_mock_tool(query: str) -> str:
    """从本地的模拟索引中搜索相关知识，搜索主要用于查阅事实相关的问题。"""
    return search_mock(query)
    
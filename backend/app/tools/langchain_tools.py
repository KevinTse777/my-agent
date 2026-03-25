import logging
import time
import json

from langchain.tools import tool

from app.tools.calculator import calculate
from app.tools.search_mock import search_mock
from app.tools.search_web import search_web_structured, search_web_text

logger = logging.getLogger("app.tools")

@tool
def calculator_tool(expression: str) -> str:
    """计算数学表达式，例如: (2+3)*4。"""
    start = time.perf_counter()
    try:
        result = calculate(expression)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=calculator_tool success=true input=%r duration_ms%.2f",
            expression,
            duration_ms,
        )
        return str(result)
    except Exception as e:
        duration_ms = (time.perf_counter - start) * 1000
        logger.exception(
            "tool=calculator_tool success=false input=%r duration_ms=%.2f error=%s",
            expression,
            duration_ms,
            str(e),
        )
        raise
    

@tool
def search_mock_tool(query: str) -> str:
    """Search study knowledge from a local mock index. Use for factual lookup questions."""
    start = time.perf_counter()
    try:
        result = search_mock(query)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=search_mock_tool success=true input=%r duration_ms=%.2f",
            query,
            duration_ms,
        )
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "tool=search_mock_tool success=false input=%r duration_ms=%.2f error=%s",
            query,
            duration_ms,
            str(e),
        )
        raise
    

@tool
def web_search_tool(query: str) -> str:
    """Search the public web for factual, up-to-date information."""
    start = time.perf_counter()
    try:
        data = search_web_structured(query=query, max_results=3)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=web_search_tool success=true input=%r duration_ms=%.2f",
            query,
            duration_ms,
        )
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "tool=web_search_tool success=false input=%r duration_ms=%.2f error=%s",
            query,
            duration_ms,
            str(e),
        )
        raise
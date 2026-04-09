import logging
import json
import time

from langchain.tools import tool

from app.core.config import settings
from app.tools.calculator import calculate
from app.tools.search_web import search_web_structured
from app.tools.tool_runtime import ToolTimeoutError, run_with_timeout

logger = logging.getLogger("app.tools")

def _run_calculator_tool(expression: str) -> str:
    start = time.perf_counter()
    try:
        result = run_with_timeout(
            calculate,
            expression,
            timeout_seconds=max(0.1, settings.calculator_tool_timeout_seconds),
            timeout_message="calculator_tool timed out",
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=calculator_tool success=true input=%r duration_ms=%.2f",
            expression,
            duration_ms,
        )
        return str(result)
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "tool=calculator_tool success=false input=%r duration_ms=%.2f error=%s",
            expression,
            duration_ms,
            str(e),
        )
        raise


@tool
def calculator_tool(expression: str) -> str:
    """计算数学表达式，例如: (2+3)*4。"""
    return _run_calculator_tool(expression)


def _run_web_search_tool(query: str) -> str:
    start = time.perf_counter()
    try:
        data = run_with_timeout(
            search_web_structured,
            query=query,
            max_results=3,
            timeout_seconds=max(0.1, settings.web_search_tool_timeout_seconds),
            timeout_message="web_search_tool timed out",
        )
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "tool=web_search_tool success=true input=%r duration_ms=%.2f",
            query,
            duration_ms,
        )
        return json.dumps(data, ensure_ascii=False)
    except ToolTimeoutError as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.warning(
            "tool=web_search_tool success=false timeout=true input=%r duration_ms=%.2f error=%s",
            query,
            duration_ms,
            str(e),
        )
        return json.dumps(
            {
                "query": query,
                "count": 0,
                "sources": [],
                "error": "timeout",
                "message": "Web search timed out before a result was returned.",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "tool=web_search_tool success=false input=%r duration_ms=%.2f error=%s",
            query,
            duration_ms,
            str(e),
        )
        raise


@tool
def web_search_tool(query: str) -> str:
    """Search the public web for factual, up-to-date information."""
    return _run_web_search_tool(query)

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def search_web_structured(query: str, max_results: int = 3) -> dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not set")

    try:
        from tavily import TavilyClient
    except ImportError as e:
        raise RuntimeError(
            "tavily-python is not installed. Run: pip install tavily-python"
        ) from e

    client = TavilyClient(api_key=api_key)
    resp = client.search(query=query, max_results=max_results)

    items = []
    for item in resp.get("results", []):
        items.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
        )

    return {
        "query": query,
        "count": len(items),
        "sources": items,
    }


def search_web_text(query: str, max_results: int = 3) -> str:
    data = search_web_structured(query=query, max_results=max_results)
    if not data["sources"]:
        return "No web results found."

    lines = []
    for i, s in enumerate(data["sources"], start=1):
        lines.append(
            f"[{i}] {s['title']}\nURL: {s['url']}\nSnippet: {s['snippet']}"
        )
    return "\n\n".join(lines)

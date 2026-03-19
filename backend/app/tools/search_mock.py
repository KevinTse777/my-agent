def search_mock(query: str) -> str:
    q = query.lower()

    if "fastapi" in q:
        return "FastAPI is a modern Python web framework for building APIs with high performance."
    if "langchain" in q:
        return "LangChain is a framework for building LLM applications with tools, chains, and agents."
    if "agent" in q:
        return "An agent is an LLM-driven system that can decide whether to call tools before answering."

    return f"No exact match found for '{query}'. Suggest refining the query."

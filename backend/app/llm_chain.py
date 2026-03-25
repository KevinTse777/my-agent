from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings

def build_basic_chain():
    api_key = settings.dashscope_api_key
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not set in environment variables.")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一个简洁、友好的学习助手。"),
            ("human", "{user_input}"),
        ]
    )

    llm = ChatOpenAI(
        model=settings.model_name,
        api_key=api_key,
        base_url=settings.dashscope_base_url,
        temperature=0,
    )

    parser = StrOutputParser()
    chain = prompt | llm | parser
    return chain

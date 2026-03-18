import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")
model_name = os.getenv("MODEL_NAME", "qwen-plus")
base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


def build_basic_chain():
    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not set in environment variables.")
    
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是一个简洁、友好的学习助手。"),
            ("human", "{user_input}"),
        ]
    )

    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )

    parser = StrOutputParser()
    chain = prompt | llm | parser
    return chain
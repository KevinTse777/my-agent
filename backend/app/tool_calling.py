import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from app.core.config import settings

from app.tools.calculator import calculate

load_dotenv()

api_key = settings.dashscope_api_key
model_name = settings.model_name
base_url = settings.dashscope_base_url

client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None


def chat_with_auto_tool(user_message: str) -> dict:
    if client is None:
        raise ValueError("DASHSCOPE_API_KEY is not set")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "计算数学表达式，例如 (2+3)*4",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "只包含数字和 +-*/(). 的表达式",
                        }
                    },
                    "required": ["expression"],
                },
            },
        }
    ]

    messages = [
        {
            "role": "system",
            "content": "你是学习助手。遇到需要精确计算的问题，必须调用 calculator 工具，不要心算。",
        },
        {"role": "user", "content": user_message},
    ]

    first = client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    assistant_msg = first.choices[0].message
    tools_used = []

    if assistant_msg.tool_calls:
        messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_msg.tool_calls
                ],
            }
        )

        for tc in assistant_msg.tool_calls:
            if tc.function.name != "calculator":
                continue

            args = json.loads(tc.function.arguments or "{}")
            expression = args.get("expression", "")
            result = calculate(expression)
            tools_used.append("calculator")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": "calculator",
                    "content": str(result),
                }
            )

        second = client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        final_answer = second.choices[0].message.content or ""
        return {"answer": final_answer, "tools_used": tools_used}

    return {"answer": assistant_msg.content or "", "tools_used": tools_used}

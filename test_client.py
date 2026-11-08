#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线自测：拉起 answer-card server，模拟一次填表和提交。"""

import asyncio
import json
from pathlib import Path

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = str(Path(__file__).with_name("server.py"))


FORM_CALLS: list[dict] = []


async def on_elicit(context, params):
    schema = params.requested_schema
    props = schema.get("properties", {})
    answers = {}
    for name, prop in props.items():
        answers[name] = 1.5 if prop.get("type") == "number" else "文本"
    FORM_CALLS.append({"message": params.message, "fields": list(props)})
    print("FORM title:", params.message)
    print("FORM fields:", list(props))
    return types.ElicitResult(action="accept", content=answers)


async def main():
    params = StdioServerParameters(
        command="uv",
        args=["run", "-q", "--with", "mcp>=2,<3", "--no-project", SERVER],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, elicitation_callback=on_elicit) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS:", [tool.name for tool in tools.tools])

            pong = await session.call_tool("ping", {})
            print("PING:", pong.content[0].text)

            result = await session.call_tool(
                "ask_blanks",
                {
                    "title": "自测",
                    "template": "周转时间 = {a_start}，等待时间 = {a_finish}",
                    "fields": [
                        {"name": "a_start", "label": "A · 开始", "type": "number"},
                        {"name": "a_finish", "label": "A · 完成", "type": "number"},
                        {"name": "note", "label": "备注", "type": "text"},
                    ],
                },
            )
            print("ASK:", result.content[0].text)
            print("PARSED:", json.loads(result.content[0].text))

            FORM_CALLS.clear()
            wizard = await session.call_tool(
                "ask_pages",
                {
                    "title": "自测",
                    "template": "A 行：{a_start}/{a_finish}；B 行：{b_start}/{b_finish}",
                    "pages": [
                        {
                            "title": "第 1/2 页 · 进程 A",
                            "fields": [
                                {"name": "a_start", "label": "开始", "type": "number"},
                                {"name": "a_finish", "label": "完成", "type": "number"},
                            ],
                        },
                        {
                            "title": "第 2/2 页 · 进程 B",
                            "fields": [
                                {"name": "b_start", "label": "开始", "type": "number"},
                                {"name": "b_finish", "label": "完成", "type": "number"},
                            ],
                        },
                    ],
                },
            )
            print("WIZARD:", wizard.content[0].text)
            print("WIZARD PARSED:", json.loads(wizard.content[0].text))
            print("FORM CALLS:", len(FORM_CALLS))


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线自测：拉起 answer-card server，模拟一次填表和提交。"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, types
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER = str(Path(__file__).with_name("server.py"))


def server_command() -> tuple[str, list[str]]:
    """有 uv 就让 uv 现拉依赖；没有就退回当前解释器（要求它已装 mcp）。"""
    if shutil.which("uv"):
        return "uv", ["run", "-q", "--with", "mcp>=2,<3", "--no-project", SERVER]
    print("未找到 uv，改用当前解释器：", sys.executable)
    return sys.executable, [SERVER]


FORM_CALLS: list[dict] = []


async def on_elicit(context, params):
    schema = params.requested_schema
    props = schema.get("properties", {})
    answers = {}
    descs = {}
    for name, prop in props.items():
        answers[name] = 1.5 if prop.get("type") == "number" else "文本"
        if prop.get("description"):
            descs[name] = prop["description"]
    FORM_CALLS.append(
        {"message": params.message, "fields": list(props), "descs": descs})
    print("FORM title:", params.message)
    print("FORM fields:", list(props))
    return types.ElicitResult(action="accept", content=answers)


async def main():
    command, args = server_command()
    params = StdioServerParameters(command=command, args=args)
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
                        {"name": "note", "label": "备注", "type": "text",
                         "desc": "题干第一行\n题干第二行\n题干第三行"},
                    ],
                },
            )
            print("ASK:", result.content[0].text)
            print("PARSED:", json.loads(result.content[0].text))
            desc = FORM_CALLS[0]["descs"].get("note", "")
            print("DESC:", repr(desc))
            assert desc == "题干第一行\n题干第二行\n题干第三行", \
                "desc 未完整透传到字段 schema"

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

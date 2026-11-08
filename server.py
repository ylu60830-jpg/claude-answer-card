#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""answer-card：在 Claude Code 终端里弹原生填空表单的 MCP server。

原理：MCP elicitation。工具运行途中调用 ctx.elicit(message, schema)，
客户端（Claude Code）负责渲染原生表单并把填写结果送回来。
"""

import json
import os
import sys
import unicodedata
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field, create_model

server = MCPServer(
    "answer-card",
    instructions=(
        "教学答题卡。用 ask_blanks 弹出原生填空表单，收集用户对练习题的答案。"
        "题干短就放 prompt；题干带表格或多行时，把完整题干打成聊天正文，"
        "prompt 只放一句「见上方」，紧跟着调用本工具。"
        "template 只用于提交后回填整句。"
        "客户端只显示 4 行、每行超宽会截断；server 会按 width 预折行。"
        "fields 按表格行、列顺序传入，label 里带上行名，例如「A · 开始」。"
        "选择题（有固定选项）优先用原生 AskUserQuestion，不用本表单。"
    ),
)


def _format_value(value: Any) -> str:
    """把答案整理成适合回填的文本：整数补成整数字符串，其余保留原样。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _build_form(fields: list[dict[str, Any]]):
    """按字段列表生成扁平 Pydantic 模型，返回 (模型类, 字段名列表)。"""
    model_fields: dict[str, Any] = {}
    for item in fields:
        name = str(item["name"])
        label = str(item.get("label", name))
        kind = str(item.get("type", "text")).lower()
        py_type = float if kind == "number" else str
        model_fields[name] = (py_type, Field(title=label))
    return create_model("AnswerCard", **model_fields), list(model_fields)


# Claude Code 的 elicitation 表单最多显示 4 行；超过 4 行会折叠成
# 「… (+N more lines)」，单行超过终端宽度则截断加「…」。所以题干必须先
# 由 server 按显示宽度预折行，控制在 4 行以内，才能完整显示。
MAX_LINES = 4
DEFAULT_WIDTH = 96
# 客户端按「终端列数 − 内边距」截断每行，折行时留一点余量。
WIDTH_MARGIN = 8

def _console_size() -> tuple[int, int] | None:
    """读当前附着控制台的窗口列数×行数；没有控制台返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import struct

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p]
        kernel32.GetConsoleScreenBufferInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        # GENERIC_READ|GENERIC_WRITE、共享读写、OPEN_EXISTING
        handle = kernel32.CreateFileW(
            "CONOUT$", 0xC0000000, 3, None, 3, 0, None)
        if not handle or handle == ctypes.c_void_p(-1).value:
            return None
        buffer = ctypes.create_string_buffer(22)
        ok = kernel32.GetConsoleScreenBufferInfo(handle, buffer)
        kernel32.CloseHandle(handle)
        if not ok:
            return None
        # CONSOLE_SCREEN_BUFFER_INFO 里 srWindow 的 right/bottom
        left, top, right, bottom = struct.unpack(
            "hhhh", buffer.raw[10:18])
        width, height = right - left + 1, bottom - top + 1
        if 20 <= width <= 1000 and 5 <= height <= 500:
            return width, height
        return None
    except Exception:
        return None


def _ancestor_pids() -> list[int]:
    """用 Toolhelp 快照取父进程链，最近的在前，不含自身。"""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        class _ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        kernel32.CreateToolhelp32Snapshot.argtypes = [
            wintypes.DWORD, wintypes.DWORD]
        kernel32.Process32FirstW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_ProcessEntry)]
        kernel32.Process32NextW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_ProcessEntry)]
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            return []
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(_ProcessEntry)
        parents: dict[int, int] = {}
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        kernel32.CloseHandle(snapshot)

        chain: list[int] = []
        pid, seen = os.getpid(), {os.getpid()}
        for _ in range(16):
            pid = parents.get(pid, 0)
            if not pid or pid in seen:
                break
            seen.add(pid)
            chain.append(pid)
        return chain
    except Exception:
        return []


def _terminal_columns() -> int:
    """问控制台要终端真实的列数。

    Claude Code 用 CREATE_NO_WINDOW 起 MCP 子进程，子进程拿到的是自己的
    隐藏控制台（恒为 120×30），读不到终端。真正的 ConPTY 挂在 claude.exe
    上，所以沿父进程链逐个附加，取第一个与自身不同尺寸的控制台。测完立刻
    摘下，免得被终端的 Ctrl+C 波及。
    """
    if sys.platform != "win32":
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 0

    import ctypes

    kernel32 = ctypes.windll.kernel32
    own = _console_size()
    own_width = own[0] if own else 0
    outermost = own_width
    detached = False

    for pid in _ancestor_pids():
        kernel32.FreeConsole()
        detached = True
        if not kernel32.AttachConsole(pid):
            continue
        found = _console_size()
        if not found:
            continue
        if not own_width:
            # 自己没有控制台（比如上次已摘下），用最外层读到的
            outermost = found[0]
            continue
        if found[0] != own_width:
            kernel32.FreeConsole()
            return found[0]

    if detached:
        kernel32.FreeConsole()
    return outermost


def _resolve_width(width: int) -> int:
    """确定折行宽度：显式参数 > 环境变量 > 实测列数 − 8 > 96。"""
    if width > 0:
        return width
    for key in ("ANSWER_CARD_WIDTH", "COLUMNS"):
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    columns = _terminal_columns()
    if columns:
        return max(20, columns - WIDTH_MARGIN)
    return DEFAULT_WIDTH


def _char_width(ch: str) -> int:
    """东亚宽字符按 2 列算，其余按 1 列。"""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _wrap_line(text: str, width: int) -> list[str]:
    """把一段文本按显示宽度折行，中文逐字断，英文尽量在空格处断。"""
    lines: list[str] = []
    current: list[str] = []
    current_width = 0
    for ch in text:
        ch_width = _char_width(ch)
        if current_width + ch_width > width and current:
            line = "".join(current)
            space_at = line.rfind(" ")
            if space_at > 0 and space_at >= len(line) // 2:
                lines.append(line[:space_at])
                current = list(line[space_at + 1:]) + [ch]
            else:
                lines.append(line)
                current = [ch]
            current_width = sum(_char_width(c) for c in current)
        else:
            current.append(ch)
            current_width += ch_width
    if current:
        lines.append("".join(current))
    return lines


def _compose_message(title: str, prompt: str, width: int = 0) -> str:
    """把标题和题干拼成表单正文，并预折行到客户端的显示预算内。"""
    width = _resolve_width(width)
    head = title.strip()
    body = prompt.strip()
    if head and body:
        text = f"{head}｜{body}"
    else:
        text = head or body
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw.strip():
            lines.extend(_wrap_line(raw.strip(), width))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES - 1] + ["…（题干过长，完整题目见上方聊天正文）"]
    return "\n".join(lines)


def _render(template: str, answers: dict[str, Any]) -> str:
    if not template:
        return ""
    try:
        return template.format(**{k: _format_value(v) for k, v in answers.items()})
    except (KeyError, IndexError, ValueError) as exc:
        return f"（模板回填失败：{exc}）"


@server.tool()
async def ask_blanks(
    title: str,
    fields: list[dict[str, Any]],
    ctx: Context,
    prompt: str = "",
    template: str = "",
    width: int = 0,
) -> str:
    """弹出单页原生填空表单，返回用户填写的答案。

    prompt 是题干正文，显示在表单上方。客户端只显示 4 行、每行超宽会截断，
    server 会按 width（显示列数，0 = 自动：显式环境变量 > 控制台实测 − 8 >
    96）预折行，题干控制在 4 行内即可完整显示；超过 4 行会提示看聊天正文。
    fields 每项格式：
        {"name": "a_start", "label": "A · 开始", "type": "number" | "text"}

    template 可选，用 {name} 标出题目的空位，提交后回填，例如：
        "周转时间 = {turnaround}，等待时间 = {waiting}"

    返回 JSON：
        {"action": "accept" | "decline" | "cancel",
         "answers": {...},
         "rendered": "回填后的整句"}
    """
    form_cls, names = _build_form(fields)

    result = await ctx.elicit(
        message=_compose_message(title, prompt, width), schema=form_cls)
    if result.action != "accept":
        return json.dumps({"action": result.action, "answers": {}, "rendered": ""},
                          ensure_ascii=False)

    answers = {name: getattr(result.data, name) for name in names}
    return json.dumps({"action": "accept", "answers": answers,
                       "rendered": _render(template, answers)}, ensure_ascii=False)


@server.tool()
async def ask_pages(
    title: str,
    pages: list[dict[str, Any]],
    ctx: Context,
    template: str = "",
    width: int = 0,
) -> str:
    """连续弹出多页填空表单（每页一小组字段），全部填完后统一返回。

    pages 每项：{"title": "第 1/4 页 · 进程 A", "prompt": "本题干", "fields": [...]}
    prompt 是每页题干，显示在表单上方，server 会按 width（显示列数，0 = 自动：
    显式环境变量 > 控制台实测 − 8 > 96）预折行到 4 行内；字段名跨页必须唯一；
    Enter 提交本页后自动弹下一页。

    返回 JSON：
        {"action": "accept" | "decline" | "cancel" | "error",
         "answers": {...}, "rendered": "回填后的整句", "pages_done": 2}
    """
    answers: dict[str, Any] = {}
    pages_done = 0
    total = len(pages)

    for index, page in enumerate(pages, start=1):
        page_title = str(page.get("title") or f"{title} · 第 {index}/{total} 页")
        page_prompt = str(page.get("prompt") or "")
        form_cls, names = _build_form(page.get("fields", []))
        result = await ctx.elicit(
            message=_compose_message(page_title, page_prompt, width),
            schema=form_cls)
        if result.action != "accept":
            return json.dumps({"action": result.action, "answers": answers,
                               "rendered": "", "pages_done": pages_done},
                              ensure_ascii=False)
        for name in names:
            if name in answers:
                return json.dumps({"action": "error",
                                   "message": f"字段名重复：{name}",
                                   "answers": answers, "rendered": "",
                                   "pages_done": pages_done}, ensure_ascii=False)
            answers[name] = getattr(result.data, name)
        pages_done += 1

    return json.dumps({"action": "accept", "answers": answers,
                       "rendered": _render(template, answers),
                       "pages_done": pages_done}, ensure_ascii=False)


@server.tool()
def ping() -> str:
    """连通性检查：返回 pong 表示 server 已加载。"""
    return "pong"


if __name__ == "__main__":
    server.run()

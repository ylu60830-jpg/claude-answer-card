# answer-card

给 Claude Code 用的终端答题卡：用**原生表单**收集结构化答案，判分和讲解留在对话里。

做题时最烦的是「答案怎么输」——手打 `1,2,3` 容易错位、对不上题号。
这个 MCP 服务器把答案收集变成一个原生表单：竖排输入框、Tab/Enter 切换、数字校验，
和选择题用的 `AskUserQuestion` 分工明确。

```
┌──────┬──────────┬──────────┬──────────┐
│ 进程 │ 到达时间 │ 服务时间 │ 完成时间 │
├──────┼──────────┼──────────┼──────────┤
│  P1  │    0     │    5     │          │
│  P2  │    1     │    3     │          │
└──────┴──────────┴──────────┴──────────┘
              ↓ 紧接着弹出
        P1 · 完成  [     ]
        P2 · 完成  [     ]
```

## 能力

| 工具 | 用途 |
|------|------|
| `ask_blanks` | 一次收集多个空。字段竖排、可上下滚动，**字段数没有上限** |
| `ask_pages` | 连弹多页，一次填完一整张表 |
| `ping` | 连通性检查 |

**自动宽度**：每次调用时现测终端列数，折到「列数 − 8」。

> 为什么不能直接读？Claude Code 用 `CREATE_NO_WINDOW` 起 MCP 子进程，
> 子进程拿到的是自己的隐藏控制台，恒报 120×30，窗口怎么缩都不变。
> 真正的 ConPTY 挂在 `claude.exe` 上，所以 server 沿父进程链逐个 `AttachConsole`，
> 取第一个尺寸不同的控制台。测完立刻摘下，免得被终端的 Ctrl+C 波及。

## 安装

需要：Python 3.10+、[uv](https://github.com/astral-sh/uv)、Claude Code。

**1. 安装 skill**（可选，但强烈建议——它包含用哪张卡的判断规则）

把 `SKILL.md` 放到：

```
~/.claude/skills/answer-card/SKILL.md
```

**2. 注册 MCP 服务器**

把 `<路径>` 换成 clone 下来的目录：

```bash
claude mcp add answer-card --scope user -- uv run -q --with "mcp>=2,<3" --no-project <路径>/server.py
```

**3. 重启 Claude Code** 生效。

验证：

```bash
claude mcp get answer-card     # 应显示 Status: ✔ Connected
```

## 用法

装好之后不用手动调用——把 `SKILL.md` 放进 skills 目录，Claude 会按题型自己选卡。
也可以直接点名：

> 用答题卡把这道题的答案收一下

单独测服务器（不需要客户端）：

```bash
uv run -q --with "mcp>=2,<3" --no-project python test_client.py
```

## 已知限制（都是实测出来的，不是猜的）

| 限制 | 说明 |
|------|------|
| 题干最多 4 行 | 超出会折叠成 3 行 + `… (+N more lines)`。**解决办法：题干写成聊天正文，`prompt` 只放一句「见上方」** |
| 单行超宽会截断 | 客户端对每行只截断、**不重排**，所以 server 必须预折行 |
| 卡片打开后缩放窗口不重排 | 内容在弹出那一刻就定死了；关掉重开即可 |
| 题干不支持 Markdown | 加粗、反引号、`#` 都原样显示，别写 |
| 数字框只收小数 | `9/4` 这类分数用 `text` 类型 |

一个反直觉但很有用的结论：**正文是聊天文本、没有硬换行，重排权在客户端**，
所以把长题干打成正文再弹一张填空卡，既同屏、又真的跟着窗口自适应；
而表单里的题干是提前折死的，不会。两边各用各的长板。

## 目录结构

```
answer-card/
├── SKILL.md        # 给 Claude 的规则：什么时候用哪张卡
├── server.py       # MCP 服务器（elicitation 通道）
├── test_client.py  # 离线自测
└── README.md
```

## 平台

主要针对 **Windows + Windows Terminal**（宽度测量走 Win32 `AttachConsole`）。
其它平台会退回 `os.get_terminal_size()`，能用但自动宽度依赖终端是否上报列数。

## 背景

这是从一个「答案卡」需求做出来的：先做了填空表单，踩完 4 行限制、截断、宽度测量
这些坑之后，才发现和原生 `AskUserQuestion` 是两条不同的渲染架构——
一个把排版交给客户端，一个把排版压在服务器上。两边的边界写在 `SKILL.md` 里。

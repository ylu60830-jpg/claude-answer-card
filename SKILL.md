---
name: answer-card
description: 终端原生答题卡。做题、批改、收集结构化答案时使用——选择题走原生 AskUserQuestion（打勾卡）；带表格/多行题干的题把题干写成正文、再用 MCP 表单收答案；多空格/多页填空走 ask_blanks / ask_pages。触发词包括 答题卡、填空、表格题、做题、练习、批改、填表、表单。
---

# 答题卡（answer-card）

一句话：**选择题用打勾卡，填空题用表单卡。** 判分和讲解留在主会话做。

## 一、路由：用哪张卡

只有两条路，按「答案是不是固定选项」来分：

| 答案长什么样 | 用什么 |
|------|--------|
| 从几个固定选项里挑 | 原生 `AskUserQuestion` |
| 要自己写（数字、时刻、公式、一段话） | `mcp__answer-card__ask_blanks` |
| 要自己写，且想分阶段做 | `mcp__answer-card__ask_pages` |
| 是 / 否、要不要继续 | 正文一句话问，不值得弹卡 |

- **选择题**（单选 / 多选 / 选错题）：`AskUserQuestion`。选项可多行、可带说明、高亮选中、可点「Type something」。
- **填空题**：`ask_blanks`。竖排输入框，Enter 提交，比手打 `A0,1,1,1;B…` 顺手。
- **多组小题、想分批做**：`ask_pages`，一次调用连弹多页，答案合并返回。

❌ 不要把选择题塞进填空表单：没有选项列表、没有选中高亮，体验反而差。

❌ 不要把填空伪装成选择题：为了走 `AskUserQuestion` 硬塞两个占位选项、让用户点「Type something」——这是把两条路混用。填空一律走 `ask_blanks`。

❌ 不要把长表格塞进填空表单的题干：题干只有 4 行，带框表一超过就被折叠（长题干放正文，见下）。

### 默认：题干放正文，填空放卡片

题干里有表格或多行时，**把题干直接打成正文**（用 ` ```text ` 代码块包住，防止 markdown 重排），
紧跟 `ask_blanks`，题干只放一句「见上方表格」+ 若干填空框。

- 关键好处：正文是聊天文本、**没有硬换行**，重排权在客户端 ⇒ 窗口拉宽拉窄它都跟着变，是**真自适应**。
  表单里的题干是 server 提前折死的，改窗口不跟随。两边各用各的长板。
- 限制：表格宽度要留余量（建议 ≤ 终端列数 − 20），窗口一缩就会被折行、对齐崩。

### 备选：两段式（题干卡 → 填空卡）

需要**原生排版**（表格特别宽、要富文本、要选中高亮）时才用：

1. `AskUserQuestion` 放完整题干，选项给「开始填写 / 跳过」
2. 选「开始填写」→ `ask_blanks` 收答案，题干压成一句「见上一张卡」

缺点：不同屏，多一次点击。原生 UI 无行数限制（实测 9 行带框表完整渲染、边框对齐）。

## 二、表单卡的硬限制（客户端定的，server 改不了）

- **题干正文最多显示 4 行**（实测确认）。`AskUserQuestion` 没有这条限制。
  超过 4 行会折叠成 3 行 + `… (+N more lines)`；单行超过「终端列数 − 6」会截断加 `…`。
- 颜色和 Markdown 不可控：题干是单一灰色，`**加粗**`、反引号、`#` 会原样显示，别写。
- 客户端对每行只截断、不重排（不像终端软折行），所以必须由 server 预折行。
- server 每次调用时现测列数：MCP 子进程自己那个隐藏控制台恒报 120×30，不可用；
  沿父进程链 `AttachConsole` 到 `claude.exe` 的真 ConPTY 取列数（`_terminal_columns()`），
  折到「列数 − 8」。窗口改了，下一张卡自动适配；卡片打开期间缩放窗口不会重排，关掉重开即可。
- 东亚模糊宽度字符（EAW=`A`，如 `·` `→` `①` `—` `×`、制表符 `│ ─ ┼`）按 **1 列** 渲染
  （已实测）。`_char_width` 用 `("W","F")` 是对的，不要扩到 `A`。
- 题干超过 4 行预算时：**完整题干放聊天正文**，`prompt` 只放一句摘要 + 「完整题目见上方」。
- 数字输入框只收小数，不收 `9/4` 这类分数（要分数就用 text 类型）。
- 字段竖排，**列表可上下滚动，字段数没有上限**（实测 15 个空一页填完）。
  表大就一页放完，不必为了行数拆页；拆页只在「想分阶段做」时才有意义。

## 三、ask_blanks 调用要点

```python
mcp__answer-card__ask_blanks(
    title="",                        # 不想多占一行就留空
    prompt="第一行题干…\n第二行…",     # 题干正文，已预折行，≤4 行
    fields=[
        {"name": "a_start", "label": "A · 开始", "type": "number"},
        {"name": "a_finish", "label": "A · 完成", "type": "number"},
    ],
    template="A 开始 {a_start}，完成 {a_finish}",  # 可选，提交后回填整句
)
```

- `name`：英文 snake_case，跨页/跨题唯一。
- `label`：中文，**带行名**（`A · 开始`），否则十几个框分不清谁是谁。
- `type`：`number` 或 `text`，默认 text。
- 返回 JSON：`action` 为 `accept` / `decline` / `cancel`；`answers` 是原始值；
  `rendered` 是 template 回填后的句子。
- `width`：显示列数，0 = 自动（环境变量 `ANSWER_CARD_WIDTH` → `COLUMNS` → 实测终端列数 − 8 → 96）。
  一般不用传，server 每次调用现测。

## 四、ask_pages 调用要点

```python
mcp__answer-card__ask_pages(
    title="复习",
    pages=[
        {"title": "第 1/2 页 · 进程 A", "prompt": "…", "fields": [...]},
        {"title": "第 2/2 页 · 进程 B", "prompt": "…", "fields": [...]},
    ],
    template="…",
)
```

- 每页 Enter 提交后自动弹下一页；中途 decline/cancel 就停，返回已填部分 + `pages_done`。
- 字段名跨页必须唯一，重复会返回 `action: "error"`。
- 每页题干同样受 4 行限制。

## 五、判分与教学衔接

- 卡只管收答案，**不判分**。收到 `answers` 后在主会话按模板对照、逐项标对错。
- 出题时正确项位置随机、题型轮换；练习的产出是盲点清单，不是正确率。
- 答错先给方向，不直接给答案。

## 六、静默授权（可选）

把这三个名字加进 `~/.claude/settings.json` 的 `permissions.allow`，调用时就不会再弹授权：

```
mcp__answer-card__ask_blanks
mcp__answer-card__ask_pages
mcp__answer-card__ping
```

## 七、实现备注

- 原理：MCP elicitation，`ctx.elicit(message, schema)`，客户端渲染原生表单。
- 改了 server 代码要等下次启动才生效（stdio 常驻进程）；当次可用「调用时预折行」兜底。
- Windows 上宽度测量走 Win32 `AttachConsole`；其它平台退回 `os.get_terminal_size()`。

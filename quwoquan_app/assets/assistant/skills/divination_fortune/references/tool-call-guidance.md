# 工具调用指引

## 调用条件
- 当外部信息可明显提升建议质量时，优先调用 `search`。
- 仅当需要纯网页补查且统一检索未覆盖时，才回退到 `web_search`。
- 用户仅要轻量建议时，可不调用工具直接回答。

## 重试策略
- 对可重试超时最多重试 1 次。
- 持续失败时返回降级但可执行的建议，不空回。

## 参数规范
- 查询模板：`今日运势 {{focusArea}} 参考信息`
- 若调用 `search`，保持 `mode=result`，只传必要 query/limit。
- 参数需明确，避免无关的大范围检索。

## 时间槽位规范
- 当问题包含“哪年/那年”时：使用 `timeScope=year`，并填写 `timeYear`。
- 当问题包含“哪年哪月/那年那月”时：使用 `timeScope=year_month`，并填写 `timeYear`、`timeMonth`。
- 当问题包含“哪年哪月哪日/那年那月那日”时：使用 `timeScope=year_month_day`，并填写 `timeYear`、`timeMonth`、`timeDay`。
- 若是自然日历点但未拆槽，可补 `timePoint`（如 `2024`、`2024-08`、`2024-08-21`）作为兜底。

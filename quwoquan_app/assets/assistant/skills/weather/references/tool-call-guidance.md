# 工具调用指引

## 调用顺序
1. `local_context`（仅在缺少城市时调用）
2. `search`（统一检索天气摘要，必要时回退 `web_search`）

## 重试策略
- 对 `timeout` / `retryable=true` 的错误最多重试 1 次。
- 仍失败则进入降级回答，并给出明确下一步。

## 参数规范
- `local_context.requestedFields`: `["location", "permissions", "device"]`
- `search.query`: `{{city}}天气`
- `search.mode`: `result`
- 参数保持最小、确定、可复现，避免宽泛查询。

## 时间槽位规范
- 当问题包含“哪年/那年”时：使用 `timeScope=year`，并填写 `timeYear`。
- 当问题包含“哪年哪月/那年那月”时：使用 `timeScope=year_month`，并填写 `timeYear`、`timeMonth`。
- 当问题包含“哪年哪月哪日/那年那月那日”时：使用 `timeScope=year_month_day`，并填写 `timeYear`、`timeMonth`、`timeDay`。
- 若是自然日历点但未拆槽，可补 `timePoint`（如 `2024`、`2024-08`、`2024-08-21`）作为兜底。

# 工具调用指引

1. 先判定是否缺关键槽位。
2. 缺失时先补槽位，再做检索。
3. 工具失败最多重试一次。
4. 失败后返回降级提示与下一步。
5. 时间语义由模型在 `toolCalls` 各元素的 `arguments`（或等价载荷）中显式给出 `timeScope`，并遵循本域 `config/retrieval_policy.json` 的允许枚举；当用户表达“某年/某年某月/某年某月某日”时，必须补齐 `timeYear/timeMonth/timeDay`（按粒度）；当 `timeScope=custom` 时必须补齐 `timeRangeStart/timeRangeEnd`。
6. 股票与估值类查询必须带 `authorityDomains`，默认：
   `cninfo.com.cn`, `sse.com.cn`, `szse.cn`, `csindex.com.cn`, `eastmoney.com`

## 时间槽位规范
- 当问题包含“哪年/那年”时：使用 `timeScope=year`，并填写 `timeYear`。
- 当问题包含“哪年哪月/那年那月”时：使用 `timeScope=year_month`，并填写 `timeYear`、`timeMonth`。
- 当问题包含“哪年哪月哪日/那年那月那日”时：使用 `timeScope=year_month_day`，并填写 `timeYear`、`timeMonth`、`timeDay`。
- 若是自然日历点但未拆槽，可补 `timePoint`（如 `2024`、`2024-08`、`2024-08-21`）作为兜底。

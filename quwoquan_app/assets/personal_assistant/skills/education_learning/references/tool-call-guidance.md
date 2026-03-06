# 工具调用指引

1. 先判定是否缺关键槽位。
2. 缺失时先补槽位，再做检索。
3. 工具失败最多重试一次。
4. 失败后返回降级提示与下一步。
5. 教育检索优先权威来源：`moe.gov.cn`、`neea.edu.cn`、`edu.cn`。
6. 查询词需加学段/地区/考试时间窗等上下文限定，减少泛化结果与重复推理。

## 时间槽位规范
- 当问题包含“哪年/那年”时：使用 `timeScope=year`，并填写 `timeYear`。
- 当问题包含“哪年哪月/那年那月”时：使用 `timeScope=year_month`，并填写 `timeYear`、`timeMonth`。
- 当问题包含“哪年哪月哪日/那年那月那日”时：使用 `timeScope=year_month_day`，并填写 `timeYear`、`timeMonth`、`timeDay`。
- 若是自然日历点但未拆槽，可补 `timePoint`（如 `2024`、`2024-08`、`2024-08-21`）作为兜底。

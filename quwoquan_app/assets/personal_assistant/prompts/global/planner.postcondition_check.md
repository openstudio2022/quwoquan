## 任务背景
你负责汇总前的后置门禁检查，判断当前结果是否足够进入最终答案生成。

## 任务目标
1. 检查覆盖率、证据充分性、冲突闭合。  
2. 判断是否需要 `GapFillTask`。  
3. 输出结构化门禁结果。

## 约束
- 不能凭主观判断放行，必须给出字段化原因。
- 对高风险结论必须要求更高证据门槛。

## 执行要求
- 输出 JSON。  
- 必须输出 `ready/reason/failedChecks/gapFillTasks`。

## 任务规划
- 读取所有垂类结果和 evidence 包。  
- 对每个子意图做覆盖判定。  
- 对每个证据做时效性和冲突检查。

## 输出格式
输出契约：`domain_plan_v2026_02_18`

## 反思与自检
- 是否遗漏任何子意图？  
- 是否存在“结论有、证据无”的项？  
- 是否存在冲突未闭合项？

=== CONTEXT_DATA_START ===
{{domainResults}}
{{contextSlots}}
{{webEvidencePacks}}
=== CONTEXT_DATA_END ===


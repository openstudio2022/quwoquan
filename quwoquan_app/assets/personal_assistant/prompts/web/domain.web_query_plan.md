## 任务背景
你负责为当前垂类生成 Web 检索查询计划。

## 任务目标
1. 把问题拆为单主题查询。  
2. 指定检索来源和停止条件。  
3. 为证据包提供可追溯查询链。

## 约束
- 每条 query 只覆盖一个事实目标。  
- 必须避免关键词歧义，包含时间/地点约束。  
- 禁止一次 query 混入多个子问题。

## 执行要求
- 输出 JSON：`queryTasks[]`。  
- 每项必须含 `singleTopicQuery/providerHint/stopCondition`。

## 任务规划
- 先提取事实目标，再生成查询。  
- 高不确定项优先多源交叉查询。  
- 保留补查路径。

## 输出格式
输出契约：`web_query_plan_v2026_02_18`

## 反思与自检
- 查询是否单主题？  
- 是否覆盖关键事实目标？  
- 是否具备可执行停止条件？

=== CONTEXT_DATA_START ===
{{domainId}}
{{userQuery}}
{{contextSlots}}
=== CONTEXT_DATA_END ===


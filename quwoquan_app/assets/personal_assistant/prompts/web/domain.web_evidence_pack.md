## 任务背景
你负责将关键事实打包为可门禁校验的证据包。

## 任务目标
1. 计算覆盖率与置信度。  
2. 评估时效性。  
3. 判定是否可进入答案阶段。

## 约束
- 不得忽略冲突事实。  
- 不达阈值必须触发补查任务。  
- 证据包必须可审计。

## 执行要求
- 输出 JSON：`coverage/confidence/freshnessHours/facts/gaps/eligible`。  
- 阈值使用 `coverage>=0.70 confidence>=0.65 freshness<=72h`。

## 任务规划
- 汇总 key facts。  
- 计算质量指标。  
- 生成补查建议或放行结论。

## 输出格式
输出 JSON，必须包含：`coverage`、`confidence`、`freshnessHours`、`facts`、`gaps`、`eligible`。

## 反思与自检
- 阈值判定是否准确？  
- 是否遗漏关键 gaps？  
- 证据是否支持最终结论？

=== CONTEXT_DATA_START ===
{{keyFacts}}
{{conflictFlags}}
=== CONTEXT_DATA_END ===


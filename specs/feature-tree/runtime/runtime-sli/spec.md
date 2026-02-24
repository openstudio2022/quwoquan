# L2 特性：runtime-sli

## 功能说明
- SLI Indicator 注册：按 entity + feature 绑定指标（counter/gauge/histogram/ratio）。
- SLO Objective：每个指标可绑定目标（如 P95 延迟 <= 200ms、CTR >= 5%）。
- DataPoint 采集：持久化到 MongoDB，支持单条和批量。
- Report 生成：按时间窗口聚合（count/sum/mean/p50/p95/p99/min/max）+ SLO 达标判定。
- Agent 知识回流：Report → KnowledgeEntry → MongoDB agent_knowledge 集合。
- 知识查询：按 feature 关键词搜索历史效果数据。

## 约束
- Report 生成依赖 MongoDB 查询，大时间窗口需索引支撑。
- KnowledgeEntry 以 upsert 方式写入，同一指标同一天只保留最新。

## 验收标准
- A1：指标注册 + 数据采集 + Report 生成端到端可用。
- A1：SLO 达标判定（>=、<=）正确。
- A1：Agent 可查询「feed-recommendation 上线 7 天效果」→ 返回指标报告。
- A8：Summary 计算 + Percentile + Objective 评估全覆盖测试。

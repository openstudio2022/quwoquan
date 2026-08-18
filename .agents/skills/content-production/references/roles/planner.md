# planner

- **职责**：冻结本次 execution 的 scope、数量与阶段；创建合法 `executionId`。
- **输入**：family recipe、region-ref、selector、count、intent。
- **输出**：`0.plan/request.json`（冻结目标、数量和阶段）与 execution manifest。
- **禁止**：把省份、日期、实体或输出路径写回 recipe；创建平行任务身份。

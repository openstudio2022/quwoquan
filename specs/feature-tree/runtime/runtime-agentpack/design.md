# runtime-agentpack

## 设计边界

- 输入：受版本控制的 `specs/feature-tree/` 三层目录。
- 输出：自动生成的 `tree_index.yaml`。
- 扫描器只识别 `L1_domain_service / L2_business_capability / L3_story`，不读取会话
  Task、树内计划文件或临时执行状态。
- 索引读写和搜索复用同一组 `TreeIndex / FeatureNode` 强类型结构。

短期执行状态留在当前会话、PR 或外部台账；业务验收状态以各节点
`acceptance.yaml` 为准，避免索引成为第二真相源。

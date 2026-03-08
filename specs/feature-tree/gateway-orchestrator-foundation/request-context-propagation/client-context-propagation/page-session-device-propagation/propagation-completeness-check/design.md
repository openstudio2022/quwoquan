# propagation-completeness-check 设计方案

## 设计定位

本节点降级为消费侧设计，主设计迁移到：

- `runtime/runtime-codegen/struct-repo-handler-migration-generation/operation-surface-route-single-source`

## 设计职责

- 约束 gateway / downstream 正确接收 `operation_id / surface_id`
- 定义兼容期 header 双写策略
- 约束弱网重试、页面重入、回退时上下文传播稳定

## 关键决策

- gateway 不定义 operation / surface / route 唯一真相源
- gateway 只消费上游 codegen 结果
- 兼容期保留旧 `X-Client-Page-Id`，但不得与上游 codegen 脱节

## 验证重点

- header propagation completeness
- decoder context consistency
- retry / re-entry stability

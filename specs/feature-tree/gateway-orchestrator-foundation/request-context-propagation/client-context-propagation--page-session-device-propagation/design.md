# 设计说明（规划阶段占位）

## 设计动因

本节点处于规划阶段，详细设计待实施时根据 spec.md 与 tasks.md 补充。

## 适用场景与约束

- **适用**：按 spec.md 定义的职责边界与验收标准实施后成立。
- **约束**：与父节点及上下游契约保持一致；实施时须满足四类文档（spec / design / tasks / acceptance）一致。
- **局限性**：当前为占位文档，具体方案与业界对标在实施阶段补充。

## 未来演进

实施时在本文档中补充演进方向与目标态；若当前即为目标态则注明「暂无演进项」。

## Folded current node `propagation-completeness-check`

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

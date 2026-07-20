# L2 特性：runtime-experiments

## 功能说明
- 提供统一实验分桶与灰度策略运行时；`AssignBucket` 是推荐与搜索当前唯一商用分桶实现。
- 为业务服务提供一致、可复现的实验命中结果，并由实际曝光/查询事实承载审计归因。

## 约束
- 分桶规则必须稳定可复现，且支持版本化。
- 命中结果需可关联 trace/request 与 experiment audit。
- 当前策略来源是各业务 metadata/codegen 配置，统一经 `runtime/experiments` 解析；禁止业务服务复制 hash 算法。
- Product Ops 控制面尚未建立到 runtime 的 durable binding，在 policyVersion 原子发布、last-good、
  实际 assignment 回写和 gamma 对账完成前必须保持 commercial blocked，不能成为第二真相源。

## 验收标准
- A1：统一分桶 API 可被服务直接集成。
- A3：策略缓存与 fallback 可配置。
- A5：实验命中可用于运营分析。
- A8：分桶与策略拉取自动化测试完整。
- A9：门禁阻断 Product Ops assignment API 进入推荐/搜索热路径，且阻断未绑定控制面在 Portal 暴露。

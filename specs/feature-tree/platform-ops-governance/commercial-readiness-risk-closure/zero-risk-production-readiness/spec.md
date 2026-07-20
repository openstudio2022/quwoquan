# L3 特性：zero-risk-production-readiness

## 用户故事

作为生产发布负责人，我希望运维运营平台只有在身份、数据、遥测、供应链、灰度、
观测、灾备和验收证据全部通过时才允许放量，从而避免把已知风险和技术债带入生产。

## 范围

- 执行父能力 `commercial-readiness-risk-closure` 的 RP1–RP7；
- 删除仓内可修复的全部 `R-OPS-*` 断点；
- 对 IdP、GitHub entitlement、法务主体、prod-hosted 凭据等外部前置条件建立
  fail-closed 发布门；
- 运行三层测试、触发范围 gate 和 stackctl release 证据；
- 完成后同步关闭 backlog；任何未满足项都保持 Story 未完成。

## 验收概要

- Given 任一风险或外部前置条件未满足，When 执行 production release，
  Then 发布被机器阻断且没有 skip/warn-only 逃逸；
- Given 所有 RP 已完成且外部前置条件真实可用，When 执行 gray-initial →
  carry-on → full，Then 使用同一不可变 manifest、真实 SLO、串行 CAS、可回滚并留下
  完整审计/观测/恢复证据。

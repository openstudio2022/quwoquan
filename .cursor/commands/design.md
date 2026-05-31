# /design

目标：冻结架构设计。

设计只作用于：
- AppRoot
- `L1_domain_service`
- `L2_business_capability`

Story 不产生 `design.md`；Story 发现设计缺口时，上收到所属业务能力。

产出：
- 对应层级 `design.md`。
- metadata/codegen、数据迁移、feature flag、观测、回滚方案。
- T1~T4 证据矩阵。

阻断：设计复述需求、绕过 metadata、缺回滚或测试证据时返回 `GATE_BLOCK`。

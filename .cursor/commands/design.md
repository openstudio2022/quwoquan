# /design

目标：冻结架构设计。

准入：
- `/prd` 或 `/explore` 已明确目标、范围、验收和一棵树归属。
- 需要明确边界、依赖、数据流、metadata/codegen、观测、回滚或迁移方案。

设计只作用于：
- AppRoot
- `L1_domain_service`
- `L2_business_capability`

Story 不产生 `design.md`；Story 发现设计缺口时，上收到所属业务能力。

执行：
- 读取 `docs/agent_context_contract.md`，完成 `Pre-work Reflection`。
- 对齐 `contracts/metadata/**`、DDD 依赖方向、环境/seed、错误码、观测和测试证据。
- 只在 AppRoot / L1 / L2 层写设计；Story 只引用上层设计。

产出：
- 对应层级 `design.md`。
- metadata/codegen、数据迁移、feature flag、观测、回滚方案。
- 三层测试 证据矩阵。

出口：
- 设计能被 `/baseline` 或 `/dev` 消费。
- 明确 metadata/codegen、测试、观测、回滚和风险处置。
- 无 Story 级 `design.md` 漂移。

阻断：设计复述需求、绕过 metadata、缺回滚或测试证据时返回 `GATE_BLOCK`。

自然语言等价触发：用户说“设计一下方案”“梳理架构”“明确边界/回滚/观测”时，也按 `/design` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

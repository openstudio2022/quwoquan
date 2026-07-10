# /prd

目标：冻结规格与验收，不做实现。

准入：`/explore` 已明确一棵树归属，目标用户、范围、Out of Scope、风险清晰。

执行：
- 读取 `docs/agent_context_contract.md`，补齐 `Spec Entry`。
- 冻结目标、用户价值、范围、Out of Scope、权限/异常、生命周期、SLO/KPI、灰度/回滚和观测。
- 将验收意图映射到 `UAT / SIT / GWT / contract` 与 `local_contract / api_integration / user_acceptance`。
- 声明受影响的 `quality_facets`：异常恢复、性能、安全隐私、可观测、可靠性/可用性、数据一致性；不适用项必须说明原因。
- 只更新规格/验收/registry/CR，不写实现。

产出：
- 对应层级 `spec.md`。
- 对应 `acceptance.yaml`，包含 UAT/SIT/GWT/contract、三层测试、`quality_facets`、`test_object`、SLO/观测/安全引用。
- 如影响跨领域体验，更新 `journey_scenario_registry.yaml`。
- 关联或新建 `specs/changelog/CR-*.yaml`。

出口：
- 规格可被 `/design` 或 `/baseline` 消费。
- 验收项可测试，非功能质量维度有证据路径，且不把未决问题伪装成已冻结。
- 说明仍需设计或 metadata 扩展的缺口。

阻断：缺权限、生命周期、SLO/KPI、灰度回滚、metadata 真相源时返回 `GATE_BLOCK`。

自然语言等价触发：用户说“冻结需求”“写 PRD”“明确规格/范围/验收”时，也按 `/prd` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

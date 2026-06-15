# /baseline

目标：在需求稳定且方案收敛时，一次冻结 spec、acceptance、必要 design 与 CR。

准入：
- 一棵树归属已明确。
- UAT/SIT/GWT/contract 可测。
- T1~T4 证据矩阵可形成。
- 无重大架构分叉。

执行：
- 读取 `docs/agent_context_contract.md`，确认 `Spec Entry` 与 `Pre-work Reflection` 都已满足。
- 对齐 `spec.md`、`acceptance.yaml`、必要 `design.md`、registry 和 CR。
- 若 metadata 基线需要创建，按 `/extend` 场景分发，不手改 generated。

产出：`spec.md`、`acceptance.yaml`、必要层级 `design.md`、registry 更新、CR。

出口：
- 后续 `/dev` 能直接消费基线，不再悬空关键决策。
- 验收和测试证据路径可落地。
- 方案未收敛时不得冻结。

阻断：发现方案未收敛时，退回 `/prd` + `/design`。

自然语言等价触发：用户说“做基线”“需求稳定了冻结一版”“把 spec/acceptance/design/CR 收齐”时，也按 `/baseline` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

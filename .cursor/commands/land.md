# /land

目标：把原型或试验结果纳入正式特性树。

必须补齐：
- AppRoot Journey/Scenario 影响。
- `L1_domain_service / L2_business_capability / L3_story`。
- `spec.md`、`acceptance.yaml`、必要 `design.md`。
- UAT/SIT/GWT/contract 与 T1~T4。

禁止：把原型任务、临时计划或旧树目录直接落为正式结构。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/land` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

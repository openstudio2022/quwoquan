# /rec

推荐专项入口。任何推荐增量先执行全局入口检查：AppRoot Journey/Scenario、`L1_domain_service / L2_business_capability / L3_story`、UAT/SIT/GWT/contract、T1~T4。

专项必须补充：召回/排序/重排/探索边界、行为信号来源、冷启动策略、指标口径、AB 与回滚。

缺树归属或缺推荐指标证据时 `GATE_BLOCK`。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁与剩余风险。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/rec` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

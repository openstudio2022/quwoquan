# /obs

可观测专项入口。任何观测增量先执行全局入口检查：AppRoot Journey/Scenario、三层目录归属、UAT/SIT/GWT/contract、三层测试。

专项必须补充：指标、日志、追踪、告警、SLO、看板、回滚触发条件。

缺业务验收映射或缺 SLO/告警证据时 `GATE_BLOCK`。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁与剩余风险。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/obs` 语义执行；执行前仍需按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

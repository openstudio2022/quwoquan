# /deliver

目标：执行 `/dev` + `/verify` + `/commit` 的闭环交付。

适用：Story spec 的 REQ/GWT 已稳定，能力设计已覆盖实现约束。

必须闭环：metadata/codegen、业务逻辑、测试、验收证据、动态变更影响报告和门禁，以及异常恢复、性能、安全隐私、可观测、可靠性/可用性、数据一致性等适用质量维度。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、非功能质量、运营观测、自动化/门禁与剩余风险。适用质量维度缺证据时必须返回 `GATE_BLOCK`。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/deliver` 语义执行；执行前仍需按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

# /deliver

目标：执行 `/dev` + `/verify` + `/commit` 的闭环交付。

适用：Story 已有 spec/acceptance，能力设计已覆盖实现约束。

必须闭环：metadata/codegen、业务逻辑、测试、验收证据、CR、门禁。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁与剩余风险。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/deliver` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

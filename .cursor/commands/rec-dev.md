# /rec-dev

推荐实现入口。

准入：Story acceptance 已冻结，推荐指标和回滚阈值明确。

必须同步：metadata、行为上报契约、seed/fixture、Mock/Remote 一致性、三层测试 证据。

禁止只改算法而不验证端侧曝光、点击、停留、负反馈等归因链。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/rec-dev` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

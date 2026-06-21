# /obs-audit

可观测审计入口。

检查：树归属、UAT/SIT/GWT/contract、三层测试、SLO 覆盖、告警噪声、日志字段、trace 串联、错误码、回滚触发条件。

输出 findings、证据缺口和阻断项。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/obs-audit` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

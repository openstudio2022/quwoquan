# /obs-dev

可观测实现入口。

准入：观测点、SLO、告警、回滚条件已冻结。

必须同步：端侧埋点、云侧指标、trace/request id、错误结构化、看板或查询、T1~T4 证据。

禁止新增不可归属到 Story/能力验收的孤立指标。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/obs-dev` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

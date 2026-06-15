# /archive

目标：归档已验证增量的证据。

归档内容：
- 一棵树归属。
- UAT/SIT/GWT/contract 状态。
- T1/T2/T3/T4 证据。
- CR、门禁命令、SLO/回滚证据。

禁止：用归档补写未完成验收。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/archive` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

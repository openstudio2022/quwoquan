# /commit

目标：提交已闭环增量。

前置：
- Story、相关能力/领域文档、metadata/codegen、测试证据、CR 均闭环。
- 触发范围 local_contract 与仓库门禁已运行。

禁止：提交无验收、无测试证据、旧树口径或未闭环 CR。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁与剩余风险。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/commit` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

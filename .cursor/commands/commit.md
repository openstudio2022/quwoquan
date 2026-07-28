# /commit

目标：提交已闭环增量。

前置：
- Story、相关能力/领域文档、metadata/codegen 与测试证据均闭环。
- 本地 pre-commit 走 L0 `commit_gate.sh`（并行静态 + 影响面测试，目标 ≤10 分钟，硬顶 15 分钟）；**不**跑全量 `make gate` / `gate_repo --scope all`。
- 全量 local_contract 由 CI Delivery Gate（App 4 分片 + serial）承接；本地失败摘要见 `.qwq_output/env/repo/runs/commit-gate/`。

禁止：提交无验收、无测试证据、旧树口径、未归属 Git 变更或未处置的 `OPEN block`。禁止把 `--no-verify` 当常规合入手段。

输出：按 Exit Review 汇总规格达成、测试证据、E2E、产品/UX、运营观测、自动化/门禁与剩余风险。


自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/commit` 语义执行；执行前仍需按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `根 AGENTS.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

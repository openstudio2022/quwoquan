---
name: /explore
id: explore
category: Specification
description: 只读确认增量的产品归属、父链、边界、并行冲突与风险
---

# /explore

目标：只读确认增量的产品归属、父链、边界与风险；不写代码和规格。

执行：

1. 读取最近 `AGENTS.md` 与 `specs/feature-tree/README.md`。
2. 已知路径时运行 `make feature-context TARGET=<path>`；否则从 AppRoot Journey 和 L1 边界逐层定位。
3. 明确 AppRoot Journey/Scenario、L1、L2、L3、In/Out of Scope、验收意图和三层测试。
4. 检查 metadata、runtime error、Mock、页面质量、Data/Service/App、观测、环境与回滚是否被触发。
5. 用 `git status` 识别脏工作树中并行会话改动与目标路径的交集；列出受影响的棘轮基线（ceiling 类门禁）当前值。脏工作树是常态，禁止回滚或清理与本目标无关的改动。
6. 读取目标父链的 OPEN；不扫描中央台账，因为中央台账不存在。

必须输出：目标与用户价值、完整父链、验收意图 `UAT/DOM/SIT/GWT/contract`、证据层 `local_contract/api_integration/user_acceptance`、直接依赖、OPEN、并行冲突风险与受影响棘轮、通过/阻断结论和下一阶段。

无法唯一定位代码 owner、父子规格冲突或验收不可观察时返回 `GATE_BLOCK`，建议进入 `/prd` 或 `/design`。

自然语言等价触发："先分析""看归属""怎么拆""有哪些风险"。

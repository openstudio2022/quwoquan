# /verify

目标：复核增量是否满足一棵树和测试覆盖。

准入：
- 已完成 `/dev`、`/extend`、`/deploy`、`data-*` 或其他增量阶段。
- 已有或可收集测试、门禁、文档和 E2E 证据。

检查：
- 读取 `docs/agent_context_contract.md` 与 `docs/agent_command_simulation_matrix.md`。
- AppRoot UAT 是否受影响并有 user_acceptance/api_integration。
- 业务能力 SIT 是否闭环并有 local_contract/api_integration。
- Story GWT/contract 是否闭环并有 local_contract。
- metadata、seed、mock、页面质量、runtime error、CR 是否同步。
- 异常/恢复、性能、安全/隐私、可观测、可靠性/可用性、数据一致性是否按 `quality_facet` 有证据。
- 是否完成 `docs/agent_context_contract.md` 要求的完成后多视角验收复盘：测试、E2E、产品/UX、运营观测、自动化/门禁、剩余风险。
- 若触及跨域链路，是否证明 Data / Service / App / Behavior / Recommendation / Observability / Environment 无断点。

输出：通过、缺口、需重跑命令、未覆盖证据和剩余风险。

出口：
- 输出 `Exit Review` 七项。
- 任何 `implemented/completed` 但无测试证据的项必须标记为缺口。
- 任何适用的非功能质量维度缺少证据，必须标记为 `GATE_BLOCK`。
- 若需要下一轮规划，先完成本轮缺口归因，再进入 `/plan-next`。

自然语言等价触发：用户说“检查是否完成”“收口一下”“验一下这轮改动”时，也按 `/verify` 语义执行。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。

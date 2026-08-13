---
name: /verify
id: verify
category: Quality
description: 以同一规格父链审核增量是否真实达成，失败先归因、环境阻塞如实报告
---

# /verify

目标：以同一规格父链审核增量是否真实达成。

检查：

1. `make feature-context TARGET=<target>` 的 REQ/UAT/DOM/SIT/GWT/DEC 是否与代码和行为一致。
2. `local_contract / api_integration / user_acceptance` 是否覆盖对应验收锚点；测试结果而非文档状态是证据。
3. metadata/codegen、Mock↔Remote、runtime error、权限、生命周期、页面四态、性能、安全隐私、可靠性、观测、配置、灰度和回滚是否适用并有证据。
4. 运维运营证据显式核对：SLI/SLO、指标与告警、配置来源、灰度与回滚是否按根 `AGENTS.md` 可观测与配置门声明并可追踪（不重复展开清单，缺证据即适用维度不达标）。
5. 跨域变更是否证明 Data → Service → App → Behavior → Recommendation → Observability → Environment 无断点。
6. `make verify-feature-tree` 和 `make feature-tree-change-report` 是否通过；不得有未归属业务变更。
7. 已完成 OPEN 是否删除并转为当前规格；未完成项是否仍位于最低 owner 节点。

失败与阻塞处理：

- 任何测试失败或门禁红灯必须先归因四选一（`本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky`）再定性；归因需基线对照证据（HEAD 版本重跑、`git log --follow`、复跑），并行中间态如实交接、不修不掩盖。
- 环境依赖缺失（URL、token、容器、凭证）按阻塞报告并说明影响的证据层，不得静默跳过或以静态声明代替执行。
- 受影响的棘轮基线（ceiling 类门禁）列出当前值与收敛方向，只减不增；新增残量直接阻断。

输出通过/阻断、证据、未跑验证原因和 Exit Review。任何适用维度无证据、失败未归因、OPEN `block` 未解决或测试失败时返回 `GATE_BLOCK`。

自然语言等价触发："验证""检查是否完成""收口"。

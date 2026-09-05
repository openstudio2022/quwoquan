# L3 Story：轻量增量代码健康治理 (`incremental-code-health-governance`)

> 所属能力：[系统架构与工程规范](../spec.md)
>
> Journey / Scenario：本 Story 为横切工程能力，不直接承接用户 Journey。
>
> 设计归属：[L2 DEC-031](../design.md#dec-031)

## 1. 用户价值

作为持续交付代码的开发者或 Agent，我希望每个 candidate 在数分钟内得到只针对新增或恶化维护债的可复现结论，从而在不让存量债拖死交付的前提下保持代码可理解、可复用、可验证。

## 2. 范围与非目标

### In Scope

- source 分类、复杂度、重复、可达性、文件规模与手写变更认知预算的 candidate delta。
- L0、L1、Delivery Gate 与 weekly report-only 的分层调度和 digest-bound receipt。
- Agent PRE/POST、Review named evidence、AI advisory 与热点 OPEN 的边界。

### Out of Scope

- 以总代码行数或提交数评价 Agent/个人，或要求一次清零全部存量债。
- 常驻质量服务、中央债务台账、路径豁免、AI 自动准出或自动删除可达性不确定代码。
- SBOM/许可证、Data JSON Schema 标准兼容和 release domain-model compatibility。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 candidate delta 只判新增或恶化事实

- 每个 changed path 必须互斥分类，generated/vendor/test 与手写生产代码使用不同判据。
- 首日 blocker 只来自确定性高置信新债；存量、无法证明的动态入口和 calibration 指标只报告。
- 删除、rename、codegen、fixture 与大迁移必须单列，不能仅按 churn 大小阻断。

<a id="req-002"></a>
### REQ-002 证据、调度与准出 authority 单轨

- delta receipt 必须绑定 exact Git range、changed paths、candidate exact bytes、policy、命令和 toolchain，输入漂移后不得复用。
- L0、L1、PR 与 scheduled 只改变执行深度，不复制指标阈值或建立第二策略。
- 确定性 terminal 不得被 AI、Reviewer、自然语言理由或旧 receipt 改写。

<a id="req-003"></a>
### REQ-003 calibration 与热点观测保持轻量

- advisory 指标只有达到最小时间/PR 样本、误报与耗时目标后，才能由显式策略版本人工升格。
- weekly 报告只输出容量趋势、churn、health 与 Top hotspots，不阻断 PR、不提交 snapshot。
- 连续出现且可行动的热点才进入最低 owner OPEN，不产生中央 backlog。

## 4. 契约引用

- canonical policy：`quwoquan_ops/policies/code_health_policy.yaml`
- canonical impact：`quwoquan_ops/ci/impact_planner_core.py`
- canonical evidence：`quwoquan_ops/cli/lib/evidence_fingerprint.py`
- canonical entry：`make verify-code-health-delta`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 changed-code 新债得到 typed terminal

- GIVEN candidate 同时包含手写、测试、generated、vendor、contract、config 与 docs 变更。
- WHEN 执行 canonical code-health delta。
- THEN 每个 path 恰好落入一种分类，只有手写生产代码参与复杂度、重复与认知预算判罚。
- THEN 新越过 1000 行、既有超限继续上升或新增无入口 private Python module 返回 `GATE_BLOCK`。
- THEN 复杂度、重复和 800 行候选阈值在 calibration 阶段只返回 `PR_WARN`。
- THEN rename、delete、generated regeneration 与具备单一验收切片的大迁移不因原始 churn 单独阻断。

<a id="gwt-002"></a>
### GWT-002 receipt 对输入漂移 fail-closed

- GIVEN 一份已经生成的 code-health receipt。
- WHEN changed paths、base/head、candidate 字节、policy 或 toolchain 任一变化。
- THEN 新运行产生不同 EvidenceFingerprint，旧 receipt 不得充当该 candidate 的 PASS。
- THEN clean CI 独立重算 exact range，不信任本地脏树或旧 named evidence。
- THEN 未达到 calibration 的 14 天或 20 PR 与低于等于 10% confirmed false-positive 条件时，策略拒绝自动把 advisory 升为 blocker。

<a id="gwt-003"></a>
### GWT-003 本地、CI、Agent 与周报分责

- GIVEN Agent 正在实现一个唯一 owner 的 candidate。
- WHEN PRE、L0、L1、Review、Delivery 与 weekly 生命周期依次消费代码健康事实。
- THEN PRE 只加载本 owner 的紧凑阈值和热点，POST 生成 current delta receipt，Reviewer 与 AI 只消费命名证据。
- THEN L0 不安装网络工具且只做 changed-file 快判，L1/Delivery 执行完整 delta，weekly 全量报告不阻断 PR。
- THEN `PR_WARN` 只能被裁决为 candidate 内修复、最低 owner OPEN 或 out-of-scope，重复两次后才可 distill 为绑定 deterministic check 的规则候选。

## 6. 依赖

- 前置要求：canonical impact planner 与 EvidenceFingerprint 可用。
- 上游事实：exact base/head、changed paths、owner identity、candidate 字节与 policy/toolchain identity。
- 下游结果：typed report、named evidence、Delivery Gate 结论与 report-only hotspots。
- 父级设计：`DEC-031`。

## 7. 开放事项

无本 Story 内开放事项。

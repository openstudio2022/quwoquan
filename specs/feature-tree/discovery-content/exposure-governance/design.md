# L2 Design：曝光治理 (`exposure-governance`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康”需要 `activity-adaptive-exposure`、`content-lifecycle-resurfacing`、`cross-session-fatigue-memory`、`dimension-frequency-and-neardup`、`dynamic-exposure-budget`、`exposure-observability-capacity`、`ops-intervention-and-policy-ejection`、`served-dedup-write-behind` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`activity-adaptive-exposure`](./activity-adaptive-exposure/spec.md)：按用户活跃度调整曝光窗口、探索比、复活比和频控强度，不突破全局安全边界。
- [`content-lifecycle-resurfacing`](./content-lifecycle-resurfacing/spec.md)：`retired` 内容不得因复活源绕过合规准入。
- [`cross-session-fatigue-memory`](./cross-session-fatigue-memory/spec.md)：过滤路径用 membership 点查或近似结构，禁止长窗口全量 `SMembers`。
- [`dimension-frequency-and-neardup`](./dimension-frequency-and-neardup/spec.md)：定义“维度频控与近重复”的可观察主路径、失败语义及父能力交接。
- [`dynamic-exposure-budget`](./dynamic-exposure-budget/spec.md)：按内容池质量和反馈动态分配曝光预算，同时保留探索下限、总预算与回滚边界。
- [`exposure-observability-capacity`](./exposure-observability-capacity/spec.md)：定义“曝光可观测性容量”的可观察主路径、失败语义及父能力交接。
- [`ops-intervention-and-policy-ejection`](./ops-intervention-and-policy-ejection/spec.md)：所有干预必须可审计，可过期，可回滚。
- [`served-dedup-write-behind`](./served-dedup-write-behind/spec.md)：召回/过滤阶段下推 served exclude，过滤用候选集 `SISMEMBER` 批量点查或短 Bloom，禁止长窗口全量 `SMembers` 回读。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 推荐反馈状态必须分离
- 决策：推荐反馈状态必须分离。
- 理由：推荐曝光治理的商用成熟度能力：served/impressed 双轨、疲劳、频控、动态预算、复活、活跃度自适应与曝光健康。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`activity-adaptive-exposure`](./activity-adaptive-exposure/spec.md)、[`content-lifecycle-resurfacing`](./content-lifecycle-resurfacing/spec.md)、[`cross-session-fatigue-memory`](./cross-session-fatigue-memory/spec.md)、[`dimension-frequency-and-neardup`](./dimension-frequency-and-neardup/spec.md)、[`dynamic-exposure-budget`](./dynamic-exposure-budget/spec.md)、[`exposure-observability-capacity`](./exposure-observability-capacity/spec.md)、[`ops-intervention-and-policy-ejection`](./ops-intervention-and-policy-ejection/spec.md)、[`served-dedup-write-behind`](./served-dedup-write-behind/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 可观测容量：重复曝光率、覆盖率、曝光基尼、复活率、各池 CTR、内存和写放大。
- 告警：`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_rec_model`。

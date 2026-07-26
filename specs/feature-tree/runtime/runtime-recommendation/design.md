# L2 Design：运行时推荐 (`runtime-recommendation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测”需要 `dual-channel-recommendation-engine` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)：**SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 推荐特征读取、策略解析和排序执行使用显式 Port
- 决策：推荐特征读取、策略解析和排序执行使用显式 Port。
- 理由：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 曝光记忆容量：`ExposureMemory` 按 `user+day` 分桶 + cardinality budget，海量阶段切 rolling bloom/CMS/分桶 ZSET，过滤开销不随会话曝光量线性放大。

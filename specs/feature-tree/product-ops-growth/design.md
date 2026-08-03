# L1 Design：product-ops-growth（运营横切） (`product-ops-growth`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。

## 2. 领域模型与所有权

- authoritative ownership：拥有产品行为事件、实验定义与分桶事实、运营反馈、策略建议、控制面审计事实，以及账号治理 case/review/decision/投递回执的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-002 / SCN-005`](../spec.md#scn-005) — 在“原生首帧、Flutter 启动恢复与启动遥测”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。
- [`JNY-010 / SCN-023`](../spec.md#scn-023) — 在“对象对外分享分发”中，接收脱敏事件与归因事实，形成可查询指标、实验或渠道转化结果。

## 4. 架构与数据流

- [`event-ingestion-and-analytics`](./event-ingestion-and-analytics/spec.md)：App 产品事件/异常、受限启动诊断、Elasticsearch 明细/聚合、Portal 查询和推荐反馈边界的端到端验收。
- [`experiment-bucketing-and-rollout`](./experiment-bucketing-and-rollout/spec.md)：推荐/搜索服务端权威分桶、实际流量事实归因，以及未绑定 Product Ops 控制面的 fail-closed 单轨验收。
- [`feedback-optimization-loop`](./feedback-optimization-loop/spec.md)：反馈优化大循环：行为反馈 → 兴趣/人群画像派生 → 元数据驱动的推荐策略解析与自调建议 → 人审发布。算法侧闭环（content 派生 + user 投影 + recpolicy 热加载引擎 + 顾问 suggest-only）。
- [`outbound-share-distribution`](./outbound-share-distribution/spec.md)：5 类对象统一对外分享分发（微信卡片/海报/口令/系统分享），携带归因并可靠回流。
- [`product-control-plane-foundation`](./product-control-plane-foundation/spec.md)：统一产品事件、实验、反馈优化与发布治理
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 产品事件、实验与策略评估使用同一归因和控制面
- 决策：产品事件、实验与策略评估使用同一归因和控制面。
- 理由：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`event-ingestion-and-analytics`](./event-ingestion-and-analytics/spec.md)、[`experiment-bucketing-and-rollout`](./experiment-bucketing-and-rollout/spec.md)、[`feedback-optimization-loop`](./feedback-optimization-loop/spec.md)、[`outbound-share-distribution`](./outbound-share-distribution/spec.md)、[`product-control-plane-foundation`](./product-control-plane-foundation/spec.md)

<a id="dec-002"></a>
### DEC-002 Product Ops 决定生产与 UserAccount 执行使用单一 HTTP outbox 轨道
- 决策：Product Ops 以唯一 `AccountEnforcementCase` 聚合拥有 moderation/appeal 双签与不可变 decision；decision 只通过持久化 HTTP outbox 和受限服务身份调用 UserAccount，application receipt、bounded retry、terminal DLQ 与同 decision recovery 均留在 Product Ops。
- 理由：审批事实与账号状态属于不同一致性边界；明确 producer/executor 所有权可避免 Product Ops 直写 User、User 反向复制 workflow，以及消息/同步双发产生的双重处罚。
- 被否决方案：包括 Product Ops 直写 UserAccount 数据库、User Service 持有审批、拆分两套 aggregate、MQ 与 HTTP 双发、DLQ 保存原始 payload，以及恢复时签发新 decision。
- 约束与影响：UserAccount public internal command 以 decision id 幂等并校验稳定 digest。只有已交付的最新 Suspend 可开启 appeal，任一 unresolved delivery 阻止同账号的新 case。Alpha/Beta/Gamma 缺少 target-scoped operator conformance、scope、服务身份或 DLQ/readiness 证据时 `GATE_BLOCK`；Prod 额外强制真实 OIDC。
- 关联要求：`REQ-001`、`REQ-002`
- 关联能力：[`product-control-plane-foundation`](./product-control-plane-foundation/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。

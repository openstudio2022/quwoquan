# L1 Design：product-ops-growth（运营横切） (`product-ops-growth`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。

## 2. 领域模型与所有权

- authoritative ownership：拥有产品行为事件、实验定义与分桶事实、运营反馈、策略建议和控制面审计事实的生命周期与写入决定权。
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

- [`event-ingestion-and-analytics`](./event-ingestion-and-analytics/spec.md)：App 产品事件/异常、受限启动诊断、SLS 明细/聚合、Portal 查询和推荐反馈边界的端到端验收。
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

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。

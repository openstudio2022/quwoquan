# design：event-schema-governance

## 设计动因

当前仓库同时存在：

- `AnalyticsEvent`
- `AppLogService` 日志 envelope
- `BehaviorEvent`
- `AssistantInteractionEvent`
- `VisitRecord`

它们在命名、字段、幂等、上报路径与保留策略上均不统一，导致无法可靠地进入统一运营与学习闭环。

## 设计结论

采用统一 EventEnvelope + 字段分级 + 事件版本治理：

1. 允许不同领域保留 `payload` 扩展；
2. 统一公共 context 与反馈语义；
3. 通过 `eventId + eventVersion` 保证幂等与兼容；
4. 通过 `priority/sampleRate/retentionClass` 控制成本与背压。

## 与现有代码的映射

- `AppLogContext` 已提供 `sessionId / journeyId / pageVisitId / requestId` 等字段，可映射到统一 context。
- `CloudRequestHeaders` 已提供 `surfaceId / operationId / routeId` 等网关上下文，可映射到统一 context。
- `BehaviorEvent` 需扩展 `eventId / experimentBucket / entity / shareTarget` 等字段。
- `AssistantInteractionEvent` 与 Scorecard 需映射为 `learning` 域 payload。

## 判重策略

- 端侧负责生成稳定 `eventId`；
- Gateway 负责快速幂等校验与基础 schema 校验；
- EventBus/OLAP 消费端负责批量幂等与版本兼容；
- Redis 热路径保留状态级去重，以支撑在线过滤与实时兴趣更新。

## 兼容策略

- `eventVersion` 升级不得破坏旧消费者；
- baseline 阶段允许旧事件通过 adapter 转换进入新 envelope；
- 长期目标是淘汰旧事件模型，避免双写无限期存在。

## 风险与对策

- 风险：高频播放器或聊天事件造成总线与 OLAP 压力。
  - 对策：P2 采样、窗口聚合、客户端批量上报。
- 风险：Assistant 学习与推荐特征对 PII 使用边界不一致。
  - 对策：统一字段分级与 `trainingEligible` 标记。
- 风险：实验字段缺失导致无法复盘。
  - 对策：experimentBucket 进入 context 必填维度。

## 未来演进

- 后续将 schema 进一步 metadata 化，并用 codegen 驱动端侧 reporter、服务端 validator 与数仓表结构；
- 本 baseline 先冻结语义与治理规则，供后续实现与 metadata 改造使用。

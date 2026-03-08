# realtime-gateway 任务列表

## 当前交付任务

- [ ] T1: [metadata] 创建 `contracts/metadata/realtime/connection/` — aggregate.yaml + fields.yaml + storage.yaml + events.yaml + service.yaml
- [ ] T2: [codegen] make verify-metadata && make codegen
- [ ] T3: [runtime] 创建 `services/realtime-gateway/` 服务骨架（cmd/api/main.go + configs + Makefile）
- [ ] T4: [domain] 实现 Connection + Topic 领域模型
- [ ] T5: [application] 实现 Hub — 连接注册/注销 + topic 路由 + fanout 广播
- [ ] T6: [application] 实现 TransportService — 自适应传输状态机管理
- [ ] T7: [adapter] 实现 ws_handler.go — WebSocket Upgrade + 帧读写 + 心跳
- [ ] T8: [adapter] 实现 poll_handler.go — Long-polling 端点（hold + timeout + 即时返回）
- [ ] T9: [adapter] 实现 redis_subscriber.go — Redis Pub/Sub 消费 → Hub.Broadcast
- [ ] T10: [infra] 实现 redis_presence.go — 在线状态存储（presence:user:{uid} Redis Hash）
- [ ] T11: [adapter] 实现 channel_webhook_handler.go + FeishuAdapter — 外部渠道 Webhook 入口
- [ ] T12: [infra] 实现 transport_state_cache.go — 用户传输状态 Redis 缓存
- [ ] T13: [观测] 实现 metrics.go — Prometheus 指标注册 + 中间件
- [ ] T14: [资源] 实现 per-user 连接限制 + per-node 容量限流 + connection_replaced 帧
- [ ] T15: [背压] 实现写缓冲背压处理（预警/合并/溢出断连）
- [ ] T16: [config] 实现 realtime 配置端点 GET /v1/config/realtime（系统级参数下发）
- [ ] T17: [端侧] 创建 `lib/cloud/services/realtime/` — RealtimeConnectionManager (Mock + Remote)
- [ ] T18: [端侧] 实现自适应传输状态机（idle ↔ active ↔ background）
- [ ] T19: [端侧] 创建 `lib/ui/chat/providers/realtime_provider.dart` — Riverpod Provider 集成
- [ ] T20: [端侧] 实现 Long-polling 客户端（自动重连循环 + inbox 更新处理）
- [ ] T21: [测试] L2 云侧：WebSocket 生命周期 + topic fanout + 跨节点路由 + 资源限制 + 背压
- [ ] T22: [测试] L2 云侧：Long-polling 端点功能测试
- [ ] T23: [测试] L3 端侧：RealtimeConnectionManager 状态机 unit test
- [ ] T24: [部署] 更新 deploy/shared/process_domain_mapping.yaml（已完成）+ Dockerfile + k8s manifest
- [ ] T25: [门禁] make gate 通过

## 搁置任务

- [ ] config-push V2 完整实现（重启条件：运营有热更新 feature flag 需求）
- [ ] protobuf/msgpack 帧压缩（重启条件：JSON 帧占带宽 > 30%）
- [ ] 连接迁移/无损漂移（重启条件：滚动更新频率 > 1 次/天）
- [ ] 多区域就近接入（重启条件：海外用户 > 10% DAU）

## 未来演进任务

- [ ] DingTalk/Slack 等更多 ChannelAdapter 实现
- [ ] 消息持久化队列（Redis Streams 替代 Pub/Sub，保证不丢）
- [ ] 连接质量评估指标（RTT/丢包率 → 自动调整心跳间隔）

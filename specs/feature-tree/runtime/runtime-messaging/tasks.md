# 开发任务：runtime-messaging

**实现状态：IN_PROGRESS**（基础 envelope 和 MQ 中间件已完成；可靠异步任务通道进入模块化部署与设计冻结阶段）

- [x] 实现：MessageEnvelope + MessageMeta — `runtime/messaging/messaging.go`
- [x] 实现：WrapMQConsumer/WrapMQPublisher（delegate to observability）
- [ ] 实现：幂等消费（dedup by messageId）（L4）
- [ ] 实现：重试 + DLQ 策略（L4）
- [ ] 实现：Outbox/Inbox 一致性模式（L5）
- [x] 规格：可靠异步任务通道 spec/design/acceptance 初版
- [x] 规格：模块化部署 module/package/catalog/retention 纳入可靠通道规划
- [x] 部署：新增 `deploy/shared/module_package_mapping.yaml`
- [x] 部署：新增 `deploy/shared/reliable_task_module_catalog.yaml`
- [x] 部署：新增 `deploy/shared/reliable_task_retention_policy.yaml`
- [x] 门禁：新增 module/package/catalog/retention/permission/migration 静态校验脚本
- [ ] 实现：`runtime/reliabletask` 公共 runtime 包
- [ ] 实现：事务性 Outbox writer、dispatcher、ready queue、worker runtime、notification outbox、DLQ
- [ ] 接入：`chat` 首批完整迁移，关闭私有 scheduler/timer/local queue 双链路
- [ ] 接入：`user` 头像传播与 `content` 非头像投影场景
- [ ] 测试：envelope 序列化/反序列化单元测试
- [ ] 测试：幂等消费契约测试
- [ ] 测试：reliable-task T1-T4 故障注入
- [ ] gate：集成到 make gate

# 开发任务：event-schema-governance

## 阶段 0：schema 冻结
- [ ] 冻结 EventEnvelope、context、business、feedback 四层结构
- [ ] 冻结字段分级、eventVersion、eventId、priority、sampleRate 语义
- [ ] 冻结兼容升级、双写迁移与回滚策略

## 阶段 1：metadata 与 validator
- [ ] 补齐 metadata/schema 定义与 codegen/validator 影响面
- [ ] 建立服务端 schema validator 与端侧 reporter 校验入口
- [ ] 明确旧事件模型的 adapter 方案

## 阶段 2：实现与存储策略
- [ ] 实现幂等、采样、背压、保留期、冷热分层控制点
- [ ] 衔接 Redis 热路径、EventBus、OLAP 与对象存储
- [ ] 确保 `surface/route/operation/experiment` 等公共维度同源

## 阶段 3：测试与 gate
- [ ] contract：schema 兼容、字段等级、幂等键
- [ ] integration：重试/补数/回放/背压场景
- [ ] gate 验证

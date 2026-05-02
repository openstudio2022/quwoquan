# 特性：端云一体化迁移（DDD + 元数据驱动）

## 目标（User Value）
- [ ] 建立“运营 + 运维 + 领域服务”统一迁移模板，支撑商用发布路径
- [ ] 保证端侧 mock/remote 无感切换，云侧契约和存储可追溯
- [ ] 将字段策略从硬编码迁移为 metadata 驱动，降低迭代成本

## 范围（Bounded Context）
- **云侧服务/对象**：`platform-ops`、`product-ops`、`chat-service`、`content-service`、`orchestrator-service`
- **端侧页面/对象**：`chat.conversation.list`、`chat.conversation.detail`、`home.feed.discovery`
- **接口**：
  - `/v1/chat/conversations`
  - `/v1/chat/conversations/{conversationId}/messages`
  - `/v1/orch/discovery/feed`
  - `/v1/product-ops/events`
  - `/v1/product-ops/experiments/bucket`
- **OpsX 变更**：`OPSX-2026-005`
- **OpsX 相关规格**：`opsx_ff_cloud_services_guide`、`assistant-domain-catalog-17`

## 非目标（明确不做什么）
- [ ] 不在本特性内完成所有 8 服务代码实现
- [ ] 不在本特性内替换记录全部埋点口径

## 风险与回滚
- **风险**：契约升级后端侧解码不兼容；metadata 缺漏导致日志/统计偏差
- **回滚**：保留旧接口版本与旧 mapper，灰度回退到 mock 数据源

## 里程碑（必须按顺序）
- [x] 1) contracts-first：产出迁移 contracts delta（本目录）
- [x] 2) specs：补齐一次性整改清单与服务构建指南（根 `specs/`）
- [x] 3) tasks：形成端云可执行任务拆解与责任分工
- [ ] 4) TDD：按 acceptance A1~A8 补齐 mock/unit/contract/integration/uat
- [ ] 5) gate：本地 `make gate` + CI required checks 全绿才允许合入


# 任务拆解（端云一体）

## 云侧（quwoquan_service）
- [ ] contracts：更新 OpenAPI + contracts 文档（chat/orchestrator/product-ops）
- [ ] specs：同步服务边界、迁移策略、SLO/SLA 与回滚
- [ ] tasks：在 `quwoquan_service/tasks.md` 关联本特性任务（引用 §0 全服务统一能力）
- [ ] 实现：DDD 分层 + 复用 `runtime/*`（errors/observability/config/messaging/experiments/learning）
- [ ] 测试：单测 + 契约测 + 集成测

### 横切服务任务

- [ ] `product-ops`：
  - [ ] 事件接入与校验（schema + metadata 校验）
  - [ ] 实验分桶与灰度读取 API
  - [ ] 反馈闭环状态查询（采集 -> 评估 -> 策略更新）
- [ ] `platform-ops`：
  - [ ] 统一日志字段模板与告警模板
  - [ ] 配置治理模板（高风险配置灰度/回滚）
  - [ ] 可靠性策略模板（timeout/retry/circuit/rate-limit）

### 领域服务任务（首批）

- [ ] `chat-service`：会话/消息读写接口契约统一，`items/nextCursor` 对齐
- [ ] `content-service`：发现流结构、错误码与 headers 对齐
- [ ] `orchestrator-service`：聚合接口输出与降级策略标准化

## 端侧（quwoquan_app）
- [ ] 页面/数据源迁移：Repository mock/remote 一键切换
- [ ] RemoteRepository：严格按 contracts 解码（items/nextCursor）
- [ ] headers：统一注入（pageId 三段式命名）
- [ ] 测试：单测/集成（必要时加 mock server）

### 首批端侧迁移

- [ ] `chat.conversation.list`：`chatRepositoryProvider` 接管列表来源
- [ ] `chat.conversation.detail`：消息流读取走 chat 远端仓储
- [ ] `home.feed.discovery`：通过 orchestrator 接口读取统一流结构

## 门禁
- [ ] 本地：`make gate`
- [ ] CI：required checks 全绿


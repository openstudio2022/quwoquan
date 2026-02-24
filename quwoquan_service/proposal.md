# Cloud Services Full Spec

## Why

趣我圈 App 当前以端侧 Mock 数据为主，缺少云侧服务的一体化规格。为支撑端云集成、推荐闭环、助手学习回传等能力，需要建立云侧 6 大服务的完整功能规格，包括业务对象、模型、接口与端云契约，作为后续实现与协作的单一事实来源。

## What Changes

- 建立 `quwoquan_service` 目录，作为云侧服务规格的统一输出位置
- 定义 **6 个业务单体 + Gateway + Orchestrator** 的业务对象、领域模型、API 接口与数据契约
- 明确各服务职责边界、端云集成点、反馈与学习数据流
- 覆盖 Content / Circle 推荐能力与用户反馈闭环
- 覆盖 Assistant 反馈→学习链路与 profileUpdateProposal 回流
- 覆盖 product-ops（运营）埋点、实验、访问记录

## Capabilities

### New Capabilities

- `content-service`: 内容服务 — 发现流、Feed、发布、媒体、帮读摘要、内容推荐、内容行为反馈
- `circle-service`: 圈子服务 — 圈子 CRUD、活动流、成员、权限、圈子内推荐、圈子行为反馈
- `user-service`: 用户服务 — 认证、Profile、画像快照、分身（persona）管理、关注关系、用户设置（通知/隐私）、push token 注册、profileUpdateProposal 消费
- `assistant-service`: 助手服务 — Run/ReAct 网关、工具、模板、域配置、反馈同步、学习数据
- `chat-service`: 聊天服务 — 会话、消息投递、联系人、群聊创建与成员管理
- `product-ops`: 产品运营服务 — 策略、埋点、实验、访问记录、内容/圈子行为采集
- `gateway-service`: API 网关 — HTTPS 终端、认证、限流、路由、可观测性
- `orchestrator-service`: 编排服务 — 跨服务流程编排与聚合（发现流/圈子流/可选群聊编排）
- `platform/observability`: 可观测性平台模块 — 统一日志字段/指标/消息 envelope 规范与接入脚本/模板（对接云厂商 SaaS）
- `platform/config`: 系统配置平台模块 — 统一运维/系统配置规范与本地/云侧配置中心落地

### Modified Capabilities

- （无 — 本变更新增云侧规格，不修改现有端侧 spec 的行为要求）

## Impact

- 新建 `quwoquan_service/` 目录及子规格文件
- 端侧 `data_service`、`app_content_repository`、`sync_adapter` 等将依据云规格对接真实 API
- 影响端侧 Assistant 的 `CloudStubSyncAdapter`、`userProfileSnapshot` 注入、`contextScopeHint` 中的 `historicalRetrievalFeedback`

## 历史澄清对齐（已纳入规格）

- 内容/圈子推荐与反馈闭环：Content/Circle 行为上报、显式/隐式反馈枚举、推荐输入含画像与 Visit、反馈驱动推荐优化
- 帮读卡「反馈偏好」：帮读摘要支持反馈偏好动作并纳入推荐
- 助手反馈→学习：interactionEvents/scorecards 上报、historicalRetrievalFeedback 注入 Run、反馈→学习闭环
- profileUpdateProposal 回流：User 服务 created/confirm/reject/apply 完整状态流转

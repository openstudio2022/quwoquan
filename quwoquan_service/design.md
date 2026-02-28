# Cloud Services Full Spec — Design

## Context

趣我圈 App 端侧当前使用 Mock 数据与 LocalMockSyncAdapter / CloudStubSyncAdapter，无真实云服务对接。云侧服务尚未有统一规格，导致端云契约、推荐闭环、助手学习回流等设计分散。本设计建立 **6 个业务单体 + Gateway + Orchestrator** 的整体架构、接口契约与数据流，作为实现与协作基线。并在该基线下新增 `integration-service` 承接外部能力统一集成（首批 location）。

## Goals / Non-Goals

**Goals:**

- 6 个业务单体服务，各服务清晰职责边界
- Gateway 与 Orchestrator 的职责与对接方式
- 各服务业务对象、领域模型、REST/gRPC 接口契约
- 端云集成点与数据流（含推荐反馈、助手学习、profileUpdateProposal 回流）
- 输出至 `quwoquan_service/` 作为云侧规格主目录

**Non-Goals:**

- 不实现具体后端代码
- 不涉及部署与基础设施细节
- 不定义端侧 UI 行为变更

## Decisions

1. **架构选型：6 个独立单体服务**
   - 每个服务（Content、Circle、User、Assistant、Chat、ProductOps）各自为单体服务，独立部署、独立进程。非“一大单体包含所有模块”，而是 6 个单体服务。
   - 业务服务间不直接调用；跨服务流程由编排层统一编排。

2. **网关：独立服务**
   - 网关为**独立单体服务**，不内置在各业务服务中。端侧统一访问网关，网关负责路由、认证、限流、SSL 终端。
   - 业务服务仅被网关、编排层、**产品运营服务（product-ops）**调用，不直接对端侧暴露。

3. **编排层：独立服务，位于各单体之上**
   - 编排服务（Orchestrator）为**独立单体**，位于 6 个业务单体之上。
   - 职责：跨服务流程编排（如发现流推荐需 User 画像 + product-ops 行为 + Content），调用各业务服务并聚合响应。
   - 业务服务间不直接调用；需多服务数据的请求由编排层完成。

4. **运营（product-ops）与接口分层**
   - 各单体服务暴露两类接口：**面向 App**（经网关/编排层）、**面向运营**（仅供 product-ops 调用的管理接口）。
   - 产品运营服务（product-ops）可管理其余 5 个服务，调用其内部管理接口。
   - **运维（平台/SRE）能力不属于 product-ops**：可观测性、系统配置、可靠性/性能基线等以平台模块沉淀（见 `platform/` 与 `contracts/configuration.md`）。

5. **静态资源与 CDN**
   - 各单体产生的静态资源（图片、视频、媒体等）**单独存储**于对象存储（如 S3/OSS），不放在业务服务进程内。
   - 端侧通过 **CDN** 访问静态资源，实现就近加速；CDN 缓存未命中时回源到对象存储。
   - 业务服务上传后返回 CDN 可访问的 URL，端侧直接请求 CDN，无需经业务接口拉取静态文件。

6. **语言栈**
   - Content / Circle / User / Chat / product-ops：Go 主栈，适合高并发与快速迭代
   - Assistant：Python，便于 LLM、ReAct、模板运行时集成

7. **接口风格**
   - 对外统一 REST，内部可辅以 gRPC
   - 版本前缀：`/v1/<service>/...`

8. **技术选型**（详见 `技术选型.md`）
   - **数据库**：MongoDB 为主、PostgreSQL 为辅；最终一致性优先，尽量减少关系型依赖。MongoDB 承载 Content/Circle/Chat/助手学习/product-ops 事件/用户画像；PostgreSQL 仅用于用户身份、认证、profileUpdateProposal 状态等强一致场景。
   - 消息队列：云消息队列 RocketMQ（阿里云/火山引擎托管）
   - 内部通信：编排 ↔ 业务服务 gRPC，运营管理接口 HTTP（由 product-ops 调用）
   - 配置中心（运维/系统配置）：MSE Nacos（阿里云）或云厂商托管等价物（运营配置由 product-ops 管理）
   - 原则：优先使用云厂商 SaaS，避免自建
   - **本地测试**：配置抽象（FileConfigProvider / NacosConfigProvider）；本地用 Docker Compose（MongoDB/PostgreSQL/Redis）与文件配置；单元测试 Mock 外部依赖；通过后再部署云侧对接 SaaS

9. **推荐归属**
   - 发现流推荐：编排层拉取 User 画像、product-ops 行为后调用 Content，Content 负责推荐逻辑
   - 圈子内推荐：编排层拉取 product-ops 行为后调用 Circle，Circle 负责圈子内推荐

10. **反馈→学习链路**
   - 助手反馈：端侧 `AssistentLearningService` 经 Sync 上报 interactionEvents/scorecards 至 Assistant 云服务
   - 云侧消费：Assistant 服务提供 `/v1/assistant/learning/ingest` 等接口，落库并供下次 run 的 `historicalRetrievalFeedback` 使用

11. **profileUpdateProposal 回流**
   - Assistant run 输出 profileUpdateProposal，端侧转发至 User 服务
   - User 服务提供 `POST /v1/user/profile/proposals/{id}/confirm|reject|apply` 等状态 API

12. **可观测性：平台能力优先（SaaS + 统一规范）**
   - 目标：让所有服务以一致方式输出 traceId/requestId、结构化日志、指标与告警信号，便于跨服务排障与影响面分析。
   - 原则：优先使用云厂商日志/APM/指标 SaaS；仓库内仅沉淀“统一规范 + 接入脚本/模板”，不自研监控平台。
   - 规范与归档：见 `platform/observability/` 与 `contracts/log_fields.md`、`contracts/metrics.md`、`contracts/messages/envelope.schema.json`。

13. **工程原则：自动化优先 + 合规可控（Commercial-grade）**
   - 目标：测试/部署/门禁/可观测性接入默认自动完成，避免“人工流程依赖个人经验”。
   - 测试驱动与验收：每个任务必须有可验证验收标准与对应测试（见 `contracts/acceptance_criteria.md`）。
   - 工程自动化：CI/CD、契约校验、安全门禁（secret scan/SCA/SAST）统一（见 `contracts/ci_cd_automation.md`）。
   - 隐私与安全：字段分级可追溯、日志可配置匿名化、存储可配置加密、保留期限可控（见 `contracts/privacy_and_security.md`）。

14. **端云一体化开发：Contract-driven + DDD（Full-stack DDD）**
   - 端侧支持 mock/remote 一键切换；端云契约以 `contracts/` 为单一事实来源。
   - 云侧按领域边界与分层实现（Domain/Application/Adapters/Infrastructure），依赖方向严格“向内”。
   - 端侧数据层按同构分层组织（Domain/UseCase/Repository/DataSource），UI 只依赖抽象。
   - 以上要求与自动化验证见 `contracts/ddd_fullstack_guidelines.md`。

## Risks / Trade-offs

- **[Risk]** 跨服务调用增多 → 通过清晰 API 契约与超时/重试缓解
- **[Risk]** 推荐与行为数据量大 → product-ops 统一埋点、采样与异步处理，Content/Circle 按需消费
- **[Risk]** profileUpdateProposal 类型漂移 → 固定 schema 与 versioned API，强校验

## Migration Plan

1. 建立 `quwoquan_service/` 目录与各服务 spec
2. 端侧逐步替换 Mock/Stub：DataService → Content API，SyncAdapter → Assistant/Chat API
3. 分阶段上线：User/Auth → Content/Circle → Chat → Assistant → product-ops 埋点

## 反馈与闭环（历史澄清对齐）

- **用户反馈→推荐优化**：Content/Circle 行为上报（显式：点赞/收藏/不感兴趣/举报；隐式：曝光/点击/停留）落库 → product-ops 统一采集 → Content/Circle 推荐按需消费 → 特征/策略更新 → 推荐结果优化
- **助手反馈→学习**：端侧 recordInteraction/recordExplicitFeedback → Sync 上报 interactionEvents/scorecards → Assistant 云落库 → 下次 Run 注入 historicalRetrievalFeedback → 推理与策略调整
- **profileUpdateProposal 回流**：Assistant run 输出 → 端侧转发 User 服务 → created/confirm/reject/apply 状态流转 → Profile 落库

## Open Questions

- 推荐模型/策略：自研 vs 第三方（如向量检索、排序模型）选型待定
- Assistant 云服务与端侧 Agent Loop 的职责切分（纯云 run vs 端云协作）待细化

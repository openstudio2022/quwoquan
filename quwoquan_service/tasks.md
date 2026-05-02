# Cloud Services Full Spec — Tasks

## 0. 全服务统一能力（必须，且必须使用公共库）

> 本节为“所有服务都必须交付”的一致性能力门槛：包括**运维/平台能力**与**运营/反馈闭环**。
> 各业务服务若未满足本节要求，即使业务 API 完成也视为“不具备上线条件”。

### 0.1 运维/平台能力（系统级）

- [ ] 0.1.1 统一错误码与响应：遵从 `contracts/error_codes.md`，并使用公共错误库（见 §13）
- [ ] 0.1.2 统一可观测性：结构化日志/指标/trace，遵从 `contracts/log_fields.md`、`contracts/metrics.md`、`contracts/openapi/common.yaml`，并使用公共可观测库（见 §11、§13）
- [ ] 0.1.3 统一告警与 SLO：至少覆盖错误率、延迟（p95/p99）、依赖失败、队列积压、资源异常（模板见 §11）
- [ ] 0.1.4 统一系统配置：遵从 `contracts/configuration.md`，通过 `ConfigProvider` 抽象接入配置中心/Secrets/env/file（见 §12、§13）
- [ ] 0.1.5 统一可靠性与性能基线：超时/重试/熔断/限流/降级开关均可配置、可灰度、可回滚（见 `contracts/configuration.md`）
- [ ] 0.1.6 统一服务治理：健康检查/优雅关停/版本化/幂等/兼容性/安全脱敏，遵从 `contracts/service_governance.md`
- [ ] 0.1.7 统一开发前字典/口径：endpoint 目录、authn/authz、ID/分页、保留/采样，遵从 `contracts/endpoint_catalog.md`、`contracts/authn_authz.md`、`contracts/id_and_pagination.md`、`contracts/data_retention_and_sampling.md`
- [ ] 0.1.8 统一验收标准与测试驱动：每个任务必须提供验收标准与对应测试，遵从 `contracts/acceptance_criteria.md`
- [ ] 0.1.9 CI/CD 与工程自动化：测试/部署/安全门禁/可观测性接入默认自动完成，遵从 `contracts/ci_cd_automation.md`
- [ ] 0.1.10 隐私与安全数据保护：字段分级标注、日志可配置匿名化、存储可配置加密、隐私数据保留可控，遵从 `contracts/privacy_and_security.md`
- [ ] 0.1.11 端云一体化 DDD：分层/依赖方向/聚合与事件/契约驱动流程/自动化验证，遵从 `contracts/ddd_fullstack_guidelines.md`
- [ ] 0.1.12 特性粒度交付：Ask/Plan→contracts-first→TDD→门禁→合入，遵从 `contracts/feature_delivery_workflow.md`

### 0.2 运营与反馈闭环（业务级 + AI 自学习/自动优化）

- [ ] 0.2.1 统一反馈事件规范：所有“可优化”的用户行为与系统输出必须以事件形式记录/上报，遵从 `contracts/feedback_and_learning.md`
- [ ] 0.2.2 统一异步链路追踪：消息/任务必须携带 `parentTraceId` / `causationId`（`contracts/messages/envelope.schema.json`），并在日志中可检索
- [ ] 0.2.3 自动化优化与自学习：推荐/助手等 AI 相关能力必须具备“数据采集→评估→策略/模型更新→灰度发布→回滚”的最小闭环（见 `contracts/feedback_and_learning.md`）

### 0.3 端云一体化工程重整（特性粒度 + 元数据驱动 + 一致性）

- [ ] 0.3.1 全量特性台账：维护 `changes/feature_catalog.yaml`，每个特性必须有 `changes/<date>-<slug>/`
- [ ] 0.3.2 特性映射完整：每个特性必须补齐 `traceability.yaml`（服务/对象/API/横切能力/测试）
- [ ] 0.3.3 模型元数据契约：维护 `contracts/metadata/entity_catalog.yaml`、`field_policy.yaml`、`event_catalog.yaml`
- [ ] 0.3.4 元数据驱动落地：字段分类/日志策略/观测统计/运营统计不得硬编码，统一按 metadata
- [ ] 0.3.5 一致性机检：`scripts/verify_feature_traceability.sh`、`scripts/verify_contract_metadata.sh` 纳入 gate
- [ ] 0.3.6 AI Agent 自动化：按特性目录执行 Ask/Plan→contracts-first→TDD→实现→门禁→合入

### 0.4 一次性整改执行（F005）

- [ ] 0.4.1 对齐整改清单：`specs/one_shot_rectification_tasklist.md`
- [ ] 0.4.2 横切与领域构建遵从：`specs/fullstack_service_build_guide.md`
- [ ] 0.4.3 特性实例落地：`changes/2026-02-23-opsx-ddd-metadata-feature-migration/`

## 1. 规格输出与目录

- [x] 1.1 创建 `quwoquan_service/` 目录并建立 README
- [x] 1.2 将 proposal、design、specs、tasks 同步至 `quwoquan_service/` 作为云侧规格主输出

## 2. Content 服务

- [ ] 2.0 接入全服务统一能力（见 §0，必须使用公共库）
- [x] 2.1 定义 Content 服务 API 契约（OpenAPI 或等价）
- [ ] 2.2 实现 Feed 接口 mock 或 stub
- [ ] 2.3 实现内容行为上报接口 mock
- [ ] 2.4 实现推荐接口 mock（含输入输出 schema）
- [ ] 2.5 实现评论接口 mock（列表/创建/删除）
- [ ] 2.6 实现互动状态与计数接口 mock（reactions/counters）
- [ ] 2.7 实现媒体资产状态查询接口 mock（media/{id}，预留异步管线）
- [ ] 2.8 推荐/排序的自动化优化闭环（反馈采集、离线评估、策略/模型版本化与灰度发布）

## 3. Circle 服务

- [ ] 3.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 3.1 定义 Circle 服务 API 契约
- [ ] 3.2 实现圈子 CRUD 与活动流接口 mock
- [ ] 3.3 实现圈子行为上报接口 mock
- [ ] 3.4 圈子内推荐/治理的自动化优化闭环（反馈采集、评估、策略更新与灰度）

## 4. User 服务

- [ ] 4.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 4.1 定义 User 服务 API 契约
- [ ] 4.2 实现 Profile 与画像快照接口 mock
- [ ] 4.3 实现 profileUpdateProposal 消费接口（created/confirm/reject/apply）
- [ ] 4.4 实现分身 persona 管理接口 mock（CRUD + activate）
- [ ] 4.5 实现关注关系接口 mock（follow/unfollow/followers/following/relationship）
- [ ] 4.6 实现用户设置接口 mock（privacy/notifications）
- [ ] 4.7 实现 push token 注册接口 mock（devices/push-tokens）

## 5. Assistant 服务

- [ ] 5.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 5.1 定义 Assistant 服务 API 契约（与端侧 run/stream 对齐）
- [ ] 5.2 实现 learning/events、learning/scorecards 上报接口 mock
- [ ] 5.3 实现 policy 拉取接口 mock
- [ ] 5.4 助手自学习闭环（反馈采集、评估/基准、策略/模板版本化、灰度与回滚）

## 6. Chat 服务

- [ ] 6.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 6.1 定义 Chat 服务 API 契约
- [ ] 6.2 实现会话与消息接口 mock
- [ ] 6.3 实现会话创建与群聊成员管理接口 mock
- [ ] 6.4 实现会话设置接口 mock（mute/pin/markRead，预留）

## 7. ProductOps（产品运营）服务

- [ ] 7.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 7.1 定义 product-ops 服务 API 契约
- [ ] 7.2 实现埋点接收接口 mock（含 content_behavior、circle_behavior）
- [ ] 7.3 实现实验分桶与访问记录接口 mock
- [ ] 7.4 运营配置（业务策略/实验/治理规则）变更治理：审计、灰度、生效范围、回滚（规范见 `contracts/configuration.md` 与 `contracts/roles_and_scopes.md`）

## 8. Gateway 服务

- [ ] 8.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 8.1 定义 Gateway 路由、鉴权、限流与 header/trace 透传契约
- [ ] 8.2 实现 gateway stub（路由表 + middleware 形态）

## 9. Orchestrator 服务

- [ ] 9.0 接入全服务统一能力（见 §0，必须使用公共库）
- [ ] 9.1 定义 Orchestrator 编排 API 契约（discovery feed / circle activities）
- [ ] 9.2 实现编排 flow stub（调用 client 占位 + 超时/降级骨架）

## 10. 端云集成准备

- [x] 10.1 端侧 DataService 增加 Content API 适配层（可切 Mock/Remote）
- [ ] 10.2 端侧 CloudStubSyncAdapter 替换为真实 Assistant learning 上报
- [ ] 10.3 端侧 _buildAssistantContextScope 注入 historicalRetrievalFeedback
- [ ] 10.4 端侧 comment_system 接入 Content 评论接口
- [ ] 10.5 端侧 persona 管理页接入 User persona 接口
- [ ] 10.6 端侧群聊创建页接入 Chat 会话创建/成员接口
- [ ] 10.7 端侧 SettingsPage 通知/隐私接入 User settings 接口

## 11. 可观测性平台模块（platform/observability）

- [ ] 11.1 统一日志字段规范落地（见 `contracts/log_fields.md`，各服务日志库对齐）
- [ ] 11.2 统一指标规范落地（见 `contracts/metrics.md`，HTTP/MQ/错误最小集合）
- [ ] 11.3 统一 MQ Envelope 规范落地（见 `contracts/messages/envelope.schema.json`，含 parentTraceId/causationId）
- [ ] 11.4 提供本地/云侧接入脚本与模板（OTEL exporter/collector、采样、字段映射）
- [ ] 11.5 提供仪表盘与告警模板（延迟、错误率、吞吐、队列积压、p95/p99）

## 12. 系统配置平台模块（platform/config）

- [ ] 12.1 配置分层规范落地（见 `contracts/configuration.md`，运营配置 vs 运维/系统配置）
- [ ] 12.2 各服务统一 `ConfigProvider` 抽象与注入规范（file/env/nacos/secrets）
- [ ] 12.3 本地配置目录与示例补齐（`configs/alpha/*.yaml / configs/beta/*.yaml`，用于集成测试）
- [ ] 12.4 运维高风险配置灰度/回滚流程模板（超时/重试/限流/降级/采样）

## 13. 云端公共库（runtime/，强制复用）

- [ ] 13.1 建立公共库清单与职责边界（`runtime/README.md`）
- [ ] 13.2 `runtime/errors`：错误码、错误类型、HTTP/gRPC 映射与脱敏
- [ ] 13.3 `runtime/observability`：logger、metrics、tracing（OTEL），字段对齐 `contracts/*`
- [ ] 13.4 `runtime/config`：ConfigProvider（file/env/nacos/secrets）与动态配置刷新
- [ ] 13.5 `runtime/messaging`：MQ envelope、trace/causation 传播、幂等消费与重试策略
- [ ] 13.6 `runtime/experiments`：实验/灰度查询客户端（对接 product-ops），避免各服务自行实现
- [ ] 13.7 `runtime/learning`：反馈事件模型、评估记录、策略/模型版本元数据（对齐 `contracts/feedback_and_learning.md`）

## 14. 运维域 specs（specs/platform-ops）

- [ ] 14.1 补齐运维/平台域规格与交付物说明（`specs/platform-ops/spec.md`）

## 15. Integration（外部集成）服务

- [ ] 15.0 接入全服务统一能力（见 §0，必须使用公共库）
- [x] 15.1 新建 integration-service 骨架与分环境配置目录
- [x] 15.2 定义 integration/location 元数据（aggregate/fields/storage/events/service/errors）
- [x] 15.3 定义 location nearby/search API 契约（`specs/integration-service/spec.md`）
- [ ] 15.4 落地 location provider adapter（百度/阿里可配置切换）

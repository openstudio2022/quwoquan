# 趣我圈云侧服务规格

本目录为趣我圈云侧 **6 个业务服务 + Gateway + Orchestrator** 的统一功能规格输出，包含服务划分、业务对象、接口契约与端云集成设计。

## 目录结构

- `proposal.md` — 变更动机与能力清单
- `design.md` — 架构与设计决策
- `architecture_review.md` — 架构核对表（对象清单/契约矩阵/一致性分级）
- `技术选型.md` — 数据库、消息队列、服务通信、配置中心等选型
- `contracts/` — 可生成/可校验的端云契约（OpenAPI 等）
- `contracts/error_codes.md` — 统一错误码规范（模块/类型/原因 + user/debug message 分离）
- `contracts/log_fields.md` — 统一日志字段规范（结构化日志）
- `contracts/metrics.md` — 统一指标规范（metrics）
- `contracts/messages/envelope.schema.json` — MQ/异步消息 Envelope 约束（trace/causation 透传）
- `contracts/acceptance_criteria.md` — 统一验收标准与测试驱动（TDD / Quality Gates）
- `contracts/ci_cd_automation.md` — CI/CD 与工程自动化规范（测试/部署/门禁）
- `contracts/endpoint_catalog.md` — 规范化 endpoint 名目录（metrics/logs 归因）
- `contracts/id_and_pagination.md` — ID 生成与 cursor 分页统一规范
- `contracts/authn_authz.md` — 认证与授权统一规范（端侧/服务间调用/persona）
- `contracts/data_retention_and_sampling.md` — 数据保留、采样与成本规范（logs/traces/rum/events）
- `contracts/privacy_and_security.md` — 隐私与安全数据保护（字段分级/脱敏/加密/保留）
- `contracts/ddd_fullstack_guidelines.md` — 端云一体化 DDD 领域驱动设计规范（分层/依赖/流程/自动化验证）
- `contracts/feature_delivery_workflow.md` — 特性粒度交付工作流（Ask/Plan→TDD→门禁→合入）
- `contracts/metadata/` — 模型元数据契约（字段策略驱动端云一致适配）
- `contracts/configuration.md` — 配置分层与统一规范（运营配置 vs 运维/系统配置）
- `contracts/roles_and_scopes.md` — 运营 vs 运维/平台：角色与范围统一定义
- `contracts/feedback_and_learning.md` — 反馈与自动优化/自学习统一规范（推荐/助手闭环）
- `contracts/service_governance.md` — 服务治理统一规范（超时/重试/熔断/限流/健康检查/发布回滚）
- `端云协同落地方案.md` — 端侧按服务组织、mock/remote 切换、联调与测试流程
- `工程目录设计.md` — 各服务工程目录设计
- `tasks.md` — 实现任务清单
- `platform/observability/` — 可观测性平台模块（接入脚本/规范/模板，优先对接云厂商 SaaS）
- `platform/config/` — 系统配置平台模块（配置中心/Secrets/环境变量/治理与本地测试策略）
- `runtime/` — 云端公共库（强制复用，统一日志/错误/配置/MQ/实验/学习闭环）
- `specs/` — 各服务详细规格
  - `content-service/spec.md` — 内容服务
  - `circle-service/spec.md` — 圈子服务
  - `user-service/spec.md` — 用户服务
  - `assistant-service/spec.md` — 助手服务
  - `chat-service/spec.md` — 聊天服务
  - `product-ops/spec.md` — 产品运营服务（业务域）
  - `gateway-service/spec.md` — API 网关
  - `orchestrator-service/spec.md` — 编排服务
  - `platform-ops/spec.md` — 运维/平台域（规范与交付物，非业务 API）

## 服务概览

| 服务 | 职责 |
|------|------|
| Content | 发现流、Feed、发布、媒体、帮读、推荐、内容行为反馈 |
| Circle | 圈子 CRUD、活动流、成员、权限、圈子内推荐、圈子行为反馈 |
| User | 认证、Profile、画像快照、分身、profileUpdateProposal 消费 |
| Assistant | Run/ReAct、工具、模板、域配置、反馈同步、学习数据 |
| Chat | 会话、消息投递、联系人 |
| ProductOps（运营） | 策略、埋点、实验、访问记录（为推荐/运营分析提供数据） |
| PlatformOps（运维/平台） | 可观测性、系统配置、服务治理、SLO/告警（规范与交付物） |

## 本地质量门禁（建议每次改动后运行）

在本目录下执行：

```bash
make gate
```

## 特性粒度交付（Ask/Plan 阶段可直接导入）

- 端云一体特性目录初始化（推荐在仓库根目录执行）：

```bash
cd ..
bash scripts/new_feature_fullstack.sh "<slug>"
```

- 仅云侧特性可使用本目录脚本（兼容入口）：

```bash
bash scripts/new_feature.sh "<slug>"
```

- 可选：安装本地 pre-commit（推荐使用根目录脚本，覆盖端云）：

```bash
cd ..
bash scripts/install-hooks.sh
```

## 规格归属说明

本目录为云侧服务规格的**唯一来源**，不再在 `quwoquan_app` 目录下保留规格副本。  
`openspec/changes/cloud-services-full-spec/`（仓库根下）仅保留 README 指向此处。

跨端云统一规则、命令与全量特性台账在仓库根目录维护：
- `.cursor/rules/*`
- `.cursor/commands/*`
- `changes/feature_catalog.yaml`
- `specs/*.md`

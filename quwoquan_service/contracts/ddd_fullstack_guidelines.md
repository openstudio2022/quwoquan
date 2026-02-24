# 端云一体化 DDD 领域驱动设计规范（Full-stack DDD）

目标：用业界最佳实践把“端侧可 mock 一键切 remote、云侧按领域开发、横切能力统一接入、测试/部署自动化”落成**可执行**工程规范。
原则：业务团队只写业务；横切能力（错误/可观测/配置/MQ/实验/学习闭环/隐私）全部通过 `runtime/` 与平台模板自动完成。

---

## 1. 统一术语与边界（Ubiquitous Language / Bounded Context）

### 1.1 服务边界（Bounded Context）

每个服务即一个主要领域边界（可包含子域模块），禁止跨服务共享领域模型代码：
- Content / Circle / User / Chat / Assistant / ProductOps（产品运营）
- PlatformOps（平台运维域，规范与交付物）
- Orchestrator（跨域编排，属于“应用层编排”，不是业务领域）

跨域协作方式：
- 同步：通过 OpenAPI / gRPC 契约调用（经 Gateway/Orchestrator）
- 异步：通过 MQ（遵从 `contracts/messages/envelope.schema.json`）
- **禁止**：跨服务直接读写对方数据库、共享同一张业务表

### 1.2 领域对象的分类（DDD 概念）

- **Entity（实体）**：有身份（id），可变（如 Post/Comment/Conversation）
- **Value Object（值对象）**：无身份，按值相等（如 Money、TimeRange、Cursor）
- **Aggregate（聚合）**：一致性边界（例如 Conversation 聚合内包含 Member/Settings）
- **Domain Event（领域事件）**：领域事实发生（如 `PostLiked`、`MessageSent`）
- **Repository（仓储接口）**：领域层只依赖接口，不依赖 DB 实现
- **Domain Service（领域服务）**：不天然属于某个实体的领域规则

---

## 2. 分层与依赖方向（强制）

统一采用四层（或三层）结构，依赖只允许“向内”：

```
Adapters (HTTP/gRPC/MQ)  ->  Application (UseCases)  ->  Domain (Model/Rules)
                                  |
                                  v
                          Infrastructure (DB/MQ/Cache/External)
```

强制约束：
- Domain 层不得 import HTTP/DB/MQ/配置/日志实现（只能用接口与领域概念）
- Application 层负责事务边界、用例编排、幂等、调用仓储接口与外部端口
- Adapters 只做协议适配（DTO/验证/鉴权上下文提取），不写业务规则
- Infrastructure 只实现端口（repositories、clients、exporters）

横切能力依赖：
- 所有层都可使用 `runtime/errors` 的“领域无关错误类型”与 `ErrorCode`
- 可观测/配置/消息等实现统一由 Application/Adapters 注入，Domain 不直接依赖

---

## 3. 云侧工程目录（建议模板）

以 Go 服务为例（其它语言保持等价分层）：

```
services/<service>/
  cmd/api/main.go
  internal/
    domain/                 # Entity/VO/Aggregate/DomainEvent/DomainService/Repo interface
    application/            # UseCases、AppService、DTO（内部）
    adapters/
      http/                 # handler/router/middleware、request/response DTO
      grpc/                 # 可选
      mq/                   # consumer/producer adapter
    infrastructure/
      persistence/          # mongo/pg 实现、migration
      messaging/            # MQ client、outbox/inbox（如采用）
      cache/                # redis
    bootstrap/              # wiring：DI、config、observability
  tests/
```

Orchestrator 特例：
- 领域规则尽量薄；以 Application 编排与 Anti-Corruption Layer 为主（对下游 DTO 做映射，避免污染上层模型）。

---

## 4. 端侧工程（Flutter）的一体化 DDD 映射

目标：端侧同样按“领域模型 + 用例 + 仓储”组织数据层，并支持 mock/remote 一键切换。

建议把 `cloud/services/<svc>/` 视作“Adapters/Infrastructure”，在其内部再分层：

```
quwoquan_app/lib/
  cloud/services/<svc>/
    domain/                 # 端侧领域模型（Entity/VO），尽量与 contracts 对齐但不等同 DTO
    application/            # UseCases（如 ListDiscoveryFeedUseCase）
    data/                   # Repository impl + DataSource（mock/remote）
      remote/               # HTTP client + DTO + mapper
      mock/
```

强制约束：
- UI（features）只依赖 UseCase/Repository 抽象，不直接依赖 remote DTO
- mock/remote 切换由 provider 统一注入（已有 `AppDataSourceMode`）
- 所有 remote 调用必须附带 `CloudRequestHeaders`（pageId/traceId/requestId）

---

## 5. 契约驱动（Contract-driven）与端云一体开发流程

强制流程（推荐）：
1. 先改 contracts（OpenAPI/Schema）→ 2. 补 specs 场景 → 3. 写契约测试与验收标准 → 4. 实现（server+client）→ 5. 自动化门禁通过 → 6. 部署与观测接入

契约一致性要求：
- 列表响应统一 `items/nextCursor`（`contracts/openapi/common.yaml`）
- 错误统一 `ErrorResponse`（`contracts/error_codes.md`）
- endpoint 名归因（`contracts/endpoint_catalog.md`）

---

## 6. 自动化验证（CI 必选项）

> 目标：把 DDD 分层与端云一体约束“自动验证”，而不是靠 code review 记忆。

CI MUST 自动检查：
- contracts 校验（OpenAPI/JSON schema）
- 分层依赖检查（Domain 不得引用 adapters/infrastructure；client UI 不得引用 remote DTO）
- 契约测试（server stub 与 client mapper 的 schema/golden 校验）
- 关键用例集成测试（Docker Compose + 冒烟）

这些门禁要求在 `contracts/ci_cd_automation.md` 与 `contracts/acceptance_criteria.md` 中执行。


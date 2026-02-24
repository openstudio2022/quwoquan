# 云侧契约（Contracts）

本目录用于落地“可生成/可校验”的端云契约，作为实现与联调的单一事实来源。

---

## 目标

- **以业务对象为基础**：接口围绕 Post/Comment/Persona/Conversation 等对象与其动作（list/create/update/delete）。
- **通用约束统一**：分页、幂等、错误码、trace、persona 上下文在所有服务一致。
- **端云协同**：端侧可基于 OpenAPI 生成/手写 Client；云侧可据此实现 Gateway/服务并跑契约测试。

---

## 目录结构（约定）

```
contracts/
├── authn_authz.md                  # 认证与授权统一规范（端侧/服务间调用/persona）
├── acceptance_criteria.md           # 统一验收标准与测试驱动开发规范（TDD / Quality Gates）
├── ci_cd_automation.md              # CI/CD 与工程自动化规范（测试/部署/门禁）
├── configuration.md                # 配置分层（运营配置 vs 运维/系统配置）与变更治理
├── data_retention_and_sampling.md  # 数据保留、采样与成本规范（logs/traces/rum/events）
├── ddd_fullstack_guidelines.md      # 端云一体化 DDD 领域驱动设计规范（分层/依赖/流程/自动化验证）
├── endpoint_catalog.md             # 规范化 endpoint 名目录（metrics/logs 归因）
├── error_codes.md                  # 统一错误码与 requestId/traceId 分段格式
├── feature_delivery_workflow.md     # 特性粒度交付工作流（Ask/Plan→TDD→门禁→合入）
├── feedback_and_learning.md        # 反馈事件与自动优化/自学习闭环规范
├── id_and_pagination.md            # ID 生成与 cursor 分页统一规范
├── log_fields.md                   # 统一结构化日志字段规范
├── metrics.md                      # 统一指标规范（metrics）
├── privacy_and_security.md          # 隐私与安全数据保护（字段分级/脱敏/加密/保留）
├── roles_and_scopes.md             # 运营 vs 运维/平台：角色与范围统一定义
├── service_governance.md           # 服务治理统一规范（超时/重试/熔断/限流/健康检查/发布回滚）
├── metadata/
│   ├── README.md                    # 模型元数据契约说明（字段策略单一事实来源）
│   ├── entity_catalog.yaml          # 业务对象目录（entity -> domain/service）
│   ├── field_policy.yaml            # 字段策略（classification/log/observe/ops）
│   └── event_catalog.yaml           # 事件目录（producer/consumer/envelope）
├── messages/
│   └── envelope.schema.json        # MQ/异步消息 Envelope 约束（trace/causation 透传）
└── openapi/
    ├── common.yaml                 # 通用 components（错误、分页、headers 约定）
    ├── content-service.v1.yaml
    ├── user-service.v1.yaml
    ├── chat-service.v1.yaml
    └── orchestrator-service.v1.yaml
```

后续可继续补齐：`product-ops`、`assistant-service` 等 OpenAPI 契约。

---

## 全局约束（必须遵守）

### 1) 版本与路径

- 外部 REST：`/v1/<service>/...`（经 Gateway 统一入口）
- 编排接口：`/v1/orch/...`

### 2) 身份、分身与追踪

- `Authorization: Bearer <accessToken>`：网关鉴权，注入 userId 到下游
- `X-Persona-Id`：可选，当前激活 persona 的上下文（或放入 token claim）
- `X-Request-Id` / `X-Trace-Id`：网关注入；Assistant Run 用 `runId` 贯穿

### 3) 幂等

- create/ingest 类接口必须支持 `Idempotency-Key`
- 服务端需对同一 key 在合理 TTL 内去重

### 4) 分页

- 列表接口优先使用 **cursor**（游标），兼容 limit
- 返回统一 `nextCursor`

### 5) 错误响应

- 所有 4xx/5xx 返回统一 `ErrorResponse`：`code/message/requestId/traceId/details`


# 模型元数据契约（Metadata Contracts）

本目录是 runtime 框架的**元数据单一事实来源**，驱动接口、存储、日志、安全、推荐、标签、画像、助手上下文、契约测试及代码生成。

架构依据：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md`
及同目录 `acceptance.yaml`；metadata 结构与 compiler 设计总览：`DESIGN.md`。

---

## 目录结构

```
contracts/metadata/
├── DESIGN.md
├── README.md
├── _schemas/                     # 唯一当前严格 schema；未知或退休字段失败
├── _shared/                      # 真正跨域且无 owner 的类型/route/surface/operation 合同
├── _vectors/                     # 跨域向量索引合同
└── {domain}/
    ├── business_object_map.yaml # context/object/identity/entrypoint/关系字段唯一登记
    ├── openapi.yaml              # [generated] ContractGraph transport 快照，禁止手改
    └── {object}/
        ├── aggregate.yaml        # aggregate_root 及 bounded members
        ├── entity.yaml           # 非 aggregate_root 对象；与 aggregate.yaml 二选一
        ├── fields.yaml
        ├── service.yaml          # public/internal operation 与 Facade facet
        ├── readiness.yaml        # 实现/测试/环境证据引用；阶段由 Graph 派生
        ├── storage.yaml          # store role、adapter contract、index/TTL
        ├── events.yaml
        ├── errors.yaml
        ├── behaviors.yaml
        ├── privacy.yaml
        ├── ui_config.yaml
        ├── projections/          # named Query Slice / ReadModel
        └── tests/                # local_contract/api_integration/user_acceptance 期望
```

---

## 每个业务对象目录结构

### 聚合目录

| 文件 | 职责 |
|------|------|
| `aggregate.yaml` | 聚合定义：domain、成员关系、存储后端、缓存、capabilities、DDD 层映射 |
| `fields.yaml` | 全实体字段策略：type、constraints、classification、log/api/ops exposure、推荐特征 |
| `events.yaml` | 领域事件：producer、consumers、channel、payload、推荐影响 |
| `storage.yaml` | 存储映射：表/集合定义、索引、唯一约束、Redis 缓存配置 |
| `service.yaml` | 服务归属：API 路由、消费者声明、**契约测试策略** |
| `readiness.yaml` | 对象 packet 的 exact-path 实现与三层/环境证据；文件内容 hash 由 compiler 派生，禁止手写阶段 |

### 非聚合对象目录

与聚合目录相同，但 `aggregate.yaml` 替换为 `entity.yaml`。`entity.yaml.object_kind`
必须是 `aggregate_root`、`owned_entity`、`value_object`、`projection`、
`external_reference`、`append_only_fact` 或 `runtime_session` 之一；禁止用
“独立实体”掩盖聚合、事实和读模型的差异。

---

## 强制要求

- **元数据先行**：新增 entity/field/tag/event 必须先在对应目录注册，再暴露接口或实现存储
- **一致性校验**：`make verify` 校验 metadata 内部一致性
- **禁止临时补丁**：禁止在代码、接口、日志中硬编码与 metadata 冲突的字段含义或策略
- **分类声明**：涉及 PII/SENSITIVE/SECRET 的字段必须声明 `classification`
- **代码生成**：`make codegen` 先生成 OpenAPI，再生成 ContractGraph 与 Go/Dart/Python 产物
- **变更追溯**：metadata 变更走 Git + PR review，同步更新特性 traceability
- **唯一 ContractGraph**：Go/Dart/OpenAPI/coverage 只消费同一个严格 AST/Graph，禁止各 generator 重复解析 YAML
- **OpenAPI 派生**：`service.yaml api_routes` 是 transport 真相；域 OpenAPI 只能由 `qwq-contract generate-openapi` 原子生成，`check-openapi` 对磁盘做全字节漂移检查
- **Object Facade**：每个 operation 必须绑定 Facade facet/method，以及 aggregate command owner 或 named Reader/Slice
- **Typed command target**：聚合写命令仅声明 `aggregate_owner`，不可变事实追加仅声明 `append_sink`；两者互斥且 owned child 永远不能成为 operation target
- **对象登记完整性**：每个 domain 必须且只能有一个 `business_object_map.yaml`；未登记 domain/object/relationship target、零入口聚合或 reference field 不守恒失败
- **单轨 schema**：Registry、readiness、ContractGraph 与 App handoff 不携带版本信封；`version`、`schemaVersion`、`registryRevision` 及 `_schemas/v*` 目录出现即失败
- **访问边界**：跨上下文 command 只经目标 aggregate Facade，query 只经 named Reader/Slice；owned entity/value object 只经 aggregate root，禁止子对象 Store/Repository/公开 Facade
- **存储角色**：authoritative/projection/cache/external/memory 必须显式；cache/ES/remote 不得冒充 write store
- **Actor 归因**：operation 必须声明 account/persona/device actor requirement，禁止使用含混 `userId`
- **零兼容**：schema 不识别旧字段，禁止 alias/fallback/dual-read/dual-write；迁移通过 reset/re-import 或一次性离线工具完成
- **派生准入**：`readiness.yaml` 不允许声明 `implemented`/`ready`；Graph 仅按对象合同、精确内容 hash、三层测试与四环境证据单调派生 `modeled → contract-ready → implemented → commercial-ready`

---

## OpenAPI 生成与检查

```bash
make codegen-openapi   # 原子替换全部 contracts/metadata/{domain}/openapi.yaml
make verify-openapi    # missing / stale / orphan 任一即失败
```

`make codegen-contract-graph` 依赖 `codegen-openapi`，保证
`generated/contract_graph.json` 最终包含最新快照摘要。生成范围包含 `/`、
`/internal/`、`/callbacks/` 的全部 ContractGraph operation；不保留手写
path、schema 或 merge/preserve 逻辑。`operationId` 为稳定 local ID，
`x-object-id`、`x-actor`、`x-application` 为 canonical binding。

字段级 schema 尚未进入 compiler AST 时，生成器使用带 `x-contract-entity` 的
命名 component 占位，不使用匿名 Map 或 `additionalProperties: true`。字段真相
仍在 `fields.yaml` 与 projection codegen，扩展字段生成必须先扩展 compiler，
不得从旧 OpenAPI 反向读取。

---

## 契约测试策略

每个 `service.yaml` 包含 `contract_test` 节，定义基于元数据的接口契约测试。
测试基础设施配置见 `_shared/test_infra.yaml`，详细设计见 `DESIGN.md` §12。

### 原则

| 维度 | 策略 |
|------|------|
| **端侧测试** | App 自身不依赖云端，mock 云端 API 响应（从 `fields.yaml` 自动生成 mock 数据） |
| **服务侧测试** | 服务使用**真实测试数据库**（embedded-postgres / testcontainers mongo / miniredis），**不 mock 存储层** |
| **隔离边界** | 端侧 mock 服务 API；服务侧真实存储 + spy EventPublisher + mock 跨服务和 AI API |
| **数据管理** | 每次测试前 Seed 预制数据，跑完 TRUNCATE/DeleteMany/FlushAll 清理 |
| **断言来源** | 真实数据库查询验证持久化 + spy 捕获验证事件 + API 响应验证 schema |

### 测试引擎选型

| 生产引擎 | 测试引擎 | Go 包 | 特点 |
|---------|---------|------|------|
| PostgreSQL 16 | embedded-postgres | `github.com/fergusstrange/embedded-postgres` | 真实 PG 二进制，无需 Docker |
| MongoDB 7 | testcontainers | `github.com/testcontainers/testcontainers-go/modules/mongodb` | 真实 mongod 容器 |
| Redis 7 | miniredis/v2 | `github.com/alicebob/miniredis/v2` | 纯 Go 内存实现，命令兼容 |

**业务代码零修改**，仅通过配置切换连接地址。

### 覆盖要求

- 每个 `api_routes` 至少一个测试场景
- 所有 `state_machine` 转换覆盖（正向 + 异常）
- 所有 `unique_constraints` 有违反测试（真实数据库拒绝）
- 所有 `SECRET` 字段验证不出现在 API 响应
- 所有 `events` 验证 payload_fields 正确（spy 捕获）
- 缓存一致性：Redis 写入/失效/TTL 真实验证
- 并发安全：乐观锁/排他约束真实数据库并发验证

---

## 消费关系

```
aggregate.yaml / entity.yaml ──→ ContractGraph object/member/owner descriptor
                              ──→ codegen model、事件与对象合同
fields.yaml                  ──→ compiler 字段 AST / typed DTO / OpenAPI schema
                              ──→ 日志脱敏 / 接口过滤 / 推荐特征标记
                              ──→ local_contract fixture 生成
_shared/domain_taxonomy.yaml ──→ 领域路由（圈子频道 / 助理领域 / 推荐场景）
                              ──→ 标签真相源 = 数据工程 control_plane/governance/taxonomy（路径制 tagRef，tag-service 只读消费发布投影）
events.yaml                  ──→ typed event / outbox / consumer / replay 合同
                              ──→ local_contract 与 api_integration 事件断言
storage.yaml                 ──→ migration / 索引 / TTL / 对象 adapter 合同
                              ──→ 服务 composition root 显式注入 Store/Reader 实现
service.yaml                 ──→ ContractGraph operation + Object Facade facet/method
                              ──→ generated transport / OpenAPI snapshot / App operation
                              ──→ 三层测试期望与覆盖率要求
readiness.yaml               ──→ exact-path evidence + compiler-derived SHA256
                              ──→ ObjectReadiness（无手写 status；缺 UAT/环境即 fail-closed）
projections/*.yaml           ──→ named Reader / typed Slice / Projector 合同
_vectors/*.yaml              ──→ 向量索引创建 / Embedding Pipeline 注册
```

---

## 统计

聚合、对象、operation、Slice、store adapter、错误、事件和覆盖数量只能由
`qwq-contract coverage --format json` 从 ContractGraph 生成。README、设计文档和
测试禁止维护手工数量；出现差异以 compiler 拒绝的 Graph 为准，而不是修改数字。

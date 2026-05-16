# Runtime 端云一体化可扩展开发规范

> 目标：所有工程约束内置于 runtime 工具链和验证流水线，AI Agent 和开发者只需执行命令，
> 无需阅读文档来遵从规范。每个扩展场景有明确的输入→工具→产出→验证闭环。

---

## 目录

- [1. 设计原则](#1-设计原则)
- [2. 端云统一目录结构](#2-端云统一目录结构)
- [3. 扩展场景全景](#3-扩展场景全景)
- [4. 0→1 场景详解](#4-01-场景详解)
- [5. 1→N 场景详解](#5-1n-场景详解)
- [6. 自动化工具链](#6-自动化工具链)
- [7. 验证流水线](#7-验证流水线)
- [8. 工具链与 runtime 内置约束清单](#8-工具链与-runtime-内置约束清单)

---

## 1. 设计原则

### 1.1 约束内置，不依赖文档

| 层级 | 约束方式 | 说明 |
|------|---------|------|
| **编译期** | Go 接口 + 类型系统 | Repository 必须实现 `runtime/repository.Repository` 接口，否则编译失败 |
| **启动期** | EntityRegistry 校验 | 服务启动时加载 metadata，未注册实体无法获取 Repository 实例 |
| **运行期** | 拦截链强制执行 | 读写自动经过字段过滤/脱敏/校验/事件发布，业务代码无法绕过 |
| **工具期** | CLI 命令 + codegen | `qwq` CLI 工具强制执行目录结构、文件命名、metadata 更新顺序 |
| **验证期** | `make verify` + `make gate` | 自动校验 metadata↔代码↔接口↔测试 全链路一致性 |

### 1.2 元数据先行，代码后行

```
任何扩展的执行顺序：

  metadata YAML → make verify → make codegen → 补充业务逻辑 → make test-contract → make gate
       ①              ②            ③                ④                ⑤              ⑥
```

**工具链强制此顺序**：`make codegen` 依赖 `make verify` 通过；`make gate` 依赖 `make test-contract` 通过。

### 1.3 端云同构语义

| 语义层 | 云侧（Go） | 端侧（Dart/Flutter） | 统一来源 |
|--------|-----------|---------------------|---------|
| 领域模型 | `domain/entity.go` | `cloud/models/{entity}_dto.dart` | `fields.yaml` |
| 接口契约 | `adapters/http/handler.go` | `cloud/services/{domain}_repository.dart` | `service.yaml` + OpenAPI |
| 字段策略 | `runtime/interceptor` 强制执行 | `cloud/runtime/field_policy.dart` 强制执行 | `fields.yaml` |
| 错误码 | `runtime/errors` | `cloud/runtime/error_codes.dart` | `contracts/error_codes.md` |
| 事件 | `domain/events.go` | `cloud/events/{entity}_events.dart` | `events.yaml` |

---

## 2. 端云统一目录结构

### 2.1 云侧服务目录（Go）

```
services/{service-name}/
├── cmd/
│   └── api/
│       └── main.go                 # 入口：加载 metadata → 初始化 Registry → 启动
│
├── internal/
│   ├── domain/                     # DDD 领域层（codegen 生成 + 手写领域逻辑）
│   │   ├── {entity}.go             # [codegen] Entity struct
│   │   ├── {entity}_repository.go  # [codegen] Repository interface
│   │   ├── {entity}_events.go      # [codegen] Event struct
│   │   └── {entity}_service.go     # [手写] 领域服务（业务规则）
│   │
│   ├── application/                # DDD 应用层（手写）
│   │   └── {usecase}_service.go    # 用例编排、事务边界
│   │
│   ├── adapters/                   # DDD 适配器层
│   │   ├── http/
│   │   │   └── {entity}_handler.go # [codegen 骨架 + 手写路由逻辑]
│   │   └── mq/
│   │       └── {event}_consumer.go # [codegen 骨架 + 手写消费逻辑]
│   │
│   └── infrastructure/             # DDD 基础设施层
│       ├── persistence/
│       │   ├── {entity}_mongo_repo.go   # [codegen] MongoDB Repository 实现
│       │   └── {entity}_pg_repo.go      # [codegen] PostgreSQL Repository 实现
│       ├── cache/
│       │   └── {entity}_cache.go        # [codegen] Redis 缓存中间件配置
│       └── migration/
│           ├── {version}_{entity}.up.sql    # [codegen] PG migration
│           └── {version}_{entity}.up.js     # [codegen] Mongo index script
│
├── tests/
│   ├── testmain_test.go            # [codegen] TestMain（引擎启动/关闭）
│   ├── fixture_test.go             # [codegen] Fixture 工厂
│   ├── event_spy_test.go           # [codegen] EventPublisher spy
│   └── {entity}_contract_test.go   # [codegen 骨架 + 手写场景断言]
│
├── configs/
│   └── config.yaml                 # 服务配置
│
├── go.mod
└── Makefile                        # 服务级 make 目标
```

**约束：`[codegen]` 标记的文件由 `make codegen` 自动生成，禁止手动创建。**

### 2.2 端侧 App 目录（Dart/Flutter）

```
lib/
├── cloud/                          # 云集成层（codegen 生成 + 手写适配）
│   ├── runtime/
│   │   ├── cloud_runtime_config.dart    # 运行时配置
│   │   ├── cloud_request_headers.dart   # 请求头构建
│   │   ├── field_policy.dart            # [codegen] 字段策略（脱敏/过滤）
│   │   └── error_codes.dart             # [codegen] 错误码枚举
│   ├── models/
│   │   └── {entity}_dto.dart            # [codegen] DTO（从 fields.yaml）
│   ├── events/
│   │   └── {entity}_events.dart         # [codegen] 事件类型定义
│   └── services/
│       └── {domain}/
│           └── {domain}_repository.dart # [codegen 骨架] Abstract + Mock + Remote
│
├── features/                       # 特性目录（手写）
│   └── {feature_name}/
│       ├── pages/                  # 页面
│       ├── models/                 # 特性模型
│       ├── providers/              # 状态管理
│       ├── widgets/                # 特性组件
│       └── components/             # 特性 UI 组件
│
├── core/                           # 核心基础设施
├── components/                     # 共享 UI 组件
└── app/                            # 应用壳
```

### 2.3 元数据目录（单一事实源）

```
quwoquan_service/contracts/metadata/
├── _shared/                        # 全局共享定义
│   ├── types.yaml                  # 枚举/值对象类型
│   ├── tag_taxonomy.yaml           # 标签分类体系
│   ├── redis_keyspace.yaml         # Redis Key 命名规范
│   └── test_infra.yaml             # 测试基础设施配置
│
├── {aggregate_name}/               # 每个聚合根独立目录
│   ├── aggregate.yaml              # 聚合定义 + 成员 + 能力 + 存储选择
│   ├── fields.yaml                 # 全部字段策略
│   ├── events.yaml                 # 领域事件
│   ├── storage.yaml                # 物理存储映射
│   └── service.yaml                # 服务归属 + API + 契约测试
│
├── {entity_name}/                  # 独立实体（非聚合根）
│   ├── entity.yaml
│   ├── fields.yaml
│   ├── events.yaml
│   ├── storage.yaml
│   └── service.yaml
│
├── _projections/                   # ReadModel 投影定义
│   └── {readmodel}.yaml
│
├── _vectors/                       # 向量存储定义
│   └── {vector_entity}.yaml
│
├── DESIGN.md                       # 设计总览
└── README.md                       # 目录说明
```

---

## 3. 扩展场景全景

### 3.1 0→1 场景（新建）

| 编号 | 场景 | 触发条件 | 复杂度 |
|------|------|---------|--------|
| **S01** | 新建聚合根 | 新业务对象需独立生命周期 | 高 |
| **S02** | 新建聚合成员 | 已有聚合需新增子实体 | 中 |
| **S03** | 新建独立实体 | 跨聚合关系或无归属的实体 | 中 |
| **S04** | 新建服务 | 新领域需独立部署单元 | 高 |
| **S05** | 新建 API 端点 | 已有服务新增对外接口 | 低 |
| **S06** | 新建领域事件 | 新业务动作需通知下游 | 低 |
| **S07** | 新建 ReadModel 投影 | 新读场景需物化视图 | 中 |
| **S08** | 新建向量实体 | 新语义搜索/推荐需求 | 中 |
| **S09** | 新建 Skill | 小趣新增能力 | 中 |
| **S10** | 新建端侧 Feature | App 新增页面/功能 | 中 |

### 3.2 1→N 场景（扩展）

| 编号 | 场景 | 触发条件 | 复杂度 |
|------|------|---------|--------|
| **S11** | 已有实体新增字段 | 业务需求新增属性 | 低 |
| **S12** | 已有实体新增能力 | 使实体可搜索/可聚合/支持向量 | 中 |
| **S13** | 已有事件新增消费者 | 新下游需要消费已有事件 | 低 |
| **S14** | 已有实体新增索引 | 查询性能优化 | 低 |
| **S15** | 已有 API 新增操作 | 接口扩展（如新增批量接口） | 低 |
| **S16** | 已有 Projector 新增字段 | ReadModel 扩展 | 低 |
| **S17** | 已有实体变更存储后端 | PG→Mongo 或反向迁移 | 高 |
| **S18** | 已有实体新增缓存 | 新增 Redis 缓存层 | 低 |
| **S19** | 已有 Skill 新增 Tool | Skill 能力扩展 | 低 |
| **S20** | 已有实体新增契约测试场景 | 测试覆盖扩展 | 低 |

---

## 4. 0→1 场景详解

### S01：新建聚合根

**触发命令：**
```bash
qwq new aggregate --name=<AggName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

**工具自动执行：**

| 步骤 | 操作 | 产出文件 |
|------|------|---------|
| ① 创建 metadata 目录 | 生成 5 个 YAML 骨架 | `metadata/{agg}/aggregate.yaml` + `fields.yaml` + `events.yaml` + `storage.yaml` + `service.yaml` |
| ② 验证 metadata | `make verify` | 校验内部一致性 |
| ③ 生成云侧代码 | `make codegen target={agg}` | `domain/{entity}.go` + `{entity}_repository.go` + `{entity}_events.go` + `infrastructure/persistence/{entity}_{storage}_repo.go` + `adapters/http/{entity}_handler.go` + `migration/` + `tests/` |
| ④ 生成端侧代码 | `make codegen-app target={agg}` | `cloud/models/{entity}_dto.dart` + `cloud/services/{domain}/{domain}_repository.dart` |
| ⑤ 更新特性树 | 自动更新 `tree.yaml` | 如涉及新 L2/L3 则创建目录 |
| ⑥ 更新 OpenAPI | 自动生成 | `contracts/openapi/{svc}.v1.yaml` 新增 paths |

**开发者/Agent 手动补充：**
- `fields.yaml` 填充具体字段定义（类型、约束、分类）
- `events.yaml` 填充领域事件
- `domain/{entity}_service.go` 编写领域逻辑
- `application/{usecase}_service.go` 编写用例编排

**验证链：**
```bash
make verify          # metadata 一致性
make codegen         # 重新生成（确保不遗漏）
make build           # 编译通过
make test-contract   # 契约测试通过
make gate            # 全量门禁
```

---

### S02：新建聚合成员

**触发命令：**
```bash
qwq new member --aggregate=<AggName> --name=<MemberName>
```

**工具自动执行：**

| 步骤 | 操作 | 产出文件 |
|------|------|---------|
| ① 更新 aggregate.yaml | 在 members 列表新增成员 | `metadata/{agg}/aggregate.yaml` |
| ② 更新 fields.yaml | 新增成员字段节 | `metadata/{agg}/fields.yaml` |
| ③ 更新 storage.yaml | 新增表/集合映射 | `metadata/{agg}/storage.yaml` |
| ④ `make verify` | 校验一致性 | |
| ⑤ `make codegen` | 生成成员 struct + 更新聚合 Repository | `domain/{member}.go` + `infrastructure/persistence/{member}_{storage}_repo.go` |

---

### S03：新建独立实体

**触发命令：**
```bash
qwq new entity --name=<EntityName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

**与 S01 类似，但使用 `entity.yaml` 替代 `aggregate.yaml`，不含 members。**

---

### S04：新建服务

**触发命令：**
```bash
qwq new service --name=<service-name> --port=<port>
```

**工具自动执行：**

| 步骤 | 操作 | 产出 |
|------|------|------|
| ① 创建服务目录 | 执行 `agent_ops/scaffold/new_service_fullstack.sh --name {svc} --port {port}` | `services/{svc}/cmd/api/main.go` + `internal/domain/` + `application/` + `adapters/` + `infrastructure/` + `tests/` + `configs/` + `go.mod` + `Makefile` |
| ② 自动生成配置目录 | `new_service_fullstack.sh` 内置调用 `scripts/bootstrap_service_config_layout.sh --service {svc}` | `configs/default|alpha|beta|gamma|prod-gray|prod/config.yaml` + `releases/config/{svc}/README.md` |
| ③ 生成 main.go | 标准启动模板 | 加载 metadata → Registry → Repository 初始化 → HTTP server |
| ④ 注册到工程 | 更新 root Makefile | 新增 `gate-{svc}` 目标 |
| ⑤ 创建 spec | 服务规范目录 | `quwoquan_service/specs/{svc}/spec.md` + `design.md` |
| ⑥ 注册到 errors | 新增模块枚举 | `runtime/errors/errors.go` 新增 MODULE |
| ⑦ 注册到 observability | 新增客户端工厂 | `runtime/observability/service_client_factory.go` + `runtime/http/http.go` |

**发布化配置门禁（S04 强制）**
- 必须通过 `scripts/verify_service_config_layout.sh`
- 生产部署清单必须声明：`APP_ENV/SERVICE_NAME/CONFIG_VERSION/IMAGE_VERSION/CONFIG_ROOT`
- 新服务上线前必须准备至少一个版本配置快照：`releases/config/{svc}/v*.yaml`

---

### S05：新建 API 端点

**触发命令：**
```bash
qwq new endpoint --service=<svc> --entity=<entity> --method=<GET|POST|PUT|DELETE> --path=</v1/...>
```

**工具自动执行：**

| 步骤 | 操作 |
|------|------|
| ① 更新 service.yaml | 在 routes 中新增操作 |
| ② `make verify` | 校验 entity/fields 引用 |
| ③ `make codegen` | 更新 handler 骨架 + OpenAPI |
| ④ 端侧同步 | 更新 Dart repository 骨架 |

---

### S06：新建领域事件

**触发命令：**
```bash
qwq new event --aggregate=<agg> --name=<EventName> --channel=<event_store|direct|internal>
```

**工具自动执行：**

| 步骤 | 操作 |
|------|------|
| ① 更新 events.yaml | 新增事件定义 |
| ② `make verify` | 校验 payload_entity 引用 |
| ③ `make codegen` | 生成 Event struct + consumer 骨架 |

---

### S07：新建 ReadModel 投影

**触发命令：**
```bash
qwq new projection --name=<ReadModelName> --source-events=<evt1,evt2>
```

**工具自动执行：**

| 步骤 | 操作 |
|------|------|
| ① 创建 `_projections/{name}.yaml` | ReadModel 定义 |
| ② `make verify` | 校验 source_events 引用 |
| ③ `make codegen` | 生成 Projector 骨架 + ReadModel struct |

---

### S08：新建向量实体

**触发命令：**
```bash
qwq new vector --name=<VectorEntityName> --source=<entity> --field=<field> --dimensions=<768|1536>
```

**产出：** `_vectors/{name}.yaml` + codegen 生成 embedding pipeline 骨架。

---

### S09：新建 Skill

**触发命令：**
```bash
qwq new skill --name=<SkillName> --trigger-scenes=<scene1,scene2>
```

**产出：** `skill_catalog.yaml` 新增条目 + Skill 实现骨架 + 授权配置。

---

### S10：新建端侧 Feature

**触发命令：**
```bash
qwq new feature --name=<feature_name> --pages=<page1,page2>
```

**工具自动执行：**

| 步骤 | 操作 |
|------|------|
| ① 创建 feature 目录 | `lib/features/{name}/pages/` + `models/` + `providers/` + `widgets/` |
| ② 创建特性树条目 | `changes/` + `acceptance.yaml` + `traceability.yaml` |
| ③ 如涉及新 API | 触发 S05 流程 |
| ④ 如涉及新实体 | 触发 S01/S03 流程 |

---

## 5. 1→N 场景详解

### S11：已有实体新增字段

**触发命令：**
```bash
qwq add field --entity=<entity> --name=<fieldName> --type=<string|int64|...> --classification=<PUBLIC|PII|SENSITIVE|SECRET>
```

**工具自动执行：**

| 步骤 | 操作 | 影响范围 |
|------|------|---------|
| ① 更新 fields.yaml | 新增字段定义 | metadata |
| ② 更新 storage.yaml | 新增列/字段映射 | metadata |
| ③ `make verify` | 校验一致性 | 全链路 |
| ④ `make codegen` | 重新生成 struct + DTO + migration | 云侧 + 端侧 |
| ⑤ migration 文件 | 生成 ALTER TABLE / updateMany | 数据库 |

**runtime 内置约束：**
- EntityRegistry 启动时加载新字段 → 拦截链自动应用新字段的 classification/api_exposure
- 无需修改任何运行时代码

---

### S12：已有实体新增能力

**触发命令：**
```bash
qwq add capability --entity=<entity> --capability=<searchable|aggregatable|vector_searchable>
```

**工具自动执行：**

| 步骤 | 操作 |
|------|------|
| ① 更新 aggregate.yaml | capabilities 列表新增 |
| ② 更新 storage.yaml | 新增搜索索引/向量索引 |
| ③ `make codegen` | Repository 接口扩展（新增 Search/VectorSearch 方法） |
| ④ migration | 创建索引 |

**runtime 内置约束：**
- Repository 工厂根据 capabilities 自动注入对应接口实现
- `Searchable` 能力 → 自动暴露 `Search(query)` 方法
- `VectorSearchable` 能力 → 自动暴露 `SimilaritySearch(embedding)` 方法

---

### S13：已有事件新增消费者

**触发命令：**
```bash
qwq add consumer --event=<EventName> --consumer=<service:handler>
```

**操作：** 更新 `events.yaml` 的 consumers 列表 → `make verify` → `make codegen` 生成 consumer 骨架。

---

### S14：已有实体新增索引

**触发命令：**
```bash
qwq add index --entity=<entity> --fields=<f1,f2> --unique=<true|false>
```

**操作：** 更新 `storage.yaml` → `make codegen` 生成 migration 脚本。

---

### S15：已有 API 新增操作

与 S05 相同，仅更新 `service.yaml` 的已有 route 下新增 operation。

---

### S16：已有 Projector 新增字段

**操作：** 更新 `_projections/{name}.yaml` 的 fields → `make codegen` 更新 ReadModel struct + Projector 映射。

---

### S17：已有实体变更存储后端

**触发命令：**
```bash
qwq migrate storage --entity=<entity> --from=<postgres> --to=<mongodb>
```

**这是高风险操作，工具执行以下检查：**
1. 校验目标存储是否支持所有已用 capabilities
2. 生成数据迁移脚本
3. 重新生成 Repository 实现
4. 更新 migration 文件
5. 更新契约测试（切换测试引擎）

---

### S18：已有实体新增缓存

**触发命令：**
```bash
qwq add cache --entity=<entity> --ttl=<seconds>
```

**操作：** 更新 `aggregate.yaml` 的 `cache_layer` + `cache_ttl_seconds` → `make codegen` 注入 Redis 缓存中间件。

**runtime 内置约束：** Repository 工厂检测到 `cache_layer: redis` 自动包装 CacheMiddleware。

---

### S19：已有 Skill 新增 Tool

**操作：** 更新 `tool_catalog.yaml` → `make verify` 校验 Skill 引用 → `make codegen` 生成 Tool 代理。

---

### S20：已有实体新增契约测试场景

**操作：** 更新 `service.yaml` 的 `contract_test.service_side.scenarios` → `make codegen-test` 生成测试骨架。

---

## 6. 自动化工具链

### 6.1 `qwq` CLI 工具

统一入口命令，所有扩展场景通过此工具触发：

```
qwq — 趣我圈端云一体化开发工具

Commands:
  new aggregate   S01: 新建聚合根
  new member      S02: 新建聚合成员
  new entity      S03: 新建独立实体
  new service     S04: 新建服务
  new endpoint    S05: 新建 API 端点
  new event       S06: 新建领域事件
  new projection  S07: 新建 ReadModel 投影
  new vector      S08: 新建向量实体
  new skill       S09: 新建 Skill
  new feature     S10: 新建端侧 Feature

  add field       S11: 已有实体新增字段
  add capability  S12: 已有实体新增能力
  add consumer    S13: 已有事件新增消费者
  add index       S14: 已有实体新增索引
  add endpoint    S15: 已有 API 新增操作
  add projection-field  S16: 已有 Projector 新增字段
  add cache       S18: 已有实体新增缓存
  add tool        S19: 已有 Skill 新增 Tool
  add test        S20: 已有实体新增契约测试场景

  migrate storage S17: 变更存储后端

  verify          运行全量验证
  codegen         运行代码生成
  codegen-app     运行端侧代码生成
  codegen-test    运行测试代码生成
  gate            运行质量门禁
```

### 6.2 CLI 内置约束

每个 `qwq` 子命令内置以下约束检查（代码级，非文档）：

```
qwq new aggregate --name=Post ...
  ├── 检查 name 是否已被注册 → 冲突则拒绝
  ├── 检查 service 是否已存在 → 不存在则提示先执行 qwq new service
  ├── 检查 storage 是否为合法值 → 仅允许 postgres/mongodb
  ├── 生成 5 个 YAML 骨架 → 带必填占位符（标记 TODO）
  ├── 执行 make verify → 不通过则提示缺失项
  └── 输出下一步操作提示（填充 fields.yaml → make codegen）
```

### 6.3 Makefile 目标体系

```makefile
# 根 Makefile
make verify              # 全量验证（metadata + 目录 + 特性树 + 一致性）
make codegen             # 云侧代码生成（Go struct/repo/handler/migration/test）
make codegen-app         # 端侧代码生成（Dart DTO/repository/events）
make codegen-test        # 测试骨架生成（TestMain/fixture/contract_test）
make build               # 全量编译
make test-contract       # 契约测试（真实数据库）
make gate                # 本地门禁（verify + build + test-contract）
make gate-full           # CI 门禁（gate + 端侧测试 + 集成测试）

# 服务 Makefile
make codegen             # 本服务代码生成
make test-contract       # 本服务契约测试
make gate                # 本服务门禁
```

---

## 7. 验证流水线

### 7.1 验证层级

```
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 1: metadata 内部一致性                                          │
│   fields.yaml enum_ref → _shared/types.yaml 存在                     │
│   events.yaml payload_entity → 同目录 aggregate 成员存在              │
│   storage.yaml entity → fields.yaml 实体匹配                         │
│   service.yaml response_entity → fields.yaml 实体存在                │
│   _projections source_events → events.yaml 事件存在                   │
│   _vectors source_entity → aggregate/entity 存在                     │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 2: metadata ↔ 代码一致性                                       │
│   Go struct 字段 ↔ fields.yaml 字段名/类型/约束                      │
│   Repository interface 方法 ↔ aggregate.yaml capabilities            │
│   Event struct ↔ events.yaml payload                                │
│   Migration DDL ↔ storage.yaml 表定义                                │
│   OpenAPI schema ↔ service.yaml + fields.yaml                       │
│   Dart DTO ↔ fields.yaml（端云同构）                                  │
│   Error module enum ↔ runtime/errors 注册                            │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 3: 代码 ↔ 运行时约束一致性                                      │
│   服务启动 EntityRegistry 加载 → 所有 metadata 无报错                  │
│   Repository 获取 → 未注册实体报错                                    │
│   拦截链 → SECRET 字段不暴露（运行时验证）                             │
│   Contract test → 覆盖 service.yaml 定义的全部场景                    │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 4: 特性树 ↔ 工程一致性                                          │
│   tree.yaml L2 条目 → 对应目录和 acceptance.yaml 存在                 │
│   acceptance.yaml A7 → contract_metadata 验证通过                    │
│   traceability.yaml → 涉及的 metadata/API/test 全部存在              │
│   端侧 feature 目录 → 对应 cloud/services 和 cloud/models 存在       │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.2 验证脚本清单

| 脚本 | Layer | 验证内容 |
|------|-------|---------|
| `verify_metadata_internal.go` | L1 | metadata YAML 内部交叉引用 |
| `verify_metadata_code_sync.go` | L2 | metadata ↔ 生成代码字段/类型匹配 |
| `verify_openapi_metadata.go` | L2 | OpenAPI ↔ metadata 一致 |
| `verify_dart_dto_sync.go` | L2 | Dart DTO ↔ metadata 一致 |
| `verify_migration_sync.go` | L2 | Migration DDL ↔ storage.yaml 一致 |
| `verify_error_module_sync.go` | L2 | error module 枚举 ↔ 服务列表 |
| `verify_contract_test_coverage.go` | L3 | 契约测试覆盖 service.yaml 场景 |
| `verify_feature_tree_consistency.sh` | L4 | 特性树 ↔ 目录 ↔ acceptance |
| `verify_fullstack_sync.go` | L4 | 端云代码同构一致性 |

### 7.3 `make gate` 完整流程

```
make gate
  ├── make verify                    # 全量验证（L1+L2+L4）
  │   ├── verify_metadata_internal
  │   ├── verify_metadata_code_sync
  │   ├── verify_openapi_metadata
  │   ├── verify_dart_dto_sync
  │   ├── verify_migration_sync
  │   ├── verify_error_module_sync
  │   ├── verify_feature_tree_consistency
  │   └── verify_fullstack_sync
  │
  ├── make build                     # 全量编译
  │   ├── go build ./runtime/...
  │   ├── go build ./services/...
  │   └── flutter analyze
  │
  └── make test-contract             # 契约测试（L3）
      ├── go test ./services/*/tests/... -run Contract
      └── verify_contract_test_coverage
```

---

## 8. 工具链与 runtime 内置约束清单

### 8.1 编译期约束（Go 类型系统）

| 约束 | 实现方式 |
|------|---------|
| Repository 必须实现标准接口 | `runtime/repository.Repository[T]` 泛型接口 |
| Event 必须实现 DomainEvent 接口 | `runtime/eventstore.DomainEvent` 接口 |
| Handler 必须返回标准错误 | `runtime/errors.AppError` 类型 |
| Interceptor 必须实现链式接口 | `runtime/interceptor.ReadInterceptor` / `WriteInterceptor` |
| Projector 必须实现消费接口 | `runtime/projector.Projector` 接口 |

### 8.2 启动期约束（EntityRegistry）

| 约束 | 实现方式 |
|------|---------|
| 未注册实体无法获取 Repository | `registry.MustGetRepository(entityName)` |
| metadata 加载失败服务启动失败 | `registry.MustLoad(metadataDir)` |
| 字段策略自动注入拦截链 | `registry.GetFieldPolicies(entity)` → 拦截链构建 |
| 存储路由自动选择适配器 | `registry.GetStorageBackend(entity)` → factory |
| 缓存 TTL 自动配置 | `registry.GetCacheTTL(entity)` → CacheMiddleware |

### 8.3 运行期约束（拦截链）

| 约束 | 实现方式 |
|------|---------|
| SECRET 字段不暴露 | ReadInterceptor 自动 drop |
| PII 字段脱敏 | ReadInterceptor 自动 mask |
| 写操作自动发布事件 | WriteInterceptor 自动 hook |
| 必填字段校验 | WriteInterceptor 自动 validate |
| 日志记录遵循 log_policy | ReadInterceptor 自动 mask/drop |
| Metric 自动产生 | WriteInterceptor 自动 emit |

### 8.4 工具期约束（qwq CLI）

| 约束 | 实现方式 |
|------|---------|
| 实体名不可重复 | `qwq new` 检查已有 metadata 目录 |
| 存储选择仅限合法值 | `qwq new` 枚举校验 |
| 字段类型仅限合法值 | `qwq add field` 枚举校验 |
| Classification 仅限合法值 | `qwq add field` 枚举校验 |
| capability 仅限合法值 | `qwq add capability` 枚举校验 |
| 服务必须存在 | `qwq new aggregate` 检查 service 存在 |
| 聚合必须存在 | `qwq new member` 检查 aggregate 存在 |

### 8.5 验证期约束（make verify）

| 约束 | 实现方式 |
|------|---------|
| metadata 内部一致性 | L1 验证脚本 |
| metadata ↔ 代码一致性 | L2 验证脚本 |
| 端云同构一致性 | `verify_fullstack_sync` |
| 契约测试覆盖率 | `verify_contract_test_coverage` |
| 特性树完整性 | `verify_feature_tree_consistency` |

---

## 9. 端云扩展全流程示例

### 示例：新增「打赏」功能（端云完整流程）

```
1. qwq new entity --name=Tip --domain=content --service=content-service --storage=mongodb
   → 自动创建 metadata/tip/ 目录 + 5 个 YAML 骨架

2. 填充 metadata:
   - fields.yaml: tip_id, user_id, post_id, amount, created_at
   - events.yaml: TipCreated(producer: content-service, consumers: [notification-service, user-service])
   - storage.yaml: MongoDB tips collection + 索引
   - service.yaml: POST /v1/tips (create), GET /v1/tips (list by post)

3. make verify → metadata 一致性通过

4. make codegen → 生成:
   云侧: domain/tip.go + tip_repository.go + tip_events.go
         infrastructure/persistence/tip_mongo_repo.go
         adapters/http/tip_handler.go
         migration/001_tip.up.js
         tests/tip_contract_test.go
   端侧: cloud/models/tip_dto.dart
         cloud/services/content/tip_repository.dart

5. 手写业务逻辑:
   - domain/tip_service.go (打赏金额校验、重复检查)
   - application/tip_usecase.go (打赏流程编排)

6. make test-contract → 契约测试通过（真实 MongoDB + EventSpy）

7. make gate → 全量门禁通过

8. 端侧开发:
   - features/tip/ (打赏页面、动画)
   - 调用 cloud/services/content/tip_repository.dart

9. make gate-full → 端云全量门禁通过
```

---

## 10. 与特性树的关系

每个扩展场景完成后，自动或手动更新特性树：

| 场景 | 特性树操作 |
|------|----------|
| S01 新聚合 | 在对应 L1 下新增/更新 L4（object_task） |
| S04 新服务 | 新增 L1 或在已有 L1 下新增 L2 |
| S05 新端点 | 在对应 L3 下更新 L4 |
| S06 新事件 | 在对应 L4 下更新 |
| S10 新 Feature | 新增 changes/ 目录 + acceptance.yaml + traceability.yaml |
| S11-S20 扩展 | 更新对应 L4/L5 的 tasks.md |

`qwq` CLI 在每个扩展操作完成后自动检查并提示是否需要更新特性树。

---

## 11. 命令与规则集成

### 11.1 Cursor 命令

| 命令 | 粒度 | 用途 |
|------|------|------|
| `/prd` / `/design` | 特性级 | 创建/推进一个用户可感知的特性并完成 metadata/codegen 基线 |
| `/dev` | 特性级 | 实施特性（含多个扩展操作），完成自验证并自动归档 |
| `/archive` | 特性级 | 兼容补归档/修复回写，非标准流 |
| `/qwq-extend` | 对象级 | 20 个扩展场景统一入口 |
| `/audit` | 全栈 | 端云语义 + 结构 + metadata + ArchUnit 审计 |
| `/commit` | 全栈 | 读取 `/dev` 自动归档结果后执行 gate、审计、提交推送 |

### 11.2 规则（.cursor/rules/）

| 规则 | 说明 |
|------|------|
| `01-arch-constraints.mdc` | DDD 层级导入约束 + runtime 统一能力 + codegen 产物保护 |
| `00-fullstack-development-flow.mdc` | 主流程、自动卡点、自动归档、提交与灰度口径 |

### 11.3 验证脚本

| 脚本 | 说明 |
|------|------|
| `scripts/verify_arch_constraints.sh` | ArchUnit-like 结构约束验证（DDD 导入、数据库隔离） |
| `scripts/verify_fullstack_audit.sh` | 全栈审计（端侧语义 + 云侧结构 + metadata 同步） |

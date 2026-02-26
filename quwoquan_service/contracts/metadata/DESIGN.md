# 业务对象元数据设计总览

> 唯一真相源。所有代码生成（Go + Dart + Python）均从本目录 YAML 驱动。
> 修改 YAML → `make verify` → `make codegen` → `make codegen-app` → `make gate`。

---

## 目录结构

```
contracts/metadata/
├── _shared/                       # 跨域共享（真正无所有者的内容）
│   ├── types.yaml                 # 枚举 + 通用类型（ContentType/Visibility 等）
│   ├── redis_keyspace.yaml        # Redis key 命名格式规范
│   ├── test_infra.yaml            # 测试引擎配置（engines/mocks/data_management）
│   ├── openapi_common.yaml        # OpenAPI 公共组件（securitySchemes/parameters）
│   └── envelope.schema.json       # 消息信封 JSON Schema（MQ/事件总线）
│
├── _vectors/                      # 向量索引（跨多服务消费，保持独立）
│   ├── content_embedding.yaml     # Post 内容语义向量（推荐 + 助手检索）
│   └── user_context_embedding.yaml# 用户上下文向量（个性化推荐）
│
├── content/                       # 域：内容 → content-service
│   ├── openapi.yaml               # HTTP 接口契约（对外快照）
│   └── post/                      # 聚合根 Post
│       ├── aggregate.yaml         # 存储后端 + counter strategy + DDD映射
│       ├── fields.yaml            # 字段定义 + 分类（PUBLIC/PII/SENSITIVE/SECRET）+ 日志策略
│       ├── storage.yaml           # 索引 + Migration DDL + TTL
│       ├── events.yaml            # 领域事件 + 消费方 + ML信号
│       ├── service.yaml           # API 路由（仅路由声明）
│       ├── projections/           # 端侧视图（紧靠实体，codegen → Dart DTO）
│       │   ├── discovery_feed.yaml
│       │   ├── photo_post.yaml
│       │   ├── video_post.yaml
│       │   ├── article_post.yaml
│       │   └── moment_post.yaml
│       ├── errors.yaml            # 域错误码（codegen → Dart enum + Go 常量）
│       ├── behaviors.yaml         # 行为采集 + 推荐特征 + 训练样本
│       ├── privacy.yaml           # 隐私策略（端侧日志过滤 + GDPR 删除级联）
│       ├── ui_config.yaml         # 端侧 UI 配置（tab/布局/feature flags，codegen → Dart）
│       └── tests/                 # 三层测试契约（测试代码的声明性规范）
│           ├── mock.yaml          # 端侧独立（flutter test，不依赖云）
│           ├── contract.yaml      # 云侧独立（go test，真实 DB）
│           └── e2e.yaml           # 端云集成（staging，advisory）
│
├── user/                          # 域：用户 → user-service
│   ├── openapi.yaml
│   ├── user_profile/
│   │   ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   │   ├── projections/user_profile_view.yaml
│   │   ├── errors.yaml  privacy.yaml
│   │   └── tests/{mock,contract,e2e}.yaml
│   ├── follow_edge/
│   │   └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   └── block_edge/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
├── messages/                      # 域：即时通讯 → chat-service
│   ├── openapi.yaml
│   └── conversation/
│       ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       ├── projections/chat_inbox.yaml
│       ├── errors.yaml
│       └── tests/{mock,contract,e2e}.yaml
│
├── social/                        # 域：社交 → circle-service + social graph
│   ├── openapi.yaml
│   └── circle/
│       ├── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       ├── projections/circle_feed.yaml
│       ├── errors.yaml
│       └── tests/{mock,contract,e2e}.yaml
│
├── assistant/                     # 域：AI 助手 → assistant-service/orchestrator
│   ├── assistant_run/
│   │   └── aggregate.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│   └── skill_consent/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
├── recommendation/                # 域：推荐 → rec-model-service
│   ├── openapi.yaml
│   └── rec_model/
│       ├── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│       └── projections/{recommend_feature,training_samples,learning_events,model_registry}.yaml
│
├── notification/                  # 域：通知 → notification-service
│   ├── openapi.yaml
│   └── notification/
│       └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
│
└── ops/                           # 域：运营/平台 → ops-service
    ├── openapi.yaml
    ├── experiment_bucket/
    │   └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
    └── visit_record/
        └── entity.yaml  fields.yaml  storage.yaml  events.yaml  service.yaml
```

---

## 每个实体目录的文件职责

| 文件 | 职责 | codegen 产出 |
|---|---|---|
| `aggregate.yaml` | 存储后端、DDD 分层映射、counter strategy | Go aggregate 骨架 |
| `fields.yaml` | 字段语义 + 分类 + 日志策略 | Go struct + Dart DTO + Migration |
| `storage.yaml` | 索引 + Migration DDL + TTL | Go migration 文件 |
| `events.yaml` | 领域事件 + 消费方 + 信号标注 | Go events.go |
| `service.yaml` | API 路由（仅路由声明） | Go routes + Dart 路由常量 |
| `projections/*.yaml` | 端侧视图投影（字段映射 + alias） | Dart typed DTO（DO NOT EDIT） |
| `errors.yaml` | 结构化错误码（MODULE.KIND.REASON） | Dart ErrorCode enum + Go 常量 |
| `behaviors.yaml` | 行为采集 + 推荐特征 + 训练样本 | Dart BehaviorTracker + Python Pydantic |
| `privacy.yaml` | 端侧日志 mask + GDPR 删除级联 | Dart PrivacyPolicy.sanitizeForLog() |
| `ui_config.yaml` | tab/布局/feature flags 配置 | Dart UIConfig（DO NOT EDIT） |
| `tests/mock.yaml` | 端侧独立测试场景声明 | Dart 测试骨架（flutter test） |
| `tests/contract.yaml` | 云侧契约测试场景声明 | Go 测试骨架（真实 DB） |
| `tests/e2e.yaml` | 端云集成测试场景声明 | staging CI 测试 |

---

## codegen 流水线（全量）

```
make verify-metadata          # YAML 内部一致性（枚举引用/字段类型/路径绑定）
make codegen                  # Go: struct + routes + errors + migration + fixture
make codegen-app              # Dart: DTO + metadata + errors + behaviors + privacy + ui_config
make codegen-rec-model-python # Python: features + training_samples（Pydantic）
```

---

## 门禁扩展（G0~G10）

| 门禁 | 检查内容 |
|---|---|
| G1 | metadata YAML 内部一致性 |
| G2 | codegen 产物 hash 保护（DO NOT EDIT 文件未被手改） |
| G3 | DDD 层级导入约束（domain ← application ← adapters ← infrastructure） |
| G4 | 错误码覆盖：errors.yaml 中每个 code 在 tests/ 至少有一个场景 |
| G5 | 行为路由一致：behaviors.yaml batch_route ⊆ service.yaml api_routes |
| G6 | UI 配置完整：ui_config.yaml contentType ⊆ fields.yaml ContentType 枚举 |
| G7 | 测试场景覆盖：tests/contract.yaml scenarios ⊆ Go 测试函数（按命名约定） |
| G8 | 隐私策略覆盖：PII/SENSITIVE 字段在 privacy.yaml 有声明 |
| G9 | 行为类型合法：behaviors.yaml events.type ⊆ _shared/types.yaml BehaviorEventType |
| G10 | 投影路径一致：projections/*.yaml output_path 前缀与所在域名称匹配 |

---

## 设计原则

1. **业务对象优先**：目录以域/实体组织，不以技术类型（metadata/openapi/projections）组织
2. **就近原则**：投影、错误码、测试声明紧靠它们的来源实体，不设全局目录
3. **无兼容路径**：0→1 构建，codegen 工具只识别规范路径，不存在 fallback
4. **声明即契约**：tests/*.yaml 是测试意图的声明；`make gate` 验证测试代码实现了全部声明场景
5. **端云对称**：一个域目录 = 一个领域服务 = app cloud/{domain}/ 目录

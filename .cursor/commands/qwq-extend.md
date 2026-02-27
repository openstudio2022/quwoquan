---
name: /qwq-extend
id: qwq-extend
category: Development
description: 实施阶段增量扩展（在已有基线上新增字段/事件/端点/横切层等）
---

> **职责定位**：`/qwq-extend` 是**实施阶段**的增量扩展入口，在已有元数据基线上做局部变更。
> **基线创建**（新建聚合/新建服务/新建特性）请使用 `/opsx-ff`，它会同时完成文档+元数据+代码三位一体的基线化。
>
> 扩展场景对应 `specs/runtime_extension_catalog.md` 中定义的 S01~S25。

---

## 使用时机

| 时机 | 使用命令 |
|------|----------|
| Plan 结束，产生新特性/新服务/新聚合 | `/opsx-ff`（基线化，包含元数据） |
| 实施中发现需要新增字段 | `/qwq-extend add-field` |
| 实施中发现需要新增 API 端点 | `/qwq-extend add-endpoint` |
| 实施中发现需要新增领域事件 | `/qwq-extend add-event` |
| 实施中发现需要补充横切层（错误码/行为/配置） | `/qwq-extend add-errors / add-behaviors / add-ui-config` |
| 实施中发现需要新增测试场景 | `/qwq-extend add-test-contracts` |

---

## 前置条件检查

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 基线已存在 | 目标实体/聚合的 `contracts/metadata/` 目录已存在，`/opsx-ff` 已完成 |
| 2 | 扩展目标明确 | 能写出要扩展的实体/字段/事件/端点名称 |
| 3 | 扩展类型已选定 | 能对应到 S01~S25 中的某一场景 |
| 4 | 归属特性已识别 | 明确此扩展属于哪个特性树节点 |

**若不满足**：输出补全列表，不执行。若基线不存在 → 引导先执行 `/opsx-ff`。

---

## 使用方式

```
/qwq-extend <scenario> [options]
```

---

## 0→1 场景（基线创建类）

> 以下场景通常由 `/opsx-ff` 在步骤 3「元数据基线执行」中自动调用。
> 若需要单独新建（例如在已有特性下补充新聚合），可直接调用。

### S01: 新建聚合根
```
/qwq-extend new-aggregate --name=<AggName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{agg}/` + 5 个 YAML 骨架（aggregate/fields/storage/events/service）
2. `make verify-metadata`
3. `make codegen --target={agg}` → Go struct/repo/handler/migration/test 骨架
4. `make codegen-app --target={agg}` → Dart DTO/repository 骨架
5. 输出手写步骤清单（domain service + application service）

### S02: 新建聚合成员
```
/qwq-extend new-member --aggregate=<AggName> --name=<MemberName>
```

### S03: 新建独立实体
```
/qwq-extend new-entity --name=<EntityName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

### S04: 新建微服务
```
/qwq-extend new-service --name=<service-name> --port=<port>
```
自动执行：
1. 执行 `scripts/new_service_fullstack.sh --name {name}-service --port {port}` 创建服务骨架
2. `new_service_fullstack.sh` 内部自动执行 `scripts/bootstrap_service_config_layout.sh --service {name}-service`
   - 生成 `configs/default|local|integration|prod/config.yaml`
   - 生成 `releases/config/{name}-service/README.md`
3. 创建 `contracts/metadata/{domain}/` 目录
4. `make verify-metadata`
5. `make codegen --service={name}` → 完整服务骨架

门禁约束（发布化配置）：
- 新服务必须通过 `verify_service_config_layout.sh`
- 生产部署清单必须包含 `APP_ENV/SERVICE_NAME/CONFIG_VERSION/IMAGE_VERSION/CONFIG_ROOT`

### S05: 新建 API 端点
```
/qwq-extend new-endpoint --service=<svc> --entity=<entity> --method=<GET|POST|PUT|DELETE> --path=</v1/...>
```

### S06: 新建领域事件
```
/qwq-extend new-event --aggregate=<agg> --name=<EventName> --channel=<event_store|direct|internal>
```

### S07: 新建 ReadModel 投影
```
/qwq-extend new-projection --entity=<entity> --name=<ReadModelName> --source-events=<evt1,evt2>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/projections/{name}.yaml`
2. `make verify-metadata`
3. `make codegen-app` → 生成对应 Dart DTO

### S08: 新建向量能力
```
/qwq-extend new-vector --name=<VectorEntityName> --source=<entity> --field=<field>
```

### S09: 新建 Skill
```
/qwq-extend new-skill --name=<SkillName> --trigger-scenes=<scene1,scene2>
```

### S10: 新建端侧 Feature 模块
```
/qwq-extend new-feature --name=<feature_name> --pages=<page1,page2>
```

---

## 1→N 场景（增量扩展类）

### S11: 已有实体新增字段
```
/qwq-extend add-field --entity=<entity> --name=<fieldName> --type=<string|int64|...> \
  --classification=<PUBLIC|PII|SENSITIVE|SECRET>
```

### S12: 已有实体新增能力
```
/qwq-extend add-capability --entity=<entity> \
  --capability=<searchable|aggregatable|vector_searchable>
```

### S13: 已有事件新增消费者
```
/qwq-extend add-consumer --event=<EventName> --consumer=<service:handler>
```

### S14: 已有实体新增索引
```
/qwq-extend add-index --entity=<entity> --fields=<f1,f2> --unique=<true|false>
```

### S15: 已有 API 新增端点（变体/动作）
```
/qwq-extend add-endpoint --service=<svc> --method=<GET|POST|PUT|DELETE> --path=</v1/...>
```

### S16: 已有投影新增字段
```
/qwq-extend add-projection-field --entity=<entity> --projection=<name> --field=<fieldName>
```

### S17: 变更存储后端
```
/qwq-extend migrate-storage --entity=<entity> --from=<postgres> --to=<mongodb>
```

### S18: 已有实体新增缓存层
```
/qwq-extend add-cache --entity=<entity> --ttl=<seconds>
```

### S19: 已有 Skill 新增 Tool
```
/qwq-extend add-tool --skill=<SkillName> --tool=<ToolName>
```

### S20: 已有实体新增契约测试场景
```
/qwq-extend add-test --entity=<entity> --scenario=<scenario_name> --layer=<mock|contract|e2e>
```

---

## 横切层扩展场景（S21-S25）

> 这 5 个场景在 `/opsx-ff` 基线化时可自动执行，也可在实施阶段单独补充。

### S21: 新增错误码层
```
/qwq-extend add-errors --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/errors.yaml` 骨架
   - 预填通用错误码：not_found / forbidden / rate_limited / invalid_argument
   - 每个 code 含：http_status / retryable / user_message(zh/en) / dart_const / go_const
2. `make verify-metadata`
3. `make codegen-app` → 生成 `{entity}_errors.g.dart`（ErrorCode enum + i18n map + isRetryable）
4. `make codegen` → 生成 `generated/errors.go`（Go 错误码常量）
5. 输出手写步骤：补充业务特有错误码、在 Handler 层绑定 go_const 使用

### S22: 新增端侧 UI 配置层
```
/qwq-extend add-ui-config --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/ui_config.yaml` 骨架
   - 从 fields.yaml ContentType 枚举推导 discovery_tabs 初始列表
   - 预填 card_config / interaction_config / feature_flags / empty_states
2. `make verify-metadata`（新增检查：tabs[*].content_type ⊆ _shared/types.yaml 枚举）
3. `make codegen-app` → 生成 `{entity}_ui_config.g.dart`
   （DiscoveryTabConfig list / CardConfig map / feature flags map / EmptyStateConfig）
4. 输出手写步骤：填充具体布局参数、文案 key、feature flags 初始值

### S23: 新增行为采集层
```
/qwq-extend add-behaviors --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/behaviors.yaml` 骨架
   - 从 events.yaml 已有行为事件推导 behavior_events 初始列表
   - 预填 recommend_features 框架（从 fields.yaml 可推导字段）
   - 预填 training_sample 框架
2. `make verify-metadata`
   （新增检查：behaviors.yaml 的 dedicated_route ⊆ service.yaml api_routes）
3. `make codegen-app` → 生成 `{entity}_behaviors.g.dart`（BehaviorTracker 类）
4. `make codegen` → 生成 `domain/event/behavior_events.go`
5. 若有 rec-model-service：`make codegen-rec-model-python`
   → 生成 `{entity}_features.py` / `training_sample.py`（Pydantic BaseModel）
6. 输出手写步骤：补充推荐特征权重、训练样本字段

### S24: 新增隐私策略层
```
/qwq-extend add-privacy --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/privacy.yaml` 骨架
   - 从 fields.yaml classification=PII/SENSITIVE 字段自动填充 app_log_policy
   - 预填 data_lifecycle 框架（retention_days / deletion_cascade）
2. `make verify-metadata`
   （新增检查：fields.yaml 中 PII/SENSITIVE 字段全部在 privacy.yaml 中有声明）
3. `make codegen-app` → 生成 `{entity}_privacy_policy.g.dart`（log sanitize 方法）
4. 输出手写步骤：确认 mask 策略、补充 GDPR 删除级联顺序

### S25: 新增三层测试契约
```
/qwq-extend add-test-contracts --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{entity}/tests/` 目录
   - `mock.yaml`：从 service.yaml api_routes 生成端侧 mock 测试场景骨架
   - `contract.yaml`：从 service.yaml contract_test（若有）迁移场景；清理 service.yaml 中的 contract_test 块
   - `e2e.yaml`：生成端云集成场景骨架（端 → 网关 → 服务 → DB 路径）
2. `make verify-metadata`
   （新增检查：contract.yaml scenarios 与 Go 测试文件函数名一致性）
3. `make codegen-app` → 生成 `test/cloud/{domain}/{entity}_mock_contract_test.dart` 骨架
4. `make codegen` → 生成 `services/{domain}-service/tests/{entity}_contract_test.go` 骨架
5. 输出手写步骤：补充具体断言逻辑（mock 解析正确性 + 云侧 DB 断言）

---

## 执行约束（所有场景）

```
① 参数校验（实体/服务是否存在、枚举值是否合法）
② metadata YAML 新建或更新
③ make verify-metadata（不通过则停止，输出修复建议）
④ make codegen / make codegen-app（视场景选择）
⑤ 输出手写补充清单（明确哪些内容需要人工完成）
⑥ make test-contract（若存在相关测试）
```

任何步骤失败 → 停止并输出错误 + 修复建议。

---

## 与 /opsx-ff 的职责边界

| 命令 | 粒度 | 时机 | 典型操作 |
|------|------|------|----------|
| `/opsx-ff` | 特性级 | Plan 结束，基线化 | 新建聚合+服务+所有横切层，生成可执行基线 |
| `/qwq-extend` | 对象级 | 实施阶段，增量变更 | 新增字段/事件/端点/补充横切层 |

**原则**：`/opsx-ff` 调用 `/qwq-extend` 的逻辑（内部分发到对应场景），用户在基线化时不需要直接调用 `/qwq-extend`。
`/qwq-extend` 是实施阶段的增量工具，当你在写业务逻辑时发现"哦，需要多一个字段"，用它。

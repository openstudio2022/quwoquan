---
name: /extend
id: extend
category: Development
description: 实施阶段增量扩展（在已有基线上新增字段/事件/端点/横切层等，对应 S01~S25）
---

> **职责定位**：`/extend` 是**实施阶段**的增量扩展入口，在已有元数据基线上做局部变更。
> **基线创建**（新建聚合/新建服务/新建特性）优先使用 `/baseline`；若规格与设计需要分两轮冻结，则使用 `/prd` + `/design`。
>
> 扩展场景对应 `specs/runtime_extension_catalog.md` 中定义的 S01~S25。

---

## 使用时机

| 时机 | 使用命令 |
|------|----------|
| 探索结束，产生新特性/新服务/新聚合 | `/baseline`，或 `/prd` + `/design`（基线化，包含元数据） |
| 实施中发现需要新增字段 | `/extend add-field` |
| 实施中发现需要新增 API 端点 | `/extend add-endpoint` |
| 实施中发现需要新增领域事件 | `/extend add-event` |
| 实施中发现需要补充横切层（错误码/行为/配置） | `/extend add-errors / add-behaviors / add-ui-config` |
| 实施中发现需要新增测试场景 | `/extend add-test-contracts` |

---

## 前置条件检查

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 基线已存在 | 目标实体/聚合的 `contracts/metadata/` 目录已存在，且 `/baseline` 或 `/design` 已完成 |
| 2 | 扩展目标明确 | 能写出要扩展的实体/字段/事件/端点名称 |
| 3 | 扩展类型已选定 | 能对应到 S01~S25 中的某一场景 |
| 4 | 归属特性已识别 | 明确此扩展属于哪个特性树节点 |

**若不满足**：输出补全列表，不执行。若基线不存在 → 引导先执行 `/baseline`，或标准链路 `/prd` + `/design`。

---

## 使用方式

```
/extend <scenario> [options]
```

---

## 0→1 场景（基线创建类）

> 以下场景通常由 `/baseline` 或 `/design` 在「元数据基线执行」步骤中自动调用。
> 若需要单独新建（例如在已有特性下补充新聚合），可直接调用。

### S01: 新建聚合根
```
/extend new-aggregate --name=<AggName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```
自动执行：
1. 创建 `contracts/metadata/{domain}/{agg}/` + 5 个 YAML 骨架（aggregate/fields/storage/events/service）
2. `make verify-metadata`
3. `make codegen --target={agg}` → Go struct/repo/handler/migration/test 骨架
4. `make codegen-app --target={agg}` → Dart DTO/repository 骨架
5. 输出手写步骤清单（domain service + application service）

### S02: 新建聚合成员
```
/extend new-member --aggregate=<AggName> --name=<MemberName>
```

### S03: 新建独立实体
```
/extend new-entity --name=<EntityName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

### S04: 新建微服务
```
/extend new-service --name=<service-name> --port=<port>
```
自动执行：
1. `scripts/new_service_fullstack.sh --name {name}-service --port {port}` 创建服务骨架
2. `scripts/bootstrap_service_config_layout.sh` 生成环境配置目录
3. 创建 `contracts/metadata/{domain}/` 目录
4. `make verify-metadata` + `make codegen --service={name}`

### S05: 新建 API 端点
```
/extend new-endpoint --service=<svc> --entity=<entity> --method=<GET|POST|PUT|DELETE> --path=</v1/...>
```

### S06: 新建领域事件
```
/extend new-event --aggregate=<agg> --name=<EventName> --channel=<event_store|direct|internal>
```

### S07: 新建 ReadModel 投影
```
/extend new-projection --entity=<entity> --name=<ReadModelName> --source-events=<evt1,evt2>
```

### S08: 新建向量能力
```
/extend new-vector --name=<VectorEntityName> --source=<entity> --field=<field>
```

### S09: 新建 Skill
```
/extend new-skill --name=<SkillName> --trigger-scenes=<scene1,scene2>
```

### S10: 新建端侧 Feature 模块
```
/extend new-feature --name=<feature_name> --pages=<page1,page2>
```

---

## 1→N 场景（增量扩展类）

### S11: 已有实体新增字段
```
/extend add-field --entity=<entity> --name=<fieldName> --type=<string|int64|...> \
  --classification=<PUBLIC|PII|SENSITIVE|SECRET>
```

### S12: 已有实体新增能力
```
/extend add-capability --entity=<entity> \
  --capability=<searchable|aggregatable|vector_searchable>
```

### S13: 已有事件新增消费者
```
/extend add-consumer --event=<EventName> --consumer=<service:handler>
```

### S14: 已有实体新增索引
```
/extend add-index --entity=<entity> --fields=<f1,f2> --unique=<true|false>
```

### S15: 已有 API 新增端点（变体/动作）
```
/extend add-endpoint --service=<svc> --method=<GET|POST|PUT|DELETE> --path=</v1/...>
```

### S16: 已有投影新增字段
```
/extend add-projection-field --entity=<entity> --projection=<name> --field=<fieldName>
```

### S17: 变更存储后端
```
/extend migrate-storage --entity=<entity> --from=<postgres> --to=<mongodb>
```

### S18: 已有实体新增缓存层
```
/extend add-cache --entity=<entity> --ttl=<seconds>
```

### S19: 已有 Skill 新增 Tool
```
/extend add-tool --skill=<SkillName> --tool=<ToolName>
```

### S20: 已有实体新增契约测试场景
```
/extend add-test --entity=<entity> --scenario=<scenario_name> --layer=<mock|contract|e2e>
```

---

## 横切层扩展场景（S21-S25）

> 这 5 个场景在 `/baseline` 或 `/design` 基线化时可自动执行，也可在实施阶段单独补充。

### S21: 新增错误码层
```
/extend add-errors --entity=<entity> --domain=<domain>
```
自动执行：
1. 创建 `errors.yaml` 骨架（code/http_status/retryable/user_message.zh/en/dart_const/go_const）
2. `make verify-metadata` + `make codegen-app` → 生成 `{entity}_errors.g.dart`
3. `make codegen` → 生成 `generated/errors.go`

### S22: 新增端侧 UI 配置层
```
/extend add-ui-config --entity=<entity> --domain=<domain>
```

### S23: 新增行为采集层
```
/extend add-behaviors --entity=<entity> --domain=<domain>
```

### S24: 新增隐私策略层
```
/extend add-privacy --entity=<entity> --domain=<domain>
```

### S25: 新增三层测试契约
```
/extend add-test-contracts --entity=<entity> --domain=<domain>
```

### S26: 修改 PersonalAssistant 输出契约字段
```
/extend pa-contract --action=<add-field|rename-field|remove-field|bump-version> --field=<fieldName>
```

**适用**：修改 `assistant_turn_v4` 输出契约字段（新增/重命名/删除字段，或版本升级）。

**自动执行**：
1. 更新 `assets/personal_assistant/prompts/global/phase.output_contract.*.md`（prompt 模板同步）
2. 更新 `assets/personal_assistant/prompts/_standards/output_contracts.json`（契约 schema）
3. 更新 `lib/personal_assistant/contracts/assistant_turn_contract.dart` 的 `AssistantTurnOutput` 类
4. 检查并更新 `_ensureAssistantTurnEnvelopeText` / `_extractAssistantTurnPayload` 等引擎逻辑
5. 若 `bump-version`：在 `AssistantSessionManager.load()` 中添加迁移逻辑，旧版本降级为遗留
6. 清理 `runtime_policies.dart` / `progress_text_policy.json` 中过时的版本签名
7. `flutter test test/personal_assistant/`

**强制检查**：
- 执行后不得存在三个及以上活跃 contractVersion（违反 `02-dart-coding §5.3`）
- 执行后引擎逻辑代码中不得有新增的字段名字符串字面量（违反 `02-dart-coding §5.1`）

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

## 与 /baseline /design 的职责边界

| 命令 | 粒度 | 时机 | 典型操作 |
|------|------|------|----------|
| `/baseline` | 特性级 | 需求明确且方案收敛时的基线化阶段 | 一次完成 spec/design/plan/metadata 基线 |
| `/design` | 特性级 | 基线化阶段 | 新建聚合+服务+所有横切层，生成可执行基线 |
| `/extend` | 对象级 | 实施阶段，增量变更 | 新增字段/事件/端点/补充横切层 |

**原则**：`/baseline` 与 `/design` 都会调用 `/extend` 的逻辑（内部分发到对应场景），用户在基线化时不需要直接调用 `/extend`。
`/extend` 是实施阶段的增量工具，当你在写业务逻辑时发现「哦，需要多一个字段」，用它。

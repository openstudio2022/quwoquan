---
name: /qwq-extend
id: qwq-extend
category: Development
description: 端云可扩展开发入口：20 个扩展场景的统一触发命令
---

执行业务对象和元数据的可扩展开发操作。对应 `specs/runtime_extension_catalog.md` 中定义的 20 个扩展场景。

## 使用方式

```
/qwq-extend <scenario> [options]
```

---

## 0→1 场景

### S01: 新建聚合根
```
/qwq-extend new-aggregate --name=<AggName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

**自动执行：**
1. 创建 `contracts/metadata/{agg}/` 目录 + 5 个 YAML 骨架
2. `make verify`
3. `make codegen target={agg}` → 生成 Go struct/repo/handler/migration/test
4. `make codegen-app target={agg}` → 生成 Dart DTO/repository
5. 提示手写步骤（domain service + application service）

### S02: 新建聚合成员
```
/qwq-extend new-member --aggregate=<AggName> --name=<MemberName>
```

### S03: 新建独立实体
```
/qwq-extend new-entity --name=<EntityName> --domain=<domain> --service=<svc> --storage=<postgres|mongodb>
```

### S04: 新建服务
```
/qwq-extend new-service --name=<service-name> --port=<port>
```

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
/qwq-extend new-projection --name=<ReadModelName> --source-events=<evt1,evt2>
```

### S08: 新建向量实体
```
/qwq-extend new-vector --name=<VectorEntityName> --source=<entity> --field=<field>
```

### S09: 新建 Skill
```
/qwq-extend new-skill --name=<SkillName> --trigger-scenes=<scene1,scene2>
```

### S10: 新建端侧 Feature
```
/qwq-extend new-feature --name=<feature_name> --pages=<page1,page2>
```

---

## 1→N 场景

### S11: 已有实体新增字段
```
/qwq-extend add-field --entity=<entity> --name=<fieldName> --type=<string|int64|...> --classification=<PUBLIC|PII|SENSITIVE|SECRET>
```

### S12: 已有实体新增能力
```
/qwq-extend add-capability --entity=<entity> --capability=<searchable|aggregatable|vector_searchable>
```

### S13: 已有事件新增消费者
```
/qwq-extend add-consumer --event=<EventName> --consumer=<service:handler>
```

### S14: 已有实体新增索引
```
/qwq-extend add-index --entity=<entity> --fields=<f1,f2> --unique=<true|false>
```

### S15: 已有 API 新增操作
```
/qwq-extend add-endpoint --service=<svc> --route=<existing_route> --method=<GET|POST|PUT|DELETE>
```

### S16: 已有 Projector 新增字段
```
/qwq-extend add-projection-field --projection=<name> --field=<fieldName>
```

### S17: 变更存储后端
```
/qwq-extend migrate-storage --entity=<entity> --from=<postgres> --to=<mongodb>
```

### S18: 已有实体新增缓存
```
/qwq-extend add-cache --entity=<entity> --ttl=<seconds>
```

### S19: 已有 Skill 新增 Tool
```
/qwq-extend add-tool --skill=<SkillName> --tool=<ToolName>
```

### S20: 已有实体新增契约测试场景
```
/qwq-extend add-test --entity=<entity> --scenario=<scenario_name>
```

---

## 执行约束

每个场景执行时强制以下顺序：

```
① 参数校验（实体/服务是否存在、枚举值是否合法）
② metadata YAML 更新
③ make verify（不通过则停止，提示修正）
④ make codegen（不通过则停止，提示修正）
⑤ 提示手写补充项
⑥ make test-contract
⑦ make gate
```

任何步骤失败 → 停止并输出错误信息 + 修复建议。

---

## 与 /opsx 命令的关系

| 命令 | 粒度 | 作用 |
|------|------|------|
| `/opsx-ff` | 特性级 | 创建/推进一个用户可感知的特性 |
| `/opsx-apply` | 特性级 | 实施特性（含多个扩展操作） |
| `/qwq-extend` | 对象级 | 单个业务对象/字段/事件/接口的扩展操作 |

一个特性（`/opsx-ff`）可能包含多个扩展操作（`/qwq-extend`）。
例如："新增打赏功能"特性 = S03(新建Tip实体) + S06(新建TipCreated事件) + S05(新建API) + S10(新建端侧Feature)。

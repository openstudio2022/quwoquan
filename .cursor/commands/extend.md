---
name: /extend
id: extend
category: Development
description: 按 D0/F1 扩展 metadata、Object Facade/Data Ports、adapter 与三层测试
---

# /extend

`/extend` 是已有规格基线上的对象级实施入口。新 Journey、领域边界或业务能力先走
`/prd`、`/design` 或 `/baseline`；本命令不得替代架构裁决。

权威来源：

- `specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md`
- `specs/feature-tree/runtime/system-architecture-and-engineering-guide/acceptance.yaml`
- `quwoquan_service/contracts/metadata/DESIGN.md`
- 执行场景：`specs/runtime_extension_catalog.md`

## 使用方式

```text
/extend <scenario> [目标与约束]
```

场景必须映射到扩展目录中的 EX01–EX11：

- `new-object` / `add-member`
- `add-command` / `add-query`
- `add-event` / `add-projection`
- `add-storage-adapter` / `migrate-storage`
- `add-endpoint`
- `add-field` / `add-error` / `add-privacy` / `add-behavior`
- `add-app-consumer`
- `new-service`
- `add-test-evidence`

## 准入

执行前必须完成：

1. `Spec Entry`：AppRoot Journey/Scenario、L1/L2/L3、范围、Out of Scope、SIT/GWT/
   contract 与三层测试证据明确。
2. `Pre-work Reflection`：确认 metadata-first、runtime error、Mock 隔离、页面质量、
   四环境、E2E 与第二真相源风险。
3. 目标对象的 metadata 基线存在；若不存在，先完成对象边界设计。
4. 对应 acceptance 已声明测试意图，且不会用本命令临时发明架构。

缺任一项时输出 `GATE_BLOCK`，返回规格或设计阶段。

## 对象边界检查

新增成员前必须先回答：

- 生命周期是否完全依附 owner？
- 写 owner 是否唯一且必须与 owner 同事务维护不变量？
- cardinality 是否有明确上限？
- 是否需要独立 ID、版本、幂等、权限、审核、保留或删除周期？
- 是否会被多个聚合/服务直接写入或持续增长？

只有“依附生命周期 + 同一写 owner + 有界集合”才能标记为 `owned_entity`。
存在独立生命周期、并发边界或无界集合时必须标记为 `separate_aggregate`。
无界集合禁止内嵌，不得以数组、子文档或级联保存掩盖。

## Command / Query 分流

- **command**：绑定 aggregate owner 与 command facet；Facade 完成 authz、幂等、load、
  领域行为和 expected-version commit + outbox。
- **query**：绑定 query facet、业务命名 Reader 与 typed Slice；禁止加载 aggregate，
  禁止动态 Filter/Map。

URL、DTO、handler 名和存储类型都不能替代该裁决。

## 固定执行顺序

```text
① 更新 metadata
② commercial validate
③ ContractGraph + codegen
④ Object Application Facade
⑤ Object Data Ports
⑥ service internal/infrastructure adapter
⑦ 显式 composition root
⑧ local_contract
⑨ api_integration
⑩ user_acceptance（涉及用户旅程时）
⑪ alpha / beta / gamma / prod 准出
```

标准命令：

```bash
cd quwoquan_service
go run ./tools/qwq_contract validate \
  --metadata-dir contracts/metadata \
  --profile commercial
make codegen
make codegen-app
make verify-contract-graph-commercial
cd ..
make gate
```

任何一步失败立即停止。禁止 alias、fallback、双读、双写、动态 skip、allowlist 或放宽
测试阈值。

## 实现约束

- `ContractGraph` 只在构建期生成；服务启动不读取 metadata。
- 每个对象使用专属 command/query Facade、AggregateStore、named Reader 和 typed Slice。
- 具体 Mongo/PG/Redis/ES/external adapter 只放服务 `internal/infrastructure/**`。
- `cmd/{entry}/main.go` 按对象显式选择并注入 adapter，不根据 metadata 在运行期选厂。
- query 直接读取 Reader/Slice，不为展示路径加载 aggregate。
- generated 文件禁止手改；边界缺失时回 metadata/design，不在 generator 中猜测。
- prod 不得装配 Memory、Noop、Mock、fixture、seed 或默认 secret。

## 特殊场景

### `new-service`

1. 先确认 domain owner 与现有服务边界。
2. 执行：

```bash
make new-service SERVICE=<name>-service PORT=<port>
```

3. 同批更新 process/domain/plane/module/workload topology 真相源。
4. 新服务使用根 Go module，并以显式 composition root 装配对象 Facade 与 adapter。

### `migrate-storage`

- 先证明对象端口语义在两个真实 adapter 上一致。
- 补 migration、replay/rebuild、回滚和数据一致性证据。
- 一次性切换 composition root；不保留长期双写或自动 fallback。

### `add-query`

- metadata 必须声明 reader、slice、分页、actor 与可见性。
- local contract 验证 typed Slice；api integration 验证真实读存储、顺序、分页、权限与空态。

## 出口

最终按 `Exit Review` 汇报：

- metadata 与 codegen 变更；
- Facade/Data Ports 与 composition root；
- local_contract、api_integration、user_acceptance 证据；
- alpha/beta/gamma/prod 装配与生产纯净；
- 门禁结果、观测/回滚和剩余风险。

自然语言等价触发：“加字段、接口、事件、查询、对象、存储 adapter、服务或测试证据”
与本命令等价。

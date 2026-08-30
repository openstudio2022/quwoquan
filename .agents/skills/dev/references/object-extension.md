# 对象级扩展（dev 条件子流程）

已有规格基线上的对象级实施口径。新 Journey、领域边界或业务能力先走 `prd` / `design`；
本子流程**不得替代架构裁决**。

权威来源：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/`
的 `design.md` 与 `spec.md` 中的 REQ/SIT，以及 `quwoquan_service/contracts/metadata/DESIGN.md`。

## 场景 EX01–EX11

```text
new-object / add-member          add-command / add-query
add-event / add-projection       add-storage-adapter / migrate-storage
add-endpoint                     add-app-consumer
add-field / add-error / add-privacy / add-behavior
new-service                      add-test-evidence
```

[MUST NOT] 再维护场景目录副本；场景语义只在这里。

## 准入

- [MUST] 目标对象的 metadata 基线存在。不存在时先完成对象边界设计，回 `design`。
- [MUST] 对应 spec 已声明验收意图。
- [MUST NOT] 用本子流程临时发明架构。

### 对象边界五问

新增成员前逐条回答：

1. 生命周期是否完全依附 owner？
2. 写 owner 是否唯一，且必须与 owner 同事务维护不变量？
3. cardinality 是否有明确上限？
4. 是否需要独立 ID、版本、幂等、权限、审核、保留或删除周期？
5. 是否会被多个聚合或服务直接写入，或持续增长？

只有「**依附生命周期 + 同一写 owner + 有界集合**」才能标记 `owned_entity`。
存在独立生命周期、并发边界或无界集合时必须 `separate_aggregate`。
**无界集合禁止内嵌**，不得用数组、子文档或级联保存掩盖。

### Command / Query 分流

- **command** — 绑定 aggregate owner 与 command facet；Facade 完成 authz、幂等、load、
  领域行为、expected-version commit + outbox。
- **query** — 绑定 query facet、业务命名 Reader 与 typed Slice；
  禁止加载 aggregate，禁止动态 Filter/Map。

URL、DTO、handler 名与存储类型都**不能**替代这个裁决。

## 固定顺序

```text
① 更新 metadata          ② commercial validate      ③ ContractGraph + codegen
④ Object Application Facade                         ⑤ Object Data Ports
⑥ service internal/infrastructure adapter           ⑦ 显式 composition root
⑧ local_contract         ⑨ api_integration          ⑩ user_acceptance（涉及用户旅程时）
⑪ alpha / beta / gamma / prod 准出
```

```bash
make verify-metadata
make codegen
make codegen-app
make -C quwoquan_service verify-contract-graph-commercial
make gate
```

任何一步失败**立即停止**。
[MUST NOT] alias、fallback、双读、双写、动态 skip、allowlist 或放宽测试阈值。

### 实现约束

- `ContractGraph` 只在构建期生成；服务启动不读 metadata。
- 每个对象用专属 command/query Facade、AggregateStore、named Reader 与 typed Slice。
- 具体 Mongo/PG/Redis/ES/external adapter 只放服务 `internal/infrastructure/**`。
- `cmd/{entry}/main.go` 按对象**显式**选择并注入 adapter，不在运行期按 metadata 选厂。
- query 直接读 Reader/Slice，不为展示路径加载 aggregate。
- generated 文件禁止手改；边界缺失时回 metadata/design，不在 generator 里猜。
- prod 不装配 Memory、Noop、Mock、fixture、seed 或默认 secret（生产装配纯净规则见
  `specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-019`）。

## 三个特殊场景

**`new-service`** — 先确认 domain owner 与现有服务边界，且 context/object 已在 metadata
中存在、对象尚无 source owner：

```bash
make new-service SERVICE=<name>-service CONTEXT=<domain.context> OBJECT=<business-object> LANGUAGE=go|python
```

脚手架不创建 registry、README、独立 Makefile 或空目录；workload 由服务自己的
`deploy/base` 与 `environments/<env>/deploy` 声明，Ops 只做动态装配与外部依赖。

**`migrate-storage`** — 先证明对象端口语义在两个真实 adapter 上一致，补 migration、
replay/rebuild、回滚与数据一致性证据，**一次性**切换 composition root；
不保留长期双写或自动 fallback。

**`add-query`** — metadata 声明 reader、slice、分页、actor 与可见性；
local_contract 验证 typed Slice，api_integration 验证真实读存储、顺序、分页、权限与空态。

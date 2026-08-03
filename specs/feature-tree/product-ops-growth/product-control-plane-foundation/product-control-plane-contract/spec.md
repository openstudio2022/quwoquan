# L3 Story：产品运营控制面契约 (`product-control-plane-contract`)

> 所属能力：[产品运营控制面基础](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为运营、治理或客服角色，我希望在同一控制面按权限执行审核、实验和推荐干预并看到审计结果，从而不需要调用各领域私有接口。

## 2. 范围与非目标

### In Scope

- 统一控制面 operation、workflow、角色、危险动作确认和审计事实。
- 领域 owner 保留业务决定权，控制面只经公开 command/query 协作。

### Out of Scope

- 复制业务聚合、绕过 owner 直写存储或在 Portal 硬编码第二套权限。

## 3. 行为要求

### REQ-001 权限与审计单轨

- 每个控制面动作必须声明 operation scope；危险动作必须记录操作者、目标、原因、revision 与结果，失败时不得生成成功审计。

### REQ-002 全局精选池由具名聚合原子治理

- `PremiumPoolEntry` 是全局精选池准入、回滚和下架的唯一 owner；身份为 `contentId`，生命周期只允许 `active`、`rolled_back`、`takedown_ejected`。
- Upsert 与 Rollback 必须把聚合状态、workflow、不可变 audit、幂等回执和 outbox 事件提交在同一 PostgreSQL transaction；任一写入失败不得留下部分成功。
- Takedown 必须由两个不同受信 operator 对同一聚合 revision 和 payload digest 双签，并在同一事务中提交终态与 outbox。
- Recommendation 只能消费 `PremiumPoolEntryUpserted`、`PremiumPoolEntryRolledBack`、`PremiumPoolEntryTakedownEjected` typed event 维护本地候选投影；Portal、环境脚本和测试不得直写 `rm_premium_pool`。
- PremiumPoolEntry operation 的 commercial status 只表达原子命令、鉴权、错误、审计和事件契约是否可执行；三环境发布证据由本节点 OPEN 与发布 Gate 验收，不得反向禁用生成该证据所必需的受信 operator command。

## 4. 契约引用

- experiment：`quwoquan_service/services/product-ops-service/contracts/product_ops/experiment/operations.yaml`
- premium pool：`quwoquan_service/services/product-ops-service/contracts/product_ops/premium_pool_entry/operations.yaml`
- audit event：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`

## 5. 验收场景

### GWT-001 越权拒绝且合法动作可审计

- GIVEN 两个运营主体分别具有允许和不允许目标 operation 的 scope。
- WHEN 两者对同一对象提交控制面动作。
- THEN 合法动作产生 owner 结果与完整审计事实；越权动作 fail-closed 且不改变对象状态。

<a id="gwt-002"></a>
### GWT-002 全局精选池命令与投影单轨

- GIVEN 受信 operator、有效内容身份、质量准入证据和真实 PostgreSQL/outbox/Recommendation consumer 已装配。
- WHEN operator Upsert、Rollback，或两名不同 operator 对同一 revision 执行 Takedown。
- THEN Product Ops 只产生一份 `PremiumPoolEntry` 聚合状态、一份命令回执和一条 durable outbox event；Recommendation 幂等投影相同终态。
- THEN 幂等键摘要冲突、revision 冲突、单人重复双签或任一事务写失败均 fail-closed，且不存在同步发布、generic Document 写入或 projection 直写旁路。

## 6. 依赖

- 前置要求：统一登录主体、scope 与领域公开 operation。
- 上游事实：控制面身份、目标 revision 与原因。
- 下游结果：owner 命令结果和审计事实。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 跨领域控制面证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前缺少本节点直接绑定的多领域权限与审计组合测试。
- 完成判定：`GWT-001` 由至少两个领域 owner 的真实 operation 直接证明。

### OPEN-002 全局精选池三环境发布证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 PremiumPoolEntry 原子 command 已可执行，但不可变候选尚未同时绑定 Alpha、Beta、Gamma 的 operator command、durable outbox、Recommendation consumer 与 content-release premium readback 收据。
- 完成判定：同一 source revision、managed snapshot 与 release digest 在 Alpha、Beta、Gamma 分别通过 target-scoped 受管非生产 operator port 形成 command receipt、唯一 typed event/outbox receipt、Recommendation premium projection receipt 和 content-release readback receipt；Prod 只接受真实 RS256 OIDC，任何非生产 operator material 不得进入 Prod。

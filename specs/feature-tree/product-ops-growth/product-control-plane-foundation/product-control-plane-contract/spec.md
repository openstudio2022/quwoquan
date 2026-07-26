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

## 4. 契约引用

- experiment：`quwoquan_service/services/product-ops-service/contracts/product_ops/experiment/operations.yaml`
- audit event：`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`

## 5. 验收场景

### GWT-001 越权拒绝且合法动作可审计

- GIVEN 两个运营主体分别具有允许和不允许目标 operation 的 scope。
- WHEN 两者对同一对象提交控制面动作。
- THEN 合法动作产生 owner 结果与完整审计事实；越权动作 fail-closed 且不改变对象状态。

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

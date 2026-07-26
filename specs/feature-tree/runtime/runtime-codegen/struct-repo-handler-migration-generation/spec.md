# L3 Story：ContractGraph 产物生成 (`struct-repo-handler-migration-generation`)

> 所属能力：[`runtime-codegen`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望从统一 ContractGraph Source 重建端云类型、路由、错误与存储产物，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 端云类型、路由、错误、处理器描述符、存储映射及其生成校验。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 生成器只消费统一 ContractGraph Source

- 所有契约型 generator 必须消费统一 ContractGraph Source；资源型 generator 只消费对应服务本地权威资源。
- 禁止 generator 直接扫描 metadata 路径或维护独立 YAML parser。

<a id="req-002"></a>
### REQ-002 生成产物可重建且可编译

- 生成的 Go/Dart/Python 产物必须通过对应编译或静态校验，clean checkout 重建结果必须稳定。
- missing、stale、orphan 任一状态必须使检查失败。

<a id="req-003"></a>
### REQ-003 业务代码不得再维护 route/page/surface/operation override 表

- 业务代码不得维护 route/page/surface/operation override 表。
- 端云只消费 codegen 生成的 canonical ID 和 header，不保留旧键兼容读取。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 从统一 Source 幂等生成产物

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 在 clean checkout 执行契约视图构建、codegen 和 check。
- THEN 各生成器只消费统一 ContractGraph Source，产物通过编译，重复执行无差异。
- AND 契约无效或产物 missing、stale、orphan 时检查明确失败且不留下部分成功产物。

## 6. 依赖

- 前置要求：[`runtime-codegen`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 ContractGraph 产物生成验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少同时证明统一 Source、clean checkout 幂等、编译通过和 missing/stale/orphan fail-closed 的直接测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

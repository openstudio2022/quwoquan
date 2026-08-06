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

<a id="open-002"></a>
### OPEN-002 存储映射缺少平台级共用存储的归属表达位

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 storage 映射只能由单个对象的 `storage.yaml` 声明表，缺少平台级共用存储的归属表达位。仓内存在跨服务共用、不属于任何单一业务对象的平台级存储，这类表既无法如实声明归属，也不会出现在任何对象的存储契约里，于是成为按对象归属工作的判定与扫描的静默盲区；硬塞给某个对象则是造假归属。落在该盲区的存储如下，全部由平台组件建表并被多服务共用：
  - `notification_outbox`（`internal/platform/reliabletaskmongo/store.go`）：通用可靠任务队列的任务表，被 chat-service 与 integration-service 两个服务共用。命名含 `outbox` 但语义是任务队列而非事件发布，属既存命名缺陷；改名需要生产数据迁移，当前不改，只如实记录。
  - `product_control_plane_outbox`、`platform_control_plane_outbox`、`generic_control_plane_outbox`（`internal/platform/controlplane/persistence/postgres_store.go`）：发布配置证明的控制面事件表，按 scope 参数化，被 8 个以上服务的 `controlplane.StartReleaseConfigAttestation` 共用。
  - `reliable_task_outbox`（由 `external_integration/external_interaction` 声明）与 `post_import_task_outbox`（由 `content/post` 声明）：已有对象归属，但与 `notification_outbox` 同属命名缺陷——名为 outbox 实为可靠任务队列，待存储 `role` 字段落地后应标为非发布型，避免按名字工作的判定把它们当成事件发件箱。
- 完成判定：storage 映射能表达平台级共用存储的归属（或显式声明其无对象归属），上述存储各自获得可引用的归属或排除出处，且按对象归属的判定不再依赖对它们的隐性缺席。

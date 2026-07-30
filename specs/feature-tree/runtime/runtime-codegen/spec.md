# L2 Business Capability：运行时代码生成 (`runtime-codegen`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

将服务本地 `contracts/` 与共享 metadata 编译为一次性 ContractGraph 视图，并从同一 Source 生成端云类型、路由、错误、存储和观测产物。

## 2. 范围与非目标

### In Scope

- 服务本地契约视图构建、统一 ContractGraph Source、模板注册和可重建生成产物。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：编译服务自治契约与共享 metadata，并由统一 Source 驱动各 generator。
  - 本能力输出：可在 clean checkout 幂等重建且通过 stale/orphan/check 校验的生成产物。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`struct-repo-handler-migration-generation`](./struct-repo-handler-migration-generation/spec.md)：从统一 ContractGraph Source 生成端云类型、路由、错误和存储等可编译产物。
- [`template-engine-and-metadata-reader`](./template-engine-and-metadata-reader/spec.md)：显式注册模板与产物类型，禁止模板或 generator 自行解析契约 YAML。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 服务自治契约只经统一 ContractGraph Source 进入生成器

- 服务本地 `contracts/`、控制面契约与跨服务共享 metadata 必须先编译到 `.qwq_output` 的一次性视图，再由统一 ContractGraph Source 驱动 generator；禁止 tracked 聚合注册表和第二个 YAML parser。

<a id="req-002"></a>
### REQ-002 生成代码必须 go build 编译通过

- 生成代码必须通过对应语言编译与 `--check` 校验。
- missing、stale、orphan 产物必须 fail-closed；生成代码不得包含硬编码存储地址或 secret。

<a id="req-003"></a>
### REQ-003 请求 wire 只从 canonical bindings 生成

- operation 的非 body wire 位置只由 `request_bindings.path/query/header/injected` 表达；body 只由 `request_entity + request_body_kind` 定义。
- `request_fields/path_params/query_params` 与 `client_contract.*_bindings` 不得作为 operation 可编辑输入，compiler、ContractGraph、OpenAPI 和 App request ABI 必须从 canonical bindings 派生。
- App 只通过 generated request type、encoder、`GeneratedCloudOperationClient` 与统一 executor 发出 metadata 已声明的 path/query/header/body；metadata、生成 encoder 与实际 wire 不一致时 fail-closed。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime codegen 能力 SIT

- GIVEN 执行“runtime codegen 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime codegen 能力”对应动作。
- THEN 服务自治契约被编译为一次性视图，直属 Story 从同一 ContractGraph Source 生成可编译产物，且重复生成无差异。
- AND 契约无效、产物 stale/orphan 或 generator 绕过统一 Source 时明确失败且不写入伪成功产物。
- AND 请求侧门禁同时校验 canonical bindings、生成 request ABI/encoder 与统一 executor，扫描为空或出现退役请求字段时失败。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime codegen 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少对服务契约视图、统一 Source、生成幂等和 stale/orphan 失败语义的完整直接证据。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

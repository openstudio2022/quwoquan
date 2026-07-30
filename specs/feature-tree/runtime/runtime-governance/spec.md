# L2 Business Capability：运行时治理 (`runtime-governance`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-governance”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`resilience-policy-engine`](./resilience-policy-engine/spec.md)：定义“韧性策略引擎”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime governance 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade

- 提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。
- 治理策略必须由 runtime-config 驱动，禁止硬编码阈值。
- 治理触发与降级行为必须可观测、可审计、可回滚。

<a id="req-003"></a>
### REQ-003 枚举所有权与对象生命周期必须单轨、可编译

- canonical enum owner 按对象级、服务级、全局级形成唯一解析层级；对象级枚举只允许在所属对象 `fields.yaml` 顶层声明，服务级枚举只允许在所属服务 `contracts/_shared/` 声明，全局枚举只允许在 `contracts/metadata/_shared/` 声明。
- 同名枚举不得在重叠层级形成遮蔽，不得在多个对象复制；无引用定义、无 owner 引用、空值域、重复 wire value 均为硬失败。`entities`、`members`、`types`、`value_objects` 内嵌 `enums:` 属于不可消费的第二真相源，必须硬失败。
- App 与 Go 生成器必须消费同一份 canonical contract view；不得另建端侧枚举表、兼容值或默认吞错解析器。
- 声明 `lifecycle.states` 的可变对象必须显式声明 enum 状态字段，枚举值域必须与生命周期状态集合完全相等；append-only fact 必须声明 immutable，且不得伪造状态机。

<a id="req-004"></a>
### REQ-004 字段、错误与事件治理必须 fail-closed

- 通用语义字段使用 canonical 基础类型：时间点为 `timestamp`，版本/单调水位为 `int64`，集合只允许 `[]T`；未知类型、无元素类型集合和非 canonical 集合写法必须在编译期失败，禁止静默生成 `any`。
- 错误定义必须声明 `emitted_by` 发射面；HTTP operation 引用与 HTTP 发射绑定必须双向一致，worker、provider、gateway 等非 HTTP 发射面不得伪装成 route 错误。
- 无消费者事件必须声明可审计的 `no_consumer_reason`，已有消费者时不得保留该理由。
- transactional outbox 没有消费者必须硬失败。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime governance 能力 SIT

- GIVEN 执行“runtime governance 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime governance 能力”对应动作。
- THEN 直属 Story 共同交付“提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade”，失败终态可区分且不产生伪成功事实。

<a id="sit-002"></a>
### SIT-002 枚举与生命周期单轨验收

- GIVEN compiler contract view 中包含对象、服务与全局 enum owner、enum reference、对象 lifecycle 以及 App/Go 生成目标。
- WHEN 元数据装载、治理校验和端云 codegen 执行。
- THEN 每个引用只解析到唯一 owner，合法对象级枚举保持内聚，任何嵌套第二真相源、重叠 owner、跨对象复制、死定义、生命周期值域漂移或端云枚举分叉均硬失败；合法值域在 App 与 Go 产物中完全一致且严格解析未知 wire value。

<a id="sit-003"></a>
### SIT-003 字段、错误与事件 fail-closed 验收

- GIVEN compiler contract view 中包含字段类型、语义类型、错误发射面、operation 引用、事件 channel 与消费者声明。
- WHEN 元数据治理与领域代码生成执行。
- THEN canonical 类型生成强类型代码，未知或弱集合类型不产生 `any`。
- THEN 错误引用与发射面双向可达，无消费者事件具有真实理由，且 outbox 必有消费者。
- THEN 任一约束不满足均导致门禁失败。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime governance 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

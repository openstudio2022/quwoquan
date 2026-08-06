# L2 Business Capability：运行时治理 (`runtime-governance`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-governance”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`resilience-policy-engine`](./resilience-policy-engine/spec.md)：定义“韧性策略引擎”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime governance 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定

- 提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定。
- 入站单 operation 超时预算不由本能力持有：唯一真相源是 operation 契约的 `reliability.timeout_ms`，经生成的入口安全描述符在 guard 层强制。本能力不得复制、覆盖或以配置键替换该数值。
- 本能力不提供下游重试；重试策略骨架已删除，不得重新引入。
- 业务到达速率配额由 api-edge 共享状态独占执行，不属于本能力；本能力只在 owner 侧做并发背压与负载摘除。
- 并发上限必须由所属服务 `config/schema.yaml` 已注册的键驱动（如 `sys.content-service.feed.max_inflight`）；熔断阈值当前是调用点代码常量，改为配置驱动前不得在规格或文档中宣称它可配。
- 治理触发与负载摘除必须可观测、可审计、可回滚。

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
- THEN 直属 Story 共同交付“提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定”，失败终态可区分且不产生伪成功事实。

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 事件 `channel` 字段混装投递机制、topic 名与拼写错误

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前事件契约的 `channel` 没有受控值域，同一字段里混装了投递机制、topic 形态的名字与拼写错误，治理规则无法据此判断一个事件走的是哪条投递语义。
- 其中一批取值把事务性发件箱写成缺前缀的简写，另一批直接写成 topic 名字，还有少数事件根本没有这个键。
- 关闭方式是拆成受控的投递语义字段与独立的 topic 字段，让投递机制与 topic 名各自拥有唯一表达。
- 连带效应必须一并处理：治理校验当前用子串匹配判断是否为发件箱，这恰好掩盖了上述简写使其行为等同正确值，因此必须先拆字段再改精确匹配，否则单独改精确匹配会净放宽既有约束。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 本能力描述的治理实现归 gateway L1，与本节点所在 L1 不一致

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前本能力描述的治理装置实现位于 `quwoquan_service/runtime/governance`，该路径的代码归属是 gateway L1，而本节点连同其唯一 Story 位于 runtime L1，描述与代码归属分处两个 L1。
- 归属本身没有歧义：gateway L1 的工程归属把 `quwoquan_service/runtime` 列为 Service 代码归属，runtime L1 把同一路径显式标注为协作引用且不用于代码归属，所以不一致只发生在规格节点的落点上。
- 后果是双向反查断裂，从治理代码反查规格会落到 gateway L1 的节点集合，而治理行为要求写在 runtime L1，两侧无法互相定位。
- 本 OPEN 只如实记录该错配，不触发结构重划。
- 在落点被裁定前不得把本能力或其 Story 移到 gateway L1，也不得把 `quwoquan_service/runtime/governance` 改写进 runtime L1 的代码归属，任一单侧改动都会制造第二个归属声明。
- 完成判定：治理能力的规格落点与 `quwoquan_service/runtime/governance` 的代码归属指向同一个 L1，或两者分离被一条 DEC 显式接受并写明反查路径。

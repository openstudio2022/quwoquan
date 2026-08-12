# L2 Design：运行时测试基础设施 (`runtime-testinfra`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：三层测试需要同时解决真实执行证据、环境数据最小准备、跨用例隔离与可比较性能，且不能建立测试清单或第二套业务模型。

## 1. 背景、目标与非目标

- 设计目标：以 canonical 目录发现测试，以强类型请求图准备最小隔离数据，并从真实执行、回读和清理生成可比较证据。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`test-execution-and-evidence`](./test-execution-and-evidence/spec.md)：发现并执行 canonical 测试，分离结构入口与运行结果。
- [`test-data-provisioning-and-isolation`](./test-data-provisioning-and-isolation/spec.md)：以强类型请求图按需准备、回读和清理隔离数据。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 Runner 扫描 canonical 目录并从执行结果生成报告
- 决策：Runner 扫描 canonical 目录并从执行结果生成报告。
- 理由：以物理目录扫描和运行报告提供三层测试证据，不维护路径登记或目录清单。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`test-execution-and-evidence`](./test-execution-and-evidence/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 Capability contract 强类型公开且 Provider 按领域自治

- 决策：通用层只定义强类型 capability 引用、请求、输出引用与已准备结果；每个领域公开 frozen 参数/结果与 capability 常量，内部稳定 key 只用于跨进程序列化和回执。
- 决策：测试只能导入 capability contract 与统一 Session；Provider 实现独立按所属服务发现，只调用本服务公开 operation，不导入兄弟 Provider。跨领域 Journey 由请求之间的强类型依赖组合。
- 理由：领域 contract 让参数重命名、结果变化和错误依赖在 mutation 前失败，同时避免字符串 DSL、中央 registry 和控制面复制业务 payload。
- 被否决方案：测试直接书写 capability ID/裸字典、YAML registry、通用表达式语言、独立代码生成平台、跨领域大 Provider 或测试专用业务 API。
- 约束与影响：不为每个标量创建 Value Object。canonical 对象统一引用已有业务对象身份，只有多字段输出才定义结果类型。
- 关联要求：`REQ-003`
- 影响 Story：[`test-data-provisioning-and-isolation`](./test-data-provisioning-and-isolation/spec.md) 的强类型公开边界。
- 关联验收：`SIT-002`

<a id="dec-003"></a>
### DEC-003 Immutable reference 复用而 mutable case-run 严格隔离

- 决策：Content、Creator、Entity 与已发布 Media 通过候选绑定的 immutable release handle 只读复用；账号、Persona、关系、评论、圈子、会话、消息与外部 sandbox 交易按 CaseResult 尝试创建。
- 决策：Actor 集只包含认证账号、Persona 与会话；租约以 generation fencing、TTL 和续约防止并发复用。可变业务对象不属于 Actor 集，也不得跨 case 共享。
- 决策：每次准备生成数据实例、请求和追加式回执身份；同一实例幂等重试，新尝试生成新实例。cleanup 不确定时进入隔离，不合成 released。
- 决策：`local_contract` 只以语言内 typed builder/generator 暴露对象级 contract example，不再构造带环境 Repository、整包数据集合或 reset 标志的场景文档。benchmark/eval corpus 是 manifest/digest 绑定的独立只读制品，执行策略与可变状态生命周期仍由 runner 和领域 capability 拥有。
- `capabilityDefinitionDigest` 标识 capability 定义及其公开 operation 闭包。`candidateBindingDigest` 标识 environment、target、package、config、release 与 import run 的组合。
- `testDataInstanceId` 标识本次实际准备实例，`requestDigest` 标识序列化后的强类型请求图，`receiptDigest` 标识一条 create-once 回执。旧配方摘要与数据集周期字段不属于测试数据身份，也不得在 active schema 中恢复。
- `AcceptanceActorSet` 只包含账号、Persona 和运行时认证会话。`ActorLease` 是该 Actor 集在一个 CaseResult 尝试内的独占使用记录，默认 TTL 30 分钟、最大两小时，并按 TTL/3 续约；状态固定为 `requested → acquiring → active → releasing → released`，清理结果不确定时转为 `quarantined`。`generation` 是 fencing token，旧 generation 不能继续 mutation、续约或释放。
- 理由：候选内只读复用降低重复工作；可变事实按 case 隔离可阻止顺序依赖、并发污染和失败清理后的伪绿。
- 被否决方案：复制 Prod 数据库、共享账号池承载可变事实、固定对象 ID、DB seed、投影预填、跨 case cleanup receipt 复用。
- 约束与影响：Prod 在首条 mutation 前拒绝；测试数据代码和运行资产不进入生产/App/Service package。
- 关联要求：`REQ-003`
- 影响 Story：[`test-data-provisioning-and-isolation`](./test-data-provisioning-and-isolation/spec.md) 的租约与实例隔离。
- 关联验收：`SIT-002`

<a id="dec-004"></a>
### DEC-004 Runner 只执行选中请求的 DAG 关键路径

- 决策：Runner 从真实 test selection 收集根请求；不同 CaseResult 以独立实例并行执行，控制面动态求依赖闭包、按需发现 Provider，并以共享的全局/Provider/capability 并发预算执行独立节点，cleanup 按逆依赖图执行。同一 ActorLease 的 mutation 始终串行。
- 决策：integration runner 在测试现场组合具体强类型 case factory；release runner 通过 `stackctl test-data-request` 导出七领域 canonical Journey composition。该 composition 是一个受规格约束的发布入口，不提供字符串 lookup，也不构成 capability registry 或测试 inventory。
- 决策：领域 capability 对外部 Provider 的依赖使用 `ProviderCapabilityKey` 强类型引用；`stackctl test-data-evidence` 从当前 Provider conformance readiness 只投影选中请求的精确依赖闭包，并绑定 candidate 与 request digest。稳定字符串只存在于序列化和长期证据中。
- 决策：`CapabilityRef.bind` 的进程内请求身份只负责对象图隔离，不作为长期证据身份；序列化器按选中 case 顺序与依赖遍历生成确定性 wire request ID，使同一 composition 的文档和 `requestDigest` 字节幂等，实际 mutation 仍由新的 `testDataInstanceId` 隔离。
- 决策：环境测试数据引用当前候选绑定的 immutable release，其 lifecycle 可为 `research` 或 `commercial`；控制面必须从 canonical readiness receipt 的显式 `readinessPhase` 选择对应严格验证器，不得按环境猜测，也不得把 Research 冒充 Commercial。
- 决策：只缓存 ContractGraph、capability definition、immutable release、Provider conformance 和 candidate binding 等只读事实；不缓存跨 case mutable object。
- 决策：报告分段记录环境、静态门、请求收集、发现、规划、Actor 准备、provision、readback、测试正文、cleanup、回执与关键路径，并记录 operation 数量和加载 Provider。
- 理由：主要性能成本来自无关 mutation 与全域 Provider 前置条件，而非动态 import；请求图把总时间从固定 recipe 总和收敛为实际依赖关键路径。
- 被否决方案：integration 固定执行全部 recipe、全域 Provider readiness、通过减少断言/回读/cleanup 提速、为测试新增 bulk API、把早退失败时长作为成功基线。
- 约束与影响：默认全局准备并发度为 4，跨 Case 也不得倍增。相同 immutable lookup 使用 single-flight；同租约、同对象和显式依赖保持串行。报告以 suite 实测 `dataPreparationMs` 表达 wall time，不把并行分支耗时相加冒充关键路径。完整回归作为受管任务，不进入 commit gate。
- 关联要求：`REQ-004`
- 影响 Story：[`test-data-provisioning-and-isolation`](./test-data-provisioning-and-isolation/spec.md) 的 DAG 与性能证据。
- 关联验收：`SIT-002`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。

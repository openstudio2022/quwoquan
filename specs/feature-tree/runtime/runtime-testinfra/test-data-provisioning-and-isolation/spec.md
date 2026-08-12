# L3 Story：测试数据准备与隔离 (`test-data-provisioning-and-isolation`)

> 所属能力：[`runtime-testinfra`](../spec.md)

> Journey / Scenario：横切工程能力，不直接拥有 AppRoot Scenario。

> 设计归属：[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为测试作者，我希望用强类型声明当前用例需要的最小领域事实，由控制面按依赖准备、回读和清理，从而让用例只保留业务行为与断言，同时避免巨型 fixture、全域前置条件和跨用例污染。

## 2. 范围与非目标

### In Scope

- 强类型 capability 请求、按需 Provider、Actor 租约、依赖图、隔离、回读、清理、回执和阶段性能证据。

### Out of Scope

- 第二套业务模型、测试专用业务 API、数据库 seed、capability registry、测试 inventory 或通用表达式语言。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 强类型声明与领域自治

- 测试只导入领域 capability contract 与统一 Session；参数、依赖和结果在 mutation 前完成运行时类型验证。
- 每个 capability 只拥有一个服务的公开 operation；跨领域 Journey 由请求图组合，Provider 不导入兄弟 Provider。
- 聚焦 integration 用例在测试现场导入具体强类型 case factory；release profile 只接受 `stackctl test-data-request` 从七领域 canonical Journey composition 导出的完整请求，禁止人工拼接 JSON 或用字符串 case/capability registry 选择。
- capability 的外部 Provider 依赖同样使用强类型 key；环境 runner 只接受 `stackctl test-data-evidence` 对当前 request/candidate 精确投影的 evidence，未选中的 Provider 不进入前置检查。
- 同一强类型 case composition 的跨进程序列化必须字节稳定；进程内随机请求身份不得进入 `requestDigest`，序列化层按 case 与依赖遍历生成稳定节点身份，同时保留每个 CaseResult 的独立数据实例。
- immutable reference release 可以是显式 `research` 或 `commercial`；控制面只按 canonical readiness receipt 声明的生命周期调用对应严格验证器，禁止环境推断与生命周期升级。
- `local_contract` 对象示例由测试语言内的 typed builder/generator 直接构造；不得在代码或结构化资产中重建场景数据源选择、整包数据集合或重置策略。独立 benchmark/eval corpus 只保存 manifest/digest 绑定的评测输入与期望，不拥有环境 Repository、Actor 或可变状态生命周期。

<a id="req-002"></a>
### REQ-002 最小准备、隔离与确定性清理

- 控制面只加载选中请求的依赖闭包；不可变引用可候选内复用，可变 Actor 与交易事实按 CaseResult 尝试隔离。
- 同一数据实例重试保持幂等，新尝试使用新实例；清理按依赖逆序执行，不确定结果进入隔离并阻断。

<a id="req-003"></a>
### REQ-003 性能证据不以降低质量换取

- 数据准备、测试正文和清理分别计时，并记录 operation 数量、Provider 闭包、并发度和关键路径。
- 多个独立 CaseResult 可并行，但必须共享全局并发预算；suite wall time 使用实测 `dataPreparationMs`，分支耗时只作为 work metric。
- 性能提升不得通过减少 CaseResult、业务断言、真实 Provider、回读或清理获得；前置失败 run 不进入基线。
- 仅完成 provision/readback/cleanup、但同一 scope 内没有通过的业务 CaseResult 时，内部 run-summary 状态必须为 `prepared` 且 `baselineEligible=false`；不得把准备成功冒充测试绿色。

## 4. 契约引用

- 领域 operation、wire 与错误：所属服务 `contracts/**`。
- 跨服务公共值：`quwoquan_service/contracts/metadata/**`。
- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 单领域请求只产生最小依赖闭包

- GIVEN 一个只依赖 Chat 与 User Actor 的选中用例。
- WHEN Runner 准备并回收其强类型请求图。
- THEN 只加载 User 与 Chat Provider，只执行声明的公开 operation；Assistant、Notification、RTC 及其他无关 Provider 不导入、不检查、不清理。
- AND 用例获得强类型结果与完整回执，不接触固定业务 ID、wire path、operation ID 或 cleanup 细节。
- AND integration 可只选择当前用例；release 必须执行七领域 canonical 关键 Journey，不把任意 focused 子集伪装为 release 准出。
- AND Provider evidence 只包含当前请求依赖闭包并绑定 request/candidate digest；测试代码不书写 Provider capability 字符串。

<a id="gwt-002"></a>
### GWT-002 可变事实隔离且失败可恢复

- GIVEN Alpha、Beta 或 Gamma 的候选、真实非生产身份与所需 Provider 有效。
- WHEN 同一实例重试、创建新 CaseResult，或 cleanup 出现不确定结果。
- THEN 同一实例不重复创建，新 CaseResult 获得新 Actor 与交易事实；不确定对象进入隔离并阻断后续复用。
- AND Prod 在首条 mutation 前拒绝，且制品中不存在测试数据实现或运行资产。

## 6. 依赖

- 前置要求：[`runtime-testinfra`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 design](../design.md)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 当前候选的环境与性能准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Alpha/Beta/Gamma 当前候选的完整绿色 `qwq.case_result`、Prod 首条测试 mutation 前拒绝回执，以及同候选五次绿色性能样本。源码侧强类型请求、CaseResult 生命周期、并行与限流、失败清理、七领域 Provider 依赖闭包和历史分支退役已经由本地门禁证明，但不能替代真实环境准出。
- 完成判定：测试数据架构门零问题，`GWT-001` 与 `GWT-002` 由真实三层测试和 Alpha/Beta/Gamma 当前候选回执共同证明，Prod 只读边界回执通过，旧执行分支与双轨引用为零，并且五次绿色运行的数据准备 median 相比旧受控基线至少下降 50%、总验证 median 至少下降 30%。

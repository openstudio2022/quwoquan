# L2 Business Capability：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

可复用实体主页与多载体内容供给、发布和环境消费闭环。

## 2. 范围与非目标

### In Scope

- family、provider policy、reference 与 execution request 的职责隔离。
- entity homepage、article、image、video 的五阶段生产、review、canonical publish 与 release。
- immutable release 的环境导入、API 验证、App 消费、rollback 与 replay 证据。

### Out of Scope

- 任何特定区域、实体、目标数量或活动阶段的运行计划。

## 3. Journey / Scenario 贡献

- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：可复用实体主页与多载体内容供给、发布和环境消费闭环。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 可复用内容 execution 与发布 SIT

- 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- homepage/article/image/video 的 quota/count 只表达请求负载与 `100/100/100/10`、`1000/1000/1000/100` 里程碑 target；每路至少一个对象闭合对象硬门且所有合格对象均发布即可形成结构性 promotion，shortfall、discard 与比率统计不否决。
- M1000 只能精确绑定同一 release/manifest/source/catalog identity 的 create-once M100 promotion receipt。
- release 只绑定 execution/source digest 与 desired state；环境 receipt、rollback/replay 通过 ship 写入输出。

<a id="req-002"></a>
### REQ-002 `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属

- `reference/<vertical>/entities`：稳定实体、别名、分类与行政归属；不得写来源 URL 或运行结论。
- 静态资产不得包含区域、实体、日期、数量、运行路径或活动阶段；这些值只在 `0.plan` 冻结。
- 每个发布对象必须有 source、媒体处置、creator/tag 引用、review 与 execution source digest。
- 运行 profile、schema、provider policy 或 target set 改变时，必须创建新 sequence，并以 `retryOf` 关联重试。
- 环境导入、API 与 App 消费未完成时保留对应 `GATE_BLOCK`；静态目录与本地 gate 不得冒充环境交付。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 可复用内容 execution 与发布 SIT

- GIVEN 执行“可复用内容 execution 与发布”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“可复用内容 execution 与发布”对应动作。
- THEN 静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- THEN execution packet 的 request 与 target set 均固化在 `0.plan`，且 output 删除后仍可从受版本控制的静态输入重建。
- THEN 四类载体均能由同一 CLI 门面创建、review、promote 与聚合 release。
- THEN M100 promotion 证明四路真实执行、每路至少一个 hard-qualified 对象全部发布、同源与资源隔离成立；receipt 记录 target/qualified/shortfall 及各 rate 分子分母，但不要求 target 或比率命中。
- THEN M1000 精确绑定该 M100 promotion identity，不以其它 release、计划值或聚合成功替代。
- THEN release 只绑定 execution/source digest 与 desired state；环境 receipt、rollback/replay 通过 ship 写入输出。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 可复用内容 execution 与发布 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：静态 family、provider、schema、prompt/template 与 reference 不含运行实例值。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

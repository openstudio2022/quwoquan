# L3 Story：契约驱动压测与性能证据 (`performance-load-harness`)

> 所属能力：[`runtime-testinfra`](../spec.md)

> Journey / Scenario：横切工程能力，不直接拥有 AppRoot Scenario。

> 设计归属：[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为开发、测试或运维角色，我希望按 operation 契约生成受控负载并出具与 SLO 声明对照的性能证据，从而让服务与旅程的延迟劣化在放量前被门禁发现，而不是靠线上告警回溯。

## 2. 范围与非目标

### In Scope

- 契约驱动的负载生成、阶梯并发、p50/p95/p99 与错误率证据。
- `stackctl loadtest` 编排入口、SLO 阈值对照与 pass/fail 判定。
- 性能证据在 `.qwq_output` 的幂等落盘与 CaseResult 关联。

### Out of Scope

- 单个业务对象的具体预算数值（由所属节点 spec 与 operation 契约拥有）。
- Prod 容量规划与放量决策。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 负载只由契约与公开 operation 生成

- 负载生成只消费 generated client 与所属领域公开 operation；禁止裸 HTTP、自造 wire payload 或测试专用 bulk API。
- 压测数据前置只经强类型 capability request 准备；Prod 在首条压测 mutation 前拒绝。
- 负载画像（并发阶梯、持续时长、目标 operation 集）是显式声明的输入，同一画像对同一候选可重复执行。

<a id="req-002"></a>
### REQ-002 性能证据与 SLO 对照且幂等可重建

- 每次执行产出 p50/p95/p99 延迟、错误率与吞吐证据，写入 `.qwq_output`，删除后可凭同一候选与画像重建。
- 证据必须与 operation 契约 `slo.*` 声明或 `slo_thresholds` 阈值对照，输出可区分的 pass/fail 判定；无阈值声明的 operation 不得输出伪判定。
- benchmark-only policy 的结果只作性能取证，不得计入环境正式绿色回执。
- 前置失败或提前退出的 run 与完整 run 分开表达，不进入性能基线。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 契约驱动压测出具 SLO 对照证据

- GIVEN alpha/beta/gamma 候选环境健康，目标 operation 具有有效 `slo.*` 或阈值声明。
- WHEN 参与者以显式负载画像执行 `stackctl loadtest`。
- THEN 产出 p50/p95/p99、错误率与吞吐证据并与阈值对照给出 pass/fail，证据可从 `.qwq_output` 幂等重建。
- AND 超阈值时判定为失败且不写入伪成功事实；Prod 目标在首条压测 mutation 前被拒绝。

## 6. 依赖

- 前置要求：[`runtime-testinfra`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-005](../design.md#dec-005)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 压测 harness 实现与首批 SLO 对照证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma release 候选上的正式取证、鉴权态与参数化 path
  operation 的覆盖扩展，以及把压测证据纳入发布准出的接线。loadgen 执行器、
  `stackctl loadtest` 编排与首批真实环境证据已落地——alpha-local 上
  GetFeed/GetAppConfig/ListCircles/SearchHomepages 四个公开只读 operation
  的 p95 与可用率全部通过契约 SLO 对照，证据于
  `.qwq_output/env/alpha/runs/*-loadtest-alpha-local/`。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

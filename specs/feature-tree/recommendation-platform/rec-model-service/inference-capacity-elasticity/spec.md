# L3 Story：推理容量弹性 (`inference-capacity-elasticity`)

> 所属能力：[`recommendation-service`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “推理容量弹性”的输入、可观察主路径、失败语义以及与父能力的交接。
- 多进程水平扩容与单进程 GIL 解除。
- 打分/特征缓存与跨请求 micro-batch。
- 超时预算分层与 guardrails 口径统一。
- 不引入深度模型平台轨的服务拆分或 ANN 检索；P1 仅完成当前 recommendation-service 的容量工程最小集。
- 深度模型平台轨。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 推理容量弹性

- guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐。

<a id="req-002"></a>
### REQ-002 guardrails 口径统一：policy.yaml guardrails suggest_only 与 online_guardrail.py 自动切流口径对齐

- guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 推理容量弹性

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“推理容量弹性”对应的公开行为。
- THEN guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`recommendation-service`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 推理容量弹性 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“推理容量弹性”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

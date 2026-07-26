# L2 Business Capability：推荐模型服务 (`rec-model-service`)

> 所属领域：[`recommendation-platform`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

按 scenario 装载已晋升模型，并通过统一推理接口向 Go 业务服务提供有版本、可降级且可观测的候选打分结果。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“recommendation-service（模型服务）”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-026`](../../spec.md#scn-026)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`go-integration`](./go-integration/spec.md)：**兜底**：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用。
- [`inference-api`](./inference-api/spec.md)：通过 POST /score 接收场景、主体、特征和候选，返回逐候选分数与可解释明细。
- [`inference-capacity-elasticity`](./inference-capacity-elasticity/spec.md)：guardrails 口径统一：`policy.yaml` guardrails `suggest_only` 与 `online_guardrail.py` 自动切流口径对齐。
- [`inference-deployment`](./inference-deployment/spec.md)：从 ModelRegistry 或 OSS 加载 production 模型，通过健康检查后提供推理服务并支持回滚。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 rec model service 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力”所定义的业务结果；失败终态必须可区分且不得伪造成功。
- recommendation-service 商用并发容量与实时性（多 worker、缓存、合批、超时预算分层、guardrails 口径统一）有规格与容量 SLI。

<a id="req-002"></a>
### REQ-002 定位：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力

- **定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
- 模型服务不可用时 Go 侧 CascadeScorer 回退。

## 6. 契约与依赖

- 上游能力：[`recommendation-platform`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 rec model service 能力 SIT

- GIVEN 执行“rec model service 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“rec model service 能力”对应动作。
- THEN 直属 Story 共同交付“**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力”，失败终态可区分且不产生伪成功事实。
- THEN recommendation-service 商用并发容量与实时性（多 worker、缓存、合批、超时预算分层、guardrails 口径统一）有规格与容量 SLI。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 rec model service 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

# L3 Story：go-integration（与 Go 业务服务集成） (`go-integration`)

> 所属能力：[`recommendation-service`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “go-integration（与 Go 业务服务集成）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 go-integration（与 Go 业务服务集成）

- **兜底**：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用。

<a id="req-002"></a>
### REQ-002 兜底：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用

- **兜底**：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用。
- 模型服务不可用时 CascadeScorer 回退，请求不失败。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 go-integration（与 Go 业务服务集成）

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“go-integration（与 Go 业务服务集成）”对应的公开行为。
- THEN **兜底**：CascadeScorer 在模型服务不可用或超时时回退到 RuleScorer；content-service 通过配置启用/禁用模型调用。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`recommendation-service`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 go-integration（与 Go 业务服务集成） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“go-integration（与 Go 业务服务集成）”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 prod 环境的模型服务上游地址缺注入轨

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：content-service 的 `prod` 配置快照把 `sys.content-service.rec_model_service.url` 写成未展开字面量 `${REC_MODEL_SERVICE_URL}`，而仓库内没有任何 prod 注入点提供该 env；`rec_model_service.enabled` 在 schema 默认为 `true`，Go 侧「url 为空则不装配」的判据对非空字面量不成立。结果是 prod 会以该字面量为 base URL 装配模型客户端，每次打分调用都失败后走 CascadeScorer 回退——回退路径本身符合 REQ-002，但失败被表达为无效 URL 而非「模型服务未部署」，容量与降级 SLI 因此把一个配置缺陷长期计入模型服务不可用率。`gamma` 指向 `http://recommendation-service:8000`，`prod` 平面的第一方服务集合（`quwoquan_ops/cli/prod/render_prod_plane_stack_lib/constants.py`）不含 `recommendation-service`，仓库内无法判定 prod 是否部署该服务，因此本项需要部署事实输入才能关闭：若 prod 不部署则应显式 `enabled: false`，若部署则应填真实 origin。content 侧已把该键纳入未展开占位符 fail-closed 校验，prod 启动会在此项关闭前显式失败而不是带着假地址运行。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效，且 `prod` 配置快照中该键为真实 origin 或 `enabled: false`。

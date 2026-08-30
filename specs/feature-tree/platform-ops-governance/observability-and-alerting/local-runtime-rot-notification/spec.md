# L3 Story：本地运行期腐烂主动告知 (`local-runtime-rot-notification`)

> 所属能力：[`observability-and-alerting`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为在本地四环境上开发与验收的工程角色，我希望本地运行时从健康转为降级时由会话主动告知我，而不是等我从 App 界面上看到「无法访问服务」再回头排查，从而把「环境是否可用」从人工偶发发现变成运行期持续可证。

## 2. 范围与非目标

### In Scope

- `dev-session` 运行期对必需容器现况与容量水位的周期性复验。
- 健康到降级的状态跃迁的主动报出与结构化会话回执。

### Out of Scope

- 启动前的一次性判定（由 [L1 REQ-004](../../spec.md#req-004) 与 `stackctl health` / `up` / `package` / App preflight 拥有）。
- 云侧服务的 SLI/SLO 与告警规则（由 [`slo-error-budget-governance`](../slo-error-budget-governance/spec.md) 与 [`log-metric-trace-unification`](../log-metric-trace-unification/spec.md) 拥有）。
- 自动修复与容器重启：本 Story 只负责告知与阻断建议，不代替人做破坏性动作。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 运行期复验必须周期执行且只读

- `dev-session` 持有会话期间必须按声明间隔复验必需容器现况与容量水位，复验只读取 Docker 与文件系统的当前事实，不改变运行时。
- 复验不得依赖启动时刻写下的 receipt 作为当前结论；receipt 只提供被复验对象的身份（target、Compose project）。
- 复验失败本身（无法查询）与观测到降级必须可区分：前者报未观测，不得冒充健康或降级。

<a id="req-002"></a>
### REQ-002 状态跃迁必须主动报出且不重复刷屏

- 状态从健康转为降级或不可用时必须立即报出，内容包含跃迁方向、触发判据（具体容器与状态，或具体 scope 的实测可用量与阈值）与可执行的下一步。
- 同一状态持续期间不重复报出；恢复为健康时同样报出一次，使「已恢复」也是显式事实。
- 报出必须进入会话结构化回执，可在会话结束后回读跃迁序列与时刻。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 判据与 typed blocker：[L1 REQ-004](../../spec.md#req-004) 与 [L1 DOM-003](../../spec.md#dom-003)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 运行期依赖断裂被主动告知

- GIVEN 某 local target 的 `dev-session` 正在持有一个健康的运行时会话。
- WHEN 必需容器在会话期间退出或转为 unhealthy，或宿主/容器存储可用空间跌破声明阈值。
- THEN 会话在下一个复验周期内主动报出健康到降级的跃迁，并给出触发判据与下一步动作。
- AND 该跃迁进入会话结构化回执；同一降级状态持续期间不重复报出，恢复为健康时报出一次恢复事实。

## 6. 依赖

- 前置要求：[`observability-and-alerting`](../spec.md) 的范围、要求与 SIT；[L1 REQ-004](../../spec.md#req-004) 的容器现况复验与容量水位判据。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

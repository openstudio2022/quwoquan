# L3 Story：多环境环境实例隔离 (`multi-environment-instance-isolation`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “多环境环境实例隔离”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多环境环境实例隔离

- beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。

<a id="req-002"></a>
### REQ-002 beta 云侧本地集成栈始终只允许一套，启动新实例前必须先停止旧实例再重启

- beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- 端侧每次启动必须显式绑定 `device-id` 或等价唯一设备选择结果。
- 端侧实例记录只用于诊断与 stop/list，不得演化为服务端多套编排。
- 环境矩阵、业务数据清单与 runbook 明确“端侧可多实例、beta/gamma 服务端单套”的统一口径。
- 开发者一键启动统一入口为 `python3 quwoquan_ops/cli/stackctl.py up --env <env> [--device-id <id>]`。
- `make dev-up ENV=<env> [DEVICE_ID=<id>]` 只是 `stackctl up --env` 的 Makefile 薄包装，不得演化出第二套启动逻辑。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多环境环境实例隔离

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“多环境环境实例隔离”对应的公开行为。
- THEN beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多环境环境实例隔离 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“多环境环境实例隔离”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

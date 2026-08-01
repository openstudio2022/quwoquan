# L3 Story：工具执行预算与失败恢复 (`tool-fabric-runtime`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为等待小趣回答的用户，我希望工具调用有明确的时限与重试上限，工具异常时得到说明了信息边界的结果，而不是长时间空转或一段看不出缺了什么的回答。

## 2. 范围与非目标

### In Scope

- 工具执行的时限、重试与循环检测
- 工具失败的恢复动作与用户可见边界
- 策略允许工具集合与运行时注册表的一致性
- 端侧动作的显式确认、平台能力降级与 continuation

### Out of Scope

- 具体工具的业务实现与外部供应商选择
- 用户可订阅的第三方工具市场
- 具体平台日历、提醒或系统能力的产品实现选择

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 工具执行遵守元数据声明的预算

- 工具执行必须遵守工具元数据声明的超时、最大尝试次数与重试间隔。
- 命中循环检测窗口的重复调用必须被拒绝，不得继续消耗该次运行的工具预算。
- 单轮工具调用次数上限必须来自技能清单或策略发布，不得固定在代码内。

<a id="req-002"></a>
### REQ-002 工具失败按恢复策略产生可观察终态

- 工具失败必须按元数据声明的恢复动作决定中止该次运行或带信息边界继续。
- 带边界继续时必须向用户说明缺失的信息范围，不得以空结果冒充成功。
- 工具失败不得写入成功的工具观察事实。

<a id="req-003"></a>
### REQ-003 策略允许的工具必须真实可用

- 技能清单与策略发布声明的允许工具集合必须是装配目录已注册工具的子集。
- 技能清单声明未注册工具时必须在清单加载环节阻断，不得等到运行期才失败。
- 已发布策略声明未注册工具时必须在该次运行的策略入口阻断，不得把未注册工具名交给工具准入判断。
- 空允许集合表示该策略不开放工具，不得被理解为开放全部工具。

<a id="req-004"></a>
### REQ-004 端侧动作必须显式确认且不得伪成功

- 变更设备状态的工具必须声明 `placement=device_action`、`readOnly=false` 与 `requiresConfirmation=true`。
- AgentLoop 必须停在等待确认状态；只有用户批准且平台 capability 可用、原生执行成功后才能通过 continuation 恢复同一 Run。
- 用户拒绝、权限拒绝、平台不可用或原生失败时不得写入成功结果，重复 continuation 不得重复外部副作用。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_tool_metadata/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/tool_use/schema.yaml`
- error / recovery：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/errors.yaml`
- operation：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_policy_release/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 工具超时按恢复策略产生可解释终态

- GIVEN 某工具元数据声明了超时时间、最大尝试次数与恢复动作
- WHEN 该工具在该次运行中持续超时
- THEN 执行在声明的时限与尝试次数内停止，不继续重试
- THEN 按恢复动作中止该次运行或返回说明了信息边界的回答
- THEN 不写入成功的工具观察事实

<a id="gwt-002"></a>
### GWT-002 声明未注册工具时在进入运行前被阻断

- GIVEN 某技能清单或某份已发布策略的允许工具集合包含装配目录里不存在的工具
- WHEN 加载技能清单或以该策略开始一次运行
- THEN 加载或该次运行被阻断并指出不存在的工具名
- THEN 未注册工具名不会进入工具准入判断
- THEN 允许工具集合全部在目录内时该次运行照常执行工具

<a id="gwt-003"></a>
### GWT-003 日历提醒只在显式确认后执行

- GIVEN Skill 提议创建系统日历提醒，且该动作被 Tool Catalog 声明为需要确认的端侧动作。
- WHEN AgentLoop 产生动作提案。
- THEN Run 停在等待确认状态，确认前不会合成成功结果。
- AND 用户批准时 App 先检查平台 capability 并调用原生桥，成功后以同一 continuation 恢复 Run。
- AND 拒绝、权限拒绝、平台不可用或原生失败均不得伪造成功，重复请求最多产生一次系统日历副作用。

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：工具元数据声明与组合根显式绑定的真实工具适配器。
- 下游结果：本 Story 声明的 GWT 可观察结果，供编排与聚合裁决消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

### OPEN-001 设备动作真机权限与重启验收收据尚未闭环

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Android instrumentation 与 iOS XCTest 已覆盖原生参数校验、边界收敛、系统日历写入、readback 和同一 `idempotencyKey` 重放不重复写入；服务端 local contract 已覆盖确认前停机、缺回执拒绝、回执续接和重复 command 不重复记录。尚缺 Android/iPhone 受管真机上的权限拒绝、重复点击、App 重启恢复和端云同一 Remote 候选收据。
- 完成判定：在 Android/iPhone 受管真机对同一 Remote 候选执行批准、用户拒绝、权限拒绝、平台不可用、原生失败、重复点击与 App 重启恢复场景；系统日历 readback 证明每个 `idempotencyKey` 最多产生一个副作用，失败场景不出现 `device_action_completed`。

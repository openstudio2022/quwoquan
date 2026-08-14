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
- 端侧动作的显式确认、平台能力降级与独立执行回执

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
- AgentLoop 必须停在等待确认状态；`ApproveTool` 只提交批准或拒绝，批准设备动作只签发短期 `DeviceActionPermit`，不代表原生执行成功。
- App 仅在 permit 的 target、expiry、capability、device 与 input digest 全部匹配时调用 Device bridge，并通过独立回执 command 恢复同一 Run；拒绝、权限拒绝、平台不可用、原生失败或重放均不得伪造成功或重复外部副作用。

<a id="req-005"></a>
### REQ-005 多检索词 fan-out 必须显式、逐项计费且保持结果桶顺序

- Tool metadata 声明的并行输入只能在冻结的来源广度、最大查询数和剩余工具调用预算内执行；每个 subquery 在进入 owner/Provider 前分别占用一次工具调用预算。
- 多 query 结果必须按计划顺序保留独立结果桶，不得把不同 query 的 score 混排，也不得隐藏额外 fan-out。
- 任一预算、输入或执行身份不满足时必须在调用 owner/Provider 前拒绝整个未开始的超额部分，不得把截断或自动 fallback 伪装成完整检索。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_tool_metadata/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/tool_use/schema.yaml`
- error / recovery：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/errors.yaml`
- operation：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/operations.yaml`（`ApproveAssistantToolUse`、`SubmitDeviceActionReceipt`）

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
- AND 用户批准时服务端先签发短期 DeviceActionPermit；App 验证绑定后调用原生桥，再以独立设备回执恢复同一 Run。
- AND 拒绝、权限拒绝、平台不可用或原生失败均不得伪造成功，重复请求最多产生一次系统日历副作用。

<a id="gwt-004"></a>
### GWT-004 多 query 检索逐项占用预算

- GIVEN 一个研究 Tool 收到冻结计划中的多个检索维度且剩余预算有限
- WHEN Tool Fabric 在进入 owner 或 Provider 前核算执行成本
- THEN 实际 subquery 数与工具调用预算消耗、独立结果桶和可审计执行数一致，任何超额分支均在外部调用前被拒绝

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
- 影响或价值：Android instrumentation 与 iOS XCTest 已覆盖原生参数校验、边界收敛、系统日历写入、readback 和同一 `idempotencyKey` 重放不重复写入。
- 已有服务端 local contract 覆盖确认前停机、缺回执拒绝、回执续接和重复 command 不重复记录。
- 尚缺 generated permit verifier、真实 installation/device binding、Assistant 与平台 bridge 的 capability 同源映射，以及把不透明 permit 绑定到 Device bridge canonical input 的 production composition；同时尚缺 Android/iPhone 受管真机上的权限拒绝、重复点击、App 重启恢复和端云同一 Remote 候选收据。
- 完成判定：`GWT-003` 在 Android/iPhone 受管真机对同一 Remote 候选成立——执行批准、用户拒绝、权限拒绝、平台不可用、原生失败、重复点击与 App 重启恢复场景；系统日历 readback 证明每个 `idempotencyKey` 最多产生一个副作用，失败场景不出现 `device_action_completed`。
- 契约翻绿路径（`ApproveAssistantToolUse` 与 `SubmitDeviceActionReceipt` 在 `contracts/assistant/assistant_run/operations.yaml` 的 `commercial.status: blocked`，gap_id `ASSISTANT_ASSISTANT_RUN_COMMERCIAL_EVIDENCE`）：
  1. 已完成：Alpha Remote 候选已启动且 assistant-service 健康（health 29/29 run `20260813T165653249874Z-0a58ee6bf08146aaa9bee55a321a1ba6-health-alpha-local`）；受管 Provider material 已登记。Android emulator device-trust 已安装（run `20260813T165814876821Z-9efef44158ec46f3aca6e5aae7bdb954-device-trust-alpha-local`），不能代替真机。
  2. `tests/api_integration/assistant/assistant_run/assistant_run_control_operations__api_integration_test.go` 中 approve 与 device-action-receipt case 在真实 Mongo 上全量通过，产出执行收据；
  3. Android/iPhone 受管真机 Patrol UAT 对同一 Remote 候选覆盖上述完成判定场景，产出系统日历 readback 收据；
  4. 凭以上三份真实收据把两个 operation 的 `commercial.status` 改为可用并删除 `block_reason`/`gap_id`，同时删除本 OPEN。真机不可得时本 OPEN 保留并注明外部阻断，禁止以模拟器通过或 skip 的 Patrol 充当收据。当前不翻绿。

### OPEN-002 交集读工具运行时绑定未实现

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仍缺绑定后真实环境会话内返回当前用户交集只读投影的 api_integration/Run 收据（依赖 alpha 官方包重新激活窗口）。运行时执行绑定已落地：`intersection.read_mine` 经既有 assistant→content delegated persona client 复用 `ListMyIntersections` 同读面。binding 构造失败时工具留在 `UnavailableCanonicalBindings` 不可用侧，不建 fallback。handler 对 persona 缺失、limit 非法、上游失败一律结构化 fail-closed。策略允许集已放行 `content.intersection.mine.read`。
- 完成判定：绑定后 `GWT-001` 的预算与恢复合同对该工具成立，且真实环境会话内返回当前用户交集只读投影、不拼句的 Run 收据在案。
- 依赖：content-service 交集读面内部授权路径；`intersection-unified-experience` REQ-009。

# L2 Business Capability：用户 Skill 产品与集成平台 (`skill-product-integration-platform`)

> 所属领域：[助手运行与学习闭环](../spec.md)
>
> 设计归属：[`本层 design.md`](./design.md)

## 1. 能力目标

让用户把官方 Skill 当作可理解、可设置、可授权、可主动订阅、可挂载到群聊/圈子并可查看运行活动的产品能力；让平台只靠不可变 package 资产、Domain Reader 和 capability adapter 扩展旅行等垂类。

## 2. 范围与非目标

### In Scope

- Active Skill package 驱动的 Catalog detail、Setting、Consent、Subscription、SurfacePlacement、运行活动与数据删除入口。
- DomainReaderDescriptor、渐进 Context、Connector grant 与 Surface privacy policy 的运行组合。

### Out of Scope

- 用户 Skill Builder、第三方市场、任意代码加载、Connector 凭证存储和业务对象写真相。
- AgentLoop 状态机细节；由 [`world-class-trinity-experience-baseline`](../world-class-trinity-experience-baseline/spec.md) 负责。

## 3. Journey / Scenario 贡献

- [`JNY-009 / SCN-034`](../../spec.md#scn-034)：接收 active package 与主体/surface，输出详情、设置、授权、订阅、Placement 和活动；失败不伪装启用。
- [`JNY-013 / SCN-030`](../../spec.md#scn-030)：为 `travel_companion` 渐进装配 Gathering/GatheringPlan、Chat、Content 与 Public Web 上下文和允许能力。
- [`JNY-013 / SCN-031`](../../spec.md#scn-031)：在主动 Trigger 和共享 surface 中重算 Consent/Placement/Connector 交集并投递安全结果。

## 4. Story

- [`active-skill-package-catalog`](./active-skill-package-catalog/spec.md)：只从 active package 解析目录、路由、上下文、能力、展示和评测资产。
- [`skill-user-lifecycle`](./skill-user-lifecycle/spec.md)：分离用户设置、Consent、主动 Subscription 与运行活动。
- [`shared-surface-skill-placement`](./shared-surface-skill-placement/spec.md)：让一个小趣在群聊/圈子默认使用多个共享安全 Skill，并由管理员维护禁用列表。
- [`domain-reader-connector-grant`](./domain-reader-connector-grant/spec.md)：通过渐进 Reader 和 Connector grant 安全装配站内、公网、设备与外部应用能力。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 SkillPackageRelease 是所有运行资产的唯一生产来源

- Catalog、Router、Context、Prompt、Capability、Trigger、Memory、Presentation 与 Evaluation 必须从 active package digest 解析。
- publisher 可读取源码资产构建 package；生产请求路径不得扫描 Manifest 文件树、巨型 profile assets 或硬编码 built-in catalog。
- Run 启动时冻结 package digest，恢复和回放继续使用该 digest；回滚只改变新 Run 的 active pointer。

<a id="req-002"></a>
### REQ-002 启用、授权、主动投递和共享挂载必须分轨

- `SkillUserSetting` 表达个人 enabled/disabled 与配置，`SkillConsent` 表达数据/动作授权，`SkillSubscription` 表达主动规则，`SkillSurfacePlacement` 表达群/圈共享策略。
- 官方响应式 Skill 默认可用；主动提醒始终需要显式 Subscription。个人停用不改变群内其他成员的共享结果。

<a id="req-003"></a>
### REQ-003 能力求交与撤权必须在安全边界生效

- 有效 Reader/Tool 必须等于 package allowlist、平台策略、surface policy、Consent、Connector grant 与 runtime availability 的交集。
- Consent 或 Connector 被撤销后，下一个 RunItem/Task 安全边界立即失效；不得因为 Run 已冻结 package 而继续使用已撤销能力。

## 6. 契约与依赖

- 上游能力：Skill package publisher、主体/权限、Chat/Circle surface、Integration Connector、各领域公开 Reader。
- 下游能力：AssistantRun routing/context/tool/presentation/evaluation 与 App Skill Center。
- 读取事实：active package、Setting/Consent/Subscription/Placement、Connector capability state、Domain Reader result。
- 写入事实：只由 Assistant 对象 Facade 修改 Assistant-owned facts；Connector/业务写操作走 owner command。
- 一致性要求：用户对象 revision/CAS，active pointer 原子切换，Run digest 冻结，撤权在安全边界重算。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 资产型 Skill 无运行时分支即可发布和使用

- GIVEN 一个只使用既有 Reader、Tool、Trigger 与 Presentation node 的签名官方测试 Skill。
- WHEN publisher stage/activate package，用户查看详情、保存设置、授权并运行，随后回滚 active pointer。
- THEN package 激活后 Catalog/Router/Run/Presentation/Evaluation 可用，Go/Dart/AgentLoop/Renderer 无任何 Skill 专用改动；旧 Run 继续使用旧 digest，新 Run 使用回滚后的 digest。
- AND 未授权、共享 surface、撤权、非法模板或旧客户端均进入明确拒绝/降级终态，不泄露个人数据。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Skill 产品平台 App 与环境闭环尚未完成

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Connector grant、Gamma 同 digest 的 package activation/rollback 收据与群聊/圈子管理面的 Placement 入口挂载。Alpha canonical 已取得官方包空环境自举激活收据（`activatedBy: service:local-managed-bootstrap:alpha-local`，health 29/29 run `20260813T160518410673Z-d38bed3e0945497980753e19bcb051e5-health-alpha-local`）。服务端对象、active/frozen package Catalog/Router/Context/Presentation 和许可交集已经单轨。App Skill Center 已按 Setting、Consent、Subscription 分轨消费，技能启用状态只读 `SkillUserSetting`。
- 完成判定：`SIT-001` 具有 SkillPackage/UserSetting/Consent/Subscription/Placement 端到端 api_integration 与 App Skill Center user_acceptance 直接 `spec_ref`；同一 package digest 取得 Alpha/Gamma activate/readback/rollback 收据。UserSetting/Consent/Subscription/Placement 的 App local_contract 与「不把 Subscription/Consent 当启用状态」已由 `quwoquan_app/test/local_contract/service/assistant_service/assistant/` 下测试承载。
- 依赖：Assistant contracts/codegen、Integration Connector、Chat/Circle placement event 与 Flutter Skill Center。

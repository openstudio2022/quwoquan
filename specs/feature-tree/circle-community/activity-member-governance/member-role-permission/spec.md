# L3 Story：成员角色权限 (`member-role-permission`)

> 所属能力：[`activity-member-governance`](../spec.md)

> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为圈子成员或圈子运营者，
我希望按加入策略申请、加入或退出圈子，并让 owner、admin 与 member 权限在失败回滚后仍一致，
从而在明确权限下参与和治理圈子。

## 2. 范围与非目标

### In Scope

- “成员角色权限”的输入、可观察主路径、失败语义以及与父能力的交接。
- CircleMembership 生命周期（pending/active/left/removed）与 joinPolicy=approval 的圈子级审批命令。
- owner/admin 审批队列的页面承载与申请者 pending 态反馈。
- 角色（owner/admin/member/visitor）与页面操作权限（编辑/管理/审批入口仅 owner/admin）
- CircleGroupMembership 群单元级审批（circle-collaboration-tools 承载）
- 通知投递通道实现（notification 域承载，本 story 只验证事件发布）

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 成员角色权限

- 加入与退出可先反馈进行中状态；失败时必须回滚展示，成功时必须以服务端成员事实收敛。

<a id="req-002"></a>
### REQ-002 open 圈子加入即 active 且游客走登录续接

- 加入与退出可先反馈进行中状态；失败时必须回滚展示，成功时必须以服务端成员事实收敛。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 成员角色、审批与退出状态机

- 系统必须圈子成员角色与权限治理：加入（open/approval 双策略）、圈子级审批、角色变更与退出的对象状态机及页面承载，且失败时不得写入成功事实。
- approval 策略圈子的加入意图必须落为 pending 成员事实，等待审批后才收敛为 active；审批通过与拒绝都以服务端成员事实为准。
- 待审批队列的读取与审批、拒绝命令只对圈主或 active admin 开放；其他调用方必须收到 canonical 权限拒绝，且不得产生成员状态变化。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 成员角色权限

- GIVEN 圈子成员或圈子运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“成员角色权限”对应的公开行为。
- THEN 界面立即反馈进行中状态；失败时恢复原成员状态，成功时以服务端成员事实收敛。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 open 圈子加入即 active 且游客走登录续接

- GIVEN 用户访问采用 open 策略的圈子。
- WHEN 登录用户加入或退出，或游客触发加入。
- THEN 登录用户的状态收敛为 active 或恢复原状，游客完成登录后只续接一次原加入动作。

<a id="gwt-003"></a>
### GWT-003 成员 Remote API 身份隔离与幂等收敛

- GIVEN 两个不同的已认证 actor 通过 generated client 与 production Remote 访问同一 Circle，且该 Circle 的加入策略允许当前动作。
- WHEN 两个 actor 分别执行加入、同幂等身份重放加入、读取成员事实与退出。
- THEN 每个 actor 只改变并读取自己的 canonical CircleMembership，重放不新增成员或重复推进版本，退出后状态按服务端事实收敛。
- AND actor 缺失、身份错配、环境配置缺失或依赖不可达时 fail closed，不共享测试身份、不直写存储且不返回伪成功成员状态。

<a id="gwt-004"></a>
### GWT-004 审批页按 actor、版本与幂等事实收敛

- GIVEN approval 策略圈子已有 pending CircleMembership，圈主或 active admin 与普通成员使用彼此独立的认证身份通过 production Remote 打开审批页。
- WHEN 授权 actor 分页读取待审批队列并通过或拒绝申请，同时发生同一意图重放、另一管理员并发处理或普通成员尝试读取与审批。
- THEN 只有授权 actor 可见并改变 pending 事实；成功与重放按 canonical CircleMembership version 收敛为唯一 active 或 rejected 结果，active memberCount 至多增加一次，页面以刷新后的 Remote 队列为准。
- AND 越权、版本冲突、已处理申请或依赖失败返回 canonical failure，普通成员看不到申请数据，页面保留或刷新真实队列且不删除未确认行、不产生伪成功成员状态。

## 6. 依赖

- 前置要求：[`activity-member-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 成员角色权限结果子句尚未逐条绑定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001` 两条结果子句的逐条证据，且两条绑定测试均无失败路径断言，t2 的 canonical failure 语义没有证据支撑。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 open 圈子加入即 active 且游客走登录续接

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：加入/退出乐观更新 + 失败回滚 + 行为事实链路在 local_contract 有断言。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 圈子审批页 production Remote UAT 尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺验收证据：真实 owner/admin/member 身份、并发处理、幂等重放与失败恢复的同一候选页面结果；现有 typed Remote 边界不能替代该结果。
- 完成判定：`GWT-004` 由 production Remote user_acceptance 直接绑定，并取得 Android 与 iPhone physical ResultBundle；缺少独立 actor、真实版本冲突或 Remote readback 时保持 BLOCK。

# L3 Story：Persona 管理 (`persona-management`)

> 所属能力：[`persona-follow-graph`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理 Persona 的用户，我希望在分身管理台创建、切换和安全退役分身，并看到配额、不可退役原因和同步建议；产品统一使用“用户 / 分身 / 主分身 / 用户号 / 用户ID”语义，从而安全维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- 分身列表、quota 与 active persona context 同源读取
- 分身编辑 canonical Persona 合同允许的显示资料与隔离设置后的管理摘要回显；userHandle 为系统分配的只读用户号，不参与编辑或同步覆盖
- profile sync suggestion 的出现、应用与 appliedCount 闭环
- 当前分身切换后 activeContext 与页面 current 标识对齐
- 管理摘要与 active persona context 显式下发 avatarUrl/avatarVersion，供端侧头像缓存失效消费
- lifecycle guard 对 primary / active / last / retired persona 的决策
- 所有非阻断 persona 统一 retire，不以跨域归因历史决定生命周期命令
- retire 后状态、retiredAt 与 isActive 落库一致
- retired persona 不可再 activate 或 update

### Out of Scope

- 分身头像图片挑选/上传入口与对象存储端到端
- 分身删除/退役的复杂守卫策略（单独归属 `persona-management--persona-lifecycle-contract`）
- 分身管理列表的一般编辑与同步建议（归属 `persona-management`）
- 合规物理清除与数据主体删除流程

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分身管理摘要、编辑同步与当前分身切换一致

- user-service 必须以同一 Persona 身份完成摘要读取、资料更新、同步建议与激活。
- App 必须以服务端 Persona 事实驱动管理页，切换成功前不得提前改变下游主体。
- 用户可在管理页编辑 Persona、查看同步建议并切换当前 Persona。

<a id="req-002"></a>
### REQ-002 分身管理首屏失败只保留宿主返回与恢复动作

- 首屏加载失败时只保留宿主返回动作与明确的重试入口，不展示半成品 Persona 数据。

<a id="req-003"></a>
### REQ-003 需要审计用户与分身映射、但又不能把该映射暴露给外部用户的平台治理团队

- 需要审计用户与分身映射、但又不能把该映射暴露给外部用户的平台治理团队。
- 切换必须是强一致操作，不允许出现前端已切换、下游主体仍旧是旧分身的中间态。
- 切换失败时，UI 必须明确展示“仍停留在原分身”，不允许出现假成功。
- 退役后禁止继续作为新动作主体，保留记录归因、审计链和 canonical identity。
- 主分身不可退役。
- 最后一个可用分身不可退役。
- 正在激活的分身若执行退役，必须先切换到其他可用分身。
- 用户可在管理台中看到当前配额占用、不可退役原因、同步建议和恢复建议。
- 管理台可以看到 `userId -> persona` 映射；普通读接口不可见。
- 退役后不得把记录内容、评论、消息重绑到 `userId` 或其它分身。

<a id="req-004"></a>
### REQ-004 分身生命周期守卫与退役语义稳定

- user-service 必须拒绝退役主 Persona、最后一个可用 Persona 或尚未完成主体切换的当前 Persona。
- 退役前必须二次确认；被阻断时展示原因，已退役 Persona 不得继续发起新动作。

<a id="req-005"></a>
### REQ-005 跨边界字段、operation 与错误语义只引用所属服务 contracts

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-006"></a>
### REQ-006 系统分配不可变身份，用户号只读且分配失败不得串号

- Account 与普通 Persona 身份由服务端按现役 canonical 身份合同安全分配；同名用户、资料变更和分身切换均不改变已发布身份或既有关系，已退役身份不重用，不为了收紧校验重算合法存量身份。
- userHandle 是系统分配的只读公开用户号，不接受客户端设置、编辑或同步覆盖；昵称与用户号都不能作为创建或关注的内部身份。
- 安全随机源失败、时间或编码超出有效域时明确失败，不退回昵称摘要、时间戳或弱随机身份。只有尚未提交且被确认属于本次新身份或系统用户号的唯一性冲突才允许有界重新分配；凭据、配额或幂等冲突不得被吞成随机碰撞。
- 未提交候选不得出现在成功结果或关系输入；持续碰撞超出预算后停止并保留可恢复上下文，不占用额外 Persona 名额、不绑定到已有他人身份。

<a id="req-007"></a>
### REQ-007 创建重放返回本 owner 已提交的真实 Persona

- 创建命令的幂等身份必须绑定已验证 owner 与操作；不同 owner 使用相同命令键或相同输入不共享结果，同 owner 同键不同意图明确冲突，不泄露其他 owner 的 Persona 或回执。
- 同意图重试、并发创建与提交后丢响应均先解析原回执；返回身份必须等于回执指向且归本 owner 的真实持久化 Persona，不能返回另一个尚未提交的新候选。
- Persona 状态、创建回执、对应事件与实际 Persona 名额保持声明的原子提交；重放不增加 Persona、不多占名额、不重发创建事实。无法证明提交结果时明确未决，不显示创建成功或重新随机换身份。

<a id="req-008"></a>
### REQ-008 Account 已建立后的 Persona 创建从稳定步骤恢复

- 注册或身份建立链由 UserAccount 保留可恢复的稳定创建意图、已选身份与步骤结果；它不成为另一套凭据或公开资料真相。
- Account 已提交而 Persona 创建失败、响应丢失或进程重启时，只恢复尚未完成的 Persona 步骤，不重建 Account，不仅凭相同请求再次调用就宣称恢复完成。
- 尚不能判定是否提交时必须先查稳定恢复依据与命令回执，不重分配身份；只有确认未提交并确认自身唯一性碰撞时，才在同一创建意图中更换候选。
- 恢复期间不宣称完整身份已就绪，不默认落回 owner 执行社交动作；恢复成功后管理摘要、激活上下文和后续动作指向同一实际 Persona。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml#PersonaManagementItemView`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml#ActivePersonaContextView`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/object.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/storage.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/object.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/storage.yaml`
- 身份合法值域、创建回执隔离、稳定恢复记录及结果分型由以上 User contracts 拥有；具体编码、安全随机与碰撞裁决见 [L2 DEC-003](../design.md#dec-003)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分身管理摘要、编辑同步与当前分身切换一致

- GIVEN 用户已有主分身与至少一个辅助分身。
- GIVEN user-service 可返回 persona management summary、active persona context 与 profile sync suggestion 所需字段。
- GIVEN App 已进入分身管理页。
- WHEN 用户浏览分身列表与 quota。
- WHEN 用户编辑辅助分身的显示资料与隔离设置等 canonical 合同允许的字段并保存；系统分配的 userHandle 仅供查看，不可编辑或同步覆盖。
- WHEN 用户应用同步建议，或切换当前分身。
- THEN 页面展示 quota、items 与 activeContext，且当前分身标识与 activeContext.personaId 一致。
- THEN 保存后管理摘要回显最新字段，分身停止继承 owner 对应字段。
- THEN 出现 sync suggestion 时，应用后返回 appliedCount 并刷新管理摘要。
- THEN persona item 与 active persona context 中的 avatarUrl/avatarVersion 显式可消费，端侧头像缓存键稳定。

<a id="gwt-002"></a>
### GWT-002 分身管理首屏失败只保留宿主返回与恢复动作

- GIVEN 用户已进入栈内分身管理页。
- GIVEN persona management summary 读取返回结构化失败。
- WHEN 页面渲染错误状态。
- THEN 顶部导航只有一个返回按钮，不出现错误 X 或额外“返回” CTA。
- THEN 标题为分身管理业务语义，原因与恢复动作由 UiErrorSemantic 解析。
- THEN 点击“再试一次”重新读取 summary，不创建假数据。

<a id="gwt-003"></a>
### GWT-003 分身生命周期守卫与退役语义稳定

- GIVEN 用户至少拥有主分身与一个辅助分身。
- GIVEN 辅助分身可能在任意下游域被并发引用。
- WHEN 客户端请求 lifecycle guard、retire、activate 或 update。
- THEN primary persona 被 retire 守卫阻断。
- THEN 非 primary、非 active、非 last、非 retired persona 可直接 retire，命令不查询跨域归因历史。
- THEN metadata、服务端、App 合同与页面均不存在 delete-empty 或物理删除入口。
- THEN retire 成功后 persona 进入 retired 态并禁止再次 activate/update。

<a id="gwt-004"></a>
### GWT-004 身份分配边界、碰撞与只读用户号不能改变归属

- GIVEN 两个同名用户或 Persona，系统可控制分配时钟与安全熵，并能区分新身份唯一性冲突和其他业务冲突。
- WHEN 创建或编辑 Persona，分别遇到非法编码/时间、安全熵失败、有限或持续身份碰撞，以及用户主动提交只读用户号。
- THEN 合法身份符合 canonical 编码并保持原有合法字节，同名不合并身份、改显示资料不改变 Persona 或 Pair；用户号只由系统分配，不被客户端或同步建议覆盖。
- AND 越界时间、不可表示的编码与熵失败停止分配，不采用弱随机或别名替代；仅确认未提交的新身份/系统用户号唯一性冲突可在冻结预算内换用新安全熵，预算耗尽安全失败。
- AND 凭据、配额与幂等冲突保持原 canonical 失败，不被当碰撞重试；数据库唯一性裁决拒绝重复身份，未提交候选不返回成功、不额外占名额、不串到既有用户。

<a id="gwt-005"></a>
### GWT-005 owner 隔离的创建重放返回回执对应真实 Persona

- GIVEN 不同 owner 可使用相同创建键和相同输入，同一 owner 的已提交创建回执指向真实 Persona，而后续尝试可能已分配不同候选。
- WHEN 并发重放、跨 owner 调用或提交后丢响应再恢复，并用原键提交不同意图。
- THEN 同 owner 原意图的成功响应身份、回执身份和实际持久化身份一致，归属经过核验，不返回未落库新候选；名额和创建事件只生效一次。
- AND 跨 owner 同键不串回执、不返回其他 owner 的对象或资料；同 owner 同键不同意图明确冲突，不新增 Persona。
- AND 提交结果未能确认时保留未决与恢复上下文；真实 PG 原子提交与请求链返回共同证明一致，单独的成功状态码或行数不能代替身份一致性断言。

<a id="gwt-006"></a>
### GWT-006 Account 提交后 Persona 失败只恢复未完成步骤

- GIVEN 同一注册或创建意图的 Account 已持久提交，而 Persona 尚未完成或提交结果未知，稳定流程依据仍可读取。
- WHEN Persona 步骤失败、服务重启或响应丢失后重试，并在确认未提交时遇到新身份冲突。
- THEN 恢复解析原流程与回执，只补未完成步骤；不重建 Account，不在结果未知时重选身份，确认自身未提交冲突才在原流程内更新候选。
- AND 恢复成功的管理摘要、激活上下文与下游主体指向同一个正确 owner 的实际 Persona，创建事件及名额没有重复；恢复失败不宣告完整身份可用，不让 owner 代发社交动作。
- AND 本地可控依赖证明步骤规则，真实请求与 PG 故障/重放证明持久恢复，绑定同一候选的 Android 与 iPhone 物理设备重启旅程证明用户回到同一 Persona；任一层未取得证据均不由其他层替代。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-003](../design.md#dec-003)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 身份分配、owner 创建回执与稳定恢复的合同及直接证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：合法身份值域与现役格式描述需校准；安全分配的边界/有界碰撞、跨 owner 回执隔离、创建返回真实身份及 Account 部分提交后的持久恢复尚无满足本规格的完整证据。用户号已按系统分配只读收敛，本节点原编辑验收仍需当前合同与真实测试重新绑定，不能复用旧可编辑前提宣告通过。
- 完成判定：`GWT-001` 的编辑与只读用户号语义及新增 `GWT-004`、`GWT-005`、`GWT-006` 全部结果取得职责匹配的有效 `spec_ref`；local_contract 以独立编码向量、固定熵和时钟覆盖反例，api_integration 证明真实唯一约束、回执/响应/行身份一致、跨 owner 隔离和部分提交恢复，user_acceptance 证明同候选双物理设备重启后仍为正确 Persona。合同、当前生成物与上述证据一致后才可关闭；本规格不声称实现或测试完成。
- 依赖：UserAccount 创建恢复记录与 Persona command receipt 的 canonical owner、存储和错误语义；共享 ID generator 的边界由其现役工程 owner 同步校验，不另建身份生成器。

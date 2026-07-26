# L3 Story：Persona 管理 (`persona-management`)

> 所属能力：[`persona-follow-graph`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理 Persona 的用户，我希望在分身管理台创建、切换和安全退役分身，并看到配额、不可退役原因和同步建议；产品统一使用“用户 / 分身 / 主分身 / 用户号 / 用户ID”语义，从而安全维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- 分身列表、quota 与 active persona context 同源读取
- 分身编辑 displayName/userHandle/phone/email/isolationLevel 后的管理摘要回显
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

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/projections/persona_management_item_wire.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/projections/active_persona_context_wire.yaml`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分身管理摘要、编辑同步与当前分身切换一致

- GIVEN 用户已有主分身与至少一个辅助分身。
- GIVEN user-service 可返回 persona management summary、active persona context 与 profile sync suggestion 所需字段。
- GIVEN App 已进入分身管理页。
- WHEN 用户浏览分身列表与 quota。
- WHEN 用户编辑辅助分身的 userHandle/phone/email 等字段并保存。
- WHEN 用户应用同步建议，或切换当前分身。
- THEN 页面展示 quota、items 与 activeContext，且当前分身标识与 activeContext.subAccountId 一致。
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

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

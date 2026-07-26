# L3 Story：错误权限展示语义 (`error-permission-display-semantics`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为遇到错误或权限限制的用户，
我希望在页面、分身和评论等入口看到同源错误提示与可执行恢复动作，
从而知道发生了什么并能安全继续。

## 2. 范围与非目标

### In Scope

- “错误权限展示语义”的输入、可观察主路径、失败语义以及与父能力的交接。
- 页面级错误按 UiErrorSemantic.presentation 选择载体。
- 跨页面/沉浸入口失败态按 sourceAppearanceMode 保持来源外观。
- 错误组件与宿主页面/模态的导航所有权。
- 整页、区块、刷新、分页和动作失败的分层载体。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。
- 启动或运行时根级不可恢复异常页面；该页面由 `cold-start-performance` 与 `unrecoverable-runtime-recovery` 的业务栈外恢复宿主持有，不复用普通页面错误卡、诊断或重试语义。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 错误权限展示语义

- 统一错误组件、Persona 页、评论区与栈页面必须按相同 canonical error 选择展示层级和恢复动作。

<a id="req-002"></a>
### REQ-002 错误恢复不复制宿主导航

- 错误恢复不得复制或重置宿主导航；恢复成功后返回原页面上下文。

<a id="req-003"></a>
### REQ-003 表单失败按操作锚点单通道呈现

- 表单失败必须在操作锚点单通道呈现，并与共享 `UiErrorSemantic` 使用同一错误分类。

<a id="req-004"></a>
### REQ-004 播放与加载失败提供无歧义恢复或退出路径

- 媒体播放或页面加载失败必须只提供真实可用的重试、替代路径或退出动作。

<a id="req-005"></a>
### REQ-005 AuthGateReason + AuthContinuation 的统一用户语义

- `AuthGateReason` + `AuthContinuation` 的统一用户语义。
- `UiErrorSemantic` 与统一 resolver 契约。
- 视频播放失败的内联覆盖层：可重试时只展示“再试一次”，不可重试时提供非按钮替代路径。
- 整页阻塞、区块阻塞、局部软失败、刷新失败、分页失败必须选择不同载体，不得用同一灰色卡片覆盖所有失败。
- **约束**：必须使用设计系统 token（AppTypography、AppSpacing、AppColors）；文案必须来自 l10n。
- **门禁**：页面不得直接消费裸 `RuntimeFailureKind` 或手写 “加载失败/请先登录/操作失败” 作为最终页态语义。
- 沉浸式或跨页面入口的首屏错误必须保留来源 `sourceAppearanceMode`，错误页不继承错误的深色沉浸上下文。
- 聊天语音发送失败仅 status bar（`chatVoicePendingRetry`），禁止 actionDialog 叠加。
- 表单发送/提交/依赖失败在操作点附近使用 `AppFormErrorCard`，字段校验使用 `AppInlineFieldError`；二者必须复用同一透明圆形感叹号错误行，同一失败不得再叠加 Toast、dialog 或第二段弱提示。
- 错误标题只说明状态；可点恢复动作不在说明或 `user_message` 中重复。可重试播放失败只展示一个“再试一次”CTA，不可重试播放失败不展示伪重试。

<a id="req-006"></a>
### REQ-006 必须完成“error-permission-display-semantics”并获得明确的成功或失败结果，且失败时不得写入成功事实

- 系统必须完成“error-permission-display-semantics”并获得明确的成功或失败结果，且失败时不得写入成功事实。

<a id="req-007"></a>
### REQ-007 列表首屏失败 / 缓存回退失败 / 分页追加失败三类语义必须区分

- 列表首屏失败 / 缓存回退失败 / 分页追加失败三类语义必须区分。

<a id="req-008"></a>
### REQ-008 JIT 麦克风权限 — 无冗余 App modal

- 同一次手势无 2+ App modal。

<a id="req-009"></a>
### REQ-009 语音发送失败 — 单一低打扰载体

- modal 与 status bar 不同时出现。

<a id="req-010"></a>
### REQ-010 权限说明与继续动作一致

- 权限说明必须解释当前阻断原因，继续按钮只能触发说明中声明的下一步动作。

<a id="req-011"></a>
### REQ-011 统一协调层：AppPermissionCoordinator + AppPermissionSurface（jit / page）

- **统一协调层**：`AppPermissionCoordinator` + `AppPermissionSurface`（`jit` / `page`）
- gate 语义：权限被拒绝时说明“当前为什么不能继续”以及“继续所需动作”。
- **统一 gate 载体**：权限态与登录门禁态共享 `AppInlineGateState` 结构，但图标、按钮和副说明由权限语义决定。

## 4. 契约引用

- 父级设计：[`runtime-client-foundation`](../design.md)
- canonical：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 错误权限展示语义

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“错误权限展示语义”对应的公开行为。
- THEN 页面使用与错误类别匹配的唯一载体，恢复成功后回到原上下文，无法恢复时提供明确退出路径。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-006"></a>
### GWT-006 JIT 麦克风权限无冗余 App modal

- GIVEN 用户以一次手势触发需要麦克风权限的操作。
- WHEN 权限说明或系统授权流程显示。
- THEN App 只展示一个必要的权限载体，不叠加第二个 App modal。

<a id="gwt-007"></a>
### GWT-007 语音发送失败使用单一低打扰载体

- GIVEN 语音消息发送失败。
- WHEN 页面呈现该失败。
- THEN 用户只看到可恢复的单一低打扰载体，modal 与 status bar 不同时出现。

<a id="gwt-008"></a>
### GWT-008 权限说明与继续动作一致

- GIVEN 页面显示权限 primer。
- WHEN 用户阅读说明并选择继续。
- THEN 文案解释当前阻断原因，继续动作只触发说明声明的下一步。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 结构化错误页保持来源外观且使用统一载体

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：完成“error-permission-display-semantics”并获得明确的成功或失败结果。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 错误权限展示语义 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“错误权限展示语义”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 JIT 麦克风权限 — 无冗余 App modal

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：同一次手势无 2+ App modal。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 语音发送失败 — 单一低打扰载体

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：modal 与 status bar 不同时出现。
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 Page L2 primer 文案与继续按钮一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：verify_permission_primer_copy.py 通过。
- 完成判定：`GWT-008` 对应行为满足且真实测试 `spec_ref` 有效。

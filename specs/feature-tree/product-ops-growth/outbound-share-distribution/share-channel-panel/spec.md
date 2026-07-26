# L3 Story：统一分享面板与渠道编排（share-channel-panel） (`share-channel-panel`)

> 所属能力：[`outbound-share-distribution`](../spec.md)

> Journey / Scenario：[`JNY-010 / SCN-023`](../../../spec.md#scn-023)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为分享内容的用户，
我希望在需要登录时完成登录后只续接一次原分享动作，并进入所选渠道，
从而不会因登录弹窗重复或丢失分享目标。

## 2. 范围与非目标

### In Scope

- “统一分享面板与渠道编排（share-channel-panel）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 卡片视觉设计（object-share-cards）。
- 归因落库与口令解析（share-attribution-and-token）。
- 入站回流（runtime/external-inbound-deeplink-routing）。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 统一分享面板与渠道编排（share-channel-panel）

- 用户关闭登录后不得再次循环弹窗；登录成功后必须续接原分享渠道。

<a id="req-002"></a>
### REQ-002 分享登录门关闭后不死循环且成功续接

- 用户关闭登录后不得再次循环弹窗；登录成功后必须续接原分享渠道。

<a id="req-003"></a>
### REQ-003 可见性分级控制渠道可用性

- `public` 内容可使用允许的站外渠道，`private` 内容必须置灰站外渠道，未知可见性必须拒绝分享。

<a id="req-004"></a>
### REQ-004 App、内容与聊天分享保持同一渠道结果

- App 发起的内容或聊天分享必须由同一渠道编排执行，并返回可观察的成功、取消或失败终态。

<a id="req-005"></a>
### REQ-005 private：渠道置灰并提示「该内容不可对外分享」

- `private`：渠道置灰并提示「该内容不可对外分享」。
- 未知或已退役 visibility：严格拒绝，不得按 public 或受控预览处理。

## 4. 契约引用

- canonical：`specs/feature-tree/product-ops-growth/outbound-share-distribution/share-channel-panel/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
- canonical：`quwoquan_app/lib/core/auth/auth_continuation.dart`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_post_placement/operations.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 统一分享面板与渠道编排（share-channel-panel）

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“统一分享面板与渠道编排（share-channel-panel）”对应的公开行为。
- THEN 关闭登录后返回安全页面且不再弹窗；登录成功后进入最初选择的分享渠道。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 分享登录门关闭后不死循环且成功续接

- GIVEN 游客从分享面板选择需要登录的渠道。
- WHEN 用户关闭登录入口或完成登录。
- THEN 关闭后回到安全状态且不再触发登录门，成功后只续接一次原渠道动作。

<a id="gwt-003"></a>
### GWT-003 可见性分级控制渠道可用性

- GIVEN 分享对象的可见性为 public、private 或未知值。
- WHEN 面板计算可用渠道。
- THEN public 显示允许渠道，private 置灰站外渠道，未知值拒绝分享。

<a id="gwt-004"></a>
### GWT-004 Post 站内分发使用 CirclePostPlacement 与聊天卡片的真实契约

- GIVEN 用户选择将 Post 分发到圈子或聊天。
- WHEN 面板提交站内分发动作。
- THEN 分发使用 CirclePostPlacement 与聊天卡片的 canonical 契约，并产生可回读的成功、取消或失败终态。

## 6. 依赖

- 前置要求：[`outbound-share-distribution`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 5 类对象统一面板两段式渠道编排

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：5 类对象面板渲染与渠道执行测试通过；Post 站内三类目标均有真实动作。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 分享登录门关闭后不死循环且成功续接

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：关闭再 pump 不再弹登录；登录成功进入目标渠道执行的测试通过。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 可见性分级控制渠道可用性

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：public/private/未知值渠道可用性测试通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 Post 站内分发使用 CirclePostPlacement 与聊天卡片的真实契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：App local_contract、内容/聊天 api_integration 与真机分发旅程形成对应证据。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

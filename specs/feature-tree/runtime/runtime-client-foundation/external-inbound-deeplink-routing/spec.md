# L3 Story：外链深链回流与微信唤起（external-inbound-deeplink-routing） (`external-inbound-deeplink-routing`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望每种失败路径都有明确 UI 与文案，无静默失败，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “外链深链回流与微信唤起（external-inbound-deeplink-routing）”的输入、可观察主路径、失败语义以及与父能力的交接。
- iOS Universal Link / Android App Links / 鸿蒙 / scheme 注册矩阵与 path 约定。
- 端侧 DeepLinkResolver 入站解析、反查实体、路由跳转与失败降级。
- 微信内 wx-open-launch-app / Universal Link 唤起与拦截检测确定性兜底。
- 延迟深链方案分层与第三方 SDK 选型决策框架。
- PlatformCapabilities 能力位与 NativeBridge 接口契约。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 外链深链回流与微信唤起（external-inbound-deeplink-routing）

- 每种失败路径都有明确 UI 与文案，无静默失败。

<a id="req-002"></a>
### REQ-002 微信内唤起按平台分流且拦截有确定性兜底

- 每种失败路径都有明确 UI 与文案，无静默失败。

<a id="req-003"></a>
### REQ-003 未安装下载后延迟深链还原原始目标

- 至少一条还原路径在 Android 与 iOS 各通过端到端验证。

<a id="req-004"></a>
### REQ-004 入站能力由能力位与 NativeBridge 防腐驱动

- mobile、web 与 ohos 必须通过同一 capability 决策入口选择深链行为，不得在页面内按平台分叉。

<a id="req-005"></a>
### REQ-005 深链运行时错误码契约

- 微信未安装/UL 未就绪/口令失效/解析失败为 MODULE.KIND.REASON + recovery，端侧消费结构化 RuntimeFailure。

<a id="req-006"></a>
### REQ-006 微信内唤起、拦截检测与可靠跳转

- Android/鸿蒙使用 `wx-open-launch-app`，iOS 使用 Universal Link，并通过统一兜底、拦截检测与恢复动作完成可靠跳转。
- 原生注册的 path 集合**必须是 `link_templates.yaml` 中实体 web.path_template + transfer_pages 的并集**，禁止原生侧另写 path。
- 禁止在 Resolver/Router 维护第二套「外链 path → page」映射（rule 01 §2.2.1）。
- 入站冷启动（App 未运行）与热启动（App 运行中）都必须处理；冷启动需在路由就绪后重放 pending link。
- **统一兜底**：唤起失败或环境不支持时，落地页显示「点击右上角 ··· 选择在浏览器打开」引导，浏览器内再走 UL/App Links/scheme；仍未装则进下载页。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml`
- canonical：`runtime/errors`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/external-inbound-deeplink-routing/spec.md`
- canonical：`quwoquan_app/lib/runtime/platform/platform_capabilities.dart`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/cross-platform-portability/spec.md`
- canonical：`MODULE.KIND.REASON`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 外链深链回流与微信唤起（external-inbound-deeplink-routing）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“外链深链回流与微信唤起（external-inbound-deeplink-routing）”对应的公开行为。
- THEN 每种失败路径都有明确 UI 与文案，无静默失败。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 微信内唤起按平台分流且拦截有确定性兜底

- GIVEN 用户在微信内打开支持的实体链接。
- WHEN 平台唤起成功、被拦截或环境不支持。
- THEN Android、iOS 与鸿蒙采用各自受支持通道，失败时显示确定性浏览器或下载恢复路径。

<a id="gwt-003"></a>
### GWT-003 未安装下载后延迟深链还原原始目标

- GIVEN 用户在未安装 App 的 Android 或 iOS 设备打开实体链接。
- WHEN 用户完成下载并首次启动 App。
- THEN 至少一条受支持路径恢复原始目标实体。

<a id="gwt-004"></a>
### GWT-004 入站能力由能力位与 NativeBridge 防腐驱动

- GIVEN mobile、web 或 ohos capability profile 接收入站链接。
- WHEN DeepLinkResolver 决定处理方式。
- THEN 行为仅由统一 capability 与 NativeBridge 决定，页面不按平台作体验分叉。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 已安装设备点击外链直达 App 目标页（5 类对象）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：post（article/photo/video/micro）、circle、user、entity_homepage 五类目标都能直达。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 微信内唤起按平台分流且拦截有确定性兜底

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：每种失败路径都有明确 UI 与文案，无静默失败。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 未安装下载后延迟深链还原原始目标

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：至少一条还原路径在 Android 与 iOS 各通过端到端验证。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 入站能力由能力位与 NativeBridge 防腐驱动

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：mobile/web/ohos 三 profile 下行为契约由同一批测试经 platformCapabilitiesProvider override 驱动。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 深链运行时错误码契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：微信未安装/UL 未就绪/口令失效/解析失败为 MODULE.KIND.REASON + recovery，端侧消费结构化 RuntimeFailure。
- 完成判定：微信未安装/UL 未就绪/口令失效/解析失败为 MODULE.KIND.REASON + recovery，端侧消费结构化 RuntimeFailure。

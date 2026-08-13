# L3 Story：页面横向布局质量 (`page-horizontal-quality`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “页面横向布局质量”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 页面横向布局质量

- 在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达。

<a id="req-002"></a>
### REQ-002 页面装配保持强类型

- 页面文件不得用 `dynamic`、`Map<String, dynamic>` 或版本化 `Current/V2` 命名承载展示与观测状态；可扩展观测属性使用 `Map<String, Object?>`，路由参数使用明确可空类型。

<a id="req-003"></a>
### REQ-003 页面对象契约表达读模型归属，不表达 HTTP 直连

- `page_object_contract.yaml` 的 `query_slices` 表达数据血缘与读模型归属，不表示该页面直接调用被认领对象的 HTTP 路由。
- 跨域 hydration 是合规形态：页面认领的对象可以只提供内部特征或读模型，真实读路径由另一个域的 App 面 operation 承载。
- 页面认领对象的必需产物是 presentation 实现，不包含 clientContract；被页面认领却没有 clientContract 的对象不得判为缺口。
- 认领 `recommendation.recommendation_feature_profile_view` 的页面即属该形态，其真实读路径由 `content.intersection_visit_state` 与 `content.post` 的 App 面 operation 承载。

<a id="req-004"></a>
### REQ-004 骨架屏由设计系统 skeleton primitives 组合

- 页面骨架屏只能由设计系统 skeleton primitives（块、行、圆位）与统一 shimmer 包装组合；页面侧只声明骨架布局形状，不得自实现 shimmer、脉冲或第二套占位动画。
- shimmer 节奏与占位圆角来自设计系统 token；`MediaQuery.disableAnimations` 为真时骨架静止。
- 骨架屏对辅助技术不可见（`ExcludeSemantics`），等待语义由页面级 `AppRequestFeedback` 或加载 semantics 承载。
- 存量私有骨架由 `verify_component_reuse_ratchet.py` 基线只减不增。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面横向布局质量

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“页面横向布局质量”对应的公开行为。
- THEN 在受支持屏宽、文字缩放和本地化文案下保持页面无横向溢出且关键动作可达。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 页面强类型扫描无例外

- GIVEN App 页面清单由 canonical page matrix 生成。
- WHEN 执行页面 A/B/C 治理门禁。
- THEN A、B、C 三类违规均为 0，且不读取默认 allowlist 掩盖页面动态类型或历史命名。

<a id="gwt-003"></a>
### GWT-003 骨架屏统一 primitives 与无障碍语义

- GIVEN 页面或区块在首屏取数期间渲染骨架占位。
- WHEN 骨架屏以设计系统 skeleton primitives 组合渲染。
- THEN shimmer 节奏与圆角来自设计系统 token，跨页面视觉一致。
- AND `disableAnimations` 为真时骨架静止不闪烁。
- AND 骨架内容不进入 semantics tree，辅助技术只感知页面级等待语义。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 列表体验层高频组件尚未收敛为共享 primitives

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺无限滚动分页的共享 primitives——各页仍自写 `ScrollController` + `hasMore/loadMore` + append footer；profile_stats 的 capability 四态关系行按钮按裁决保留独立语义，不并入关注 pill。空态已收敛到 `AppEmptyState`、关注 pill 已收敛到 `design_system/actions/app_follow_button.dart`（tinted/onMedia 两变体，feed 卡片与沉浸式 toolbar 消费）、骨架屏已收敛到 `design_system/feedback/skeleton/app_skeleton.dart`（Shimmer/Block/Line/Circle，含 reduce-motion 静止与 ExcludeSemantics，feed/关注条/分享互动/交集卡/助手半弹窗全部消费，组件测试在位），均配 `verify_component_reuse_ratchet.py` 棘轮防新增。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效——design_system 提供分页列表 wrapper 共享组件并在 ≥3 个高频列表落地，`verify_component_reuse_ratchet.py` 基线随迁移逐步归零，新增页面不再出现私有轮子。

<a id="open-002"></a>
### OPEN-002 页面测试长尾与模态子流程 URL 化

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚有三类页面测试与路由长尾未消化。
  1. 四个页面缺少直接 Widget/contract 测试：`voice_call_page`、
     `persona_management_form_page`、`one_tap_movie_preview_page`、
     `assistant_reference_webview_page`；`circles_page` 名实已修正为直接挂载测试，
     router recovery 已补 wiring 合约测试。
  2. 测试树仍有约 182 处固定 `Future.delayed` 等待（flaky 主要风险面），以及
     `mockContentFacetOverrides` 等对象级 typed double 的历史 mock 命名残留
     （实现已对象级、标识未更名）。
  3. 约 42 处 `MaterialPageRoute`/`CupertinoPageRoute` 模态子流程不进 GoRouter URL，
     涉及编辑资料、创作选片、圈子设置等。评估结论：这些子流程均已挂
     `PageAccessInternalRoutes` 观测，且其宿主入口路由已被契约驱动的
     `requiredRouteGateForLocation` 深链守卫拦截，零漂移由
     `route_auth_contract_parity__local_contract_test.dart` 保证，鉴权绕过风险
     已消除；剩余债务是 Web 深链可达性与返回栈语义。
- 完成判定：`GWT-001` 对应行为满足——四页补齐最小 Widget/contract 测试并以
  `spec_ref` 绑定；固定 delay 按套件替换为条件等待；typed double 命名去 mock
  化（与并行 content mock 迁移会话协调，避免同批文件冲突）；高价值模态子流程
  （编辑资料、创作发布确认）迁移为 GoRouter 子路由并声明 route_id。

<a id="open-003"></a>
### OPEN-003 页面与组件存量 a11y guideline 违规

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前首页在 `meetsGuideline` a11y 闭集下存在两类真实存量违规，
  由 a11y 样板测试首次实测发现。其一，触控目标小于 44x44 设计系统下限，
  含搜索栏高 43、频道 chip 高 28、关注按钮 56x28 与多个 32x32 图标按钮；
  组件收敛后关注 pill 的 56x28 热区已随 `AppFollowButton` 固化为共享组件
  行为（`CupertinoButton.minimumSize: Size.zero`），热区扩展到
  `AppSpacing.minInteractiveSize` 需与 feed 作者栏、沉浸式 toolbar 的
  行高布局协同修复。
  其二，多个可点节点缺语义标签，含 feed 卡片、频道 chip 与图标按钮。
  文本对比度部分已闭合：`AppColors.secondaryLabelAccessible` token 落地，
  `AppEmptyState` 标题与副标题的 `textContrastGuideline` 断言双主题常绿；
  首页其余 `iosSecondaryLabel` 正文级使用点仍待按同 token 收敛。另有新实测
  裁决项：CTA 主色（iOS 系统蓝）在浅色底上约 3.65:1 低于 WCAG AA 4.5:1，
  属 iOS HIG 与 WCAG 的设计系统级张力，需裁决主色文字是否引入可达性变体。
  修复涉及首页高频组件，需与组件收敛（OPEN-001）协同。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效——首页的
  `iOSTapTargetGuideline`、`labeledTapTargetGuideline`、
  `textContrastGuideline` 断言全部常绿并以 `spec_ref` 绑定本节点。

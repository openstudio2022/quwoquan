# L3 Story：app-theme-infrastructure — Cupertino-first 全局视觉运行时 (`app-theme-infrastructure`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用应用的用户，
我希望让主要页面以 Cupertino-first 视觉语言和统一语义 Theme 呈现，只在平台必要处使用 Material 兼容宿主，
从而在深浅模式和不同页面间获得一致原生体验。

## 2. 范围与非目标

### In Scope

- “app-theme-infrastructure — Cupertino-first 全局视觉运行时”的输入、可观察主路径、失败语义以及与父能力的交接。
- 全局 light/dark/system 主题运行时。
- 页面错误态的来源外观继承。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 app-theme-infrastructure — Cupertino-first 全局视觉运行时

- 必须坚持 `Cupertino-first`：Material 仅用于兼容和平台必要能力，不得成为主要视觉语法来源。

<a id="req-002"></a>
### REQ-002 所有终端用户：在发现、内容、聊天、圈子、个人页、设置、创作等全量页面获得统一、简洁、清晰、苹果风格的视觉体验

- 所有终端用户：在发现、内容、聊天、圈子、个人页、设置、创作等全量页面获得统一、简洁、清晰、苹果风格的视觉体验。
- 必须坚持 `Cupertino-first`：Material 仅用于兼容和平台必要能力，不得成为主要视觉语法来源。
- 视觉真相源必须收敛到统一主题运行时：禁止页面继续以 `Colors.*`、裸 `TextStyle`、裸 `Icon`、局部 `isDark` 分支维护第二套规则。
- 全量页面必须纳入本 Story 推广范围，禁止只修壳层或只修单域页面后宣布完成。
- 路由、surface、operation 等业务标识仍必须来自 metadata codegen，主题系统不得引入第二套业务配置表。
- 必须与 `page-layout-semantics`、`dart-semantic-gate` 保持一致，并把苹果风格约束沉淀为长期门禁。
- 任何可交互元素必须满足最小热区 `44x44`，主操作建议 `48x48`。
- 发布：以统一生效、简单灰度为主，保障可回滚。
- 全量页面在手机、平板、横屏、分屏、桌面窗口下无系统性 overflow / 裁切 / 不可点击区域。
- 共享主题运行时必须支持后续账号同步与离线补同步接入，但本 Story 不直接承载同步逻辑。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 app-theme-infrastructure — Cupertino-first 全局视觉运行时

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“app-theme-infrastructure — Cupertino-first 全局视觉运行时”对应的公开行为。
- THEN 必须坚持 `Cupertino-first`：Material 仅用于兼容和平台必要能力，不得成为主要视觉语法来源。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 跨页面错误态继承来源外观

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：建立以 `Apple HIG / Cupertino-first` 为基线的全 app 视觉运行时，统一主题、字体、图标、表面、状态栏、安全区与多设备适配，并为主题/字号设置提供全局应用能力。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

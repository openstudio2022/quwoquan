# Design: Page Layout Semantics

## 设计动因

端侧创作、选择、设置、聊天等页面在顶部 leading、内容区结构、底部栏上不一致：
- Modal 与 Stack 混用 close / arrow_back
- 设置类页面结构分散，缺少统一 Section/Block
- 选择器模式（单选 tap 即返回 vs 多选 select-then-confirm）需统一

需建立跨域统一契约，并统一以 Apple HIG（iOS 设计语言）为主语义。

## 关键决策

| 决策点 | 选项 A | 选项 B（选定） | 原因 |
|--------|--------|----------------|------|
| Modal leading | arrow_back | close | Material：模态关闭语义明确，close 更符合「放弃/取消」 |
| Stack leading | close | arrow_back | 返回上一级，符合导航栈语义 |
| 单选选择器底部 | 固定 取消\|完成 | 无底部条，tap 即返回 | 单选场景 tap 即选，无需显式确认 |
| 多选选择器底部 | 无 | 固定 取消\|完成 | 多选需显式确认提交 |
| 设置页结构 | 各页面自行实现 | SettingsSemanticConstants 统一 | 视觉与交互一致，可复用 |
| Cupertino 场景交互组件 | 混用 Material 交互组件 | 纯 Cupertino 或语义化自绘交互 | 规避语义漂移，保证页面认知一致 |

## 适用范围与排除

- **适用**：创作、选择器、设置、聊天、资料管理等页面
- **排除**：用户主页、作者主页、圈子主页（后续单独规范「主页设计」）

## 与现有系统关系

- **specs/ux/page-layout-semantics.md**：权威规范
- **SettingsSemanticConstants**：设置类页面 token
- **AppTypography / AppSpacing / AppColors**：设计系统

## iOS 语义 v1（落地边界）

- 优先落地创作入口的两个选择器页面：`PublishLocationSelectorPage`、`PublishCircleSelectPage`
- 同步覆盖创作页设置行 trailing 语义（chevron、开关、选择值）
- 本轮不扩展到用户主页/作者主页/圈子主页（仍按排除范围执行）

## v1.1 扩展：圈子频道管理面板

- 在 `CirclesPage` 一级 tab 下方增加“频道管理面板”语义层，使用微博式双区块结构（我的频道/全部频道）。
- 面板入口图标采用三横管理图标，替换非频道语义入口。
- 频道排序与选中状态在端侧本地持久化，默认排除 `car`、`humanity`、`sports`。
- 主动作色统一蓝色主题，避免与历史橘色动作语义冲突。

## 未来演进

- 抽取 SettingsSection、SettingsRow 共享组件
- 用户/作者/圈子主页设计规范与改造

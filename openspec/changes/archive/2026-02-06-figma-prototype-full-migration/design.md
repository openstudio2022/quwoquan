# Figma 原型全量迁移 - 设计文档

## Context

- **目标**：在 quwoquan_app（Flutter）中按 Figma 最新原型与「趣我圈2026」设计文档，完整实现功能、视觉与交互。
- **现状**：quwoquan_app 已有编码规范与语义化设计系统（01-core-coding-standards）；参考实现为 趣我圈2026 的 React/TS 代码与 DESIGN_SPECIFICATION、CONTENT_SPECIFICATION、InformationArchitecture、PROFILE_PAGE_DESIGN、CIRCLE_DESIGN、CHAT_FEATURES 等文档。
- **约束**：禁止硬编码；所有 UI 使用 AppColors、AppSpacing、UITextConstants、ContentTypeConstants、DesignSemanticConstants；导入使用包引用 `package:quwoquan_app/...`；视觉与交互以 Figma 为准，行为与文档一致。

## Goals / Non-Goals

**Goals:**

- 欢迎/登录页、五大频道（发现、圈子、创作、趣聊、我的）、内容创作与展示、各主页与趣聊与原型/文档一致。
- 设计系统全覆盖：颜色、间距、文本、类型均用语义 token；不足处扩展语义（新常量或新 key）。
- 路由与叠加层与 趣我圈2026 App.tsx 行为对齐（欢迎 → 主框架 → 作者/圈子/文章/查看器/评论/ActionSheet/创作抽屉等）。

**Non-Goals:**

- 后端 API 真实对接、登录鉴权实现、推送与离线存储的完整方案（本阶段以 UI/交互与本地状态为主）。
- 好物/标记、半屏微详情等已弃用概念的完整实现（设计文档 v3 已整合进爱物与生活模块）。

## Decisions

### 1. 语义 Token 扩展策略

- **决策**：先按 Figma 与现有设计文档逐页对照，列出所有用到的颜色、间距、字号、圆角等；在 `AppColors`、`AppSpacing`、`UITextConstants` 等中补全语义项，避免在 UI 层出现硬编码。
- **备选**：在组件内写死再重构 → 易遗漏且违反规范，不采用。

### 2. 页面与叠加层结构

- **决策**：主容器为底部导航 + 当前频道页；作者主页、圈子主页、文章详情、沉浸查看器、评论、ActionSheet、创作抽屉等以全屏/半屏叠加（Route 或 Overlay）呈现，与 趣我圈2026 的 AnimatePresence + 状态驱动一致。
- **备选**：全部用命名路由 → 状态（如选中的 post、initialMediaIndex）传递复杂；采用「主框架 + 叠加层」更贴近原型。
- **细化**：详见 [routing-and-user-journeys.md](./routing-and-user-journeys.md)，含 z-index 层级表、路由建议、关键用户旅程与实现检查清单。

### 3. 发现页与圈子页的内容组件复用

- **决策**：帖子卡片、瀑布流、Tab 导航等抽象为可复用组件；发现页与圈子页传入数据源与回调（onAuthorClick、onCircleClick、onPostClick 等），避免两套实现。
- **备选**：发现与圈子各写一套 → 易导致视觉/交互不一致，不采用。

### 4. 创作流程入口与编辑器

- **决策**：底部导航「创作」点击打开创作入口抽屉（微趣 3 类 + 作品 3 类）；选择类型后进入对应编辑器；与 DESIGN_SPECIFICATION v3.1 一致；已废弃瞬间、随记、好物标签。
- **备选**：直接进入单一编辑器 → 与设计不符，不采用。

### 5. 作者主页 vs 圈子主页差异

- **决策**：按 PROFILE_PAGE_DESIGN v3.0 与 CIRCLE_DESIGN v2.0：统一 3-Tab（创作/互动/生活）；创作子分类全部/图片/视频/文章；生活子分类足迹/书影音/味蕾/爱物；统计与操作按页面类型区分；共用布局组件，通过参数区分。
- **备选**：两套完全独立页面 → 维护成本高且易不一致，不采用。

### 6. 趣聊消息与输入

- **决策**：消息列表、聊天详情、底部输入栏（文本/语音/表情/更多面板）、长按菜单（转发、多选、复制、撤回、删除）按 CHAT_FEATURES 实现；消息类型与气泡样式与 Figma 一致。
- **备选**：先做简化版再迭代 → 用户要求无遗漏，首版即按文档做全。

### 7. 创作入口行为（原型与 spec 差异）

- **决策**：创作入口点击须**先打开创作入口抽屉（CreateEntrySheet）**，用户选择微趣/作品六入口之一后再进入创作页。与 create-flow spec 及 DESIGN_SPECIFICATION v3.1 一致。
- **现状**：趣我圈2026 原型中创作按钮直接打开 CreatePage，未展示 CreateEntrySheet；迁移时需修正为该流程。

### 8. 路由与 Shell

- **决策**：采用 ShellRoute 包裹五大频道，叠加层通过 push/Overlay 呈现；创作流程不占路由，由 Overlay 或 Modal 承载。
- **细化**：详见 [routing-and-user-journeys.md](./routing-and-user-journeys.md)。

## Risks / Trade-offs

- **[Risk] Figma 与文档细节冲突** → 以 Figma 为准；文档仅作交互与文案参考，视觉尺寸/颜色以 Figma token 或导出值为准。
- **[Risk] 语义 token 膨胀** → 按页面/模块分批扩展，命名保持 `DesignSemanticConstants` / 语义间距等既有体系，避免重复语义。
- **[Risk] 叠加层 z-index 与安全区** → 统一约定 z-index 层级，详见 routing-and-user-journeys.md；安全区使用 MediaQuery + SafeArea，与现有规范一致。
- **[Trade-off] 先 UI 后接口** → 列表与详情可先用本地 mock/空状态，保证高保真与可测；接口对接放在后续任务。

## Migration Plan

1. **语义扩展**：对照 Figma 与设计文档，在 lib 内设计系统文件中新增/扩展 token，跑通 `flutter analyze`。
2. **欢迎与主导航**：实现欢迎页与五大频道框架、底部导航、创作入口打开抽屉；路由与叠加层结构按 [routing-and-user-journeys.md](./routing-and-user-journeys.md) 实现。
3. **发现与圈子**：发现页 Tab 与内容流、圈子页入口与列表；帖子卡片与点击跳转（作者/圈子/帖子）。
4. **创作流程**：入口抽屉 6 个入口、各编辑器页面布局与基础交互。
5. **主页**：我的、作者、圈子、小趣四类主页；布局与 Tab 与设计文档一致。
6. **内容查看与操作**：沉浸式查看器、文章详情、评论、ActionSheet、点赞/收藏/分享状态同步。
7. **趣聊**：消息列表、聊天详情、输入栏、长按菜单。
8. **联调与测试**：关键路径与视觉回归；按 tasks 验收。

**回滚**：本次为功能迁移，无数据迁移；若有问题可回退到迁移前提交。

## Open Questions

- 小趣主页的具体交互与数据来源（是否与现有「小趣」服务对接）需产品确认。
- 爱物/生活模块的标记与关联交互，是否在本期实现完整流程（可先做 UI 骨架）。

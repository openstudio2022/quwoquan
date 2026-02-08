# Figma 原型全量迁移 - 需求提案

## Why

需要将趣我圈 App 与 Figma 最新全量原型对齐：在 Flutter 工程（quwoquan_app）中完整实现原型中的功能、视觉与交互，做到零遗漏。当前参考实现为「趣我圈2026」React 原型及其设计文档；迁移后需符合 quwoquan_app 的编码规范与语义化设计系统（语义 token），必要时扩展语义体系。

## What Changes

- **欢迎与入口**：实现 App 登录/欢迎页，与 Figma 视觉与动效一致。
- **五大频道**：发现、圈子、创作、趣聊、我的主页；底部导航与频道内 Tab/子导航与原型一致。
- **内容体系**：采用「创作-互动-生活」三位一体（CONTENT_SPECIFICATION v3.0）；创作含图片/视频/文章；发现页推荐+图片/视频/文章；已弃用瞬间、随记、好物，改用微趣/作品/爱物等。
- **创作流程**：创作入口抽屉（微趣 vs 作品）——微趣（照片/文字/视频）与作品（图片/文章/视频）六入口；创作页与 CreateEntrySheet、CreatePage 一致。
- **主页体系**：我的、作者、圈子主页统一 3-Tab（创作/互动/生活）；创作子分类全部/图片/视频/文章；生活子分类足迹/书影音/味蕾/爱物；小趣入口与 PROFILE_PAGE_DESIGN v3.0 一致。
- **趣聊**：一级 Tab 消息/通讯，二级 Tab；聊天详情、小趣专属对话；与 MessagePage 一致。
- **小趣**：核心理念「以兴趣为半径，画出我们的交集」；小趣为星火图标、智多星、Slogan「让兴趣闪亮」；沉浸式工具栏中心入口、半屏面板 55–60vh。
- **设计系统**：全部使用语义 token（颜色、间距、文本、类型常量）；头像按 AVATAR_DESIGN_SYSTEM（个人圆形、圈子圆角正方形、尺寸语义）扩展；禁止硬编码。

## Capabilities

### New Capabilities

- `welcome-auth`: 欢迎/登录页：视觉、动效、进入主 App 的过渡。
- `main-nav`: 主导航与底部导航：五大频道（发现、圈子、创作、趣聊、我的）、当前项高亮、创作入口触发抽屉。
- `app-global`: 产品整体定位、关键概念（微趣/作品/创作/互动/生活/爱物/小趣等）、已弃用概念（瞬间/随记/好物）、五大频道、3-Tab 架构、小趣入口规范。
- `discovery-feed`: 发现页：推荐 + 图片/视频/文章 Tab（CONTENT_SPECIFICATION v3.0）、内容流与卡片、小趣悬浮球；点击作者/圈子/帖子跳转。
- `circles-feed`: 圈子页：兴趣维度 DiscoveryView、创建圈子入口、进入圈子主页；与 CirclesChannel 一致。
- `create-flow`: 创作流程：入口抽屉（微趣 3 类 + 作品 3 类）、创作页四 Tab 编辑器；与 CreateEntrySheet、CreatePage 一致。
- `chat`: 趣聊：一级 Tab 消息/通讯、二级 Tab、会话列表、聊天详情、输入栏、长按操作；与 MessagePage 一致。
- `profile-my`: 我的主页：创作/互动/生活 Tab、身份/分身切换、设置与小趣入口；与 MyProfilePage 一致。
- `profile-author`: 作者主页：创作（全部/图片/视频/文章）、互动、生活（足迹/书影音/味蕾/爱物）；关注/圈子/粉丝/获赞；与 PROFILE_PAGE_DESIGN v3.0 一致。
- `profile-circle`: 圈子主页：创作/讨论/生活/聊天子频道；3-Tab 创作/互动/生活；与 CIRCLE_DESIGN v2.0 一致。
- `profile-xiaoqu`: 小趣主页：私人助理身份、与主 App 的联动入口与展示。
- `content-display`: 内容展示：帖子卡片、瀑布流/网格、沉浸式媒体查看器、文章详情页、评论入口。
- `comments`: 评论：评论列表、发表评论、@提及等；已弃用好物标签，生活相关以爱物等模块承载。
- `post-actions`: 帖子操作：点赞、收藏、分享、更多（ActionSheet）、与列表状态同步。

### Modified Capabilities

- （当前 `openspec/specs/` 为空，无既有规格；本次不修改既有 capability，全部为新增。）

## Impact

- **代码库**：quwoquan_app 的 lib 下各 feature（home、circles、create、chat、profile 等）、shared 组件与路由。
- **设计系统**：`AppColors`、`AppSpacing`、`UITextConstants`、`ContentTypeConstants`、`DesignSemanticConstants` 等；若 Figma 新增语义则扩展对应常量与 token。
- **参考源**：趣我圈2026 的 `src/`（App.tsx、各组件、设计文档如 DESIGN_SPECIFICATION.md、CONTENT_SPECIFICATION.md、InformationArchitecture.md、PROFILE_PAGE_DESIGN.md、CIRCLE_DESIGN.md、CHAT_FEATURES.md 等）作为功能与交互的权威参考；视觉以 Figma 最新原型为准。
- **测试**：关键路径与视觉回归需覆盖欢迎、五大频道、创作、各主页、趣聊与内容查看。

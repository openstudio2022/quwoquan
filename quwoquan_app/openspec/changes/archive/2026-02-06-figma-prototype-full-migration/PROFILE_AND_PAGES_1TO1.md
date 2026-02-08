# 我的主页 / 作者主页 / 圈子主页 1:1 对照与实现清单

参考：趣我圈2026 `MyProfilePage.tsx`、`AuthorProfile.tsx`、`CirclePageV2.tsx` 及 PROFILE_PAGE_DESIGN.md。

---

## 一、我的主页（与 Figma 差异及跳转）

### 1. 需保留的交互（当前已有，勿改）
- **背景下拉拉伸**：下拉时背景图缩放、内容区弹簧阻尼（`_pullOffset`、`_getSpringPullOffset` 等）—— 保留。
- **吸顶**：上滑时顶部工具栏/按钮浮现—— 保留。

### 2. 与 Figma（MyProfilePage.tsx）的布局差异

| 项目 | Figma / MyProfilePage.tsx | 当前 my_profile_page.dart | 动作 |
|------|---------------------------|---------------------------|------|
| 顶部封面 | 固定高度 320px、max-w 1440、圆角无、底部渐变 | 动态比例、1/4 屏高 | 可选：统一为固定高度约 320 或保持当前比例，与设计确认 |
| 内容卡片 | 白底、圆角 56px、-mt-24 与封面重叠、padding 8/10、阴影+边框 | 圆角、头像溢出 | 统一：圆角 56、-mt-24 视觉、内边距 8/10 对应 |
| 头像区 | 128×128、-mt-20、6px 白边、右下角蓝色 ChevronDown 点击展开分身 | 头像约 90、无分身下拉 | 1:1：头像 128、-mt-20、点击头像打开分身切换（含「管理所有分身」） |
| 右侧按钮组 | **资料编辑**（浅灰 pill）+ **分身管理**（深灰 pill）+ **小趣**（纯图标，无蓝底） | 更多菜单里才有编辑/分身 | 1:1：主区显示三按钮「资料编辑」「分身管理」「小趣」图标 |
| 姓名/简介 | heading-2 姓名、body 简介 + @name \| 加入趣我圈 124 天 | 有 displayName/bio | 补：加入天数等副文案可占位 |
| 交集卡片 | 蓝色浅底、4 头像 +「本周有 128 位趣友与你有交集」+ 右箭头 | 无 | 新增：点击进入「我的交集」页 |
| 统计行 | 关注 \| 圈子 \| 粉丝 \| 获赞（四列、竖线分隔、数字+小写 LABEL） | 有统计区 | 1:1：点击「关注」→ 关注列表；「粉丝」→ 粉丝列表；「获赞」→ 获赞列表；「圈子」可占位 |
| Tab | 创作 \| 互动 \| 生活（sticky、下划线指示） | 有 | 保持，子 Tab 与 Figma 一致 |
| 创作子 Tab | 全部、图片、视频、文章 + 网格/列表切换 | 有 | 对齐标签与切换 |
| 互动子 Tab | 浏览、赞和收藏、评论 + 我收到/我发出 | 需核对 | 1:1 二级 Tab 与列表 |
| 生活子 Tab | 全部、足迹、书影音、味蕾、爱物 + 网格/列表 | 需核对 | 1:1 |
| 作品网格 | 2~5 列、正方块、角标（视频/文章） | 有网格 | 对齐列数与角标 |

### 3. 我的主页 — 点击跳转与页面（无遗漏）

| 入口 | 目标 | 路由/实现 | 状态 |
|------|------|------------|------|
| 设置图标（顶栏） | 设置页 | 已有 `/profile` 内或 push 设置 | 需确认 |
| 头像（点击） | 分身切换下拉 +「管理所有分身」 | 弹层/抽屉；管理→管理分身页 | 待接 |
| 资料编辑按钮 | 编辑资料页 | `/profile/edit` → EditProfilePage | 待接 |
| 分身管理按钮 | 管理分身页 | `/profile/personas` → PersonaManagementPage | 待接 |
| 小趣图标 | 小趣管理页 | `/xiaoqu/management` 或从我的进小趣主页再管理 | 已有 xiaoqu 路由，需从我的页入口 |
| 交集卡片 | 我的交集页 | `/profile/resonance` → ResonanceDashboard 页 | 待接 |
| 关注 | 关注列表 | `/profile/stats?type=following` 或叠层 AuthorStatsList | 待接 |
| 粉丝 | 粉丝列表 | `/profile/stats?type=fans` | 待接 |
| 获赞 | 获赞列表 | `/profile/stats?type=likes` | 待接 |
| 圈子 | 我的圈子列表 | 可占位或 `/circles` | 可选 |

### 4. 需新增/补齐的页面与路由
- **编辑资料**：`EditProfilePage`（1:1 `EditProfilePage.tsx`），路由 `/profile/edit`。
- **管理分身**：`PersonaManagementPage`（1:1 `PersonaManagementPage.tsx`），路由 `/profile/personas`。
- **我的交集**：`ResonanceDashboardPage`（1:1 `ResonanceDashboard.tsx`），路由 `/profile/resonance`。
- **粉丝/获赞/关注列表**：`AuthorStatsListPage` 或全屏叠层（1:1 `AuthorStatsList.tsx`），路由 `/profile/stats?type=fans|likes|following` 或同一页 query。
- **小趣**：我的页点击小趣图标 → 进入小趣主页 `/xiaoqu` 或直接小趣管理 `/xiaoqu/management`（已有，仅需在我的页接入口）。

---

## 二、作者主页（1:1 及所有点击跳转）

参考：`AuthorProfile.tsx`。

### 1. 布局 1:1
- 封面 320px、顶栏返回 + 更多。
- 内容卡：头像 128、-mt-20、右侧「关注」「发消息」两按钮（无资料编辑/分身/小趣）。
- 姓名、简介、交集卡片「你们有 12 个交集点」+ 交集详情。
- 统计行：关注 | 圈子 | 粉丝 | 获赞（点击同下）。
- Tab：创作 | 互动 | 生活；创作子 Tab：全部/图片/视频/文章；网格/列表切换；作品带类型角标。

### 2. 作者主页 — 点击跳转（无遗漏）
- **返回**：`onBack()`，pop 或 go 上一页。
- **更多**：更多操作 Sheet（举报、拉黑等）。
- **关注**：切换关注状态。
- **发消息**：进入与该作者的聊天（如 `/chat?userId=xxx`）。
- **交集卡片**：进入与该作者的「交集详情」页（可与 ResonanceSpace 复用或独立）。
- **关注/粉丝/获赞**：打开 AuthorStatsList 叠层/页（关注列表、粉丝列表、获赞列表）。
- **圈子**：可占位或该作者加入的圈子列表。
- **作品项**：进入作品详情（图/视频/文章详情）。
- **互动/生活**：与我的主页一致的二级 Tab 与内容结构。

### 3. 当前 AuthorProfile（author_profile.dart）
- 已有吸顶、下拉、Tab、作品网格、关注按钮等。
- 需补齐：AuthorStatsList 全量（关注/粉丝/获赞列表页或叠层）、交集入口与交集详情页、发消息跳转、更多菜单。

---

## 三、圈子主页（1:1 及所有点击跳转）

参考：`CirclePageV2.tsx`。

### 1. 布局 1:1
- 封面 + 顶栏返回 + 更多。
- 圈子头像 128、-mt-20；名称、简介。
- 身份/角色：访客显示「关注圈子」「加入圈子」；管理员显示「编辑圈子」「管理中心」。
- 统计：成员 | 群聊 | 粉丝 | 获赞（点击打开对应列表）。
- Tab：创作 | 互动 | 生活；子 Tab 与作者/我的保持一致；作品网格。

### 2. 圈子主页 — 点击跳转（无遗漏）
- **返回**：onBack。
- **更多**：圈子更多菜单（分享、举报等）。
- **编辑圈子**（owner/admin）：EditCircleModal。
- **管理中心**（owner/admin）：CircleManagementCenter。
- **关注圈子/加入圈子**：切换状态；加入审批中→显示「加入审批中」。
- **成员/群聊/粉丝/获赞**：对应列表页或 AuthorStatsList 风格列表（type=members|groups|fans|likes）。
- **作品项**：进入作品详情。
- **返回逻辑**：从圈子详情 pop 回到来源（发现/我的/圈子列表）。

### 3. 当前 circle_detail_page.dart
- 需补齐：编辑圈子、管理中心、成员/群聊/粉丝/获赞列表 1:1、更多菜单。

---

## 四、实施顺序建议
1. **路由**：统一新增 `/profile/edit`、`/profile/personas`、`/profile/resonance`、`/profile/stats`；确认 `/xiaoqu`、`/xiaoqu/management` 从我的页可进。
2. **我的主页**：先做 Profile 区 1:1（头像+三按钮+交集卡片+统计行）、再接所有跳转（编辑资料、管理分身、小趣、我的交集、粉丝/获赞/关注列表）。
3. **作者主页**：补齐 AuthorStatsList、交集详情、发消息、更多菜单。
4. **圈子主页**：补齐编辑/管理中心、成员等列表、更多菜单。

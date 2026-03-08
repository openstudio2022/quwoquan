# 个人主页全面重构（我的 + 他人主页统一化）

## 背景与动机

当前个人主页存在严重的体验和工程质量问题：

1. **代码重复**：`my_profile_page.dart`（1546行）与 `author_profile_page.dart`（2539行）存在 80%+ 重复代码（背景图拉伸、头像、统计行、Tab 框架），但数据源、操作按钮不同，维护成本高且易产生不一致。
2. **Tab 结构与发现页脱节**：发现页使用 `[微趣, 作品]` 双轨道，个人主页使用 `[创作, 互动, 生活]`，内容分类语义不统一，用户在发现页看到的分类无法在主页上找到对应。
3. **无圈子展示**：个人主页统计行有"圈子"数字，但无已加入圈子的列表展示，与圈子社区功能脱节。
4. **目录结构违规**：`my_profile_page` 仍在 `lib/features/profile/`，未按领域规范迁移到 `lib/ui/user/`。
5. **编码质量低下**：大量硬编码间距（`16.w`, `50.h`, `140.w`）、非语义颜色引用、中文硬编码文案，违反设计系统规范。
6. **数据源割裂**：`my_profile_page` 使用 `_generateMockPosts()` 硬编码假数据，而 `author_profile_page` 已接入 `userProfileRepositoryProvider`。
7. **零测试覆盖**：user 域没有任何 L1a/L1b/L1c 测试。
8. **端云 DTO 缺失**：用户域无 codegen 生成的类型化 DTO（`user_profile_dto.g.dart`），端侧仍使用手写 User model。

## 目标用户

- 所有趣我圈用户（查看自己的主页、管理创作内容、查看已加入圈子）
- 其他用户（浏览他人主页、关注互动、查看共同交集）

## 功能范围

### F1: ProfileShell 统一组件

将我的主页和他人主页的 80%+ 共性 UI 抽取为统一的 `ProfileShell` 组件，通过 `ProfileMode.mine / ProfileMode.other` 枚举切换差异区域：

**共享区域**：
- 背景图 + 下拉弹簧阻尼拉伸 + 回弹动效
- 头像 **靠左对齐**（非居中），侵入背景图区域 1/3（顶部 1/3 在背景区内，底部 2/3 在用户信息区内）
- 用户名与头像 **同行显示**（Row 布局），垂直对齐到头像下部 2/3 区域；**不显示 @username**
- bio、统计行、交集卡片、Tab 导航框架
- 滚动吸顶：上滑过头像/名字后，小头像+名字平滑过渡到顶部工具栏；继续上滑一级 Tab 吸顶
- 暗色模式全面支持：所有背景、前景、渐变、工具栏颜色通过语义 Token 切换

**mine 差异**：操作按钮 = [编辑资料, 管理人设]（等宽双按钮）；创作可见性含「私密」；顶栏 = [设置]
**other 差异**：操作按钮 = [关注/已关注, 私信]（等宽双按钮，与 mine 布局一致）；无「私密」；顶栏 = [返回, 更多]

### F2: 一级 Tab 重新设计

一级 Tab：`[创作 | 圈子 | 互动 | 生活]`，默认选中「创作」。

命名语义：「创作」包含用户所有原创内容（含微趣），「作品」仅指发现页的图片/视频/文章频道。「创作 ⊃ 作品 + 微趣」，避免与发现页「作品」Rail 语义冲突。

### F3: 创作 Tab（二级分类 + 可见性过滤）

- 二级 SubTab：`[全部 | 微趣 | 图片 | 视频 | 文字]`
  - 与发现页 `contentType` 对齐：`micro(moment) / image(photo) / video / article`
- 可见性过滤：点击已选中的「创作」Tab 弹出 popup
  - 我的主页：`[全部 | 公开 | 私密]`
  - 他人主页：`[全部 | 公开]`（无「私密」选项）
  - 私密作品封面叠加锁标
  - 选中非「全部」时，Tab 文字旁显示筛选指示器

### F4: 圈子 Tab

- 展示用户已加入的全部圈子（我的主页）或公开圈子（他人主页）
- 卡片形式：圈子封面 + 圈子名
- 点击跳转到 `circle_detail_page`
- 空态：友好提示「还没加入圈子」或「Ta 还没加入圈子」

### F5: 互动 Tab

- 子维度：`[赞 | 评论]`
- 方向切换：`[收到 | 发出]`（我的主页）/ 仅 `[Ta收到]` 公开部分（他人主页）
- 互动列表：头像 + 用户名 + 互动内容摘要 + 时间

### F6: 生活 Tab

- 子分类：`[足迹 | 书影音 | 味蕾 | 爱物]`
- 网格/列表视图切换
- 生活记录卡片

### F7: 目录迁移与 features/ 清退

- `features/profile/*` 全部迁移到 `lib/ui/user/*`
- 更新 `app_router.dart` 路由指向
- 更新所有 import 路径
- 删除 `features/profile/` 目录

### F8: 端云 DTO 对齐

- 推进 `contracts/metadata/user/user_profile/fields.yaml` → `codegen-app` → `user_profile_dto.g.dart`
- 扩展 `UserProfileRepository`：新增 `listUserCircles()` / `getUserStats()`
- Mock 数据补齐圈子列表和统计数据

### F9: 私人助理入口移除

- 从我的主页操作按钮行移除「私人助理」入口
- 统一到底部导航「小趣」入口，减少操作按钮行的视觉拥挤

### F10: 视觉一致性与设计 Token 全面对齐

- 所有间距使用 `AppSpacing.*` 语义标签
- 所有颜色使用 `AppColorsFunctional.getColor()` / `AppColors.*`
- 所有字号使用 `AppTypography.*`
- 所有文案使用 `UITextConstants.*` 或 l10n
- Tab 导航与发现页、圈子页复用 `CenteredScrollableTabBar` 组件
- 可交互热区下限 44×44，主操作 48×48
- 深色模式全面适配：背景渐变、工具栏折叠态、分界区衔接、所有前景色均通过语义 Token 跟随暗色切换

### F11: 四层测试覆盖

- L1a: 契约测试（UserProfile DTO schema、统计字段、圈子列表 DTO）
- L1b: Widget 测试（ProfileShell mine/other 渲染、创作 Tab 子分类切换与可见性过滤、圈子 Tab 卡片渲染、空态）
- L1c: Journey 测试（完整流程：打开→Tab切换→内容过滤→圈子跳转）
- L4: Patrol E2E（真机 Tab 切换验证）

## 不做什么（Out of Scope）

- **O1**: 用户档案编辑页重构（`edit_profile_page.dart` 保持现有实现，仅迁移目录）
- **O2**: 分身管理页重构（`persona_management_page.dart` 保持现有实现，仅迁移目录）
- **O3**: 交集/共鸣详情页（`resonance_page.dart` 保持现有实现，仅迁移目录）
- **O4**: 统计详情页（`profile_stats_page.dart` 保持现有实现，仅迁移目录）
- **O5**: 圈子推荐算法（圈子 Tab 仅展示已加入列表，不含推荐）
- **O6**: 生活 Tab 数据源重构（保持现有 `listUserLifeItems` 接口，不新增后端 API）
- **O7**: 其他 features/ 目录迁移（create、assistant、settings、welcome 不在本次范围，后续批次处理）
- **O8**: Go 云侧 UserProfile 服务实现（本次聚焦端侧重构 + metadata/codegen 对齐，Go 实现独立 story）

## 适用范围与约束

### 适用范围

- 端侧 Dart/Flutter 主页重构（`lib/ui/user/`）
- metadata 补齐与 codegen（`contracts/metadata/user/`、`lib/cloud/runtime/generated/user/`）
- 端侧 Repository 扩展（`lib/cloud/services/user/`）
- 四层测试建立（`test/ui/user/`）

### 约束

- **技术约束**：
  - DDD 分层：UI 通过 Provider 访问 Repository，禁止直接实例化 Mock/Remote
  - 所有新代码必须通过 `flutter analyze` + `verify_dart_semantic.py` 无新增违规
  - codegen 文件 `DO NOT EDIT` 禁止手改
  - ProfileShell 必须支持 Riverpod Provider 注入，不能用构造函数直接传 Repository
- **设计约束**：
  - Tab 导航语义必须与发现页、圈子页保持一致层级结构
  - 创作 SubTab 的 contentType 枚举必须与 `ContentUIConfig.discoveryTabs` 对齐
  - 可见性过滤的交互模式借鉴抖音（点击已选中 Tab 弹出过滤 popup）
- **不适用情形**：
  - Go 云侧 Handler 实现不在本 spec 范围
  - 端侧 Web/Desktop 适配（仅 mobile）
  - 生活 Tab 的后端新增 API

## 对标输入与吸收结论

### 抖音个人主页

| 维度 | 抖音 | 借鉴 | 适用边界 |
|------|------|------|---------|
| 一级 Tab | [作品, 收藏, 喜欢] | 不借鉴 | 抖音纯视频，极简三栏；趣我圈多内容形态+圈子，需更丰富分类 |
| 公开/私密过滤 | 点击已选中 Tab 弹出筛选 | **借鉴** | 交互自然、不占额外空间，完全适用 |
| 私密标识 | 封面加锁标 | **借鉴** | 视觉清晰，用户认知成本低 |
| 网格布局 | 3列等比 | 部分借鉴 | 创作 Tab 用2列瀑布流（与发现页一致），生活 Tab 用3列 |
| 2级触达 | 从4级优化到2级 | **借鉴** | Tab + SubTab = 2级，高效 |
| 收藏/喜欢独立 Tab | 与作品平级 | 不借鉴 | 收纳到互动 Tab 子维度，避免一级 Tab 过多 |

### 内部对标

- **发现页** `discovery_page.dart`：双轨道 `[微趣, 作品]`，Tab 组件 `CenteredScrollableTabBar`，contentType 枚举 → 创作 SubTab 对齐
- **圈子页** `circles_page.dart`：圈子卡片样式、分类导航 → 主页圈子 Tab 复用

## 验收重点

核心维度（详见 acceptance.yaml）：
1. ProfileShell 统一组件 mine/other 差异正确
2. 一级 Tab 结构 [创作|圈子|互动|生活] 渲染与交互
3. 创作 Tab 二级分类与可见性过滤
4. 圈子 Tab 已加入圈子卡片展示与跳转
5. features/ → ui/ 目录迁移完整
6. 端云 DTO codegen 对齐
7. 四层测试覆盖
8. 视觉一致性：零硬编码，全语义 Token

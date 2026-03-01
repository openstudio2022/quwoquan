# 页面布局语义规范（iOS 设计语言 v1）

> 适用于创作、选择、设置、聊天等页面；**不含用户主页、作者主页、圈子主页**（见 §6 遗留事项）。  
> **特性树**：`runtime/runtime-client-foundation/page-layout-semantics`（L3）  
> 参考：`02-dart-coding.mdc`、`error-and-permission-semantics.md`、`create-entry-location-visibility-circle/design.md`

---

## 1. 适用范围与排除

### 1.1 适用页面

| 分类 | 页面 | 说明 |
|------|------|------|
| **创作/编辑** | CreatePage, EditProfilePage, ImageEditorPage, CreateMediaPickerPage | 全屏模态或编辑 |
| **选择器** | PublishLocationSelectorPage, PublishLocationSearchPage, PublishCircleSelectPage | 单选/多选 |
| **设置** | SettingsPage, DeveloperSettingsPage, ChatSettingsPage, AssistantManagementPage | 配置/管理 |
| **聊天** | ChatDetailPage, StartGroupChatPage | 对话与群组 |
| **资料/分身** | PersonaManagementPage, ResonancePage, ProfileStatsPage | 个人数据管理 |
| **发现/圈子 Tab** | DiscoveryPage, CirclesPage, ChatPage（Tab 容器） | 主 Tab 页 |

### 1.2 排除页面（遗留事项）

| 页面 | 说明 |
|------|------|
| **MyProfilePage**（我的主页） | 后续单独规范「用户主页设计」 |
| **AuthorProfile**（作者主页） | 后续单独规范「作者主页设计」 |
| **CircleDetailPage**（圈子主页） | 后续单独规范「圈子主页设计」 |

> **遗留事项**：用户主页、作者主页、圈子主页的顶部/内容/底部语义与布局规范将在后续「主页设计」规范中统一补充，本规范不覆盖。

---

## 2. 页面结构三区

```
┌─────────────────────────────────────────────────────────────────────────┐
│  顶部工具栏（AppBar 或等效）                                              │
│  leading | title | actions                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  内容区（List / Form / Picker / Editor）                                 │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  底部工具栏（可选）                                                      │
│  cancel | confirm 或 工具条 / 操作区                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 顶部工具栏规范（iOS v1）

### 3.1 页面模式与 leading

| 模式 | leading | 语义 | 适用页面 |
|------|---------|------|----------|
| **Modal** | `CupertinoIcons.xmark` | 关闭当前模态，放弃/取消 | 创作、编辑、选择器 |
| **Stack** | `CupertinoIcons.back` / `CupertinoIcons.chevron_back` | 返回上一级 | 设置、详情、管理、列表 |

### 3.2 规则

| 规则 | 说明 |
|------|------|
| **R1** | Modal 页（创作、编辑、选择）必须使用 `close`；Stack 页（设置、管理、从导航进入的子页）必须使用 `arrow_back` |
| **R2** | title 居中（Modal）或左对齐/居中（Stack），使用 `AppTypography` |
| **R3** | 主操作（发布、完成、确定）放在 `actions`；次操作（草稿、搜索）可放 `actions` |
| **R4** | 选择器页面采用 **iOS 统一方案**：`CupertinoPageScaffold` + `CupertinoNavigationBar`，leading 用 `CupertinoIcons.xmark` |
| **R5** | `CupertinoPageScaffold` 场景禁止混入 Material 交互组件（`Checkbox`、`SnackBar` 等），选择态与反馈必须使用 Cupertino 或语义化自绘组件 |

### 3.3 选择器统一

| 选择器 | leading | 说明 |
|--------|---------|------|
| 地点选择、地点搜索 | `close` | Modal 选择 |
| 圈子选择 | `close` | Modal 选择 |
| 媒体选择 | `close`（自定义顶栏） | Modal 选择 |

---

## 4. 内容区规范

### 4.1 内容形态

| 形态 | 结构 | 示例 |
|------|------|------|
| **List** | `ListView` / `ListView.builder` / `ListView.separated` | 设置项、选项列表 |
| **Form** | `ListView` 或 `SingleChildScrollView` + 标签 + 输入 | 编辑资料、助理管理 |
| **Picker** | 列表 + 单选/多选（`ListTile` 或 `CheckboxListTile`） | 地点、圈子 |
| **Editor** | `TabBarView` / 画布 / 工具区 | 创作、图片编辑 |

### 4.2 设置类页面统一结构

设置类页面（SettingsPage、DeveloperSettingsPage、ChatSettingsPage、AssistantManagementPage）须使用统一语义：

| 元素 | API / 约定 |
|------|------------|
| **页面背景** | `SettingsSemanticConstants.pageBackground(isDark)` |
| **功能块背景** | `SettingsSemanticConstants.blockBackground(isDark)` |
| **块容器** | 左右 padding `blockHorizontalPadding`，上下 `sectionVerticalPadding`，圆角 `blockBorderRadius`，边框 `blockBorderColor` |
| **块内分割线** | `SettingsSemanticConstants.dividerColor(isDark)`，`dividerThickness` |
| **块间距** | `SettingsSemanticConstants.blockSpacing` |
| **设置行** | 最小高度 `AppSpacing.buttonHeight`，leading 图标 + label + trailing（Switch/chevron/文案） |

**建议**：抽取 `SettingsSection`、`SettingsRow` 等可复用组件，确保各设置页视觉与交互一致。

---

## 5. 底部工具栏规范

### 5.1 何时有底部条

| 场景 | 底部形态 | 示例 |
|------|----------|------|
| **多选选择器** | 固定 `取消 \| 完成` | 圈子选择 |
| **创作/编辑** | 工具条、切换条（emoji/键盘） | CreatePage 微趣、ImageEditorPage |
| **列表/表单/单选选择** | 无底部条 | 主操作在 AppBar actions 或 tap 即完成 |

### 5.2 多选选择器底部

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SafeArea + Padding                                                     │
│  [取消]                                    [完成]                        │
│  TextButton                              FilledButton                    │
└─────────────────────────────────────────────────────────────────────────┘
```

- 左「取消」：`pop(null)` 或放弃选择
- 右「完成」：`pop(selected)` 提交选择结果

### 5.3 单选选择器

- **无底部条**：tap 选项即 `pop(result)`，无需显式「完成」
- 适用于：地点选择、搜索选结果

---

## 6. 选择器模式

### 6.1 单选 vs 多选

| 类型 | 交互 | 底部 |
|------|------|------|
| **单选** | tap 选中即返回 | 无 |
| **多选** | 勾选后点「完成」返回 | 取消 + 完成 |

### 6.2 当前对齐

| 选择器 | 类型 | 符合规范 |
|--------|------|----------|
| 地点选择 | 单选 | tap 即返回，无底部 ✓ |
| 圈子选择 | 多选 | 底部 取消+完成 ✓ |

### 6.3 iOS 语义细化（v1）

| 语义点 | 规范 |
|--------|------|
| 行尾箭头 | 统一使用 `CupertinoIcons.chevron_forward`，避免 Material `Icons.chevron_right` |
| 选择态 | 单选/多选的选中图标使用 iOS 语义（如 `check_mark_circled_solid`），禁止 Material Checkbox |
| 操作文案 | 选择器页使用通用动作语义（取消/确认/完成），禁止借用无关域文案（如图片编辑文案） |
| 页面职责 | 发布选择器只承载“选择并返回”，不得混入关注、举报等增长/治理动作 |

---

## 7. 实现约束（强制）

- 顶部 leading 必须符合 Modal/Stack 模式，禁止混用
- 颜色、字号、间距必须使用 `AppTypography`、`AppSpacing`、`AppColors` / `SettingsSemanticConstants`
- 设置类页面必须使用 `SettingsSemanticConstants` 和统一块/行结构
- 选择器 leading 统一为 `close`（Modal）
- 创作入口设置行（位置/可见性/圈子）统一使用 iOS 语义图标、行高和 trailing 规则

---

## 8. 遗留事项（后续补充）

| 事项 | 计划 |
|------|------|
| 用户主页、作者主页、圈子主页 | 后续单独规范「主页设计」，统一顶部/内容/底部语义 |
| CreateMediaPickerPage 自定义顶栏 | 当前保留；若后续统一为 AppBar，需同步更新本规范 |

## 9. v1 第二批推广清单

| 模块 | 页面 | 已对齐项 |
|------|------|----------|
| 设置 | SettingsPage | 行尾箭头统一为 iOS 语义 |
| 助理 | AssistantManagementPage / AssistantHomePage | 行尾箭头统一为 iOS 语义 |
| 聊天 | ChatSettingsPage | 行尾箭头统一为 iOS 语义 |
| 圈子 | CircleStatsPage | 行尾箭头统一为 iOS 语义 |
| 聊天选择器 | StartGroupChatPage | 多选选择态改为 iOS 语义图标（替换 Material Checkbox） |
| 圈子频道管理 | CirclesPage | 一级 tab 下方滑出频道管理面板；我的频道支持拖拽排序；+/- 互转；动作色为蓝色主色 |

> 门禁：`scripts/verify_dart_semantic.py` 已新增 iOS 语义风格检查，并由 `scripts/gate_repo.sh` 在 app gate 阶段执行。

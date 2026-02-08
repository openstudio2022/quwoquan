# chat

## 新增需求

### 需求：趣聊频道与原型 MessagePage 一致

「趣聊」频道须与 MessagePage 一致：一级 Tab 为**消息**与**通讯**（或 contacts）。消息 Tab 下二级 Tab 为全部、@我、未读、密信等；通讯 Tab 下二级 Tab 为全部、圈子、好友、群聊等。支持小趣（AQu）首页与管理入口（若原型提供）。

#### 场景：一级与二级 Tab

- **当** 用户处于「趣聊」频道
- **则** 一级 Tab 为消息/通讯；切换后二级 Tab 与列表内容随之更新（会话列表或联系人列表）

#### 场景：点击会话打开聊天详情

- **当** 用户在消息列表中点击某条会话
- **则** 打开该会话的聊天详情页，展示消息线程与底部输入栏

### 需求：聊天详情展示消息与输入区

聊天详情须展示消息列表（己方/对方气泡）、自动滚动到最新消息，以及底部输入工具栏。消息类型须包含文本、图片等，与 CHAT_FEATURES 及 Figma 一致。

#### 场景：消息与输入区可见

- **当** 用户处于聊天详情页
- **则** 消息按正确对齐与样式展示，底部输入工具栏可见

### 需求：输入工具栏与长按菜单

输入工具栏须支持文本输入与发送、以及可选的更多/附件面板。长按消息须展示操作菜单（转发、多选、复制、撤回、删除等），与 CHAT_FEATURES 一致。

#### 场景：发送与更多

- **当** 用户输入文本并点击发送，则消息加入会话；点击更多/附件可展开扩展面板

#### 场景：长按菜单

- **当** 用户长按某条消息
- **则** 展示包含转发、多选、复制等操作菜单；己方消息可撤回、删除

### 需求：趣聊头像与语义 token

会话列表与聊天详情中的**用户头像**须使用圆形（avatar-user-sm，消息列表场景）。小趣头像与用户头像尺寸 1:1，均为圆形。会话列表、聊天详情与输入区所有 UI 须使用 AppColors、AppSpacing、UITextConstants。禁止使用硬编码值。

#### 场景：趣聊中的 token

- **当** 趣聊相关页面被构建时
- **则** 所有样式与文案使用设计系统常量

---

## 实现细节与 UI 规范（与 Figma / 同好列表一致）

以下为已落地的实现约定，须与 Figma 及「同好列表」图二保持视觉与语义一致。

### 聊天详情页（ChatDetailPage）

- **底部输入工具栏**
  - 不展示占位符「输入消息」；点击输入框不出现系统「Scan Text」浮层（`hintText: ''`，`enableInteractiveSelection: false`，`contextMenuBuilder` 返回空）。
  - 麦克风/表情/加号图标与输入框等高：使用 `AppSpacing.buttonSize` 作为图标区域尺寸，禁止 `44.h`/`44.w` 等魔鬼数字。
  - 表情图标使用嘴部为轮廓的样式（如 `Icons.mood_outlined`）；所有工具栏图标描边细、颜色浅：`IconThemeData` 中 `weight: 100`、`color: fgPrimary.withValues(alpha: 0.5)`、`fill: 0`。
- **语义 token**
  - 尺寸与间距全部使用 AppSpacing、DesignSemanticConstants、Theme 字号；禁止 `.h`/`.w`/`.r`/`.sp` 硬编码。气泡最大宽度、气泡内图片尺寸等使用命名常量（如 `_chatBubbleMaxWidth`、`_chatBubbleImageSize`）；头像半径使用 `AppSpacing.avatarUserSm / 2` 等语义值。

### 聊天信息页（ChatSettingsPage）

- **整体可滚动**
  - 使用 `ListView` + `AlwaysScrollableScrollPhysics`，body 用 `SizedBox.expand` 包裹以保证有界高度；底部 padding 含 `MediaQuery.paddingOf(context).bottom`，确保最后一项可完整滚入视口。
- **成员区域**
  - 最多展示 4 行成员（如 5 列×4 行）；超过 20 人时显示「更多群成员」入口，点击展开全部。
  - 添加成员按钮为**矩形**（宽 = 头像高度×1.2，高 = 头像高度），与头像上下等高；用 `Align(alignment: Alignment.topCenter)` 与头像行顶部对齐，不与姓名底部对齐。
- **开关（消息免打扰、置顶聊天、隐私屏障）**
  - 未选中：轨道与拇指颜色接近背景（如 `borderColor.withValues(alpha: 0.12)`、`fgPrimary.withValues(alpha: 0.2)`）；选中：轨道为主色蓝、拇指为白色，形成对比。
  - 开关视觉高度略小：使用 `Transform.scale(scale: 0.85)`。

### 发起群聊 / 选择成员（StartGroupChatPage、_MemberSelectSheet）

- **字母分割行（A、B、C…）**
  - 与同好列表（图二/ContactsList）一致：整行使用浅色背景做分割，字体小、非黑、与列表项有主次。
  - 语义：`color: borderColor.withValues(alpha: 0.15)`；padding 水平 `AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd`，垂直 `AppSpacing.xs`；字体 `AppTypography.sm`、`color: fgSecondary`、`FontWeight.w600`。
- **选择框（Checkbox）**
  - 视觉上略小：使用 `Transform.scale(scale: 0.82, alignment: Alignment.centerLeft)` 包裹；未选中边框与填充使用 `fgPrimary.withValues(alpha: 0.35)` 等浅色，`fillColor` 使用 `WidgetStateProperty`。

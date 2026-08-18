# iOS 浮层与页面 surface 目录

具体 surface 的既定形态。新增页面或浮层前先在这里找对应分型，找不到再回 spec 讨论，
不要就地发明第三套组合。

## 全局浮层分型

- **全屏**：全局搜索是**唯一**允许的全屏全局浮层。
- **贴底非全屏**：创作、更多功能、评论、联系人选择等必须保留上半屏上下文，
  统一复用 `ColorType.modalScrim`、`createEntrySheetHandle*`、`modalSheetMaxHeightRatio`。

## 贴底对话态 Sheet

选项表、说明列表、更多菜单：

- [MUST] 使用 `AppBottomModalSurface` + `SettingsSemanticConstants.conversationSheet*`。
- 标准互斥选择优先 `showAppActionSheet` 或 `ConversationSheet*` 积木
  （`lib/design_system/surfaces/conversation_sheet.dart`、`app_action_sheet.dart`）。
- [MUST NOT] 新建裸 `showCupertinoModalPopup` 自绘第二套白卡灰底。
- 新调用须经 `quwoquan_app/scripts/runtime/page/verify_conversation_sheet_canonical.py`
  登记与校验。

## 设置类全屏页（Inset 同源）

- **A 类**（分组列表 / 表单）：`SettingsInsetFormPageScaffold` +
  `SettingsInsetGroupedSection` / `SettingsInsetFormRow` / `SettingsInsetFormSectionDivider`
  （`lib/design_system/forms/settings/`）。
- **B 类**（成员选择 + 内嵌搜索）：`SettingsInsetMemberPickerPageScaffold`，
  与 A 类同源顶栏与灰底。
- [MUST NOT] 内页返回使用 `GlobalTopBarIconButton`。
- [MUST NOT] 新建 `pageBackground` + `selectionToolbarBackground` + 白顶栏这套未登记的第三种组合。
- 新增或移动受控页必须在同一 PR 更新
  `quwoquan_app/scripts/runtime/page/settings_canonical_manifest.yaml`；
  例外页在文件前部注释 owner、理由与失效条件。
- gate: `python3 quwoquan_app/scripts/runtime/page/verify_settings_canonical.py`

## 导航图标语义

- Modal leading 统一 `CupertinoIcons.xmark`。
- Stack 子页使用 `CupertinoIcons.back` / `chevron_back`。
- `CupertinoPageScaffold` 场景禁止混用 Material 交互组件（`Checkbox`、`SnackBar` 等）；
  选择态使用 Cupertino 或语义化自绘组件。

## 内容密度

- 横向内容区优先 `feedContentHorizontal`、`postPreviewSectionPadding`、
  `postPreviewGridSpacing`；post 媒体默认 edge-to-edge。
- 作者主页遵循 `iosProfileSurface`、`feedMaxContentWidth`、
  `profileHeaderBaseHeightRatio`、`profileHeaderMaxStretchHeightRatio`，
  不允许再做第二套白色层级。

## 沉浸式浏览器

- 指示器在文字之上，最多 6 个点，当前点与其它点共线。
- 文章不显示媒体页码。
- 「我的 post」底栏隐藏作者与关注，使用三等分同行操作。

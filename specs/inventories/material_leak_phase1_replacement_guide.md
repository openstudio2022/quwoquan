# Phase-1 Material 清理：五类热点替代方案

> 范围：`quwoquan_app/lib/ui`、`quwoquan_app/lib/components`（与 `material_leak_lib_ui_components.*` 一致）  
> 依据：`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`（Token 唯一来源、No Android Leakage）  
> 数据：`python3 scripts/scan_material_leaks.py` 中的启发式 `signals`；**非严格 AST**，用于分桶与排期。

## 0. 扫描口径修正（必读）

- **`theme_of`（59）**  
  正则 `Theme\.of\(` 会匹配 **`CupertinoTheme.of`** 的子串。脚本侧应用「`Theme.of` 前紧邻非 `Cupertino`」过滤后，**Material 的 `Theme.of(context)` 仍为 59 处**（与 inventory 一致）；全量含 Cupertino 约 98 处。  
  迁移时：**不要把 `CupertinoTheme.of` 当成 Material 债**；仅替换 `Theme.of` + `ThemeData` / `textTheme` / `colorScheme` 路径。
- **`Colors.*`（约 400）**  
  含 `Colors.transparent`、`Colors.black`/`white` 等；其中 **`Colors.transparent` 可改为 `dart:ui` 的 `Color(0x00000000)` 或项目常量**，但收益低，可放最后一波或保留（仍依赖 `material.dart` 时无意义，去掉 material import 时需处理）。

---

## 1. `colors_dot` — Material 调色板字面量

### 问题

- 绕过 `AppColors` / `ColorType` + `AppColorsFunctional.getColor`，深浅色与品牌不一致风险高。  
- `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §3：**缺失语义 MUST 先补 token**。

### 替代矩阵（按出现形态）

| 现状 | 替代方向 |
|------|----------|
| `Colors.white` / `Colors.black` | `AppColors.white` / `AppColors.black`（或语义色 `foregroundPrimary`/`pageBackground` 等） |
| `Colors.grey.shade200` ~ `shade900` | `AppColorsFunctional.getColor(isDark, ColorType.*)`：`borderPrimary`、`foregroundSecondary`、`surfaceMuted` 等；缺语义则在 `app_colors`/`ColorType` 补一项 |
| `Colors.red` / `amber` 等语义色 | 已有：`AppColors.error`、`AppColors.primaryColor`；警告/星标等新增 **命名 token**，禁止散落 `Colors.amber` |
| `color.withValues(alpha: x)` 链在 Material 灰阶上 | 以 **底色素 token + alpha** 表达，或增加 `glassSurface` / `overlay` 类 token |
| 沉浸式作品区黑底 | 规范已定义：`AppColors.worksBackground`（勿混用 `Colors.black`） |

### 热点文件（按命中数，优先改）

- `ui/discovery/pages/discovery_page.dart`（多：`grey`、`black`/`white` 半透明）  
- `ui/content/widgets/article_paged_canvas.dart`、`ui/content/entry/pages/create_page.dart`  
- `ui/discovery/widgets/works_immersive_viewer.dart`  
- `components/media/picker/create_media_picker_page.dart`、`one_tap_movie_preview_page.dart`  
- `components/navigation/secondary_capsule_tab_bar.dart`、`centered_scrollable_tab_bar.dart`  
- `components/petal_mark.dart`（纯装饰色）

### 执行策略

1. **先组件库**（`components/navigation`、`components/media/*`），再业务页，避免重复改同一视觉。  
2. 每文件改完跑 `dart analyze`，并目视深浅色各一遍。  
3. 改完后该文件若不再需要 `material.dart`，**删除 import**（真正降低 Material 依赖）。

---

## 2. `theme_of` — `Theme.of(context)`（Material）

### 问题

- 绑定 `ThemeData`、`colorScheme`、`textTheme`，与 **Cupertino + 自有 Typography** 双轨，易产生 Android 语义（字重、字间距、ripple 前提）。

### 替代矩阵

| 用途 | 替代 |
|------|------|
| 明暗判断 `Theme.of(context).brightness` | `MediaQuery.platformBrightnessOf(context)` 或 `CupertinoTheme.of(context).brightness`（与现有壳一致即可） |
| 正文/标题样式 | `AppTypography.*` + `AppColorsFunctional.getColor(isDark, ColorType.foreground*)`；导航栏标题可用 `CupertinoTheme.of(context).textTheme.navTitleTextStyle`（已是 Cupertino） |
| `colorScheme.surface` / `onSurface` | `ColorType.backgroundPrimary` / `foregroundPrimary` |
| `textTheme.bodyMedium` 等 | 显式 `TextStyle` 组合（从 `AppTypography` 取字号字重） |
| `Theme.of(context).canvasColor` 等少见 API | 对应 `ColorType.pageBackground` 或具体表面 token |

### 相对集中的文件（便于分批 PR）

- `ui/chat/pages/chat_page.dart`、`start_group_chat_page.dart`  
- `ui/assistant/pages/assistant_dev_replay_page.dart`（命中较多）  
- `ui/assistant/widgets/message/*`、`ui/entity/pages/*homepage*`  
- `components/input/customizable_chat_input_bar.dart`、`components/media/camera/camera_capture_page.dart`  
- `components/avatar/*`、`components/comment_system/*`、`components/conversation/message_bubble_frame.dart`

### 执行策略

- **禁止**用 `Theme.of` 只取 `brightness` — 统一一种来源（建议 `CupertinoTheme` 与全 app 壳一致）。  
- 与 `colors_dot` 清理可 **同一 PR 文件内合并**，减少多次读上下文。

---

## 3. `material` — `Material(` widget

### 常见动机

1. **祖先材质**：为子树提供 `Material` 以便 `InkWell` / `TextField` 等要 `Material` 的后代不报错。  
2. **历史遗留**：复制粘贴的包裹层。  
3. **AppScaffold 内已有一层透明 `Material`**（见 `lib/core/widgets/app_scaffold.dart`），子页面再包一层常属冗余。

### 替代矩阵

| 场景 | 替代 |
|------|------|
| 仅为 Ink 溅射 | 去掉 `InkWell` → 改用 **`CupertinoButton` / `GestureDetector`**（见 §5–6），多数可删外层 `Material` |
| 需要裁剪圆角 + 背景 | `Container`/`DecoratedBox` + `ClipRRect`，颜色用 token |
| 在 `AppScaffold`/`CupertinoPageScaffold` 子树内再包 `Material(type: transparency)` | **评估删除**；若仅修复文字下划线，以壳层已有 `Material` 为准 |
| 必须保留 Material 子控件（极少数第三方） | 在**最小子树**包一层 `Material(type: transparency)`，并注释原因；**禁止**整页再包 |

### 出现位置（便于点名改）

- `ui/content/entry/pages/create_page.dart`、`ui/chat/pages/chat_conversation_page.dart`  
- `ui/discovery/pages/home_page.dart`、`ui/circle/pages/home_circles_hub_page.dart`  
- `ui/assistant/pages/*`、`widgets/assistant_half_sheet.dart`、`welcome_screen.dart`  
- `components/input/customizable_chat_input_bar.dart`、`components/media/image/editor/*`、`message_action_menu_overlay.dart`、`tab_navigation.dart`

---

## 4. `material_buttons` — `IconButton` / `TextButton` / `ElevatedButton` / `FilledButton`

### 问题

- 默认 Material 形状、焦点、部分带 **ripple**；与规范 §2.8 **No Android Leakage** 冲突。

### 替代矩阵

| 组件 | 替代 |
|------|------|
| 顶栏/导航区图标 | **`AppNavigationBarIconButton`**（`lib/core/widgets/app_scaffold.dart`），或 `CupertinoButton` + `minInteractiveSize` |
| 主操作 / 填充按钮 | **`CupertinoButton.filled`**（`padding`、`borderRadius` 对齐 `AppSpacing`） |
| 文字型次要操作 | **`CupertinoButton`**（`padding: EdgeInsets.zero` + `AppTypography`） |
| 列表行尾「文字按钮」 | `CupertinoButton` 或 `GestureDetector` + semantics |

### 出现位置（全量在 ui+components 内很少，可一轮清完）

- `components/media/image/editor/image_editor_page.dart`、`panels/image_editor_operation_panel.dart`、`top_bar/image_editor_top_bar.dart`、`panels/image_editor_curve_overlay_bar.dart`  
- `components/input/customizable_chat_input_bar.dart`、`unified_emoji_picker.dart`  
- `ui/discovery/pages/discovery_page.dart`、`widgets/works_immersive_viewer.dart`  
- `ui/assistant/widgets/assistant_half_sheet.dart`

---

## 5. `ink_well` — `InkWell` / `InkResponse`

### 问题

- **Material ripple**；iOS 规范要求轻量、可预期反馈（§2.1 / §2.8）。

### 替代矩阵

| 场景 | 替代 |
|------|------|
| 可点击列表行 / 图标 | **`CupertinoButton`**（最小尺寸 44）或 **`GestureDetector` + `onTapDown`/`onTapCancel` 改透明度**（0.6→1.0） |
| 需保持「整行点击」 | `GestureDetector` + `behavior: HitTestBehavior.opaque` |
| 与 `ListTile` 组合 | 优先改为 **Inset Grouped 行**（`SettingsSemanticConstants` / 现有 settings 行模式）或自定义 `Row` |

### 出现位置

- `components/media/shared/toolbar/media_viewer_toolbar.dart`（5）  
- `components/media/image/editor/panels/image_editor_operation_panel.dart`（4）  
- `ui/assistant/pages/assistant_management_page.dart`（2）  
- 其余单点：`discovery_page`、`home_circles_hub_page`、`assistant_half_sheet`、`assistant_floating_ball`、`tab_navigation` 等

---

## 6. 推荐落地顺序（与风险）

| 顺序 | 类别 | 理由 |
|------|------|------|
| 1 | `material_buttons` + `ink_well`（23+20） | 文件少、交互语义收益最大，常顺带删掉多余 `Material(` |
| 2 | `material`（32） | 依赖 1 完成后大量冗余层可删 |
| 3 | `colors_dot`（400） | 工作量大，按「组件库 → 高热页面」分批 PR |
| 4 | `theme_of`（59） | 与 3 可交错；先统一 `brightness` 来源减少反复 |

---

## 7. 验收与回归

- 每批：`dart analyze`、关键路径手测深浅色。  
- 全量后再跑：`python3 scripts/scan_material_leaks.py`，五类计数应下降；可选后续加 **AST 级** 门禁（避免 `CupertinoTheme` 误伤）。  
- 设计验收：对照 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.8（无默认 ripple、无 Material 主按钮语义外露）。

---

## 8. 与 inventory 的同步

更新清单数据：

```bash
python3 scripts/scan_material_leaks.py
```

本指南不替代 codegen/元数据流程；仅服务客户端视觉债治理。

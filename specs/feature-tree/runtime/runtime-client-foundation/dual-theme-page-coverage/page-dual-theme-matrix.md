# 全页面深色 / 浅色矩阵（S6）

> **状态**：v1 代码审计基线（2026-03-29）。**审计方法**：逐文件检索 `isDarkProvider` / `AppColorsFunctional` / `AppColors.ios*`（`resolveFrom`）/ `CupertinoTheme.of(context).brightness`；委托页追溯 **实际渲染** 子树（如 `ChatConversationPage`、`ProfileShell`）；对固定渐变/黑底沉浸按 `spec.md` S6-2 登记 **exempt** 或 **partial**。  
> **列说明**：`dual_theme` = `full` | `partial` | `no` | `exempt`；`evidence` = 自检摘要（非截图）。  
> **与横向质量矩阵**：P6 列与本表 `dual_theme` 对齐：`full`→`✓`，`exempt`→`—`，`partial`/`no`→`○`（待修复或登记技术债）。

## 排除说明（不计入独立验收行）

| 路径 | 原因 |
|------|------|
| `lib/ui/chat/pages/chat_display_fallbacks.dart` | 仅为 `export` 重导出，无 Widget；对话态由 `assistant_display_fallbacks` 等承载。 |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 barrel，矩阵中单独一行标 `—`，与 `home_circles_hub_page` 同源验收。 |

---

## app / shell（S6-1 明确要求纳入）

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/app/shell/main_app_shell.dart` | app | Tab 壳 `IndexedStack` | full | | TBD | `isDarkProvider` + `AppColorsFunctional.getColor(..., pageBackground)`；`videoForceDark` 时 `worksBackground`。 |
| `lib/app/shell/bottom_navigation.dart` | app | 底栏 | full | | TBD | `isDarkProvider` + `AppColorsFunctional` glass / separator；`forceDark` 分支与壳一致。 |

---

## welcome

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/welcome/pages/welcome_screen.dart` | welcome | 首启全屏 | partial | | TBD | 品牌渐变与花瓣色为固定 `AppColors.welcome*`；装饰大量 `AppColors.white/black` 透明度叠加，**未**接 `isDarkProvider`。深浅色下可读但非对称材质。 |

---

## discovery

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/discovery/pages/home_page.dart` | discovery | Tab 根 | full | | TBD | `ref.watch(isDarkProvider)` 传入 `_buildBody` / `MomentSocialFeed` / tab strip。 |
| `lib/ui/discovery/pages/discovery_page.dart` | discovery | 壳内子视图 | partial | | TBD | 虽有 `isDark` 用法，但 Feed/卡片内大量 `AppColors.black` / `AppColors.white` 主表面与文字，**未**全部走语义 token；需按域收敛。 |

---

## assistant

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/assistant/pages/assistant_tab_page.dart` | assistant | Tab 根 | full | | TBD | `isDark` 分支 + `AppColors.white/black` 仅作浅表分隔，主结构随主题。 |
| `lib/ui/assistant/pages/assistant_management_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` / 语义色混用，主背景可随主题。 |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | assistant | GoRoute | partial | | TBD | `WebView` 内文档外链不控；**壳层** `setBackgroundColor(AppColors.white)` 与多处固定黑白边框/字色，深色下 chrome 偏浅。 |
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` + 功能色。 |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | assistant | 开发页 | full | | TBD | 具备 `isDark` 与功能色（工具页仍建议抽检）。 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` 等。 |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` 等。 |

---

## chat

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/chat/pages/chat_page.dart` | chat | Tab 根 | partial | | TBD | 全局 `isDark` 与功能色为主；列表/胶囊等仍有多处 `AppColors.white` 硬编码，深色下需对照 S6-2 收敛。 |
| `lib/ui/chat/pages/chat_detail_page.dart` | chat | 委托入口 | full | | TBD | 仅包装 `ChatConversationPage`，与对话页同结论。 |
| `lib/ui/chat/pages/chat_conversation_page.dart` | chat | 全屏/嵌套 | full | | TBD | `isDarkProvider` + 功能色。 |
| `lib/ui/chat/pages/chat_settings_page.dart` | chat | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/chat/pages/start_group_chat_page.dart` | chat | 模态 | full | | TBD | `isDarkProvider` + 功能色。 |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | chat | 子路由 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/chat/pages/group_member_search_page.dart` | chat | 子路由 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/chat/pages/group_manage_page.dart` | chat | 子路由 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/chat/pages/group_admins_page.dart` | chat | 子路由 | full | | TBD | `isDarkProvider`。 |

---

## circle

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | circle | Tab 根 | full | | TBD | `isDarkProvider` + 功能色。 |
| `lib/ui/circle/pages/circles_page.dart` | circle | Tab 根 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/circle/pages/circle_detail_page.dart` | circle | GoRoute | full | | TBD | 委托 `CircleShell`；shell 内 `isDarkProvider` + `iosLabel`。 |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | circle | 子路由/表单 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/circle/pages/circle_stats_page.dart` | circle | 子路由 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/circle/pages/circles_hub_page.dart` | circle | T0 export | exempt | 与 `home_circles_hub_page` 同源 | TBD | 不单独双色验收。 |

---

## content

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/content/pages/article_detail_page.dart` | content | GoRoute | full | | TBD | `AppColorsFunctional` / 主题相关用法。 |
| `lib/ui/content/pages/photo_detail_page.dart` | content | GoRoute | full | | TBD | `AppColorsFunctional`。 |
| `lib/ui/content/pages/video_detail_page.dart` | content | GoRoute | full | | TBD | `AppColorsFunctional`。 |
| `lib/ui/content/pages/unified_media_viewer_page.dart` | content | GoRoute | exempt | 作品沉浸浏览强制暗场（S6-2） | TBD | `CupertinoPageScaffold(backgroundColor: AppColors.black)` + `WorksImmersiveViewer`；浅色模式仍为暗底，须在矩阵登记。 |

---

## content / entry

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/content/entry/pages/create_page.dart` | content | 模态 | partial | | TBD | 主体可走主题；发布流程内多处 `AppColors.white/black` 叠加层与按钮，需逐项换语义 token。 |
| `lib/ui/content/entry/pages/article_preview_page.dart` | content | push | full | | TBD | `CupertinoColors.systemGroupedBackground.resolveFrom(context)`。 |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | content | push | full | | TBD | `isDarkProvider` / 功能色。 |
| `lib/ui/content/entry/pages/video_editor_page.dart` | content | push | full | | TBD | `CupertinoTheme.of(context).brightness` 驱动 `backgroundColor`；预览区固定黑底为编辑场景。 |
| `lib/ui/content/entry/pages/publish_circle_select_page.dart` | content | push | full | | TBD | `AppColors.iosPageBackground` / `iosSystemBackground(context)`。 |

---

## entity

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/entity/pages/suggest_homepage_page.dart` | entity | 模态 | full | | TBD | `isDarkProvider` 等。 |
| `lib/ui/entity/pages/homepage_picker_page.dart` | entity | GoRoute | full | | TBD | `AppColors.iosPageBackground` / `iosSystemBackground`。 |
| `lib/ui/entity/pages/homepage_claim_page.dart` | entity | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/entity/pages/homepage_maintenance_page.dart` | entity | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/entity/pages/homepage_status_report_page.dart` | entity | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/entity/pages/homepage_detail_page.dart` | entity | GoRoute | full | | TBD | 委托 `HomepageDetailShell`；shell 内 `iosPageBackground` + `brightness` 分支阴影。 |

---

## rtc

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | rtc | GoRoute | partial | | TBD | 固定 `welcomeGradientStart/End` 渐变，**不**随系统深浅切换主表面。 |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | rtc | GoRoute | partial | | TBD | 同上。 |
| `lib/ui/rtc/pages/voice_call_page.dart` | rtc | GoRoute | partial | | TBD | 渐变 + 部分 `AppColors.primaryColor` 叠加；非完整语义双色。 |
| `lib/ui/rtc/pages/video_call_page.dart` | rtc | GoRoute | partial | | TBD | `AppColors.black` 底 + 渐变覆盖层，通话 UI 未按 S6 完整对称材质。 |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | rtc | GoRoute | full | | TBD | `isDarkProvider` + `AppNavigationSemanticConstants`。 |

---

## search

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/search/pages/global_search_page.dart` | search | GoRoute | full | | TBD | 大量 `isDarkProvider` / `SearchSemanticConstants`。 |
| `lib/ui/search/pages/search_network_results_page.dart` | search | 子路由 | full | | TBD | `isDarkProvider`。 |

---

## settings

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/settings/pages/settings_page.dart` | settings | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/settings/pages/developer_settings_page.dart` | settings | GoRoute | full | | TBD | `isDarkProvider`（P2/P3 可标 —，双色仍接主题）。 |

---

## user

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/user/pages/my_profile_page.dart` | user | Tab / GoRoute | full | | TBD | 委托 `ProfileShell`；`isDarkProvider` + `iosLabel`。 |
| `lib/ui/user/pages/other_profile_page.dart` | user | GoRoute | full | | TBD | 同上。 |
| `lib/ui/user/pages/edit_profile_page.dart` | user | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/user/pages/persona_management_page.dart` | user | 壳内子视图 | full | | TBD | `isDarkProvider`。 |
| `lib/ui/user/pages/sub_account_management_page.dart` | user | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/user/pages/resonance_page.dart` | user | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/user/pages/profile_stats_page.dart` | user | GoRoute | full | | TBD | `isDarkProvider`。 |
| `lib/ui/user/pages/profile_comments_page.dart` | user | GoRoute | full | | TBD | `isDarkProvider`。 |

---

## components（全屏 / 骨架）

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/components/settings_form/settings_inset_form_page.dart` | components | 复用壳 | full | | TBD | `AppColorsFunctional.getColor`。 |
| `lib/components/media/image/editor/image_editor_page.dart` | components | push | full | | TBD | 多处 `AppColorsFunctional`（文件体量大，建议 Golden 抽检）。 |
| `lib/components/media/camera/camera_capture_page.dart` | components | 全屏 | full | | TBD | `isDark` + `AppColorsFunctional`（取景区 P7 可 —，控件用语义色）。 |
| `lib/components/media/picker/create_media_picker_page.dart` | components | 全屏 | full | | TBD | `AppColorsFunctional`。 |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | components | 全屏 | exempt | 预览器固定黑底白字 chrome（浅色模式不切换主阅读面） | TBD | `AppScaffold` 恒 `AppColors.black`，控件 `AppColors.white`；与 S6-2「强制暗场」同类登记。 |

---

## 统计（本表）

| 类别 | 数量 |
|------|------|
| 表内数据行（shell 2 + `ui/**/pages` 与 `components/**/*_page` 全量逐行，**不含** 文首「排除说明」表） | **64** |
| `dual_theme = full` | **52** |
| `dual_theme = partial` | **9** |
| `dual_theme = exempt` | **3**（`circles_hub` T0、`unified_media_viewer`、`one_tap_movie_preview`） |
| **partial 闭环优先级（建议）** | `welcome_screen`、`discovery_page`、`assistant_reference_webview` 壳、`chat_page`、`create_page`、RTC 四通道路由页 |

> **说明**：`exempt` 与 `partial` 均须在发版前在 `plan.yaml`/issue 有截止或设计确认；禁止无文档永久豁免。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-29 | 全量逐页代码审计首填；补齐 `app/shell`；排除 `chat_display_fallbacks` 误计；与 `page-horizontal-quality-matrix.md` P6 对齐。 |

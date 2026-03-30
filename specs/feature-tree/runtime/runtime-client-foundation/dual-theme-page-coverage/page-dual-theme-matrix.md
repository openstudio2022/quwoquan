# 全页面深色 / 浅色矩阵（S6）

> **状态**：v1 代码审计基线（2026-03-29）；**S6 /baseline** 见 **`CR-20260330-012-s6-dual-theme-baseline.yaml`**。**实施策略 v3**：**L1（`AppColorsFunctional`/ThemeExtension）→ L2（高扇出组件）→ L3（Welcome/RTC/WebView 共享模块）**，少改 `*_page.dart`；详见 **`design.md`「减少散弹式修改」** 与 **`plan.yaml` v3**。**S7/S8** 在其它会话。  
> **审计方法**：逐文件检索 `isDarkProvider` / `AppColorsFunctional` / `AppColors.ios*`（`resolveFrom`）/ `CupertinoTheme.of(context).brightness`；委托页追溯 **实际渲染** 子树（如 `ChatConversationPage`、`ProfileShell`）；对固定渐变/黑底沉浸按 `spec.md` S6-2 登记 **exempt** 或 **partial**。  
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
| `lib/ui/welcome/pages/welcome_screen.dart` | welcome | 首启全屏 | full | | TBD | `WelcomeAppearance`（`welcome_appearance.dart`）集中品牌渐变/光斑/水滴 token；页面仅组合动效与布局。 |

---

## discovery

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/discovery/pages/home_page.dart` | discovery | Tab 根 | full | | TBD | `ref.watch(isDarkProvider)` 传入 `_buildBody` / `MomentSocialFeed` / tab strip。 |
| `lib/ui/discovery/pages/discovery_page.dart` | discovery | 壳内子视图 | full | | TBD | 网格卡角标 `ColorType.mediaThumbnailOverlay*`；竖滑视频 UI `videoImmersionOverlay*` / `videoImmersionBottomGradientEnd`；`post_preview_list_tile` 阴影 `dropShadow`。 |

---

## assistant

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/assistant/pages/assistant_tab_page.dart` | assistant | Tab 根 | full | | TBD | `isDark` 分支 + `AppColors.white/black` 仅作浅表分隔，主结构随主题。 |
| `lib/ui/assistant/pages/assistant_management_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` / 语义色混用，主背景可随主题。 |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | assistant | GoRoute | full | | TBD | 文档内容仍不控；`setBackgroundColor`→`webViewPlaceholderBackground`；信息卡与 WebView 容器 `chromeInfoCardBackground` / `chromeInfoCardBorder`；主次文 `foregroundPrimary`/`Secondary`。 |
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` + 功能色。 |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | assistant | 开发页 | full | | TBD | 具备 `isDark` 与功能色（工具页仍建议抽检）。 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` 等。 |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | assistant | GoRoute | full | | TBD | `isDarkProvider` 等。 |

---

## chat

| path | domain | entry | dual_theme | exemption_reason | owner | evidence |
|------|--------|-------|------------|------------------|-------|----------|
| `lib/ui/chat/pages/chat_page.dart` | chat | Tab 根 | full | | TBD | 子树：`streaming_scroll_fab`/`voice_message_bubble`/`chat_message_bubble`（尾阴影 `dropShadow`）/`secondary_capsule_tab_bar`（`secondaryCapsuleTrack`、角标 `badgeForeground`）等走 `AppColorsFunctional` + `brightness`。 |
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
| `lib/ui/content/entry/pages/create_page.dart` | content | 模态 | full | | TBD | 媒体格按压遮罩基色 `createMediaOverlayBase`；`ios_article_editor` 封面叠字走 `mediaThumbnailOverlay*` + `ColorType.black`；`video_editor_page` 预览区同色体系。 |
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
| `lib/ui/rtc/pages/incoming_call_page.dart` | rtc | GoRoute | full | | TBD | `CallStageChrome.backgroundGradient` + `callStageGradientStart/End`；叠字 `primaryOnGradient` 等。 |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | rtc | GoRoute | full | | TBD | 同 incoming（`call_stage_chrome.dart`）；调试面板仍 `glassSurface`/`separatorSubtle`。 |
| `lib/ui/rtc/pages/voice_call_page.dart` | rtc | GoRoute | full | | TBD | 主背景与来去电对齐：`CallStageChrome.backgroundGradient`；控件条等子树仍 `glassSurface` + `foregroundPrimary`。 |
| `lib/ui/rtc/pages/video_call_page.dart` | rtc | GoRoute | full | | TBD | 根底 `fullBleedMediaBackdrop`；顶栏渐变基色 `createMediaOverlayBase` + alpha；REC 等仍为功能色。 |
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
| `dual_theme = full` | **61** |
| `dual_theme = partial` | **0** |
| `dual_theme = exempt` | **3**（`circles_hub` T0、`unified_media_viewer`、`one_tap_movie_preview`） |
| **partial 闭环优先级（建议）** | —（S6 W1–W5 `/dev` 已清零矩阵内 `partial`；新债须再登记） |

> **说明**：`exempt` 与 `partial` 均须在发版前在 `plan.yaml`/issue 有截止或设计确认；禁止无文档永久豁免。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-29 | 全量逐页代码审计首填；补齐 `app/shell`；排除 `chat_display_fallbacks` 误计；与 `page-horizontal-quality-matrix.md` P6 对齐。 |
| 2026-03-30 | **/baseline S6**：CR-012；`plan.yaml` slices W1–W5 + matrix-sync；spec/design/acceptance 冻结；与 **S7/S8 正交**。 |
| 2026-03-30 | **方案审视**：`plan.yaml` **v3**（L1/L2/L3）；`design.md` 增补「减少散弹式修改」；`spec` S6-3 对齐。 |
| 2026-03-30 | **/baseline 再确认**（本会话）：范围仅 **S6/P6**；**S7（P7）、S8（P8）** 由其它会话并行，不阻塞本 L3 的 `/dev` slice；仍以 **CR-20260330-012** 为唯一 baseline CR。 |
| 2026-03-29 | **S6 `/dev`**：W1–W5 九处 `partial`→`full`（welcome/discovery/chat/create/RTC×4/assistant webview）；统计行与 P6 横向矩阵同步。 |

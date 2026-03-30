# 页面全量清单 × 横向质量矩阵（领域 × 类型 × P1–Pn）

> **符号**：`✓` 已落实 · `—` 本页不涉及（须在备注说明）· `○` 待落实 / 待审计  
> **命名**：**不叫「支柱」**；**P1–Pn 为可扩展横向维度**，后续新增合规项只追加列（P9…），不合并既有维度。  
> **类型**：见 [`page-horizontal-quality-spec.md`](./page-horizontal-quality-spec.md)（T1–T7，另 **T0** = 仅 barrel / 非独立页面）  
> **维护**：新增/改版页面须更新本表 + `specs/gates/page_horizontal_quality_pr_checklist.md`  
> **关联**：双色矩阵 `dual-theme-page-coverage/page-dual-theme-matrix.md`（P6 可与本表交叉引用，避免双写结论）

**扫描基线**：`quwoquan_app/lib/ui/**/pages/*_page.dart`、`lib/components/**/*_page.dart`、`lib/ui/welcome/pages/welcome_screen.dart`（无 `_page` 后缀的入口屏）、**`lib/app/shell/*.dart`**（主壳 / 底栏，P1+P6 强相关）。  
**排除**：`lib/ui/chat/pages/chat_display_fallbacks.dart` 仅为 `export`，不占行（见 `dual-theme-page-coverage/page-dual-theme-matrix.md`）。  
**P6 口径**：与 `page-dual-theme-matrix.md` 一致 — `✓`=full，`○`=partial（待按 S6 收敛），`—`=exempt。

**挂靠面（不单独占行，验收结论记在父行备注）**：`publish_location_selector_page.dart` 内 `PublishLocationSearchPage`（Navigator.push 全屏）与父行共用 P1–P8；`app_router.dart` 内 `_CreateEntryRoutePage`（`CreateEntrySheet`）从属于创作入口链，与 `create_page.dart` / 路由 `create` 一并审计。

---

## app / shell

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/app/shell/main_app_shell.dart` | T1 | ✓ | — | — | ✓ | — | ✓ | ○ | ✓ | `IndexedStack`+状态栏；`isDarkProvider` / `AppColorsFunctional` |
| `lib/app/shell/bottom_navigation.dart` | T1 | ✓ | — | — | ○ | — | ✓ | ○ | ✓ | 底栏玻璃 / `forceDark` 与壳一致 |

---

## welcome

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/welcome/pages/welcome_screen.dart` | T2 | ✓ | — | — | ○ | — | ○ | ✓ | ✓ | **P1**：`MaterialApp.home` 下 `AppScaffold` + `DefaultTextStyle.merge` 收口调试黄下划线；标语旁 `CupertinoIcons.sparkles`。P6 品牌渐变未接 system dark（S6 partial） |

---

## discovery

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/discovery/pages/home_page.dart` | T1 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | Tab 根；频道内容在壳内；P4 经 MainAppShell pageAccess；P1 内嵌 Scroll 无独立 CupertinoPageScaffold |
| `lib/ui/discovery/pages/discovery_page.dart` | T7 | ✓ | ○ | ✓ | ✓ | — | ○ | ○ | ✓ | 壳内子视图；P6 Feed 内多固定黑白（S6 partial） |

---

## assistant

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/assistant/pages/assistant_tab_page.dart` | T1 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | Tab 根；P4 MainAppShell |
| `lib/ui/assistant/pages/assistant_management_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `SettingsInsetFormPageScaffold` |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | T2 | ✓ | — | — | ○ | — | ○ | ○ | ✓ | WebView 内容域 P2/P3 —；P6 壳层固定浅色 chrome |
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `ConversationPageScaffold`/`AppScaffold`；P5 对话态标准壳 |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | T2 | ✓ | — | — | ○ | — | ✓ | ○ | ✓ | 开发工具 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | T2 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | 含 AppLog 类埋点 |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `AppScaffold`；P5 对话设置向标准壳对齐 |

---

## chat

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/chat/pages/chat_page.dart` | T1 | ✓ | ○ | ✓ | ✓ | ✓ | ○ | ○ | ✓ | Tab 根；P6 列表/胶囊等仍多 `AppColors.white` |
| `lib/ui/chat/pages/chat_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | 委托 `ChatConversationPage`，P1/P5 以会话页为准 |
| `lib/ui/chat/pages/chat_conversation_page.dart` | T7 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `ConversationPageScaffold` |
| `lib/ui/chat/pages/chat_settings_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | 聊天信息；`AppScaffold` |
| `lib/ui/chat/pages/start_group_chat_page.dart` | T4 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | 模态建群 |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | T3 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `SettingsInsetMemberPickerPageScaffold`（P5 设置表单系） |
| `lib/ui/chat/pages/group_member_search_page.dart` | T3 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `EmbeddedMemberSearchPageShell` |
| `lib/ui/chat/pages/group_manage_page.dart` | T3 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `SettingsInsetFormPageScaffold` |
| `lib/ui/chat/pages/group_admins_page.dart` | T3 | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `SettingsInsetMemberPickerPageScaffold` |

---

## circle

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | T1 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | Tab 内嵌 Scroll+Stack；无根 Scaffold；P4 MainAppShell |
| `lib/ui/circle/pages/circles_page.dart` | T1 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | `AppScaffold`；P4 MainAppShell |
| `lib/ui/circle/pages/circle_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | T5 | ✓ | ○ | ✓ | ○ | ○ | ✓ | ○ | ✓ | |
| `lib/ui/circle/pages/circle_stats_page.dart` | T3 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 | — | — | — | — | — | — | — | — | 仅 `export` `home_circles_hub_page`，不单独验收 |

---

## content

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/pages/article_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/content/pages/photo_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/content/pages/video_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/content/pages/unified_media_viewer_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | — | ○ | ✓ | 作品沉浸强制暗场；P6 exempt（S6-2） |

---

## content / entry（创作与发布子域）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/entry/pages/create_page.dart` | T4 | ✓ | ○ | ✓ | ○ | — | ○ | ○ | ✓ | 创作模态；P6 叠加层多固定色 |
| `lib/ui/content/entry/pages/article_preview_page.dart` | T5 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | T5 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | 子面 `PublishLocationSearchPage` 同结论 |
| `lib/ui/content/entry/pages/video_editor_page.dart` | T5 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/content/entry/pages/publish_circle_select_page.dart` | T5 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |

---

## entity（主页实体）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/entity/pages/suggest_homepage_page.dart` | T4 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/entity/pages/homepage_picker_page.dart` | T4 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/entity/pages/homepage_claim_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/entity/pages/homepage_maintenance_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/entity/pages/homepage_status_report_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/entity/pages/homepage_detail_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |

---

## rtc

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ○ | ○ | ✓ | 固定欢迎渐变；P6 partial |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ○ | ○ | ✓ | 同上 |
| `lib/ui/rtc/pages/voice_call_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ○ | ○ | ✓ | 通话 UI 未完整对称材质 |
| `lib/ui/rtc/pages/video_call_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ○ | ○ | ✓ | 黑底+渐变；P6 partial |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |

---

## search

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/search/pages/global_search_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppFullscreenModalSurface`+Cupertino 控件；无根 Scaffold |
| `lib/ui/search/pages/search_network_results_page.dart` | T3 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |

---

## settings

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/settings/pages/settings_page.dart` | T2 | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ○ | ✓ | `AppScaffold`；P5 设置列表模板 |
| `lib/ui/settings/pages/developer_settings_page.dart` | T2 | ✓ | — | — | ○ | ✓ | ✓ | ○ | ✓ | 开发者页 P2/P3 — |

---

## user

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/user/pages/my_profile_page.dart` | T2 | ✓ | ○ | ✓ | ✓ | — | ✓ | ○ | ✓ | `ProfileShell`→`AppScaffold`；Tab 场景 P4 MainAppShell |
| `lib/ui/user/pages/other_profile_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `ProfileShell` |
| `lib/ui/user/pages/edit_profile_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ○ | ✓ | ○ | ✓ | |
| `lib/ui/user/pages/persona_management_page.dart` | T7 | ✓ | ○ | ✓ | ○ | ○ | ✓ | ○ | ✓ | |
| `lib/ui/user/pages/sub_account_management_page.dart` | T2 | ✓ | ○ | ✓ | ○ | ○ | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/user/pages/resonance_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | `AppScaffold` |
| `lib/ui/user/pages/profile_stats_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |
| `lib/ui/user/pages/profile_comments_page.dart` | T2 | ✓ | ○ | ✓ | ○ | — | ✓ | ○ | ✓ | |

---

## components（跨域复用全屏 / 骨架）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/components/settings_form/settings_inset_form_page.dart` | T6 | ✓ | — | — | — | ✓ | ✓ | ○ | ✓ | `SettingsInsetFormPageScaffold`；P5 复用本体 |
| `lib/components/media/image/editor/image_editor_page.dart` | T5 | ✓ | — | — | ○ | — | ✓ | ○ | ✓ | 本地编辑为主 |
| `lib/components/media/camera/camera_capture_page.dart` | T5 | ✓ | — | — | ○ | — | ✓ | — | ✓ | P7 取景区 —；壳控件 P1 已检 |
| `lib/components/media/picker/create_media_picker_page.dart` | T5 | ✓ | — | — | ○ | — | ✓ | ○ | ✓ | |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | T5 | ✓ | — | — | ○ | — | — | ○ | ✓ | 预览固定黑底白字；P6 exempt |

---

## 统计（基线）

| 类别 | 数量 |
|------|------|
| `ui/**/pages/*_page.dart`（含 T0 一行） | 56 |
| `welcome_screen.dart`（额外入口） | 1 |
| `components/**/*_page.dart` | 5 |
| `app/shell/*.dart`（主壳 + 底栏） | 2 |
| **矩阵数据行（含 T0 + shell）** | **64** |
| **需验收的独立页面行（排除 T0）** | **62** |
| **P6 = ✓（full）** | **52** |
| **P6 = ○（partial，待收敛 S6）** | **9** |
| **P6 = —（exempt 或整行 —）** | **3**（`circles_hub` T0 全列 — + `unified_media_viewer` + `one_tap_movie_preview`） |
| **当前横向列** | **P1–P8**（可扩展至 P9…） |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-29 | 初版：全量路径 + 类型 + P1–P7 默认 ○ / 显式 — |
| 2026-03-29 | 更名「横向质量矩阵」；**P7/P8 拆分**（断点响应式 vs 设计系统语义 token） |
| 2026-03-29 | **P6 与 S6 双色矩阵对齐**：补 `app/shell` 两行；逐页填 `✓/○/—`；扫描基线注明排除 `chat_display_fallbacks` |
| 2026-03-29 | **全量审计**：P1 逐页/子面挂靠结论；登记 `PublishLocationSearchPage`、`_CreateEntryRoutePage`；P4/P7 对非 Tab 页保留 ○ 待 GoRouter 级与断点专项 |
| 2026-03-29 | **P2 与 `metadata_driven_ui_gap_inventory.yaml` 对齐**：`partial`→○，`compliant`→✓，`exempt`/无云→—（见 `page-horizontal-quality-spec.md` P2、`metadata-driven-client-data-contract/explore-baseline-readiness-20260329.md`） |
| 2026-03-29 | **/baseline**：`page-horizontal-quality` L3 冻结 CR-005；`acceptance` T3/T4 证据矩阵；parent spec 商用/NFR 段落 |

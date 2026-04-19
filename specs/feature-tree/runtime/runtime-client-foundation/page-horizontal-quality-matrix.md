# 页面全量清单 × 横向质量矩阵（领域 × 类型 × P1–Pn）

> **符号**：`✓` 已落实 · `—` 本页不涉及（须在备注说明）· `○` 待落实 / 待审计  
> **命名**：**不叫「支柱」**；**P1–Pn 为可扩展横向维度**，后续新增合规项只追加列（P9…），不合并既有维度。  
> **类型**：见 [`page-horizontal-quality-spec.md`](./page-horizontal-quality-spec.md)（T1–T7，另 **T0** = 仅 barrel / 非独立页面）  
> **维护**：新增/改版页面须更新本表 + `specs/gates/page_horizontal_quality_pr_checklist.md`  
> **关联**：双色矩阵 `dual-theme-page-coverage/page-dual-theme-matrix.md`（P6 可与本表交叉引用，避免双写结论）

**扫描基线**：`quwoquan_app/lib/ui/**/pages/*_page.dart`、`lib/components/**/*_page.dart`、`lib/ui/welcome/pages/welcome_screen.dart`（无 `_page` 后缀的入口屏）、**`lib/app/shell/*.dart`**（主壳 / 底栏，P1+P6 强相关）。  
**门禁**：`scripts/verify_page_matrix_scan_complete.py` — 磁盘扫描集 **=** 矩阵路径集，且矩阵路径 **⊆** `metadata_driven_ui_gap_inventory.yaml` 的 `ui_pages`（防漏页、漏清单）。  
**帖子全链路 P2**：`post-projection-pipeline-inventory.md`；2026-04-11 已收口为清单 `compliant` + 矩阵 **P2=✓**（`unified_media_viewer` 的 P6 仍 exempt）。  
**排除**：`lib/ui/chat/pages/chat_display_fallbacks.dart` 仅为 `export`，不占行（见 `dual-theme-page-coverage/page-dual-theme-matrix.md`）。  
**P6 口径**：与 `page-dual-theme-matrix.md` 一致 — `✓`=full，`○`=partial（待按 S6 收敛），`—`=exempt。

**挂靠面（不单独占行，验收结论记在父行备注）**：`publish_location_selector_page.dart` 内 `PublishLocationSearchPage`（Navigator.push 全屏）与父行共用 P1–P8；`app_router.dart` 内 `_CreateEntryRoutePage`（`CreateEntrySheet`）从属于创作入口链，与 `create_page.dart` / 路由 `create` 一并审计；`assistant_chat_settings_page.dart` 内 `_AssistantConversationHistoryPage` 与父行共用 P1–P8。

---

## app / shell

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/app/shell/main_app_shell.dart` | T1 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | `IndexedStack`+状态栏；`isDarkProvider` / `AppColorsFunctional` |
| `lib/app/shell/bottom_navigation.dart` | T1 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 底栏玻璃 / `forceDark` 与壳一致 |

---

## welcome

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/welcome/pages/welcome_screen.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | **P1**：`MaterialApp.home` 下 `AppScaffold` + `DefaultTextStyle.merge` 收口调试黄下划线；标语旁 `CupertinoIcons.sparkles`。P6 与双色矩阵 `welcome_screen` full 对齐 |

---

## discovery

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/discovery/pages/home_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：Feed/沉浸 `PostReadSurfaceId.immersive` + wire；`MediaPostCard`/`PostSummaryView.readPresentation`；见 `post-projection-pipeline-inventory.md`；Tab 根；P4 MainAppShell |
| `lib/ui/discovery/pages/discovery_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：同 home（微趣/沉浸）；P6 与双色矩阵 `discovery_page` full 对齐 |

---

## assistant

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/assistant/pages/assistant_tab_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | Tab 根；P4 MainAppShell；P2 无页内云行 Map |
| `lib/ui/assistant/pages/assistant_management_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；P2 同左 |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | WebView 内容域 P2/P3 —；P6 壳层与双色矩阵 `assistant_reference_webview` full 对齐 |
| `lib/ui/assistant/pages/assistant_conversation_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `ConversationPageScaffold`/`AppScaffold`；P2 `AssistantTranscriptTimelineRow` + C4 协议载荷（Codec）；P5 对话态标准壳 |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 开发工具 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `AssistantLocalSessionSummaryView`；含 AppLog 类埋点 |
| `lib/ui/assistant/pages/assistant_chat_settings_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `AssistantLocalSessionSummaryView`/`AssistantSessionDetailView`；`AppScaffold` |

---

## chat

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/chat/pages/chat_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | Tab 根；P2 联系人 `ChatContactsRow`+`listContacts` DTO；P6 on-accent 字色走 `badgeForeground` |
| `lib/ui/chat/pages/chat_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 委托 `ChatConversationPage`；P2 消息链 `ChatMessageDto` + Repository 强类型 |
| `lib/ui/chat/pages/chat_conversation_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `ConversationPageScaffold`；P2 消息列表 codegen DTO |
| `lib/ui/chat/pages/chat_settings_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatGroupSettingsDto`；聊天信息；`AppScaffold` |
| `lib/ui/chat/pages/start_group_chat_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `ChatInboxDto`/`CircleDto`/`ChatConversationCreatedDto` + 向导 ViewModel；模态建群 |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 成员 DTO 过滤/展示；`SettingsInsetMemberPickerPageScaffold` |
| `lib/ui/chat/pages/group_member_search_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatConversationMemberDto`；**P5** `shell=search_embedded`（`settings_canonical_manifest`）；**P7** 按默认 B 验收 |
| `lib/ui/chat/pages/group_manage_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatGroupSettingsDto`；`SettingsInsetFormPageScaffold` |
| `lib/ui/chat/pages/group_admins_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 多选行 `ChatConversationMemberDto` |

---

## circle

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`CircleHubFeedPostEntry` presentation + dto/raw 同步；viewer `immersive`+wire；频道管理改为 iPad 全宽顶置抽屉，轻 blur / 轻 scrim / grouped surface，右对齐完成按钮与响应式 chip 间距；见 inventory |
| `lib/ui/circle/pages/circles_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `List<CircleDto>`；`AppScaffold`；P4 MainAppShell |
| `lib/ui/circle/pages/circle_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`section_creations` DTO+`PostReadSurfaceId.circleWorks`；壳 `CircleDto` 已合规 |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `CircleEditSubmitPayload` |
| `lib/ui/circle/pages/circle_stats_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CircleStats*RowViewData`；`AppScaffold` |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 | — | — | — | — | — | — | — | — | 仅 `export` `home_circles_hub_page`，不单独验收 |

---

## content

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/pages/article_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`PostReadUiBundle.detailArticle` + `projectArticleDetailView` 同 wire。P7/P8：`ArticleReadOnlyBookDeck` 等不变 |
| `lib/ui/content/pages/photo_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`PostSummaryView` + `PostReadSurfaceId.detailPhoto` |
| `lib/ui/content/pages/video_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`PostReadSurfaceId.detailVideo` |
| `lib/ui/content/pages/unified_media_viewer_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | **P2 ✓**：薄壳→`WorksImmersiveViewer`+`readPresentation`；**P6** 仍 exempt（S6-2） |

---

## content / entry（创作与发布子域）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/entry/pages/create_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromPublishConfirmSummary`（draftPreview）；P6 full。P7/P8：reader host 口径不变 |
| `lib/ui/content/entry/pages/article_typography_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromCreateEditorState` 标题/投影；书页分页不变 |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：帖子投影 N/A；`LocationPoiDto`+Settings；主预览在 create 链 |
| `lib/ui/content/entry/pages/video_editor_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：回写草稿；与 draftPreview 桥一致（类注释） |
| `lib/ui/content/entry/pages/publish_circle_select_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：帖子投影 N/A；`CircleDto`+Settings |

---

## entity（主页实体）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/entity/pages/suggest_homepage_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageSuggestionDraft` / `HomepageRepository` |
| `lib/ui/entity/pages/homepage_picker_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageSummary` |
| `lib/ui/entity/pages/homepage_claim_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageClaimRequestDraft` |
| `lib/ui/entity/pages/homepage_maintenance_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageBasicDraft` |
| `lib/ui/entity/pages/homepage_status_report_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageStatusReportDraft` |
| `lib/ui/entity/pages/homepage_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageDetail`/`HomepageShellData`；`ActivePersonaContextViewData` |

---

## rtc

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CallSessionDto`+Rtc；P6 `CallStageChrome` + `callStageGradient*`（与双色矩阵 full 一致） |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | 同 incoming；P6 full |
| `lib/ui/rtc/pages/voice_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 选人 `CallParticipantPickerRouteExtra`；P6 主舞台渐变与来去电对齐 + 顶栏玻璃 |
| `lib/ui/rtc/pages/video_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P6 `fullBleedMediaBackdrop` + 顶栏渐变 `createMediaOverlayBase` |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CallPickerParticipantRow`+Chat DTO；`AppScaffold` |

---

## search

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/search/pages/global_search_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：本页无帖子卡；帖子 `searchCard` 在 `search_network_results_page`；历史 `RecentSearchReadPresentation` |
| `lib/ui/search/pages/search_network_results_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`_openPost` `PostReadSurfaceId.searchCard`+wire；payload fromMap 仅解析边界 |

---

## settings

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/settings/pages/settings_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `AppScaffold`；P5 设置列表模板 |
| `lib/ui/settings/pages/developer_settings_page.dart` | T2 | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | 开发者页 P2/P3 — |

---

## user

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/user/pages/my_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：作品/微趣 Tab `profileWorks`/`profileMoments`+readPresentation；资料 DTO |
| `lib/ui/user/pages/other_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：同 my_profile |
| `lib/ui/user/pages/edit_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ProfileEditUpdatePayload |
| `lib/ui/user/pages/persona_management_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | UserRepository summary / PersonaDtoSurface |
| `lib/ui/user/pages/sub_account_management_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `AppScaffold` |
| `lib/ui/user/pages/resonance_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ResonanceBuddyViewData |
| `lib/ui/user/pages/profile_stats_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ProfileCircleViewData / ProfileSocialRelationRowViewData |
| `lib/ui/user/pages/profile_comments_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | CommentDto |

---

## components（跨域复用全屏 / 骨架）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/components/settings_form/settings_inset_form_page.dart` | T6 | ✓ | — | — | — | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；P5 复用本体 |
| `lib/components/media/image/editor/image_editor_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 本地编辑为主 |
| `lib/components/media/camera/camera_capture_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | — | ✓ | P7 取景区 —；壳控件 P1 已检 |
| `lib/components/media/picker/create_media_picker_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ |  |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | T5 | ✓ | — | — | ✓ | — | — | ✓ | ✓ | 预览固定黑底白字；P6 exempt |

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
| **P6 = ✓（full）** | **53** |
| **P6 = ○（partial，待收敛 S6）** | **8** |
| **P6 = —（exempt 或整行 —）** | **3**（`circles_hub` T0 全列 — + `unified_media_viewer` + `one_tap_movie_preview`） |
| **P2 = ✓（compliant）** | **52**（含帖子全链路 17 页/面，2026-04-11 收口） |
| **P2 = ○（partial，待 metadata/UI 收敛）** | **0**（帖子管线已 ✓；后续非帖子 P2 另开项） |
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
| 2026-03-29 | **/dev**：`verify_page_matrix_scan_complete.py` 接入 gate；磁盘↔矩阵↔`metadata_driven_ui_gap_inventory` 双向无漏页；挂靠面补 `_AssistantConversationHistoryPage` |
| 2026-03-30 | **S2**：全页 P2↔清单 `status` 机器核对一致；逐页对照与基线锁定见 `page-horizontal-quality/s2-metadata-driven-contract-baseline-20260330.md` |
| 2026-03-30 | **S3–S9 合卷**：S3 代码审计无页内裸 HTTP（P3 维持 ✓/—）；S4 增加 `AppPageAccessNavigatorObserver` + `page_access_log_util` + Welcome `/welcome` 埋点，P4 列全 ✓；S5/S6/S7/S8 矩阵登记与 dual-theme/门禁同向更新；剩余 **P2 ○** 登记 **PHQ-P2-TBD**（见 `CR-20260330-008`） |
| 2026-03-30 | **P2 滚动**：`ChatMessageDto` projection + `ChatRepository.listMessages` 强类型；`chat_detail`/`chat_conversation` P2 ✓；清单 **TBD 清零**（目标类名见 `metadata-driven-client-data-contract/design.md` §7） |
| 2026-03-30 | **chat 域 P2 扩面**：`ChatGroupSettingsDto` / `ChatContactSearchItemDto` / 扩展 `ChatContactRowDto`；`getGroupSettings`·`searchContacts`·`updateGroupSettings` 强类型；联系人 Tab `ChatContactsRow`；群管理/设置/成员检索 DTO 化 |
| 2026-03-30 | **`start_group_chat_page` P2 ✓**：`chat_inbox` 增 `circleId`；`ChatConversationCreatedDto` + `createConversation` 强类型；建群向导去 `listConversations`；`ChatInboxDto`/`CircleDto`/ViewModel 替代 UI Map |
| 2026-03-30 | **Phase2 发现域切片**：`discoveryFeedWireRowByPostId`；`MediaPostMoreActionConfig` 去 `post`；`discovery_page`/`home_page`/`media_post_card` 清单 compliant + 矩阵 P2 ✓ |
| 2026-03-30 | **Phase2 content 详情/沉浸**：`article_detail`/`photo_detail`/`video_detail` 去 `DataService`；`ContentRepository.getPost`/`listDiscoveryFeed`；`WorksImmersiveViewer` wire 用 `discoveryFeedWireRowByPostId` |
| 2026-03-30 | **Phase2 content/entry 五页**：`PublishSettings.locationPoi`；`CreateCircleOption.fromCircleDto`；`ContentPublishDraftComposite` typedef；清单 content 域 entry 全 compliant |
| 2026-03-30 | **帖子投影管线**：新增 `post-projection-pipeline-inventory.md`；清单帖子相关行改 `partial`（增 `target_read_projection`/`target_edit_draft`）；矩阵 **P2 ○** 17 行直至 ReadPresentation+Draft+Wire 收口后再改 ✓ |
| 2026-03-30 | **Phase3 user 八页**：`ProfileSocialRelationRowViewData`；`listProfileCircles`；`PersonaManagementPage` 接 `UserRepository`；`ResonanceBuddyViewData`；`ProfileEditUpdatePayload`；`UserProfileViewData`/`PersonaDtoSurface` typedef |
| 2026-03-30 | **Phase4 circle 五页**：`CircleStatsViewData`/`circleStats` 去 raw Map；`circles_page` `List<CircleDto>`；`CircleEditSubmitPayload`；`CircleHubFeedPostEntry`+`HomeCirclesCategoryTab` `PostBaseDto`；`CircleStats*RowViewData`；清单 circle 域 non-exempt 全 compliant |
| 2026-03-30 | **Phase5 entity 六页**：`homepage_models.dart` 迁至 `runtime/generated/entity/` 并对齐 `entity/homepage/fields.yaml` 注释；`HomepageRepository` 清单；`homepage_detail` 用 `ActivePersonaContextViewData`；清单 entity 全 compliant + 矩阵 P2 ✓ |
| 2026-03-30 | **Phase6 search 两页**：`SearchCoordinator` 联系人 `ChatContactSearchItemDto`；最近搜索 `RecentSearchEntryView.toMap`；网络结果群组 `CircleSearchItemView`+`circleName`；`SearchHit` 契约注释；清单 search 全 compliant + 矩阵 P2 ✓ |
| 2026-03-30 | **Phase7–9**：rtc 选人 `CallPickerParticipantRow`+`ChatInboxDto`；路由 `CallParticipantPickerRouteExtra`；assistant 设置/技能中心 `AssistantLocalSessionSummaryView`/`AssistantSessionDetailView`；清单 rtc 全 compliant、assistant 非对话页 compliant；矩阵 P2 统计 51/1 |
| 2026-03-30 | **Assistant 对话时间轴 DTO**：`AssistantTranscriptTimelineRow`/`PersistedTimelineTurnCodec`/`AssistantFeedbackTarget`；`assistant_conversation_page` 与 bubble/answer 对外 API 用 transcript row；清单 assistant 对话页 compliant；矩阵 P2 余量清零（52/0） |
| 2026-04-11 | **帖子 ReadPresentation + Surface 全量收口**：`PostReadProjectionFacade`/`PostReadUiBundle`；发现/圈子/资料/详情/搜索/创作链/分享模板接表面枚举与 wire；清单 content/circle/user/search 帖子相关行 compliant；矩阵上述 17 行 P2 ✓；见 `post-projection-pipeline-inventory.md` §4 |
| 2026-03-29 | **P3 Mock/Remote 收口**：`ui_mock_isolation_allowlist` 清零；聊天/圈子/搜索/global_surface 数据经 `ChatRepository`/`CircleRepository`/`AppContentRepository`；`RemoteAppContentRepository` 不再委托 Mock（空态/最小 Map）；`APP_DATA_SOURCE` + Release 隐藏开发者数据源开关；`main_prod.dart` + CI `flutter build macos` 带 `dart-define` |
| 2026-03-30 | **S7/P7 默认 B** + **`search_embedded`**：`GroupMemberSearchPage` 纳入 `settings_canonical_manifest`；`verify_settings_canonical` 校验 `EmbeddedMemberSearchPageShell`；§4.3 增 C 类；`page-horizontal-quality-spec` / `nine-session-rollout-plan` 写明 P7 默认策略 B |
| 2026-03-30 | **S8/P8**：`verify_dart_semantic` 全仓无命中；`.verify_dart_semantic_baseline.txt` 清空（仅注释）；增补 `AppSpacing.zero`/`textLineHeightSingle`、`AppColors.networkCallQualityWeak`、HSL 八色 token；见 `s8-p8-semantic-token/plan.yaml` 各 slice 已实施 |
| 2026-04-11 | **元数据驱动分波（续）**：`MediaPostCard`/`RecentSearchReadPresentation`/`ContentBehaviorBatchEventDto` 等；同日本仓完成帖子全链 P2 ✓（见上行） |

# 页面全量清单 × 横向质量矩阵（领域 × 类型 × P1–Pn）

> **符号**：`✓` 已落实 · `—` 本页不涉及（须在备注说明）· `○` 待落实 / 待审计  
> **命名**：**不叫「支柱」**；**P1–Pn 为可扩展横向维度**，后续新增合规项只追加列（P9…），不合并既有维度。  
> **类型**：见 [`page-horizontal-quality-spec.md`](./page-horizontal-quality-spec.md)（T1–T7，另 **T0** = 仅 barrel / 非独立页面）  
> **维护**：新增/改版页面须更新本表 + `specs/gates/page_horizontal_quality_pr_checklist.md`  
> **关联**：双色矩阵 `dual-theme-page-coverage/page-dual-theme-matrix.md`（P6 可与本表交叉引用，避免双写结论）

**扫描基线**：`quwoquan_app/lib/ui/**/pages/*_page.dart`、`lib/components/**/*_page.dart`、`lib/ui/welcome/pages/welcome_screen.dart`（无 `_page` 后缀的入口屏）、**`lib/app/shell/*.dart`**（主壳 / 底栏，P1+P6 强相关）。  
**门禁**：`quwoquan_app/scripts/runtime/verify_page_matrix_scan_complete.py` — 磁盘扫描集 **=** 矩阵路径集，且矩阵路径 **⊆** `metadata_driven_ui_gap_inventory.yaml` 的 `ui_pages`（防漏页、漏清单）。  
**帖子全链路 P2**：`post-projection-pipeline-inventory.md`；2026-04-11 已收口为清单 `compliant` + 矩阵 **P2=✓**（`unified_media_viewer` 的 P6 仍 exempt）。  
**排除**：`lib/ui/chat/pages/chat_display_fallbacks.dart` 仅为 `export`，不占行（见 `dual-theme-page-coverage/page-dual-theme-matrix.md`）。  
**P6 口径**：与 `page-dual-theme-matrix.md` 一致 — `✓`=full，`○`=partial（待按 S6 收敛），`—`=exempt。

**挂靠面（不单独占行，验收结论记在父行备注）**：`publish_location_selector_page.dart` 内 `PublishLocationSearchPage`（Navigator.push 全屏）与父行共用 P1–P8；`app_router.dart` 内 `_CreateEntryRoutePage`（`CreateEntrySheet`）从属于创作入口链，与 `create_page.dart` / 路由 `create` 一并审计。

**对外引流（CR-20260606-030，规格冻结，暂不占行）**：`outbound-share-distribution` 的统一分享面板为 overlay/sheet（非 `*_page.dart`）、`external-inbound-deeplink-routing` 的 `DeepLinkResolver` 为非页面 runtime 能力，二者均不进入页面扫描基线、不新增矩阵行；落地实现引入新 `*_page.dart`（如未来公开 Web 对象页/分享详情页）时再按基线补行。Web 安装转化扩展落在既有 `lib/app/shell/web_app_install_banner.dart` 与 `lib/app/shell/web_main_app_shell.dart` 行（见 `public-content-web-entry` 多对象 SEO/中转页扩展），实现时在对应父行备注登记，不新增行。

---

## app / shell

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/app/shell/main_app_shell.dart` | T1 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 五栏 `IndexedStack`+状态栏；小趣退出底栏；移动端未登录点击消息/我的进入登录门禁，PC Web 不弹独立登录覆盖层；`isDarkProvider` / `AppColorsFunctional`；2026-05-17 收口底部安全区与底栏背景一体化，避免 home indicator 机型下缘留白过厚；regular 档底栏高度同步降到紧凑基线 |
| `lib/app/shell/bottom_navigation.dart` | T1 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 五栏底栏；C 位创作触发 `/create-entry`；底栏背景 / `forceDark` 与壳一致；2026-05-17 底栏内容改为占满含底部安全区总高、顶部留白与底部安全区对称，并在有圆角/indicator 机型增加左右保护量；2026-05-19 图标/label/阴影接入 chrome 语义 token，视觉基线不变 |
| `lib/app/shell/web_app_install_banner.dart` | T1 | ✓ | — | — | — | — | ✓ | ✓ | ✓ | Web 顶部 App 安装提示；由 `PlatformCapabilities.promotesAppInstall` 控制，手机/Pad 提供下载与分享安装页，PC 提供 iOS/Android(鸿蒙)安装包入口；P7 走 `AppSpacing.wideBreakpoint`/`webContentMaxWidth`，P8 走 `UITextConstants`/`AppColors`/`AppTypography` |
| `lib/app/shell/web_main_app_shell.dart` | T1 | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | ✓ | PC Web 独立宽屏壳；顶部短欢迎区复用移动端 `WelcomeFlowerMark` 花瓣动效并居中展示品牌簇，不放登录/下载提示，内容页在欢迎区下方并随滚动推入/拉回，工具栏吸顶后再出现 `趣我圈` 花瓣图标/名称且左侧 tab 槽位稳定；Web 启动欢迎已改为 `QuWoQuanAppRoot` 上的 intro overlay（`WelcomeScreen.deferSequenceStart`），shell 仅承载内容首屏 hero，不再作为独立欢迎/登录主流程；右侧五个一级操作仅显示同尺寸图标并保留语义 label；**2026-06-06 商用收口**：首页/精品内容区改为复用移动端 `HomeMultiFormFeed`（多列瀑布 + 四态 + `referralSource: organicFeed`/`feedRequestId` 同源埋点），post 点击经统一 `openHomeFeedPost` → `MediaViewerExtra(dtoPosts)` 进沉浸 viewer（P3 端云一体复用 `discoveryFeed`/`PostBaseDto`，不另起 Web 数据/埋点链）；精品移除「精品队列」改干净多列墙；添加页复用分组模型分「内容创作/社交关系」两组（含发起群聊/加同好/创建圈子）并去掉「小趣创作助手」；消息右栏「消息助手」→「消息中心」且去掉「小趣」助手 tab；「我的」右栏去掉「多端同步」；字号/列宽/最大宽度走 Web PC 专用语义 token；P7 走 `PlatformCapabilities.wideScreenLayout`/`AppSpacing.wideBreakpoint`，P8 走既有 `AppColors`/`AppTypography`/`AppSpacing` token |
| `lib/app/shell/web_main_app_shell_auth.dart` | T0 | — | — | — | — | — | — | — | — | `web_main_app_shell.dart` 的 `part` helper；仅承载 PC Web 登录守卫与规格类，不是独立页面，验收归入父壳 |

---

## welcome

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/welcome/pages/welcome_screen.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | **P1**：启动 fast path 先以 `MaterialApp.home` 直出 `AppScaffold` 欢迎页，首帧已有品牌花瓣与文案；`DefaultTextStyle.merge` 收口调试黄下划线。P6 与双色矩阵 `welcome_screen` full 对齐；2026-06 Web intro overlay 改用 `deferSequenceStart`，让动效在内容页首帧后再启动；启动登录 prompt 不再进入 Web 主流程；2026-05-19 登记为品牌屏 chrome 豁免，无传统 toolbar |

---

## discovery

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/discovery/pages/home_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：Feed/沉浸 `PostReadSurfaceId.immersive` + wire；`MediaPostCard`/`PostSummaryView.readPresentation`；见 `post-projection-pipeline-inventory.md`；Tab 根为关注/推荐 + 校园/旅行/摄影/科技/车之家，默认推荐；P4 MainAppShell；2026-05-21 旅行/摄影图片使用页内轮播并禁用图片沉浸跳转，P7/P8 分列保持 ✓ |
| `lib/ui/discovery/pages/discovery_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：同 home（微趣/沉浸）；P6 与双色矩阵 `discovery_page` full 对齐；2026-05-19 顶部主导航接入 `appChromeTopSafeInset`/`appChromeTopBarHeight` |

---

## assistant

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/assistant/pages/assistant_management_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；P2 同左 |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | WebView 内容域 P2/P3 —；P6 壳层与双色矩阵 `assistant_reference_webview` full 对齐 |
| `lib/ui/assistant/pages/personal_assistant_conversation_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | “找私助”唯一入口；P2 `AssistantConversationWire`/`AssistantTurnEnvelopeWire`/`AssistantStreamEventWire`/`SkillSubscriptionWire` + `AppMessageWire`；P3 经 `assistantRepositoryProvider`/`appMessageRepositoryProvider` Mock/Remote；用户 query 与主动 AppMessage 均投影到统一 transcript；2026-05-19 导航栏接入 `AppNavigationBar`，设置/返回和底部输入栏接入 appChrome/chatInput token，并补 runArtifacts 脏数据兼容 |
| `lib/ui/assistant/pages/assistant_dev_replay_page.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 开发工具 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `AssistantSkillCatalogItemView`/`SkillSubscriptionWire` + `AssistantLocalSessionSummaryView`；P3 经 `assistantRepositoryProvider` Mock/Remote；含 AppLog 类埋点 |

---

## chat

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/chat/pages/chat_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 消息体系商用重构入口；消息/联系为消息模块内两个独立一级页面状态，均无内联搜索框并统一走顶部工具栏搜索入口；消息筛选收口为 `全部/未读/群聊/私聊/通知`，联系筛选收口为 `全部/互关/圈子/群聊`；P2 以 `MessageHomeRowDto`、`ContactHomeRowDto`、`AppMessage`/notification inbox 和交集摘要 read model 为真相源，App 不拼来源/交集/成员数；打开会话后统一刷新全部消息筛选引用的已读状态；群头像只消费服务端预合成 `avatarUrl`，禁止端侧群成员九宫格 fallback；P3 生产 Remote-only，Mock 仅作 contract fixture |
| `lib/ui/chat/pages/chat_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 委托 `ChatConversationPage`；P2 消息链 `ChatMessageDto` + Repository 强类型 |
| `lib/ui/chat/pages/chat_conversation_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `ConversationPageScaffold`；P2 消息列表 `ChatMessageDto` + `ChatMessageDisplayItem` 强类型展示链；2026-05-19 三点入口、选择态文字操作与默认单行输入栏统一到 appChrome/chatInput token；2026-05-30 语音消息接入 `VoiceRecorder`/`voiceSendProvider`，compact 输入栏收敛 `@小趣` 防挤压，语音发送沿 metadata `audio` 契约；2026-06-06 body 外包统一 `WebPageMaxWidthFrame`（宽屏内容区限宽居中、左右用 page background 区分阅读区，移动端透传），时间分隔按 `sentAtIso` 间隔（≥5min）降噪 |
| `lib/ui/chat/pages/chat_settings_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `GroupHomeDto` + `ChatGroupSettingsDto`；聊天信息/群主页入口消费 `GetGroupHome` 的来源、公告、成员数和能力；`AppScaffold`；P7 成员网格按头像与文字高度计算；2026-05-19 登记为三点入口链路设置 Inset chrome |
| `lib/ui/chat/pages/start_group_chat_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `ChatInboxDto`/`CircleDto`/`ChatConversationCreatedDto` + 向导 ViewModel；模态建群；选择群聊页与主列表共享会话头像 token / 占位视觉 |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 成员 DTO 过滤/展示；`SettingsInsetMemberPickerPageScaffold` |
| `lib/ui/chat/pages/group_member_search_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatConversationMemberDto`；**P5** `shell=search_embedded`（`settings_canonical_manifest`）；**P7** 按默认 B 验收 |
| `lib/ui/chat/pages/group_manage_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatGroupSettingsDto`；`SettingsInsetFormPageScaffold`；2026-05-19 登记为聊天设置链路 Inset chrome |
| `lib/ui/chat/pages/group_admins_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 多选行 `ChatConversationMemberDto`；2026-05-19 完成按钮接入 `AppNavigationBarTextAction` |

---

## circle

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`CircleHubFeedPostEntry` presentation + dto/raw 同步；viewer `immersive`+wire；频道管理改为五垂类阶段隐藏；2026-05-21 首页垂类固定为校园/旅行/摄影/科技/车之家，群组瀑布流恢复默认双列自适应，旅行/摄影图片使用页内轮播，P7/P8 分列保持 ✓ |
| `lib/ui/circle/pages/circles_page.dart` | T1 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `List<CircleDto>`；`AppScaffold`；P4 MainAppShell |
| `lib/ui/circle/pages/circle_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`section_creations` DTO+`PostReadSurfaceId.circleWorks`；壳 `CircleDto` 已合规；对象页网络 IA 收敛为 `首页/内容/群或组织/成员`，首屏接 `ObjectPageContext` 小趣行动 dock |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `CircleEditSubmitPayload` |
| `lib/ui/circle/pages/circle_stats_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CircleStats*RowViewData`；`AppScaffold` |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 | — | — | — | — | — | — | — | — | 仅 `export` `home_circles_hub_page`，不单独验收 |

---

## content

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/pages/unified_media_viewer_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | **P2 ✓**：薄壳→`WorksImmersiveViewer`+`readPresentation`；**P6** 仍 exempt（S6-2）；2026-05-19 进入沉浸媒体时使用 appChrome 压缩 safeTop，对齐首页精品顶栏 |
| `lib/ui/content/pages/work_browser_entry_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | `workBrowser` 统一深链入口；P2 `WorkBrowserItemDto`/`PostReadPresentation` + `ContentRepository` 定位队列；P3 走 `contentRepositoryProvider` Mock/Remote；P6 跟随 `WorksImmersiveViewer` 深色沉浸与文章 Dark Paper |

---

## content / entry（创作与发布子域）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/entry/pages/create_page.dart` | T4 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromPublishConfirmSummary`（draftPreview）+ `CreatePostRequestWire` 写入 `summary/tagRefs/entityRefs/assistantUsePolicy`；P6 full。P7/P8：reader host 与发布 sheet token 口径不变 |
| `lib/ui/content/entry/pages/article_typography_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromCreateEditorState` 标题/投影；书页分页不变；2026-05-19 黑场顶栏 safeTop/按钮尺寸接入 appChrome |
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
| `lib/ui/entity/pages/homepage_detail_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageDetail`/`HomepageShellData`/`ObjectPageBundle`；对象页网络 IA 为 `首页/内容/口碑/关联`，首屏消费 `IntersectionReason`/`ObjectRelationEdge`/`ObjectPageContext`；2026-05-19 overlay 顶栏 safeTop/按钮节奏接入资料页 appChrome token |
| `lib/ui/entity/pages/homepage_introduction_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `HomepageIntroduction`/`HomepageIntroductionSection`；完整介绍页，P5 非设置/半屏表单 |

---

## rtc

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CallSessionDto`+Rtc；P6 `CallStageChrome` + `callStageGradient*`（与双色矩阵 full 一致）；2026-05-19 登记为通话舞台 chrome 豁免 |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | 同 incoming；P6 full；2026-05-19 登记为通话舞台 chrome 豁免 |
| `lib/ui/rtc/pages/voice_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 选人 `CallParticipantPickerRouteExtra`；P6 主舞台渐变与来去电对齐 + 顶栏玻璃；2026-05-19 登记为通话舞台 chrome 豁免 |
| `lib/ui/rtc/pages/video_call_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P6 `fullBleedMediaBackdrop` + 顶栏渐变 `createMediaOverlayBase`；2026-05-19 登记为通话舞台 chrome 豁免 |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `CallPickerParticipantRow`+Chat DTO；`AppScaffold` |

---

## search

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/search/pages/global_search_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：本页无帖子卡；帖子 `searchCard` 在 `search_network_results_page`；记录 `RecentSearchReadPresentation`；2026-05-19 返回按钮热区与图标尺寸接入 appChrome token |
| `lib/ui/search/pages/search_network_results_page.dart` | T3 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：`_openPost` `PostReadSurfaceId.searchCard`+wire；payload fromMap 仅解析边界；2026-05-21 业务垂类后缀与圈子首页同源五项且过滤旧推荐/遇见/人文等垂类 |

---

## settings

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/settings/pages/settings_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `AppScaffold`；P5 设置列表模板；登录态显示切换账号/退出登录，未登录显示登录入口；2026-06-06 body 外包统一 `WebPageMaxWidthFrame`，宽屏内容区限宽居中 |
| `lib/ui/settings/pages/developer_settings_page.dart` | T2 | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | 开发者页 P2/P3 —；2026-06-06 body 外包统一 `WebPageMaxWidthFrame`，宽屏内容区限宽居中 |

---

## user

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/ui/user/pages/my_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：对象页网络 Tab 显示口径收敛为 `看点/作品/圈子/互动`（底层仍由 codegen `UserProfileUIConfig.profileTabs` 驱动）；创作/生活强类型 DTO 不变；首屏接 `ObjectPageContext` 小趣行动 dock。**V5 埋点**：进入曝光 + dispose 停留（`contentBehaviorTracker`，contentType=user，referralSource=authorProfile）；other 模式交集卡 `onReasonTap` → `BehaviorEvent.intersectionDimension/intersectionTagRefs` 归因 |
| `lib/ui/user/pages/login_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | P2 `AuthRepository.loginOneTap/loginWechat/loginApple/loginPasskey` + `AuthLoginResultDto`；P3 Mock/Remote 由 `authRepositoryProvider` 切换；微信 / Apple / Credential Manager / passkey 入口由 `PlatformCapabilities + NativeAuthBridge` 预留并降级，协议勾选前不调用原生登录 SDK |
| `lib/ui/user/pages/legal_document_page.dart` | T2 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 远端 WebView 展示用户协议/隐私政策；P2/P3 —，内容来自配置 URL；禁用 JS，保留返回与失败重试 |
| `lib/ui/user/pages/other_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：同 my_profile；other 模式展示真实交集卡 |
| `lib/ui/user/pages/my_intersection_inbox_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：我的交集分维度列表，消费 `GET /v1/content/intersections`（list）+ `POST /v1/content/intersections/visit`（打开即推进已读水位清零）；强类型 `IntersectionReason`；统一原子 `IntersectionEntity`（头像+名字+维度chip，概率标「推荐」）；P3 Mock/Remote 经 `intersectionRepositoryProvider` 切换；空/错误兜底；点条目带 `relationKind` 进对象页 |
| `lib/ui/user/pages/my_footprint_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | **P2 ✓**：我的足迹私有只读列表，消费 `GET /v1/content/footprint`（type 过滤 + cursor 分页）；强类型 `FootprintEntry`；P3 Mock/Remote 经 `footprintRepositoryProvider` 切换；type 枚举由云侧定义、端侧只透传；空/错误/分页兜底；点条目按 R21 带 referralSource 进作品浏览器 |
| `lib/ui/user/pages/edit_profile_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ProfileEditUpdatePayload |
| `lib/ui/user/pages/persona_management_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | UserRepository summary / PersonaDtoSurface |
| `lib/ui/user/pages/profile_stats_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ProfileCircleViewData / ProfileSocialRelationRowViewData |
| `lib/ui/user/pages/profile_comments_page.dart` | T2 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | CommentDto |

---

## components（跨域复用全屏 / 骨架）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | 备注 |
|------|------|----|----|----|----|----|----|----|----|------|
| `lib/components/settings_form/settings_inset_form_page.dart` | T6 | ✓ | — | — | — | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；P5 复用本体 |
| `lib/components/media/image/editor/image_editor_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 本地编辑为主；2026-05-19 编辑器黑场顶栏 safeTop/按钮尺寸接入 appChrome |
| `lib/components/media/camera/camera_capture_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | — | ✓ | P7 取景区 —；壳控件 P1 已检；2026-05-19 登记为相机/选择器专用 chrome |
| `lib/components/media/picker/create_media_picker_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | 2026-05-19 登记为媒体选择器专用 chrome |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | T5 | ✓ | — | — | ✓ | — | — | ✓ | ✓ | 预览固定黑底白字；P6 exempt |

---

## 统计（基线）

| 类别 | 数量 |
|------|------|
| `ui/**/pages/*_page.dart`（含 T0 一行） | 58 |
| `welcome_screen.dart`（额外入口） | 1 |
| `components/**/*_page.dart` | 5 |
| `app/shell/*.dart`（主壳 + 底栏 + Web 安装提示 + PC Web 宽屏壳） | 4 |
| **矩阵数据行（含 T0 + shell）** | **67** |
| **需验收的独立页面行（排除 T0）** | **63** |
| **P6 = ✓（full）** | **54** |
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
| 2026-05-07 | **chat 强类型收口**：`LocalChatSearchStore` 联系人/会话快照改具名记录；`SearchHitPayloadChatContact` 收口 chat contact payload；`MockChatRepository` 内部缓存转 typed state；`chat_conversation_page` / `ChatMessageBubble` / `ConversationMessageActionMenuOverlay` 改消费 `ChatMessageDisplayItem` |
| 2026-05-17 | **主壳安全区节奏收口**：`main_app_shell`/`bottom_navigation`/`home_page`/`chat_page` 调整顶部与底部安全区消费方式；底栏改为背景吃满底部安全区、内容上下对称收口；首页与消息页主顶栏 regular 档降到紧凑基线，并让关注/精品切换共用同一顶栏几何与 T2 位置稳定回归测试 |
| 2026-03-29 | **P3 Mock/Remote 收口**：`ui_mock_isolation_allowlist` 清零；聊天/圈子/搜索/global_surface 数据经 `ChatRepository`/`CircleRepository`/`AppContentRepository`；`RemoteAppContentRepository` 不再委托 Mock（空态/最小 Map）；`APP_DATA_SOURCE` + Release 隐藏开发者数据源开关；`main_prod.dart` + CI `flutter build macos` 带 `dart-define` |
| 2026-03-30 | **S7/P7 默认 B** + **`search_embedded`**：`GroupMemberSearchPage` 纳入 `settings_canonical_manifest`；`verify_settings_canonical` 校验 `EmbeddedMemberSearchPageShell`；§4.3 增 C 类；`page-horizontal-quality-spec` / `nine-session-rollout-plan` 写明 P7 默认策略 B |
| 2026-03-30 | **S8/P8**：`verify_dart_semantic` 全仓无命中；`.verify_dart_semantic_baseline.txt` 清空（仅注释）；增补 `AppSpacing.zero`/`textLineHeightSingle`、`AppColors.networkCallQualityWeak`、HSL 八色 token；见 `s8-p8-semantic-token/树内计划文档` 各 slice 已实施 |
| 2026-04-11 | **元数据驱动分波（续）**：`MediaPostCard`/`RecentSearchReadPresentation`/`ContentBehaviorBatchEventDto` 等；同日本仓完成帖子全链 P2 ✓（见上行） |
| 2026-06-06 | **Web 商用体验系统收口**：`web_main_app_shell` 首页/精品复用移动端 `HomeMultiFormFeed`（多列瀑布 + 四态 + `referralSource`/`feedRequestId` 同源埋点），post 经统一 `openHomeFeedPost`(`home_feed_post_open_action.dart`)→`MediaViewerExtra(dtoPosts)` 进沉浸 viewer；精品移除「精品队列」；添加页分「内容创作/社交关系」两组（发起群聊/加同好/创建圈子）去「小趣创作助手」；消息右栏「消息助手」→「消息中心」并去「小趣」助手 tab；新增单一抽象 `WebPageMaxWidthFrame` 收口消息/设置/开发者页宽屏最大宽度，会话页时间分隔按 `sentAtIso` 间隔降噪；「我的」右栏去「多端同步」；新增 T2：`web_page_max_width_frame_test`/`web_create_groups_test`/`web_featured_no_queue_test`/`web_feed_post_tap_viewer_test`/`web_chat_frame_test` + 扩展 `main_app_shell_widget_test`（feed 同源断言） |

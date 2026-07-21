# 页面全量清单 × 横向质量矩阵（领域 × 类型 × P1–Pn）

> **符号**：`✓` 已落实 · `—` 本页不涉及（须在备注说明）· `○` 待落实 / 待审计
> **命名**：**不叫「支柱」**；**P1–Pn 为可扩展横向维度**，后续新增合规项只追加列（P10…），不合并既有维度。
> **类型**：见 [`page-horizontal-quality-spec.md`](./page-horizontal-quality-spec.md)（local_contract–T7，另 **T0** = 仅 barrel / 非独立页面）
> **维护**：新增/改版页面须更新本表 + `specs/gates/page_horizontal_quality_pr_checklist.md`
> **关联**：双色矩阵 `dual-theme-page-coverage/page-dual-theme-matrix.md`（P6 可与本表交叉引用，避免双写结论）

**扫描基线**：`quwoquan_app/lib/ui/**/pages/*_page.dart`、`lib/components/**/*_page.dart`、`lib/ui/welcome/pages/welcome_screen.dart`（无 `_page` 后缀的入口屏）、**`lib/app/shell/*.dart`**（主壳 / 底栏，P1+P6+P9 强相关）。
**门禁**：`quwoquan_app/scripts/runtime/verify_page_matrix_scan_complete.py` — 磁盘扫描集 **=** 矩阵路径集，且矩阵路径 **⊆** `metadata_driven_ui_gap_inventory.yaml` 的 `ui_pages`（防漏页、漏清单）。
**职责边界**：本表只承载页面类型与 P1–P9 横向质量结论；页面到业务对象、路由、Surface、Query Slice、鉴权、能力位和 telemetry 的唯一契约是 `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`，禁止在本表复制对象绑定。
**帖子全链路 P2**：`post-projection-pipeline-inventory.md`；2026-04-11 已收口为清单 `compliant` + 矩阵 **P2=✓**（`unified_media_viewer` 的 P6 仍 exempt）。
**排除**：`lib/ui/chat/pages/chat_display_fallbacks.dart` 仅为 `export`，不占行（见 `dual-theme-page-coverage/page-dual-theme-matrix.md`）。
**P6 口径**：与 `page-dual-theme-matrix.md` 一致 — `✓`=full，`○`=partial（待按 S6 收敛），`—`=exempt。
**P9 口径**：`✓`=已在页面清单登记等待模式和运行中证据，`—`=纯静态/无异步请求；P9 禁止 `○`。

**挂靠面（不单独占行，验收结论记在父行备注）**：`publish_location_selector_page.dart` 内 `PublishLocationSearchPage`（Navigator.push 全屏）与父行共用 P1–P9；`app_router.dart` 内 `_CreateEntryRoutePage`（`CreateEntrySheet`）从属于创作入口链，与 `create_page.dart` / 路由 `create` 一并审计。

**对外引流（CR-20260606-030，规格冻结，暂不占行）**：`outbound-share-distribution` 的统一分享面板为 overlay/sheet（非 `*_page.dart`）、`external-inbound-deeplink-routing` 的 `DeepLinkResolver` 为非页面 runtime 能力，二者均不进入页面扫描基线、不新增矩阵行；落地实现引入新 `*_page.dart`（如未来公开 Web 对象页/分享详情页）时再按基线补行。Web 安装转化扩展落在既有 `lib/app/shell/web_app_install_banner.dart` 与 `lib/app/shell/web_main_app_shell.dart` 行（见 `public-content-web-entry` 多对象 SEO/中转页扩展），实现时在对应父行备注登记，不新增行。

---

## app / shell

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/app/shell/main_app_shell.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 六栏 `IndexedStack`+状态栏（含同频/广场）；小趣退出底栏；移动端未登录点击消息/我的进入登录门禁，同频/广场游客可浏览；PC Web 不弹独立登录覆盖层；`isDarkProvider` / `AppColorsFunctional`；2026-06-18 非首页页签改为首次访问后再初始化；2026-07-01 底栏 `+` 动作面板走统一 modal presenter，页面亮度原地 fade、面板独立 slide，动作 intent 等待关闭完成后再导航；2026-07-20 RTC PiP 长按挂断等待真实 `HangupCall` 成功后才清理 active call，失败保留通话与恢复路径；2026-07-21 页面体验 TTI 从实际 Tab 导航起点计时，首帧与首个可用终态不再从 post-frame 回调起算 |
| `lib/app/shell/bottom_navigation.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 五项底栏（发现/视频书/创作/联系/我）；C 位创作触发动作面板；「同趣 / 兴趣配对」不再占底栏常驻 tab，改由加号动作面板进入；底栏背景 / `forceDark` 与壳一致；创作面板不再依赖随 sheet 上滑的可见蒙皮 |
| `lib/app/shell/object_detail_global_bottom_nav.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 对象页（实体/圈子主页）详情态全局底栏适配器，复用 `BottomNavigationWidget` 与主壳同款 token/图标/尺寸；浏览态不高亮任一项（传越界 index），加号触发 `GlobalQuickActionSheet`、其余 tab `context.go` 回对应根 tab；对象页加号同主壳走统一 modal presenter；由实体/圈子 shell widget 测试覆盖 |
| `lib/app/shell/web_app_install_banner.dart` | local_contract | ✓ | — | — | — | — | ✓ | ✓ | ✓ | — | Web 顶部 App 安装提示；由 `PlatformCapabilities.promotesAppInstall` 控制，手机/Pad 提供下载与分享安装页，PC 提供 iOS/Android(鸿蒙)安装包入口；P7 走 `AppSpacing.wideBreakpoint`/`webContentMaxWidth`，P8 走 `UITextConstants`/`AppColors`/`AppTypography` |
| `lib/app/shell/web_main_app_shell.dart` | local_contract | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | PC Web 独立宽屏壳；顶部短欢迎区复用移动端 `WelcomeFlowerMark` 花瓣动效并居中展示品牌簇，不放登录/下载提示，内容页在欢迎区下方并随滚动推入/拉回，工具栏吸顶后再出现 `趣我圈` 花瓣图标/名称且左侧 tab 槽位稳定；Web 启动欢迎已改为 `QuWoQuanAppRoot` 上的 intro overlay（`WelcomeScreen.deferSequenceStart`），shell 仅承载内容首屏 hero，不再作为独立欢迎/登录主流程；右侧五个一级操作仅显示同尺寸图标并保留语义 label；**2026-06-06 商用收口**：首页/精品内容区改为复用移动端 `HomeMultiFormFeed`（多列瀑布 + 四态 + `referralSource: organicFeed`/`feedRequestId` 同源埋点），post 点击经统一 `openHomeFeedPost` → `MediaViewerExtra(dtoPosts)` 进沉浸 viewer（P3 端云一体复用 `discoveryFeed`/`PostBaseDto`，不另起 Web 数据/埋点链）；精品移除「精品队列」改干净多列墙；添加页复用分组模型分「内容创作/社交关系」两组（含发起群聊/加同好/创建圈子）并去掉「小趣创作助手」；消息右栏「消息助手」→「消息中心」且去掉「小趣」助手 tab；「我的」右栏去掉「多端同步」；字号/列宽/最大宽度走 Web PC 专用语义 token；P7 走 `PlatformCapabilities.wideScreenLayout`/`AppSpacing.wideBreakpoint`，P8 走既有 `AppColors`/`AppTypography`/`AppSpacing` token |
| `lib/app/shell/web_main_app_shell_auth.dart` | T0 | — | — | — | — | — | — | — | — | — | `web_main_app_shell.dart` 的 `part` helper；仅承载 PC Web 登录守卫与规格类，不是独立页面，验收归入父壳 |
| `lib/app/shell/web_main_app_shell_state.dart` | T0 | — | — | — | — | — | — | — | — | — | `web_main_app_shell.dart` 的 `part` helper；仅承载 PC Web 宽屏壳状态与构建拆分，不是独立页面，验收归入父壳 |

> 2026-07-17：`main_app_shell.dart` 与 `web_main_app_shell.dart` 仅在默认推荐首页处透传“非空内容已绘制”信号；实际启动可用仍由欢迎遮罩移除共同门控，P1–P9 结论不变。

---

## welcome

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/welcome/pages/welcome_screen.dart` | local_contract | ✓ | — | — | ✓ | — | — | ✓ | ✓ | — | **P1**：启动 fast path 直出 `AppScaffold` + `WelcomeStaticFrame`（品牌簇 + 底部品牌名），原生使用自适应渐变背景、同源透明品牌簇与贴底品牌名条，Flutter 首帧 `bloomAmount=1` identity 接管。2026-07-20 信息结构简化与图一高保收口：仅保留上亮下深品牌蓝渐变、八瓣花（可见直径约屏宽 40%，clamp 132~168dp）、slogan「遇见同趣，绽放热爱」（Noto Sans SC 28~32sp/600 单色主视觉）与底部品牌名「趣我圈」（18sp/500，视觉中心约 90% 屏高）；Noto Sans SC 以 OFL-1.1 + pinned commit + SHA-256 固定为正式品牌字体；欢迎页/登录品牌标/App 图标共用唯一 `WelcomeAppearance`，Android launch 颜色从 Dart token 生成。删除中央大标题、小趣低语与 ShaderMask 渐变文字；深浅色统一品牌深蓝，状态栏透明浅色内容与原生同源；品牌簇单一无障碍语义。首帧稳定 90ms 后播放约 1390ms 的「逆序聚拢→花蕊停顿→顺时针绽放」，单控制器纯函数时间轴；正常一轮 ready 即进入，3s 为 Shell 首帧目标，6s 仅为进程启动起算的硬退出门。未 ready 才在品牌名上方淡入 24px 单行 `启动中，马上进入`，最多重放两次；超预算进入安全 Shell，禁止回到欢迎页。Shell 首帧后 120ms 内移除欢迎层并记录 `overlayRemovedMs`，探针不再把“Shell 已画但仍被欢迎遮住”判为成功。Root 在 initState 即武装绝对截止，`StartupStateMachine` 只在 Router Shell 实际首帧后淡出 overlay，Router 失败进入可重试安全恢复页。`disableAnimations`、后台恢复、压缩周期与 terminal latch 均有 local_contract。品牌屏 chrome 豁免，无传统 toolbar |

---

## discovery

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/discovery/pages/home_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：Feed/沉浸 `PostReadSurfaceId.immersive` + wire；`MediaPostCard`/`PostSummaryView.readPresentation`；见 `post-projection-pipeline-inventory.md`；Tab 根为关注/推荐 + 校园/旅行/摄影/科技/车之家，默认推荐；P4 MainAppShell；2026-07-20 助手入口经 production `AssistantHalfSheet.show` 呼出真实半弹层（不再直接跳全屏），上下文个性化与首条问题透传同源；Post 更多面板挂靠本页验收：无开发中假入口，举报先选原因，负反馈全归因、即时移除且支持撤销，拉黑/屏蔽关键词具登录续接；P7/P8 分列保持 ✓ |

> 2026-07-17：仅当可见首页仍为默认 `recommend` 且 `HomeMultiFormFeed` 的非空卡片首帧完成时，才向启动 runtime 发送内容就绪信号；空态、错误态、其他频道与后台保留页不计为首页可用。

---

## assistant

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/assistant/pages/assistant_management_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；2026-07-21 管理页只读取并渲染 active preference，撤销后仅保留本次操作的窗口内恢复动作；偏好/consent operations 与 required auth 均由 metadata 对齐。P7 继续复用 Inset 响应式壳；P8 继续复用设置语义间距、字阶与双色 token。 |
| `lib/ui/assistant/pages/assistant_reference_webview_page.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | WebView 内容域 P2/P3 —；P6 壳层与双色矩阵 `assistant_reference_webview` full 对齐 |
| `lib/ui/assistant/pages/personal_assistant_conversation_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | “找私助”唯一入口；P2 `AssistantConversationWire`/`AssistantTurnEnvelopeWire`/`AssistantStreamEventWire` + `AppMessageWire`；P3 经 `assistantConversationRunFacetProvider`/`assistantLearningAppendFacetProvider`/`appMessageQueryProvider` Remote-only 装配；2026-07-20 补欢迎空态、真实 phase、结构化错误卡与原请求重试，反馈类型与工具栏选中态同源 |
| `lib/ui/assistant/pages/assistant_skill_center_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `AssistantSkillCatalogItemView`/`SkillSubscriptionWire`/`AssistantUserTaskView` + `AssistantLocalSessionSummaryView`；P3 经 `assistantPersonalDataFacetProvider`/`assistantSkillSubscriptionFacetProvider` Remote-only 装配；2026-07-20 删除 8 个本地假开关与演示订阅载荷，新增任务四态、会话展开、写失败回弹；P5 因能力仪表板非设置表单标 — |

---

## chat

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/chat/pages/chat_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 消息体系商用重构入口；消息/联系为消息模块内两个独立一级页面状态，均无内联搜索框并统一走顶部工具栏搜索入口；消息筛选收口为 `全部/未读/群聊/私聊/通知`，联系筛选收口为 `全部/互关/圈子/群聊`；P2 以 `MessageHomeRowDto`、`ContactHomeRowDto`、`AppMessage`/notification inbox 和交集摘要 read model 为真相源，App 不拼来源/交集/成员数；`未读` 胶囊数统一汇总 `ListMessageHome(unread)` 返回的 `unreadCount`，与列表未读行同源，单数字 badge 收口为圆形；打开会话后统一刷新全部消息筛选引用的已读状态；群头像只消费服务端预合成 `avatarUrl`，禁止端侧群成员九宫格 fallback；P3 生产 Remote-only，Mock 仅作 contract fixture；**2026-07-19 B11 通知维度打通**：`通知` 胶囊改由 `notificationInboxProvider`（ListAppMessages）独立渲染 `_NotificationInboxTile`，点击按 `AppMessageNavigationTarget` 真实路由并 `ReadAppMessage` 推进已读，通知胶囊未读徽标接 `GetAppMessageUnreadCount`，曝光/点击经 `JourneyEventTracker(journey=notification_inbox)`，invocation context surface 修正为 `chatList` |
| `lib/ui/chat/pages/greeting_inbox_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | GreetingRequest 独立收发箱；收到侧支持回复升级会话/忽略，发出侧支持撤回，pending/replied/ignored/blocked/cancelled/expired 全状态回显；加载与动作错误均消费 runtime semantic，路由 page access + greeting 关键动作埋点；P5 —（非推荐内容消费页） |
| `lib/ui/chat/pages/chat_conversation_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `ConversationPageScaffold`；P2 消息列表 `ChatMessageDto` + `ChatMessageDisplayItem` 强类型展示链；2026-05-19 三点入口、选择态文字操作与默认单行输入栏统一到 appChrome/chatInput token；2026-05-30 语音消息接入 `VoiceRecorder`/`voiceSendProvider`，compact 输入栏收敛 `@小趣` 防挤压，语音发送沿 metadata `audio` 契约；2026-06-06 body 外包统一 `WebPageMaxWidthFrame`（宽屏内容区限宽居中、左右用 page background 区分阅读区，移动端透传），时间分隔按 `sentAtIso` 间隔（≥5min）降噪；2026-07-19 B12 主文件拆为 lifecycle/render 519 行 + actions 862 行，补 loading/空会话/可重试错误三态；2026-07-20 群聊 `@` 输入接入服务端 `ListMembers(query)` 选择器、稳定 mentions token、owner/admin `@所有人` 与气泡高亮/主页跳转 |
| `lib/ui/chat/pages/chat_settings_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `GroupHomeDto` + `ChatGroupSettingsDto`；聊天信息/群主页入口消费 `GetGroupHome` 的来源、公告、成员数和能力；`AppScaffold`；P7 成员网格按头像与文字高度计算；2026-07-19 B12 消费 GroupHome/members 结构化失败并提供页面级重试，不再以默认设置静默渲染；2026-07-20 删除 JoinRequest 对象落地前无真相源的隐私盾开关；2026-07-20 群治理收口：退群改走 `LeaveConversation` 自愿语义（owner 须先转让）、成员网格补 owner/admin「−」移出成员入口（服务端角色矩阵强制）、公告行跳转公告页；2026-07-21 `circleGroupId` 非空时保留成员与 RTC 能力展示，隐藏 Chat 侧加人/移人入口，标题、公告、群管理与退出统一跳转 Circle 详情，避免必败重试；P7 仍复用成员网格响应式列宽；P8 仍复用 Settings 语义颜色、间距与字阶 token |
| `lib/ui/chat/pages/chat_announcement_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | GroupHome 公告只读投影 + UpdateAnnouncement typed command；owner/admin 编辑发布、成员只读；Inset form 壳、确认/结构化错误与 route page access 齐备 |
| `lib/ui/chat/pages/start_group_chat_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `SelectableGroupConversationRowDto`（`source=group\|circle` 分页前分流 + `circleId`）/`ChatContactRowDto`/`ChatConversationCreatedDto` + 单一向导 ViewModel；私建群与圈子绑定群共用成员交集链，选择页与主列表共享会话头像 token / 占位视觉；**2026-06-25 P4 观测收口**：发起群聊/添加成员页接入 `PageLifecycleObservability`（enter/onlineLoading/onlineSuccess/emptyState/blockingFailure/submitSuccess/submitFailure/exit + itemCount/durationMs）与 `JourneyEventTracker`（`start_group_chat.create_success`/`create_failed`/`add_members_*` funnel，payload 带 memberCount/isCreateMode），失败事件携服务端 `sourceCode`（错误码到埋点同源），并经 `runtimeErrorDisplayMessage` 结构化透出；术语统一「群聊」、用户可见文案/魔数全走 `UITextConstants`；**2026-06-25 错误文案去私信语境**：建群关系门改用群专用错误码 `CHAT.USER.group_member_not_mutual`/`group_member_blocked`（metadata errors.yaml → Go+Dart codegen），不再复用私信态 `not_mutual`/`blocked`；**2026-07-20 三来源闭环**：新增圈子来源入口、服务端 source 分流、Alpha/Provider/Widget/UAT 证据，route/surface 改用 metadata generated 常量；**R03 拆分**：主文件与两个 part 均 <1000 |
| `lib/ui/chat/pages/transfer_ownership_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 成员 DTO 过滤/展示；`SettingsInsetMemberPickerPageScaffold` |
| `lib/ui/chat/pages/group_member_search_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatConversationMemberDto`；**P5** `shell=search_embedded`（`settings_canonical_manifest`）；2026-07-19 B12 成员加载失败接 `AppPageErrorState` + retry |
| `lib/ui/chat/pages/group_manage_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `ChatGroupSettingsDto`；`SettingsInsetFormPageScaffold`；2026-07-19 B12 消费 members/settings 加载失败并提供重试，禁止默认开关静默顶替真实状态；2026-07-20 单轨仅保留 `nameEditableByAdminOnly`、`conversationType`、`circleId`，删除二维码进群与进群审批假开关；2026-07-21 消费 generated `circleGroupId`，圈群绑定会话隐藏 Chat 治理表单并跳转 Circle 详情，P7 继续复用 Inset 宽度壳，P8 继续复用设置语义 token |
| `lib/ui/chat/pages/group_admins_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 多选行 `ChatConversationMemberDto`；2026-05-19 完成按钮接入 `AppNavigationBarTextAction` |

---

## circle

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/circle/pages/home_circles_hub_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：`CircleDiscoveryFeedPageSlice` → `CircleHubFeedPostEntry` 仅走强类型 projection，拒绝缺失 `placementId`；默认 `recommended` 单请求、认证后才读 `mine`、keyset cursor 按 placement 去重追加，不再 `limit: 200` 或本地重排/过滤。2026-05-21 首页垂类固定为校园/旅行/摄影/科技/车之家，群组瀑布流恢复默认双列自适应，旅行/摄影图片使用页内轮播。**P7**：沿用 `AppSpacing` 响应式双列与滚动壳；**P8**：沿用语义色、间距和字阶 token。 |
| `lib/ui/circle/pages/circles_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `List<CircleDto>`；`AppScaffold`；P4 MainAppShell |
| `lib/ui/circle/pages/circle_detail_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：`section_creations` DTO+`PostReadSurfaceId.circleWorks`；壳 `CircleDto` 已合规；2026-06-14 首屏 IA 收敛为身份区、加入/私信、与你的交集、圈子影响力、内容/讨论/成员；管理/编辑/分享等操作进入更多菜单；内容二级筛选为全部/图片/视频/文字；2026-07-19 B4 补对象级行为信号（impression/dwell + join/leave 接 `ReportCircleBehavior` HotPath，游客态守卫） |
| `lib/ui/circle/pages/circle_edit_settings_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P2 `CircleEditSubmitPayload` |
| `lib/ui/circle/pages/circle_stats_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `CircleStats*RowViewData`；`AppScaffold`；2026-07-20 补曝光/停留埋点（行为通道） |
| `lib/ui/circle/pages/circle_membership_approval_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：`CircleMembershipSlice` typed 队列 + `DecideCircleMembershipCommand`；owner/admin 审批 pending 加入申请（metadata `ApproveCircleMember/RejectCircleMember`，2026-07-20 新建，M8-H Phase 3 / R-CIRCLE-002）；分页/空/错/加载态 + journey 埋点齐备 |
| `lib/ui/circle/pages/circles_hub_page.dart` | T0 | — | — | — | — | — | — | — | — | — | 仅 `export` `home_circles_hub_page`，不单独验收 |

---

## content

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/discovery/pages/unified_media_viewer_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | **P2 ✓**：薄壳→`WorksImmersiveViewer`+`readPresentation`；**P6** 仍 exempt（S6-2）；2026-05-19 进入沉浸媒体时使用 appChrome 压缩 safeTop，对齐首页精品顶栏；更多面板挂靠验收：复制/分享/原图/主题均为真实动作，沉浸负反馈带完整 feed 归因并跳至下一内容，撤销可返回原内容 |
| `lib/ui/discovery/pages/work_browser_entry_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | `workBrowser` 统一深链入口；P2 `WorkBrowserItemDto`/`PostReadPresentation` + `ContentRepository` 定位队列；P3 走 `contentRepositoryProvider` Mock/Remote；P6 成功态跟随 `WorksImmersiveViewer` 深色沉浸与文章 Dark Paper，首屏错误态按 `sourceTheme` 回到来源 light/dark；举报理由与拉黑/屏蔽关键词登录 continuation 均由 Work Browser 原表面续接 |

---

## content / entry（创作与发布子域）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/content/entry/pages/create_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromPublishConfirmSummary`（draftPreview）+ `CreatePostRequestWire` 写入 `summary/tagRefs/entityRefs/assistantUsePolicy`；P6 full。P7/P8：reader host 与发布 sheet token 口径不变；2026-06-23 商用化图片发布（P3）：本地图片先 `initMediaUpload`→上传→`completeMediaUpload`→`createPost`→`bindMediaAssetsToPost`（metadata codegen path/pageId）→`publish`，远端不提交本地路径，失败 `abort` 不产半成品；同日补重入旅程：图片选择器再次进入不预选旧图，但确认后新图会按剩余名额追加到现有图片末尾，不覆盖第一次选择；同日补 `/create?type=capture` 高保拍照：capture 初始 flow 固定图片，拍照→预览→图片编辑→创作页追加，`cameraPageBuilder` 仅作测试注入；2026-06-25 图片 flow 顶栏主标题统一为“图片创作”，首屏不再 34% 淡化；图片网格拖拽悬停时目标区间即时让位，保持与选择器/编辑器共用 `MediaReorderableView` |
| `lib/ui/content/entry/pages/article_typography_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：`postReadPreviewBundleFromCreateEditorState` 标题/投影；书页分页不变；2026-05-19 黑场顶栏 safeTop/按钮尺寸接入 appChrome |
| `lib/ui/content/entry/pages/local_draft_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：本地草稿页只消费 `CreateDraftStoreState` / `CreateDraft`，续草稿统一回到 create 链 `draftPreview`；P3 仅经 provider/store，不直连 mock 列表；P6 空态/缺图占位与删除确认已覆盖 |
| `lib/ui/content/entry/pages/publish_location_selector_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2/P3 ✓**：`LocationPoiDto` + ContractGraph generated operation client；production 仅 Remote，alpha 由独立 `quwoquan_cloud_mock` fixture bundle 覆盖；compact/light、regular/dark、expanded/light 共用同一 Slice；主预览在 create 链 |
| `lib/ui/content/entry/pages/video_editor_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：回写草稿；与 draftPreview 桥一致（类注释） |
| `lib/ui/content/entry/pages/publish_circle_select_page.dart` | T5 | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：帖子投影 N/A；`CircleDto`+Settings |

---

## entity（主页实体）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/entity/pages/suggest_homepage_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageSuggestionDraft` / `HomepageRepository`；WP4 标准 `IosSelectionSection` 表单、强登录安全关闭与提交 success/failure `product_action` |
| `lib/ui/entity/pages/homepage_picker_page.dart` | user_acceptance | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageSummary`；WP4 共享主页类型标签并补搜索/确认 `product_action` |
| `lib/ui/entity/pages/homepage_claim_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageClaimRequestDraft`；WP4 标准 iOS 分组表单、字段校验、强登录安全关闭、runtime form error 与提交 `product_action` |
| `lib/ui/entity/pages/homepage_maintenance_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageBasicDraft` / UpdateClaimedHomepageBasics；WP4 按 claimStatus + active persona owner fail-closed，非 owner 仅展示结构化权限页；标准表单、登录与提交观测齐备 |
| `lib/ui/entity/pages/homepage_status_report_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageStatusReportDraft`；WP4 删除 Material Divider，改标准 iOS 选项/表单、原因校验、强登录安全关闭与提交观测 |
| `lib/ui/entity/pages/homepage_detail_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageDetail`/`HomepageShellData`/`ObjectPageBundle`；2026-06-14 地点和事物主页 IA 收敛为身份区、关注/私信、与你的交集、认识对象、内容/讨论/兴趣圈；2026-07-19（B6）口碑子 tab 接 `HomepageReview` typed 读写；2026-07-21 可到访主页按 generated `wishlistHomepageTypes` 消费 `GetEntityWishlistState`，想去/取消经 `wishlist_add/remove` 单轨事实回流交集，非地点保留 `SubjectFollow`；WP4 记录卡接 generated workBrowser 并透传 entityPage/feed 归因，主页类型/状态/评分标签统一 token 化 |
| `lib/ui/entity/pages/homepage_introduction_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `HomepageIntroduction`/`HomepageSource` metadata codegen；公开 HTTPS 来源卡，不展示内部 sourceRefs；WP4 页尾三入口通过 route extra 直达详情指定 tab，相关主页/圈子仅在有真实目标时可点，空态与页面错误分层诚实 |

---

## intersection

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/intersection/pages/object_intersection_list_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：全部交集页，消费 `IntersectionReason` + `ObjectIntersectionQuery(limit: 50)`；路由 `objectIntersections` 由 metadata codegen 生成；纵向列表复用 `ObjectIntersectionCard`；页面壳为 `singleList` 语义，背景、空/错误态与列表页统一 |

---

## rtc

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/rtc/pages/incoming_call_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 typed `CallQuery` + realtime ringing 首帧；真实事件先 seed caller presentation、再 GetCall 补全；结构化失败横幅可重试；P8 页面字面量清零；保留通话舞台 chrome |
| `lib/ui/rtc/pages/outgoing_call_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 typed lifecycle Facet；generated route；debug 模拟面板删除；参与者展示走统一 resolver；结构化失败横幅可重试；P8 清零 |
| `lib/ui/rtc/pages/voice_call_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `CallParticipantPickerRouteExtra` + typed Facet；参与者与 video 页统一消费 `callParticipantsProvider`（成员投影 + LiveKit）；结构化失败横幅；多人摘要超过可见上限显示 `+N` 并进入成员面板；P8 清零 |
| `lib/ui/rtc/pages/video_call_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 typed media/screen-share Facet；屏幕共享开始/停止与信令态同源；锁定模式隐藏危险控制并保留明确解锁；PiP 渲染 active speaker 真实视频轨；媒体建连/重连与结构化错误统一由 `CallStageBanner` 消费；P8 清零 |
| `lib/ui/rtc/pages/call_participant_picker_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `CallPickerParticipantRow`+Chat DTO；`AppScaffold`；中文文案与间距全部改用 `UITextConstants` / `AppSpacing` |

---

## search

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/search/pages/global_search_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2/P3/P8/P9 ✓**：本页无帖子卡；帖子 `searchCard` 在 `search_network_results_page`；2026-07-20 B7.5 记录改 `RecentSearchQuery/CommandWriter`，猜你想搜改 `ListHotQueries` term-heat 真实读模型，热门圈子/地点只消费 Remote 对象且删除端侧合成 fallback；2026-07-20 WP-K 将伪热门语义收口为「发现圈子/地点」，补卡片封面、真实对象类别徽标及网络直达行图标/副文案/箭头，未制造热度事实；alpha/test 由 cloud_mock fixture Facet 注入；错误模块收起并上报结构化观测；全部用户文案/间距/字阶归语义 token；超限主文件按历史/灵感/建议 part 拆分，等待态与 supersede 测试保持全绿 |
| `lib/ui/search/pages/search_network_results_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2/P3/P8/P9 ✓**：`_openPost` `PostReadSurfaceId.searchCard`+wire；2026-07-20 B7.5 `SearchResponse.requestId` 驱动查询级 impression 与条目 click（rankPosition 归因）经 `SearchFeedbackCommandWriter` 上报；2026-07-20 WP-K 补 user.profile 分区、404/410 typed 失效提示/条目移除/degrade 回流、空态 query+相关词+调整行动；production Remote-only、alpha/test 显式 override；RuntimeFailure/空态/慢态统一；用户文案与视觉值归语义 token；页面按状态/卡片/模型/加载/导航拆为 <500 行 part，canonical search 单 generation 一次调用证据保留 |
| `lib/ui/search/pages/location_place_landing_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2/P4/P8 ✓**：`location.place` 临时地点卡，命中详情来自搜索 payload（route extra），无独立后端 operation（surface `locationPlaceLanding` operation_ids=[]）；提升 CTA 复用 `suggestHomepage`；JourneyEventTracker enter/exit 曝光停留 + promote_click；2026-07-20 B7.5 复核无端侧业务假数据、无中文字面量与视觉魔法值 |

---

## settings

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/settings/pages/settings_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | `AppScaffold`；P5 我的主页设置中枢：编辑资料、分身管理、权限管理、深色模式、关于趣我圈、切换账号、退出登录；2026-06-24 重构为与资料编辑页一致的 Inset grouped IA，body 继续外包 `WebPageMaxWidthFrame`；2026-06-25 深色模式改为详情页，账号动作居中无图标；2026-06-27 主列表统一 `SettingsInsetNavigationRow`/compact density，图标行 divider 按正文缩进，退出确认改为 `CupertinoAlertDialog` |
| `lib/ui/settings/pages/blocked_keywords_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | UserSettings 隐私设置子页；P2/P3 经 `UserSettingsQueryReader/CommandWriter` typed Facet 读取/更新 `PrivacySettingsView.blockedKeywords`；Inset form 壳、结构化错误、曝光/更新观测与语义 token 齐备；深色 390×844 golden 已验证 |
| `lib/ui/settings/pages/my_reports_page.dart` | api_integration | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 当前 Persona 私有举报进度页；P2/P3 经 `ContentReportQuery` typed Facet 分页读取 `ContentMyReportPage`；Inset form 壳、加载更多、结构化错误、生命周期观测与语义 token 齐备；浅色 390×844 golden 已验证 |
| `lib/ui/settings/pages/settings_permissions_page.dart` | local_contract | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 系统权限管理页；只承载真实联系人系统权限并按 capability 提供“去设置/当前设备不可用”，已删除无正式对象支撑的圈子/实体权限占位；Inset form 壳 |
| `lib/ui/settings/pages/settings_dark_mode_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 深色模式详情页；复用 `AppearanceSettingsWireDto` / `AppearanceSettingsController`，系统开关 + 浅色/深色手动单选；Inset form 壳；2026-06-27 行 UI 改为复用 `SettingsInsetSwitchRow` / `SettingsInsetChoiceRow` |
| `lib/ui/settings/pages/settings_notifications_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 通知设置对象页；消费 `NotificationSettingsView` 与 `UserSettingsCommandWriter`，覆盖加载/错误/乐观更新回滚；Inset form + Web 最大宽度壳 |
| `lib/ui/settings/pages/settings_privacy_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 隐私设置对象页；消费 `PrivacySettingsView`，管理陌生人私信、助手与主页可见范围；结构化错误与重试 |
| `lib/ui/settings/pages/settings_calls_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 通话设置对象页；消费 `CallSettingsView`，管理铃声、好友专属铃声、振动及群通话响铃 |
| `lib/ui/settings/pages/settings_account_security_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 账号安全对象页；消费 `ListCredentialsSlice` 与 typed CredentialBinding writer，凭证脱敏展示并由服务端保护最后凭证 |
| `lib/ui/settings/pages/settings_about_page.dart` | local_contract | ✓ | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 关于趣我圈页；展示产品名与 `PackageInfo.version`，并提供用户协议/隐私政策/权限说明/第三方 SDK 清单入口；法律正文经 `/legal/*` 静态 URL 获取，不承载云业务契约；Inset form 壳 |

---

## interest_match（同趣 / 找同趣 · 兴趣配对发现入口）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/interest_match/pages/interest_match_page.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | **找同趣 / 兴趣配对发现启动器**（加号动作面板「兴趣配对」入口，route `/interest-match`；不再占底栏常驻 tab）；不自建 Mock 候选列表（守 R16），按兴趣发现方式导流到既有真实面：找同趣的人 → `/search/network`、找圈子/找地点/按兴趣搜索 → `/search`、今日同趣机会 → `/profile/intersections`；游客可浏览无登录门；曝光 `VisitTarget.page(interest_match)`；**P2/P3 —**：本页为纯导流 launcher，不直接消费云契约（云契约在目标真实面）；附近/结伴/局真实聚合 deferred（见 specs/product/intersection-action-deepening-and-social-ia.md §0） |

---

## user

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/ui/user/pages/my_profile_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：2026-06-17 我的主页首屏固定为封面→身份(✎)→Slogan→单行统计→我的连接→我的影响力→记录/互动/足迹（V5：圈子降为统计数字，足迹=浏览历史 mine-only）；连接/影响力共用主谓宾交集卡，记录筛选为全部/图片/视频/长文；进入曝光 + dispose 停留（`contentBehaviorTracker`）；2026-06-18 首屏经 `getUserHomepageBundle` 一次聚合身份域真相（profile/stats/关系能力/viewerContext）+ 作品/帖子并发补充，聚合失败渲染结构化 `AppPageErrorState`+重试（不被乐观壳层静默吞掉，R17/R20）；2026-07-12 互动二级行收敛为点赞/评论/转发/浏览 + 收到的/我发起的，转发 mine-only，消费 metadata/codegen、Mock/Remote 双向分页、双桶缓存、seen/read 与 `ShareInteractionObservability`，P7 继续由共享滚动壳与可横滑二级控制行承担，P8 使用 profileShare 语义尺寸/色阶/token |
| `lib/ui/user/pages/login_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | P2 `AuthRepository.loginOneTap/loginWechat/loginAlipay/loginQq`、`SocialAuthorizationRepository` + `AuthLoginResultDto` 均消费 metadata/codegen；P3 Mock/Remote 由统一 Provider 切换；运营商、微信、支付宝、QQ 入口由强类型 capability 区分可用/未安装/未配置/超时/SDK/平台状态，支持平台临时不可用仍可发现；协议勾选前不调用原生 SDK；字段、表单、服务状态与社交反馈均按操作锚点单通道呈现，并复用透明圆形感叹号错误行（浅色 #E5484D / 深色 #FF6B6B）；`LoginDismissPolicy` 明确普通返回、受限安全关闭与宿主关闭，错误不持有导航；2026-07-14 品牌与返回态收口：头像仅在可信候选成功解码后显示，空值/加载中/失败零占位，昵称按 `nicknameCustomized` 展示，短名称/完整无障碍动作、短信验证码 CTA、共享两层花蕊 Painter 与 light/dark/narrow/wide 视觉基线；2026-07-16 返回会话与运营商一键动作分离，空摘要不建卡，显式一键失败紧凑降级，OTP 发送后折叠号码且保持单主动作 |
| `lib/ui/user/pages/legal_document_page.dart` | local_contract | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | — | 远端 WebView 展示用户协议/隐私政策/权限说明/第三方 SDK 清单；P2/P3 —，内容来自配置 URL；禁用 JS，保留返回与失败重试 |
| `lib/ui/user/pages/other_profile_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：2026-06-14 用户主页首屏固定为身份区、关注/私信、你们的交集、TA的影响力、作品/圈子/互动、双列内容流；交集卡 `onReasonTap` → `BehaviorEvent.intersectionDimension/intersectionTagRefs` 归因；2026-06-18 首屏经 `getUserHomepageBundle` 一次聚合身份域真相 + 关系能力 seed（免首屏额外 `getCapability` 串行），聚合失败渲染结构化 `AppPageErrorState`+重试（R17/R20） |
| `lib/ui/user/pages/my_intersection_inbox_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：交集/影响力详情双一级 tab，与 `ProfileStatsPage` 共用 `AppSegmentedChoiceBar` tap-only 分段控；交集 tab 消费 `GET /content/intersections`（list）+ `POST /content/intersections/visit`（打开即推进已读水位清零），强类型 `IntersectionReason`，展示筛选与十年时间桶；影响力 tab 消费 `GET /content/sub-accounts/{subAccountId}/author-impact`，强类型 `AuthorImpactSummary`；P3 Mock/Remote 经 `intersectionRepositoryProvider` / `authorImpactProvider` 切换；空/错误兜底；点条目带 `relationKind` 进对象页；P4 由 `app_pages.yaml collect_page_access` 单轨生成 page_open/page_return，交集证据点击与反馈仅走 `ContentBehaviorTracker` |
| `lib/ui/user/pages/my_footprint_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | **P2 ✓**：我的足迹私有只读列表，消费 `GET /content/footprint`（type 过滤 + cursor 分页）；强类型 `FootprintEntry`；P3 Mock/Remote 经 `footprintRepositoryProvider` 切换；type 枚举由云侧定义、端侧只透传；空/错误/分页兜底；点条目按 R21 带 referralSource 进作品浏览器 |
| `lib/ui/user/pages/edit_profile_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 2026-06-24 商用资料编辑页重构：固定顺序封面/头像/昵称/性别/生日/地区/手机号/趣我圈号/我的二维码/签名/标签；二次修正为媒体、基础资料、账号社交、扩展资料四个 iOS 分组区块；二维码使用真实 HTTPS payload；P2 读 `ProfileEditSnapshotData`/`ProfileQrCardData`，经 `ProfileCommandWriter` 写 `UpdateUserProfileCommand`；2026-07-20 B7.5 地区与标签校验统一切 `TagCatalogQuery` typed Facet，production Remote-only、alpha fixture adapter，不再依赖聚合 TagRepository；资料提案 `applying` 检查点可在响应丢失后继续应用且禁止并发拒绝；P4 页面曝光/TTI/停留仅由 route page_open/page_return 采集，保存结果继续由 `JourneyEventTracker(profile_edit)` 记录，禁止手工 enter/exit 双计 |
| `lib/ui/user/pages/career_interest_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 资料编辑职业/兴趣独立页；P2 读取 `ProfileEditSnapshotData`，职业/兴趣候选经 `TagCatalogQuery.listChildren/resolveTag/validateRefs`，保存经 `ProfileCommandWriter` 写 `UpdateUserProfileCommand`；2026-07-20 B7.5 标签添加/移除经 `TagFeedbackCommandWriter` 追加 click/ignore 事实，alpha 目录来自 metadata seed bundle，production Remote-only；裸 StateError 与视觉魔法值清零；加载、结构化失败重试、未保存离开 iOS alert、保存中状态齐备 |
| `lib/ui/user/pages/add_contact_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 添加联系人主页：胶囊搜索、扫一扫、手机联系人能力位入口；二维码经 `profileEditQueryProvider` 读取 typed `ProfileQrCardData`，最近匹配经 `ContactDiscoveryRepository.getLatest/dismiss` 回读并可撤销；`PlatformCapabilities.contacts` 驱动通讯录入口降级 |
| `lib/ui/user/pages/contact_search_result_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 趣我圈号/昵称搜索结果页；查询经对象级 `profileQueryProvider.searchSocialRelations`，添加动作统一进入 `UserRelationshipStateNotifier.setFollowingWithSync` 持久 outbox，列表行使用 typed `SocialRelationSearchItemView` → `ContactCandidateVm`；空/加载/结构化失败与 pending 态齐备 |
| `lib/ui/user/pages/contact_confirm_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 扫码/搜索/手机号添加确认页；对象资料经 `personaQueryProvider`、关系能力经 `RelationshipCapabilityRepository`，添加动作统一进入 `UserRelationshipStateNotifier.setFollowingWithSync` 持久 outbox；错误态使用 `AppPageErrorState` + runtime semantic |
| `lib/ui/user/pages/my_qr_code_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 独立我的二维码页；经对象级 `profileEditQueryProvider.getProfileQrCard` 返回 typed `ProfileQrCardData`，复用 `MyQrCardView` 真实二维码渲染，扫一扫 CTA 进入扫码路由，错误态支持重试；P4 route page_open/page_return 承载曝光/停留，扫码入口以 `JourneyEventTracker(contact_add.open_scanner_from_my_qr)` 单次记录产品动作 |
| `lib/ui/user/pages/scan_contact_qr_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 扫一扫页；`QrPayloadParser` 解析 HTTPS payload 后经 `profileEditQueryProvider.resolveProfileQrToken` 返回 typed `ProfileQrResolveWireDto`，摄像头/相册能力位降级、图库识别和无效码结构化反馈齐备 |
| `lib/ui/user/pages/phone_contacts_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 手机联系人页；`ContactHashService` 本地规范化哈希、`ContactDiscoveryRepository.initiate` 返回 typed `ContactDiscoveryResultView`，添加动作统一进入关系 outbox，手机号原文不上传；权限请求、设置跳转与返回重检唯一经 `AppPermissionCoordinator` |
| `lib/ui/user/pages/persona_management_page.dart` | T7 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 分身管理总览；`PersonaManagementNotifier` 只消费对象级 `PersonaQuery` / `PersonaManagementCommandWriter` typed Facet，覆盖列表、配额、激活、退役/删除守卫与资料同步；加载/动作失败走 RuntimeFailure，曝光、停留与关键动作埋点齐备 |
| `lib/ui/user/pages/persona_management_form_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 分身管理内嵌创建/编辑页；消费 `PersonaManagementNotifier` typed command，userHandle 服务端分配且只读；保存失败走 RuntimeFailure，视觉与交互均使用语义 token |
| `lib/ui/user/pages/blocked_users_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | PersonaRelationship 私有拉黑管理页；消费对象级 `BlockedListQuery` + `BlockCommandWriter` typed Facet，云端列表展示 persona 公开快照，支持分页、空/加载/结构化错误态与解除拉黑确认；P5 —（非推荐内容消费页）；路由级 page access + unblock 关键动作埋点 |
| `lib/ui/user/pages/profile_stats_page.dart` | local_contract | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | 2026-06-25 商用化重设计：顶部改为与设置/资料编辑同源的 inset chrome + `AppSegmentedChoiceBar` tap-only segmented selector `[粉丝 | 关注 | 圈子]`，搜索条下沉为列表首块；P2/P3 同源读模型为 `CircleDto` + `ProfileSocialRelationRowViewData(relationshipCapability/profileVisibility/relationState)`，followers/following/circles 全部走 `query+cursor+limit` 云侧分页过滤；private/blocked 权限卡、空态、分页、inline retry 与 action sheet 全链路齐备 |
---

## components（跨域复用全屏 / 骨架）

| 路径 | 类型 | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 | 备注 |
|------|------|----|----|----|----|----|----|----|----|----|------|
| `lib/components/settings_form/settings_inset_form_page.dart` | T6 | ✓ | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | `SettingsInsetFormPageScaffold`；P5 复用本体；2026-06-27 新增 `SettingsInsetNavigationRow` / `SettingsInsetSwitchRow` / `SettingsInsetChoiceRow` / `SettingsInsetTrailingText` / `SettingsInsetChevron` 与可缩进 divider，统一设置族表单行模板 |
| `lib/components/media/image/editor/image_editor_page.dart` | T5 | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | 本地编辑为主；2026-05-19 编辑器黑场顶栏 safeTop/按钮尺寸接入 appChrome；2026-06-25 底部缩略条左对齐 reveal-not-center + 共享重排；2026-07-20 商用化收敛：移除相框/透视/修复/色调对比度/魅力光晕等全部占位入口，曲线（多通道+直方图 LUT）/白平衡（AWB+色温色调）/马赛克（像素化与模糊实绘）/文字（图层拖缩旋+描边底纹）真实实现；裁剪、旋转/翻转、颜色矩阵、局部径向调整、曲线、马赛克和文字统一走 `ImageEditorExportEngine`（预览导出同源、解码降采样上限 4096）；确认即烘焙+文件快照全局撤销/重做/历史回退；back 有修改弹放弃确认、顶栏「完成」显式提交；落地 `page.media.image_editor` enter/exit/submit/failure 埋点与 `image_editor_tool_used` 工具分布（P4 由 — 转 ✓）；8 个 image_editor local_contract 套件共 52 个用例通过 |
| `lib/components/media/camera/camera_capture_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 2026-05-19 登记为相机/选择器专用 chrome；2026-06-23 高保拍照相机：全黑沉浸式，顶部返回/拍照模式/闪光灯，取景九宫格+点击对焦，底部滤镜/74pt 快门/翻转；滤镜入口复用图片编辑器三光圈语义图标；六滤镜来自 `filter_presets.json` 的 `camera_photo` 集合并共享 `image_editor_filter_matrix.dart`；闪光灯单击 on/off 开关、前置置灰、拍后预览、使用照片先进入 `ImageEditorPage` 再按 picker/create 追加；新增 fake preview/capture/editor 注入、深色权限/错误页、layout local_contract 与 user_acceptance 证据。2026-06-23 同壳新增高保视频摄像模式（`initialMode=video`）：共享深色 chrome/取景/九宫格/滤镜条/错误态/底部 Dock 几何，独立顶部“摄像模式”/灯光、品牌蓝录像按钮、最短 1s/最长 60s 录制状态机、录制中锁定翻转与滤镜、麦克风拒绝可继续无声录制、录后视频预览确认再进 `VideoEditorPage`；共享壳抽至 `camera_capture_shell.dart`，图片/视频路由结果与埋点前缀独立，证据见 video_camera_hifi_layout / capture_camera_photo_video_independence / video_creation_publish_roundtrip |
| `lib/components/media/picker/create_media_picker_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 2026-05-19 登记为媒体选择器专用 chrome；2026-06-23 商用化：图片/视频子流互斥（图片模式隐藏视频分类与一键成片、底部「编辑图片/完成(n)」、视频完全过滤），相册目录/宫格高保（全页强制深色 chrome、去分类 tab、手机统一三列且平板/PC 递增、选中编号缩至双位数友好、首格拍照去圆圈保持呼吸感）；相册弹层强制深色且最高到顶部工具栏下，编辑回填保序；图片模式每次进入忽略外部 initialSelection 重新选择，已选宫格再次点击进入编辑器；同日首格拍照改为 camera→preview→editor→picker 追加并在进入前拦截上限，`cameraBuilder` 仅作旅程测试注入；注入 `MediaPickerService` + widget local_contract，行尾箭头改 `CupertinoIcons.chevron_forward`；2026-06-25 已选缩略条不足一屏时固定左对齐，拖拽悬停阶段即时空出目标槽位并与创作页/编辑器共用同一重排反馈 |
| `lib/components/media/picker/desktop/desktop_image_picker_page.dart` | T5 | ✓ | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | 2026-06-24 桌面（PC）本机图片选择器：能力位路由（`shouldUseDesktopImagePicker` 仅 `mediaLibrary==false && hasLocalFileSystem` 的图片入口进入，非平台名分叉），`file_picker` 选目录 + `FileStorageGateway.listDirectory` 递归扫描含图子目录聚合相册（`DesktopImageAlbumScanner`，深度/目录数/单册封顶），跨目录「全部照片」置顶；记忆上次目录（`DesktopPickerDirectoryMemory`/SharedPreferences）；多选编号 + 已选条复用 `MediaReorderableView`（strip）拖拽重排，相册下拉复用 `AppTopAnchoredDropdown`；缩略图走 `gateway.readAsBytes`+`Image.memory`（不新增 `dart:io`）；缺能力位/空目录结构化降级空态；P2/P3 — 因无云契约/Repository，数据源为本机文件系统；证据 desktop_image_album_scanner / desktop_picker_services / desktop_image_picker_page_widget |
| `lib/components/media/picker/one_tap_movie_preview_page.dart` | T5 | ✓ | — | — | ✓ | — | — | ✓ | ✓ | ✓ | 预览固定黑底白字；P6 exempt |

---

## 统计（基线）

| 类别 | 数量 |
|------|------|
| `ui/**/pages/*_page.dart`（含 T0，不含下列 welcome_screen） | 73 |
| `welcome_screen.dart`（额外入口） | 1 |
| `components/**/*_page.dart` | 6 |
| `app/shell/*.dart`（主壳 + 底栏 + 对象页详情态全局底栏 + Web 安装提示 + PC Web 宽屏壳及 part helper） | 7 |
| **矩阵数据行（含 T0 + shell）** | **87** |
| **需验收的独立页面行（排除 3 行 T0）** | **84** |
| **P6 = ✓（full）** | **81** |
| **P6 = ○（partial，待收敛 S6）** | **0** |
| **P6 = —（exempt 或整行 —）** | **6** |
| **P2 = ✓（compliant）** | **67** |
| **P2 = ○（partial，待 metadata/UI 收敛）** | **0**（帖子管线已 ✓；后续非帖子 P2 另开项） |
| **当前横向列** | **P1–P9**（可扩展至 P10…） |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-20 | **CR-20260720-125 欢迎页信息结构简化与图一高保收口**：welcome_screen 只保留深蓝渐变 + 八瓣花 + slogan + 底部品牌名 + 状态栏；删除中央大标题、小趣低语、ShaderMask 渐变文字与相关文案常量；花朵可见直径响应式（屏宽 40%，clamp 132~168dp）；Noto Sans SC 以 OFL-1.1 固定为正式品牌字体；欢迎页/登录品牌标/App 图标共用唯一 appearance，Android launch 颜色从 Dart token 生成；品牌深蓝深浅色统一（P6 `✓`→`—` 登记 exempt）；状态栏透明浅色内容原生/Flutter 同源；原生启动图新增贴底品牌名条（Android layer-list + iOS storyboard）；品牌簇单一无障碍语义；golden/native/motion probe 契约同步刷新。 |
| 2026-07-19 | **CR-20260719-124 页面商用成熟度横向收口**：content/discovery/chat/交集/welcome/settings/share 范围新增用户可见中文文案 token 零容忍门禁（范围外按文件计数棘轮）；handled exception 补 RuntimeFailure code/kind/reason；content/discovery production composition 去 `AppDataSourceMode` 并以 `ContentDiscoveryFeedQuery` 收窄首页依赖；删除 alpha-only embedded discovery 展示旁路与无 DeleteMessage 契约的假删除入口；`WorksImmersiveViewer`、CreatePage state、chat conversation 按职责拆分并清理 R03 allowlist。P1–P9 结论保持全绿，证据见 page-horizontal-quality/acceptance.yaml。 |
| 2026-07-19 | **B12 横向商用成熟度复核**：assistant 管理页清假、chat 会话页拆分并补三态、chat 群设置链路错误恢复、RTC 通话页加载/错误恢复、entity 认领页文案 token 化；同步修正已失真的 P6 统计（partial=0） |
| 2026-03-29 | 初版：全量路径 + 类型 + P1–P7 默认 ○ / 显式 — |
| 2026-03-29 | 更名「横向质量矩阵」；**P7/P8 拆分**（断点响应式 vs 设计系统语义 token） |
| 2026-03-29 | **P6 与 S6 双色矩阵对齐**：补 `app/shell` 两行；逐页填 `✓/○/—`；扫描基线注明排除 `chat_display_fallbacks` |
| 2026-03-29 | **全量审计**：P1 逐页/子面挂靠结论；登记 `PublishLocationSearchPage`、`_CreateEntryRoutePage`；P4/P7 对非 Tab 页保留 ○ 待 GoRouter 级与断点专项 |
| 2026-03-29 | **P2 与 `metadata_driven_ui_gap_inventory.yaml` 对齐**：`partial`→○，`compliant`→✓，`exempt`/无云→—（见 `page-horizontal-quality-spec.md` P2、`metadata-driven-client-data-contract/explore-baseline-readiness-20260329.md`） |
| 2026-03-29 | **/baseline**：`page-horizontal-quality` L3 冻结 CR-005；`acceptance` api_integration/user_acceptance 证据矩阵；parent spec 商用/NFR 段落 |
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
| 2026-03-30 | **Phase3 user 八页**：`ProfileSocialRelationRowViewData`；`listProfileCircles`；`PersonaManagementPage` 接 `UserRepository`；`ResonanceBuddyViewData`；资料编辑现已收敛到 `UpdateUserProfileCommand`；`UserProfileViewData`/`PersonaDtoSurface` typedef |
| 2026-03-30 | **Phase4 circle 五页**：`CircleStatsViewData`/`circleStats` 去 raw Map；`circles_page` `List<CircleDto>`；`CircleEditSubmitPayload`；`CircleHubFeedPostEntry`+`HomeCirclesCategoryTab` `PostBaseDto`；`CircleStats*RowViewData`；清单 circle 域 non-exempt 全 compliant |
| 2026-03-30 | **Phase5 entity 六页**：`homepage_models.dart` 迁至 `runtime/generated/entity/` 并对齐 `entity/homepage/fields.yaml` 注释；`HomepageRepository` 清单；`homepage_detail` 用 `ActivePersonaContextViewData`；清单 entity 全 compliant + 矩阵 P2 ✓ |
| 2026-03-30 | **Phase6 search 两页**：`SearchCoordinator` 联系人 `ChatContactSearchItemDto`；最近搜索 `RecentSearchEntryView.toMap`；网络结果群组 `CircleSearchItemView`+`circleName`；`SearchHit` 契约注释；清单 search 全 compliant + 矩阵 P2 ✓ |
| 2026-03-30 | **Phase7–9**：rtc 选人 `CallPickerParticipantRow`+`ChatInboxDto`；路由 `CallParticipantPickerRouteExtra`；assistant 设置/技能中心 `AssistantLocalSessionSummaryView`/`AssistantSessionDetailView`；清单 rtc 全 compliant、assistant 非对话页 compliant；矩阵 P2 统计 51/1 |
| 2026-03-30 | **Assistant 对话时间轴 DTO**：`AssistantTranscriptTimelineRow`/`PersistedTimelineTurnCodec`/`AssistantFeedbackTarget`；`assistant_conversation_page` 与 bubble/answer 对外 API 用 transcript row；清单 assistant 对话页 compliant；矩阵 P2 余量清零（52/0） |
| 2026-04-11 | **帖子 ReadPresentation + Surface 全量收口**：`PostReadProjectionFacade`/`PostReadUiBundle`；发现/圈子/资料/详情/搜索/创作链/分享模板接表面枚举与 wire；清单 content/circle/user/search 帖子相关行 compliant；矩阵上述 17 行 P2 ✓；见 `post-projection-pipeline-inventory.md` §4 |
| 2026-05-07 | **chat 强类型收口**：`LocalChatSearchStore` 联系人/会话快照改具名记录；`SearchHitPayloadChatContact` 收口 chat contact payload；`MockChatRepository` 内部缓存转 typed state；`chat_conversation_page` / `ChatMessageBubble` / `ConversationMessageActionMenuOverlay` 改消费 `ChatMessageDisplayItem` |
| 2026-05-17 | **主壳安全区节奏收口**：`main_app_shell`/`bottom_navigation`/`home_page`/`chat_page` 调整顶部与底部安全区消费方式；底栏改为背景吃满底部安全区、内容上下对称收口；首页与消息页主顶栏 regular 档降到紧凑基线，并让关注/精品切换共用同一顶栏几何与 local_contract 位置稳定回归测试 |
| 2026-07-15 | **启动欢迎 3/6 秒时限纠偏**：删除“2s 后才动、最早 6s 才能进”和 8-controller/8-loop 实现；首帧 90ms 后立即完整开合一轮，正常一轮即进，未 ready 最多重放两次，6s 只作硬退出门；原生改为自适应背景 + 同源透明品牌簇（CR-20260715-104） |
| 2026-06-26 | **启动欢迎诚实边界纠偏**：删除 Android `StartupActivity` / `NativeWelcomeView` / 原生 overlay / `quwoquan/startup/native` handoff；原生层只显示无内容中性过渡背景，Flutter `WelcomeScreen` 成为唯一欢迎页。启动初始化改为 best-effort，不再阻断 Shell；欢迎页最多正常播放一次 + 两次重放，之后进入 Shell/降级 Shell |
| 2026-06-26 | **启动首帧探针纠偏**：`verify_startup_first_frame.py` 默认启动 `MainActivity`，禁止 native welcome 日志/链路，Android 默认 3 秒内需出现 Flutter 欢迎页或主壳，避免用原生镜像绕过真实 Flutter 首帧 |
| 2026-06-26 | **启动性能与 iOS 过渡收口**：本地 HTTPS CA 安装从 `runApp` 前阻塞改为 prerequisite 并行，`WelcomeScreen` 等首帧 rasterized 后启动花瓣动效；iOS 改用 `LaunchTransitionScreen` 无内容中性背景；probe 区分启动空背景与进入 Shell 后骨架屏，并把旧亮蓝快照作为失败信号 |
| 2026-03-29 | **P3 Mock/Remote 收口**：`ui_mock_isolation_allowlist` 清零；聊天/圈子/搜索/global_surface 数据经 `ChatRepository`/`CircleRepository`/`AppContentRepository`；`RemoteAppContentRepository` 不再委托 Mock（空态/最小 Map）；`APP_DATA_SOURCE` + Release 隐藏开发者数据源开关；`main_prod.dart` + CI `flutter build macos` 带 `dart-define` |
| 2026-03-30 | **S7/P7 默认 B** + **`search_embedded`**：`GroupMemberSearchPage` 纳入 `settings_canonical_manifest`；`verify_settings_canonical` 校验 `EmbeddedMemberSearchPageShell`；§4.3 增 C 类；`page-horizontal-quality-spec` / `nine-session-rollout-plan` 写明 P7 默认策略 B |
| 2026-03-30 | **S8/P8**：`verify_dart_semantic` 全仓无命中；`.verify_dart_semantic_baseline.txt` 清空（仅注释）；增补 `AppSpacing.zero`/`textLineHeightSingle`、`AppColors.networkCallQualityWeak`、HSL 八色 token；证据见 S8 acceptance 与 CR |
| 2026-04-11 | **元数据驱动分波（续）**：`MediaPostCard`/`RecentSearchReadPresentation`/`ContentBehaviorBatchEventDto` 等；同日本仓完成帖子全链 P2 ✓（见上行） |
| 2026-06-06 | **Web 商用体验系统收口**：`web_main_app_shell` 首页/精品复用移动端 `HomeMultiFormFeed`（多列瀑布 + 四态 + `referralSource`/`feedRequestId` 同源埋点），post 经统一 `openHomeFeedPost`(`home_feed_post_open_action.dart`)→`MediaViewerExtra(dtoPosts)` 进沉浸 viewer；精品移除「精品队列」；添加页分「内容创作/社交关系」两组（发起群聊/加同好/创建圈子）去「小趣创作助手」；消息右栏「消息助手」→「消息中心」并去「小趣」助手 tab；新增单一抽象 `WebPageMaxWidthFrame` 收口消息/设置/开发者页宽屏最大宽度，会话页时间分隔按 `sentAtIso` 间隔降噪；「我的」右栏去「多端同步」；新增 local_contract：`web_page_max_width_frame_test`/`web_create_groups_test`/`web_featured_no_queue_test`/`web_feed_post_tap_viewer_test`/`web_chat_frame_test` + 扩展 `main_app_shell_widget_test`（feed 同源断言） |
| 2026-06-25 | **发起群聊 P4 观测断点收口**：`start_group_chat_page` 接入 `PageLifecycleObservability`（曝光/加载/空态/失败/转化/停留 + itemCount/durationMs）与 `JourneyEventTracker`（create/add_members success\|failed funnel），失败事件携服务端 `sourceCode`（承接上轮 `not_mutual`/`blocked`/size 错误码，错误码到埋点同源）；同轮关闭提交错误吞错（`catch(_)`→`runtimeErrorDisplayMessage` 结构化透出，R17）、术语统一「群聊」、用户可见文案/魔数收敛 `UITextConstants`；新增 local_contract：发起群聊曝光/加载/转化与失败 sourceCode 断言 + 错误透出断言 |
| 2026-06-25 | **发起群聊错误文案去私信语境 + R03 拆分**：建群关系门新增群专用错误码 `CHAT.USER.group_member_not_mutual`/`group_member_blocked`（metadata `messages/conversation/errors.yaml` → 隔离 codegen 落地 Go `errors.go` + Dart `chat_errors.g.dart`，未触碰他域 `generated/`），服务端 `validateGroupInitialMembers` 改用新码并经 api_integration 断言；端侧经 `runtimeErrorDisplayMessage` 透出群语境文案，widget local_contract 同步断言新 `sourceCode`。R03：`start_group_chat_page.dart` 1383 行 `part` 拆为 743(主)+302(widgets)+343(member sheet)，三文件 <1000、analyzer 净，移除 allowlist 死条目 |
| 2026-06-25 | **profile_stats 视觉字面量收口（R27/verify_dart_semantic）**：`profile_stats_page_widgets.dart` 12 处魔数/旧图标改语义 token——新增 `AppSpacing.profileStatsRowAvatarSize`(52)/`profileStatsFollowSkeletonWidth`(78)/`profileStatsFollowSkeletonHeight`(34)/`listTrailingChevronSize`(18)，骨架行高复用 `AppSpacing.ten`，行尾箭头 `chevron_right`→`chevron_forward`；恢复 `verify_dart_semantic` 仓库级绿 |

# PR 自检：页面横向质量矩阵（强制）

> 若本 PR **新增或实质性改版** `lib/ui/**/pages/*` 或 `lib/components/**/*_page.dart`，请完成下列项。  
> **不叫「七支柱」**：合规项以矩阵 **P1–Pn** 为准，可扩展；**P7（断点/布局）与 P8（语义 token）须分开自检**，不得合并成一条描述。

## S9 / 持续治理（合入前必过）

| 层级 | 要求 |
|------|------|
| **规则** | 仓库 [.cursor/rules/09-page-horizontal-quality.mdc](../../.cursor/rules/09-page-horizontal-quality.mdc)（`alwaysApply`）：改页面路径即须矩阵 + 清单。 |
| **架构约束** | [.cursor/rules/01-arch-constraints.mdc](../../.cursor/rules/01-arch-constraints.mdc) §2.4 表内「横向质量矩阵」行。 |
| **命令** | `make verify-app-page-horizontal-quality`（矩阵 + 漏页/清单）；全量 `bash quwoquan_ops/gate/gate_repo.sh --scope app` 或根目录 `make gate`。 |
| **门禁** | `quwoquan_ops/gate/gate_repo.sh` → `verify_page_horizontal_quality_matrix.py`、`verify_page_matrix_scan_complete.py`、`verify_metadata_driven_ui_gate.py` 等与 P2 同向脚本。 |
| **流程** | 历史九会话规划见 `specs/.../page-horizontal-quality/nine-session-rollout-plan.md`；**新增页**不等待旧波次重跑，但须满足 P1–P9 当前列；P1–P8 可按既有规则标 `○`，P9 只能为 `✓` 或明确 `—`。 |

## 矩阵更新

- [x] 已在 [`page-horizontal-quality-matrix.md`](../feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md) **新增一行**或更新已有行（路径、领域、类型、**P1–P9**）。
- [x] **P1–P8** 已填 **`✓` / `—` / `○`**；**P9** 已填 **`✓` / `—`**，无 `○`；所有列无空白，`—` 已在备注说明。
- [x] 2026-07-17 启动遥测改动已复核 `main_app_shell.dart`、`web_main_app_shell.dart` 与 `home_page.dart`：默认推荐内容首帧和欢迎遮罩移除共同决定首页可用，未改变 P1–P9 结论。
- [x] 2026-07-20 B8 页面商用深化已复核 `home_page.dart` 与 assistant 四页：Remote-only Facet、错误恢复、任务/记忆四态、半弹层生产入口及 P7/P8 分列均与矩阵备注一致。
- [x] 2026-07-20 B7.5 已复核搜索三页、资料编辑与职业兴趣页：term-heat/RecentSearch/SearchFeedback/TagFeedback typed Facet、fake 清零、结构化错误、P7 断点与 P8 token 分列、R03 part 拆分均与矩阵备注一致。
- [x] 2026-07-20 WP-K 已复核搜索默认页与结果页：发现圈子/地点不再伪称热门，卡片与网络直达行复用真实对象语义；全部 Tab 承载 user.profile；404/410 命中失效使用 typed 提示、条目移除与 degrade 回流；空态保留 query 并承载相关词/调整行动；P7 版式与 P8 token 结论未漂移。
- [x] 2026-07-20 B1 身份账号商用化已复核设置四个对象页、资料编辑、分身管理与法律文档页：generated typed Facet、alpha 物理注入、结构化错误、P7 宽度壳与 P8 语义 token 分列均与矩阵一致。
- [x] 2026-07-20 Post 更多功能商用化已复核两个挂靠面与新增的屏蔽关键词/我的举报页：metadata route/surface、typed Facet、Inset 壳、登录 continuation、结构化错误、页面生命周期观测、P7 与 P8 分列均已同步矩阵。
- [x] 2026-07-20 联系人商用收口已复核 `settings_permissions_page.dart`：删除无正式对象支撑的圈子/实体权限占位，仅保留 capability 驱动的联系人系统设置入口；P7 继续复用 Inset 宽度壳，P8 继续复用设置语义 token。
- [x] 2026-07-20 CR-124 W1–W5 复核 content/discovery/chat/交集/welcome/settings：页面对象合同与矩阵无漏页，P7/P8 结论未漂移；创作失败恢复、群公告/治理权限、交集下钻、沉浸浏览和 pageflip 像素不变量均有 local_contract/UAT 证据。
- [x] 2026-07-20 RTC 商用收口已复核 `main_app_shell.dart`、`voice_call_page.dart`、`video_call_page.dart`：PiP 真实 Hangup、屏幕共享、控制锁定、真实视频轨与 `+N` 摘要均复用 typed Facet/LiveKit 运行态，P7 版式和 P8 语义 token 结论不变。
- [x] 2026-07-20 群聊提及闭环已复核 `chat_conversation_page.dart`：`ListMembers(query)` typed 搜索、稳定 mentions token、角色受控 `@所有人`、气泡高亮和主页跳转共用 metadata 契约；P7 保持既有 `WebPageMaxWidthFrame`，P8 复用 chatInput/主题语义 token。
- [x] 2026-07-20 发起群聊三来源闭环已复核 `start_group_chat_page.dart`：互关联系人、私建群和圈子绑定群经 `ListSelectableGroupConversations(source)`/`SelectableGroupConversationRowDto` 同源，跨来源共用向导与成员交集；P7 保持既有二/三级选择页和 A-Z 版式，P8 复用设置页/聊天语义 token。
- [x] 2026-07-20 M12 主页观测收口已复核 `edit_profile_page.dart`、`my_intersection_inbox_page.dart` 与 `my_qr_code_page.dart`：P4 曝光/TTI/停留统一由 metadata page access 产生，产品动作与推荐行为分别由 Journey/Content tracker 承载，无手工 enter/exit 双计；P7/P8 版式与 token 结论不变。
- [x] 2026-07-20 B6.2 实体主页商用收口已复核 `homepage_claim_page.dart`、`homepage_maintenance_page.dart`、`homepage_status_report_page.dart`、`homepage_detail_page.dart` 与 `homepage_introduction_page.dart`：typed Query/Command Facet、强登录及 owner fail-closed、结构化错误恢复、真实内容跳转与 product action 观测均有 local_contract/UAT 证据；P7 版式与 P8 语义 token 分列结论已同步矩阵。
- [x] 2026-07-21 CM-003 已复核 `main_app_shell.dart`：Tab 页面 P4 TTI 统一从真实导航起点计时，首帧与首个 content/empty/error 可用终态分轨；P1–P3、P5–P9 及 P7/P8 结论不变。
- [x] 2026-07-21 M9 实体主页想去闭环已复核 `homepage_detail_page.dart`：地点类型由 generated UI 配置裁决，`GetEntityWishlistState` 与 `wishlist_add/remove` 事实同源，登录成功续接 one-shot；P7 版式未变，P8 复用对象操作栏与语义 token。
- [x] 2026-07-21 私助偏好管理已复核 `assistant_management_page.dart`：仅投影 active 偏好、撤销恢复限于本次操作窗口；surface operation、required auth 与 typed Facet 同源。P7 延续 Inset 响应式壳，P8 延续设置语义 token。
- [x] 2026-07-21 圈群托管治理已复核 `chat_settings_page.dart` 与 `group_manage_page.dart`：`circleGroupId` 从 metadata projection 生成；保留会话成员与 RTC 能力展示，隐藏 Chat 侧成员/治理写入并跳转 Circle 详情。P7 分别延续成员网格列宽和 Inset 宽度壳；P8 分别延续设置语义颜色、间距与字阶 token。
- [x] 2026-07-21 圈子主页 Phase 2 已复核 `home_circles_hub_page.dart`：聚合 typed Slice 保证默认 `recommended` 单请求、认证后才请求 `mine`；cursor 仅服务端解释并按 `placementId` 去重追加，未回退 N+1 或 raw Map。P7 保持 `AppSpacing` 双列/滚动响应式壳；P8 保持既有语义色、间距和字阶 token。

## 维度快速核对（当前 P1–P9）

- [x] **P1** iOS 根壳与材质符合规范；无违规 Material 根 Scaffold（见 `ios-native-page-enforcement`）。
- [x] **P2** 云接口与模型来自 metadata codegen；无手写 path/operation 第二真相源。
- [x] **P3** production 组合根 Remote-only；alpha/test 由独立 runner/package 显式 override typed Facet（无云则标 **—**）；且 **未** 在 `lib/ui`、`lib/app`、`lib/core` 新增 mock import 或 UI 模型内嵌域名 `prototype*` 占位数据（见 §Mock 与端云隔离）。
- [x] **P4** 页面观测已接统一管道或已标 **—**（豁免说明备注）。
- [x] **P5** 设置/半屏场景已复用标准组件或标 **—**。
- [x] **P6** 浅色/深色可读可点或已登记豁免（S6）。
- [x] **P7** 仅谈 **断点与版式**：`AppSpacing`/`responsiveValue`/登记宽度语义；**不与 token 混写**。
- [x] **P8** 仅谈 **语义 token**：间距/字阶/圆角/色等；**不与断点策略混写**。
- [x] **P9** 声明等待模式与真实 `request_wait_tests`；同一请求单一进度、6 秒前台出口、supersede/dispose 防旧响应回写均有证据。

## 各维置 ✓ 的最低证据（与门禁 / 脚本对齐）

| 维 | 置 ✓ 时须满足（摘要） | 自动化 / 文档 |
|----|------------------------|---------------|
| **P1** | 根 `build` 为 `AppScaffold` / `CupertinoPageScaffold` / 已登记等价壳（含 `ConversationPageScaffold`、`SettingsInsetFormPageScaffold`、`IosSelectionPageScaffold` 等）；或 Tab 内嵌内容区无根 `Scaffold`；子树 `Material` 为 `MaterialType.transparency` 宿主 | `python3 quwoquan_app/scripts/runtime/verify_ios_native_surface_gate.py`；`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.1、§2.8 |
| **P2** | 主读写 API 与 DTO 来自 `contracts/metadata` → codegen；无第二套 path/operation | `python3 quwoquan_app/scripts/runtime/verify_cloud_services_semantic.py`（同向）；逐页 import/Repository 核对 |
| **P3** | production 只装配 Remote typed Facet，业务/UI 不读取 `AppDataSourceMode`；alpha/test 在独立 composition root 注入 contract-seeded adapter；UI 无裸 HTTP；production `lib/**` 不可达 Mock/fixture | `python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py`；[`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) |
| **P4** | 页面级 open/close/停留进入 `AppLogService` 等统一管道；或备注豁免 | Tab 根：`MainAppShell` pageAccess；其余待 GoRouter 级补全时标 **○** 并备注 |
| **P5** | 设置表单走 `SettingsInsetForm*`；成员搜索嵌入式壳走 **`search_embedded`**（`EmbeddedMemberSearchPageShell`，见 `settings_canonical_manifest`）；对话态走 `settings_conversation/` / `ConversationPageScaffold` 等 | `python3 quwoquan_app/scripts/settings/verify_settings_canonical.py`、`verify_conversation_sheet_canonical.py`（同向） |
| **P6** | 双色下可读可点；或与 `dual-theme-page-coverage/page-dual-theme-matrix.md` 交叉引用 | 兄弟 L3 S6 |
| **P7** | compact/regular/expanded 版式可用；优先 `AppSpacing.responsiveValue`、`feedMaxContentWidth` 等 | 与 `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md` §2.7 一致 |
| **P8** | 间距/字阶/圆角/色用语义 token，无魔法数体系 | `python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py` 等 gate 脚本 |
| **P9** | 异步等待与恢复；模式、阶段、取消、终态和页面证据同源 | `make verify-test-coverage-map` + request wait local_contract |

## Mock 与端云隔离（强制）

> 策略全文：[`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md)  
> **禁止**为本 PR **新增** `specs/gates/ui_mock_isolation_allowlist.yaml` 条目；仅允许在清记录债时 **删除** 已有条目。

- [x] `lib/ui/**`、`lib/app/**`、`lib/core/**` **未新增** `import 'package:quwoquan_app/.../mock/...'`。
- [x] **未新增** UI 模型中的域名占位（如 `prototypeCircles`、`unsplash` 业务头像链等）；假数据只放在 `packages/quwoquan_cloud_mock`、`runners/alpha` 或 `test/`。
- [x] 正式包路径不得依赖 **伪 Remote→Mock 委托**或运行时数据源枚举；production provider 恒装配 Remote，alpha/test 通过独立 composition override。
- [x] **编译单元**：未在 `lib/**` 与业务代码 **同文件** 新增仅测用 fake、`forTest` 工厂、`@visibleForTesting` 扩权等（策略 [`mock_data_cloud_integration_policy.md`](./mock_data_cloud_integration_policy.md) **§4.1**）；夹具放在 `test/**`。
- [x] 本地：`make verify-app-mock-isolation` 或 `python3 quwoquan_app/scripts/env/verify_ui_mock_isolation.py` 通过。

## Reviewer

- [x] Reviewer 已确认矩阵列与代码变更一致。

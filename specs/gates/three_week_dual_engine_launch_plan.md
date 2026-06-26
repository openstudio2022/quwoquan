# 三周双引擎发布项目计划书（落实跟踪版）

> 用途：本文件是「三周双引擎发布」的**落实状态唯一跟踪台账**，供逐任务跟踪与建立开发/排查对话使用。
> 关联真相源：`.cursor/plans/三周双引擎发布_ddae7322.plan.md`（原始计划，不在本文件覆盖范围内修改）、`specs/gates/launch_runbook.md`、`specs/gates/release_scope_whitelist.md`、`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md`。
> 最后更新：W?（按实际编辑日回填）。

## 0. 如何使用本计划书

- **状态图例**：
  - ✅ 已完成：代码/规格闭环 + 有测试或门禁证据。
  - 🟡 部分完成：可由代码闭环的部分已落地，剩余受服务端/工期约束（仍可推进）。
  - ⛔ 外部阻断：需法务/设计/云账号/人力，无法由代码会话完成（须责任人）。
  - ⬜ 待办：未开始。
- **任务编号**：沿用 `WSx / Tx.y`。建立对话时请直接引用编号，例如「继续 T6.2 服务端落库」「排查 T3.4 搜索建议」。
- **跟踪粒度**：以 Tx.y 为最小跟踪单元；每个 Tx.y 给出「状态 / 已落地证据 / 剩余项 / 负责方 / 验收与 verify」。
- **优先级**：P0 = 上线阻断；P1 = 公开但可降级；P2 = 保底不主推。

## 1. 主线与战略定位

主线：**交集推荐 + 官方内容工厂 + 用户创作并行**，以**双向可解释性**为核心差异化。

- 官方内容工厂：解决冷启动、质量锚定、对象页完整度、专题深度、首发内容密度。
- 用户创作体系：解决真实体验、关系互动、社区活性、长尾供给、长期留存。
- 两类内容统一进入交集推荐主链，仅在排序、解释、承接与运营上区分。
- 双向可解释性：消费端解释「为什么推荐给我」，生产端解释「你的内容帮到了谁、促成了什么有价值行动」，两端共用同一套交集 + 动作数据、方向相反。

差异化本质：给作者的是**有效连接分配（影响力指标）**，而非流量分配（虚荣指标）。首发尖刀锁定 `校园 + 旅游出行`。

## 2. 真相源

- 推荐与首页承接：`specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md`
- 应用内创作主链：`specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md`
- 8 类反馈闭环契约：`specs/feature-tree/discovery-content/content-display-journey-consistency/content-action-intent-contract/spec.md`
- 交集统一体验与转化漏斗：`specs/feature-tree/object-homepage-network/intersection-unified-experience/design.md`
- 分享回流与归因：`specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md`
- 指标字典与交集北极星：`specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md`
- 发布与 ACK 基线：`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md`
- 行为字段真相源：`quwoquan_service/contracts/metadata/content/post/behaviors.yaml`
- 分享归因参数真相源：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`（`attribution_params`）

## 3. 状态总览仪表盘

| 工作流 | 关键任务 | 状态 | 一句话结论 |
|---|---|---|---|
| WS1 主线冻结与发布纪律 | T1.1–T1.3 | ✅ | 白名单/对外口径/五条主旅程/候选基线已冻结 |
| WS2 合规与双端上架 | T2.1–T2.4 | 🟡 | 治理入口+应用名+隐私清单+安全 spec 已落地；法律正文/图标/签名/商店素材/备案为外部人工 |
| WS3 五条主旅程硬化 | T3.1–T3.6 | ✅ | 孤儿页处理、搜索去伪、退出群聊接线、占位收敛、prototype 隔离确认 |
| WS4 用户创作激活 | T4.1–T4.3 | 🟡 | P0 对象/圈子锚点入口+契约测试已闭环；T4.3 模板提示词（P1）待做 |
| WS5 双向可解释性与 Creator Impact | T5.1–T5.3 | 🟡 | Creator Impact v0 客户端组件（真实总数叙事+零估算）已接入「我的·收到」+测试；服务端 rm_author_impact 反向聚合读模型为后续 P0 |
| WS6 数据闭环与归因 | T6.1–T6.4 | 🟡 | T6.1 pageVisitId 已注入；T6.2 客户端分享归因链接(share_id/utm)+模型+测试已落地，DB 落库需服务端 SharePost 扩展；T6.3/T6.4 为 P1 |
| WS7 可观测与 SLO | T7.1–T7.3 | 🟡 | T7.1 看板去伪已完成；T7.2/T7.3 需后端 recording rule 基础设施 |
| WS8 ACK 发布演练与 Go/No-Go | T8.1–T8.3 | 🟡 | Go/No-Go+降级+演练计划已冻结；真实 ACK 灰度/回滚演练需云账号与 secrets（外部阻断） |
| WS9 运营与内容工厂 | T9.1–T9.3 | 🟡 | 排产表模板+激活规则+客服/FAQ/launch room 已冻结；种子创作者招募与官方内容生产为人力投入（外部阻断） |

## 4. 工作流任务台账

### WS1 主线冻结与发布纪律（P0）

#### T1.1 冻结发布范围白名单与对外口径 — ✅
- 已落地：`specs/gates/release_scope_whitelist.md`（P0/P1/P2 白名单、命名/IA 冻结、禁用旧词、五条主旅程、变更冻结纪律）。
- 剩余：随发布窗口维护白名单条目；非主线能力降级/隐藏策略持续校验。
- 负责方：产品 + 研发。
- 验收/verify：白名单评审通过；前台无白名单外旧词外显。

#### T1.2 冻结五条首发主旅程 — ✅
- 已落地：`release_scope_whitelist.md` 与 `launch_runbook.md §1.2` 冻结 A 登录/游客、B 推荐消费/对象承接、C 小趣解释、D 搜索跳转、E 消息会话。
- 剩余：每条旅程 T4 UAT 脚本随真机回归补充。
- 负责方：研发 + 测试。
- 验收/verify：每条旅程有入口/步骤/成功态/失败态/负责人。

#### T1.3 建立发布候选基线与变更冻结 — ✅
- 已落地：`release_scope_whitelist.md` 冻结变更纪律与脏变更三分类口径。
- 剩余：W2 周日 feature freeze 时建立 release 候选分支并打 tag。
- 负责方：研发。
- 验收/verify：候选基线建立；非 P0 改造冻结。

### WS2 合规与双端上架（P0，含外部阻断）

#### T2.1 法律与合规正文就绪 — ⛔（外部人工）
- 现状：登录强制勾选协议并携带 `agreementVersion/privacyVersion`；法律正文已规划为 `legal-static` 独立静态包，prod canonical 为 `https://quwoquan.com/legal/*`，gateway 同路径兜底；`security-privacy-audit/spec.md` 已填充关键条目。
- 剩余：隐私政策/用户协议/权限说明/SDK 清单经法务确认后通过 `stackctl package --env gamma --kind legal-static` 与 `stackctl verify --env gamma --kind legal-static`；prod URL 200 可达；ICP/算法备案。
- 负责方：法务 + 运营 + 研发。
- 验收/verify：双端审核所需法律 URL 全部 200。

#### T2.2 双端上架物料与签名 — ⛔（外部人工/二进制）
- 已落地：iOS `CFBundleDisplayName` 统一为「趣我圈」。
- 剩余：iOS 全尺寸 AppIcon PNG + LaunchImage；Android mipmap 全密度 launcher；正式 keystore + release 签名；CI 增加 Android AAB / iOS IPA 上架构建（带 `APP_DATA_SOURCE=remote`）。
- 负责方：设计 + 研发 + CI。
- 验收/verify：双端可产出正式签名上架包并归档。

#### T2.3 商店素材、审核说明与测试账号 — 🟡
- 已落地：`quwoquan_app/ios/Runner/PrivacyInfo.xcprivacy`（iOS 隐私清单）。
- 剩余：截图/预览/描述文案；各渠道审核说明 + 敏感权限用途；可走通五条主旅程的测试账号。
- 负责方：运营 + 研发。
- 验收/verify：双端提交清单齐备；测试账号可登录走通主旅程。

#### T2.4 治理入口闭合 — ✅
- 已落地：资料页用户级举报/拉黑接 Remote（`profile_shell_builders.dart` 经 `blockRepositoryProvider`/`reportRepositoryProvider`，登录门 + 二次确认 + 举报原因面板 `_ProfileReportReason`），相关文案补全。
- 剩余：英文本地化逐步补齐（非阻断）。
- 负责方：研发。
- 验收/verify：用户级举报/拉黑可真实提交；登录门覆盖。

### WS3 五条主旅程硬化与痕迹清理（P0）— ✅

#### T3.1 旅程 A 登录/游客硬化 — ✅
- 已落地：欢迎→登录/游客闭环、防死循环；调试码由服务端标志驱动；第三方登录占位在 release 收敛。
- 验收/verify：prod 构建无调试码可见路径；无「假可用」入口。

#### T3.2 旅程 B 推荐消费与对象承接硬化 — ✅
- 已落地：交集理由双形态同源、点击按对象类型路由并归因；`discovery_page.dart` 孤儿页确认/处理（live home = `home_page.dart`）。
- 验收/verify：首页/详情/对象页主路径走通；无孤儿页参与构建。

#### T3.3 旅程 C 小趣解释硬化 — ✅
- 已落地：助手全局/沉浸/评论@入口、Remote 流式、推荐解释投影；半弹窗交互收敛；失败文案结构化。
- 验收/verify：无「假输入框」；错误态走结构化文案。

#### T3.4 旅程 D 搜索硬化 — ✅
- 已落地：移除伪造网络建议（`search_coordinator.dart` 仅保留诚实的分 tab 跳转意图）；关键 catch 补处理；主文案语义化。
- 验收/verify：搜索无伪造建议误导；无静默吞错主路径。

#### T3.5 旅程 E 消息会话硬化 — ✅
- 已落地：「退出群聊」接真实 `removeMember(self)`（确认弹窗 + 成功 toast + 返回列表）。
- 验收/verify：会话主路径稳定；无「开发中」可见入口。

#### T3.6 横切技术债隔离确认 — ✅
- 已落地：确认 `prototype_mock_data.dart` 不进入主旅程渲染；R02/R26 债登记发布后 backlog。
- 验收/verify：prod 主旅程不消费 prototype 数据。

### WS4 用户创作激活（P0 + P1）

#### T4.1 多入口创作召唤（P0）— ✅
- 已落地：圈子页「向圈子投稿」入口（`circle_shell.dart` more-actions，携带 `CreateEntryArguments` 的 circleId/circleName）；底栏加号 + `createEntry` 面板既有入口。
- 剩余：对象页「写我的体验」（homepage 锚点）、首页场景化召唤可继续补强。
- 负责方：研发。
- 验收/verify：圈子页一键进入带锚点创作；入口走登录门。

#### T4.2 结构化创作锚点强化（P0）— ✅
- 已落地：`create_entry_arguments.dart` 模型 + `create_page.dart` 接收 `initialCircleId/initialCircleName` 注入 `PublishSettings`；`app_router.dart` 从 `extra` 解析；契约测试 `publish_payload_contract_test.dart` 校验圈子锚点注入 payload（circleIds + 公共可见性）。
- 剩余：对象/地点锚点同样前置到创作主流程。
- 负责方：研发。
- 验收/verify：`flutter test test/ui/content/entry/contract/publish_payload_contract_test.dart`。

#### T4.3 创作模板与提示词（P1）— ⬜
- 现状：仅有视觉排版模板，无写作/选题提示词机制。
- 剩余：校园经验/路线记录/住宿反馈/地点打卡/对象评价/圈内问答 6 类场景模板与提示词骨架 + 模板选用率埋点。
- 负责方：产品 + 研发。
- 验收/verify：创作不再面对空白输入框；模板可选并预填结构。

### WS5 双向可解释性与 Creator Impact（P0 v0，差异化核心）

#### T5.1 作者影响力聚合读模型（P0）— ⬜（服务端）
- 现状：仅有 per-actor 明细（`ListByAuthor`、`/users/me/received-comments`、`interactions/received`），无按 authorId 聚合的作者影响力读模型/投影。
- 剩余：metadata-first 定义 `rm_author_impact`（authorId → 收到的赞/收藏/评论/分享/关注转化/对象页跳转/被引用，按交集维度下钻）→ codegen → 投影器消费行为/交集事件聚合到 authorId；T1 契约 + Mock/Remote 同形 + T3 远端对齐。
- 负责方：服务端研发。
- 验收/verify：作者维度聚合可查询；口径与指标字典一致。

#### T5.2 Creator Impact 影响力面板 v0（P0）— 🟡（客户端 v0 已落地）
- 已落地：`creator_impact_summary.dart`（模型，count==0 隐藏、零估算）+ `creator_impact_card.dart`（卡片）；以 `getUserStats` 真实聚合总数（关注/赞同/作品/圈子）翻译为影响力叙事；接入 `profile_interaction_tab.dart` 的「我的·收到」；单元 + widget 测试通过，未破坏 profile 几何测试。
- 剩余：接入 T5.1 服务端读模型后扩展决策/知识/交集等动作类，并将面板叙事从「总数」升级为「促成了什么有价值行动」。
- 负责方：研发（依赖 T5.1）。
- 验收/verify：`flutter test test/ui/user/creator_impact_summary_test.dart test/ui/user/creator_impact_card_test.dart test/ui/user/widgets/profile_shell_widget_test.dart`。

#### T5.3 消费端可解释首屏强化（P0）— 🟡
- 现状：交集理由已双形态呈现且同源（首屏交集模块 + 卡片 chip）。
- 剩余：每条内容显性化下一步动作（收藏/进对象页/问小趣/加入圈子/关注）；动作→归因回流校验。
- 负责方：研发。
- 验收/verify：用户 30 秒内同时获得「为什么给我」和「看完能干什么」。

### WS6 数据闭环与归因（P0）

#### T6.1 session/pageVisitId 口径收敛 — ✅
- 已落地：`app_trace_context_store.dart` 增加共享 `currentPageVisitId`，`journey_event_tracker.dart` 消费注入，`pageVisitId` 不再恒空。
- 剩余：指标字典补登 `feedSessionId` 与 `sessionId` 区分。
- 负责方：研发 + 数据。
- 验收/verify：页级漏斗可按 pageVisitId 归因。

#### T6.2 分享归因落库（P0，传播类基石）— 🟡
- 已落地：`core/links/share_attribution.dart`（`ShareAttribution` 生成 share_id + UTM，key 对齐 `link_templates.yaml attribution_params`，仅追加 http(s)、scheme 深链不动）；`content_share_template.dart` 每次分享生成 shareId 并注入 landingUrl、暴露只读 `shareId`；单元测试 `share_attribution_test.dart` + 分享模板断言更新。
- 剩余（服务端）：扩展 `SharePost` 携带并落库 `share_id/utm`（metadata→codegen→Go）；口令/短链/二维码解析回流；`shareIntent/shareClick/shareSuccess/tokenResolved` 四段埋点 + T3 回流验证。
- 负责方：服务端研发 + 端研发。
- 验收/verify：`flutter test test/core/links/share_attribution_test.dart test/ui/content/share/`；服务端落库后单次分享可归因、站外回流可归因。

#### T6.3 小趣引用专用信号（P1）— ⬜
- 现状：服务端仅落 `assistantMentioned`；`xiaoqu.mention.triggered`/`xiaoqu.open` 无端侧专用 tracker、无作者归因。
- 剩余：端侧上报 `xiaoqu.mention.triggered`；引用→authorId 归因接入 T5.1 知识类。
- 负责方：研发（依赖 T5.1）。

#### T6.4 创作绑定实体埋点（P1）— ⬜
- 现状：字典定义 `content.homepage.attach`，端侧是否发该专用 telemetry 未确认。
- 剩余：创作绑定对象/地点时上报 `content.homepage.attach`。
- 负责方：研发。

### WS7 可观测与 SLO（P0 + P1）

#### T7.1 看板去伪数据（P0）— ✅
- 已落地：`OverviewDashboardPage.tsx` 移除合成趋势假数据，替换为真实 `ReleaseItem` 字段，未监控指标显式标「暂无数据」。
- 验收/verify：launch dashboard 无伪造数据；缺数据显式空态。

#### T7.2 实时落点补齐（P1）— ⬜（需后端基设）
- 现状：`deriveL1L4MetricState` 仅 4 个指标实时，其余 snapshot 兜底。
- 剩余：补齐 launch 必需 L1/L2 实时指标（circle_join_rate、交集转化）实时落点；coverage 达标。
- 负责方：服务端 + 数据。

#### T7.3 端侧 SLO 告警落地（P1）— ⬜（需后端基设）
- 现状：端侧 `ClientAPILatencyHigh` 为占位、非 Prom 直采。
- 剩余：端侧 API 延迟/错误率/降级经 recording rule 或日志平台落为可触发告警 + 值班路由。
- 负责方：SRE + 研发。

### WS8 ACK 发布演练与 Go/No-Go（P0）

#### T8.1 gamma-local 左移主验证链 — 🟡
- 现状：`local-gamma-mirror` 与 prod-hosted 同构性 T2 PASS；左移链 GWT1/GWT2 仍 pending、脚本为 planned。
- 剩余：跑通 gamma-local 提交前左移 T3/T4 并回填 acceptance recorded。
- 负责方：研发 + 测试。

#### T8.2 ACK prod 灰度/SLO/回滚真实演练 — ⛔（需云账号）
- 现状：CI(`deploy-prod-auto.yml`) + `stackctl.py` + `gray_rollout_stages.yaml` 接线 ready、拓扑 T1/T2 PASS；端到端 T3/T4 pending（本地无云账号不虚标）。
- 剩余：配置 `PROD_KUBECONFIG`/state；执行灰度(initial→full)→SLO gate→auto rollback 全链；回填 gray-release/instance-isolation 证据。
- 负责方：SRE + 研发。

#### T8.3 Go/No-Go 与降级预案 — ✅
- 已落地：`launch_runbook.md §1` Go/No-Go 清单 + `§2` 降级预案（Android 先行 / 邀请制 / 继续内测）。
- 剩余：W2 周日与 W3 周日各执行一次 Go/No-Go 并留痕。
- 负责方：全体。
- 验收/verify：两次评审留痕。

### WS9 运营与内容工厂（P0 + P1）

#### T9.1 官方内容工厂排产 — 🟡
- 已落地：`launch_runbook.md §3` 两周内容排产表模板（校园包/川西成都旅行包/住宿避坑/路线交通/对象点评 + 对象页基础层）。
- 剩余：填充实际条目与负责人；对象页基础层补完批次入库。
- 负责方：运营 + 数据工程。

#### T9.2 用户创作激活计划 — 🟡
- 已落地：`launch_runbook.md §4` 种子创作者、任务与精选规则、创作者反馈看板（以可见影响力为核心）。
- 剩余：种子创作者名单 + 招募；精选/任务/荣誉规则落地;创作激活看板上线。
- 负责方：运营。

#### T9.3 客服、FAQ 与 launch room — 🟡
- 已落地：`launch_runbook.md §5` 客服入口/FAQ/举报处置 SLA/launch room 值班与每日复盘。
- 剩余：实际客服入口与 FAQ 上线;值班表确认。
- 负责方：客服 + 运营。

## 5. 三周日历映射

- W1 周三：T1.1 T1.2 T1.3；T2.1 T2.2 T2.3 启动；确认合规责任人。
- W1 周日：T3.1–T3.6；T4.1 T4.2；T5.3。
- W2 周三：T6.1 T6.2；T5.1 T5.2；T7.1；T9.1 T9.2。
- W2 周日：Feature freeze；T2.2 T2.3 提审包；T8.1 T8.2 演练；T8.3 第一次 Go/No-Go。
- W3 周三：内测周中收敛；T7.2 T7.3 T6.3 T6.4 收尾。
- W3 周日：T8.3 第二次 Go/No-Go；按结果灰度开放或降级；T9.3 值班复盘。

## 6. 验收与门禁总表

- UAT：五条主旅程 + 创作发布 + 分享回流。
- SIT：创作→推荐、创作→对象页、分享→回流、交集解释→后续动作、Creator Impact 反向归因。
- GWT/contract：创作 payload、分享归因(share_id/utm)、交集字段、feedRequestId/pageVisitId、对象锚点、发布可见性、author impact 聚合口径。
- T1~T4：
  - T1：metadata/codegen/contract 与创作、分享、推荐、author impact 字段一致。
  - T2：P0 页面与 Provider/Widget（含 Creator Impact 卡片、创作锚点）。
  - T3：gamma-hosted/ACK 关键 API、关键旅程、SLO 与告警、分享回流。
  - T4：五条用户旅程 + 双端提审前复验 + gamma-local 左移。
- 门禁命令：
  - `make gate` / `bash agent_ops/gate/gate_repo.sh --scope app`
  - `flutter test test/core/links/share_attribution_test.dart`
  - `flutter test test/ui/content/share/`
  - `flutter test test/ui/content/entry/contract/publish_payload_contract_test.dart`
  - `flutter test test/ui/user/creator_impact_summary_test.dart test/ui/user/creator_impact_card_test.dart`
  - `flutter test test/ui/user/widgets/profile_shell_widget_test.dart`

## 7. 风险与降级预案

- 合规/上架物料是最大外部阻断：W1 周三未就绪 → Android 先行或邀请制受控开放。
- Creator Impact 需新读模型，有工期风险：v0 仅真实计数 + 叙事；复杂权重/收益估值/现金结算 Out of Scope。
- ACK 真实演练依赖云账号/secrets：无法及时获得 → 至少完成 gamma-local 左移 + ACK 演练计划，并在 Go/No-Go 降级。
- 脏变更回归面大：靠 release 候选基线 + 变更冻结 + 主旅程 T2/T4 回归控制。

## 8. 发布后 backlog 与 Out of Scope

- 发布后 backlog：`prototype_mock_data` 清理、`AppContentRepository` 上帝接口拆分、全域埋点补齐、超大文件强拆、第三方登录与运营商原生实现、英文本地化补齐。
- 显式 Out of Scope：复杂 RTC、深度助手增强、复杂运营后台、Creator Impact 复杂权重/收益/现金、所有非首发平台化重构。

## 9. 关键剩余阻断清单（建立对话优先级）

1. T5.1 服务端 `rm_author_impact` 反向聚合读模型（解锁 T5.2 升级、T6.3 归因）— 服务端研发。
2. T6.2 服务端 `SharePost` 落库 share_id/utm + 口令/短链回流 — 服务端研发。
3. T2.1/T2.2/T2.3 法律正文/图标/签名/商店素材/备案 — 法务/设计/运营。
4. T8.2 ACK 真实灰度/回滚演练 — 云账号/SRE。
5. T4.3 创作模板与提示词（降低创作门槛）— 产品/研发。

## 10. 变更记录

- 初始版：基于代码与规格实测的 Readiness 评估 + WS1–WS9 任务台账冻结。WS1/WS3 已完成；WS2/WS4/WS5/WS6/WS7/WS8/WS9 部分完成，剩余项按本台账「负责方」推进。

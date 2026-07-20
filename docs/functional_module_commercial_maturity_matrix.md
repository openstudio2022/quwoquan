# 趣我圈功能版块商用成熟度基线与并行会话任务规格

> 状态：功能版块级审计底料（不是“已商用”证明）  
> 证据截点：2026-07-20  
> 适用范围：App、Service、metadata、测试、观测、运营与环境验收  
> 风险唯一真相源：[`docs/outstanding_risks_backlog.md`](outstanding_risks_backlog.md)  
> 执行总控：本文任务包已收敛为稳定编号的 CM 清单项，批次编排、启动提示词与追踪表见
> [`docs/commercial_maturity_master_plan.md`](commercial_maturity_master_plan.md)（M/H → CM 反查见其 §2）。

## 0. 使用边界与结论口径

本文用于把“全面商用”拆成可并行执行、又能重新汇合的功能版块任务包。它不把现有页面、目录、接口或模型视为天然正确，也不以“代码存在”“矩阵为绿”“按钮可点击”替代商业闭环证据。

统一审查主线：

`业务目标 → 核心业务对象 → 对象关系 → 对象生命周期 → 用户旅程 → 功能能力 → 页面承载 → 交集差异化 → 运营指标 → 测试验证`

本文结论分为三种：

- **已证实**：有可定位的 metadata、代码、测试或环境证据。
- **待专项核验**：现有静态证据不足，尤其是视觉、真机、真实 SLS、真实外部 SDK 与 hosted prod 证据。
- **GATE_BLOCK 候选**：已发现可能阻断商用的对象、页面、旅程或测试断点；专项会话必须复核并决定修复、删减或在用户确认后登记 backlog。

### 0.1 双 P 口径

- **页面成熟度级 P0～P5**：本文和专项会话用于决定新增、删除或重构；P0=缺失/错位，P1=原型/空壳，P2=基本可用但不完整，P3=功能较完整但体验不足，P4=业界成熟商用，P5=在 P4 上形成趣我圈交集差异化。
- **页面横向质量维 P1～P9**：[`page-horizontal-quality-matrix.md`](../specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md) 中的 iOS、metadata、端云、埋点、模板、双色、断点、token、异步恢复维度。

两者不能互相替代。横向质量维全绿只表示静态治理项已登记，不代表页面已达到成熟度 P4/P5。

### 0.2 视觉证据限制

本文的页面成熟度均为**静态预评级**。未在本轮通过真实运行、真机截图或高保设计核验的页面统一标记“视觉未核验”；专项会话不得据此直接宣称视觉 P4/P5。

## 1. Spec Entry 与商用目标

- **AppRoot Journey/Scenario**：覆盖 registry 的全部 11 条 Journey 和 23 条 Scenario，详见 §4.3。
- **L1 domain service**：覆盖 14 个 canonical 业务对象域 + 1 个 platform 控制面逻辑域、14 个 Go 服务及 realtime/coturn/livekit 等运行依赖。
- **L2 capability / L3 story**：由各版块 A 段绑定到现有 feature-tree；找不到绑定时返回 GATE_BLOCK，先补规格而非直接实现。
- **验收意图**：AppRoot 用 UAT；跨域能力用 SIT；对象状态机与页面规则用 GWT/contract。
- **测试证据**：`local_contract`、`api_integration`、`user_acceptance` 三层缺一不可；环境分层为 alpha、beta、gamma-local、prod-hosted。
- **用户价值**：形成真实可走通、可恢复、可观测、可运营、可灰度回滚的商用旅程，而不是仅把页面和 API “接上”。

## 2. 六维度统一商用基线

| 维度 | 当前全局基线 | 目标规格 | 全局验收门 |
|---|---|---|---|
| D1 功能与旅程 | 11 条 Journey 中既有 `specified` 也有 `draft`；backlog 仍有登录凭据、RTC 鉴权、通知断链、搜索伪热点等阻断项 | 核心对象生命周期各关键状态均有可进入页面、合法操作、反馈、回流和恢复；真实数据，无 Mock 伪装 | 对应 UAT 全链通过；关闭登录不循环；失败/权限/失效均有安全终态 |
| D2 DDD 与 metadata | 生产 Go application/domain 分层扫描无直接反向依赖；业务路径硬编码已清；辅助对象仍有错误契约与目录治理缺口 | 聚合、关系、状态机、command/query/event/error、存储/缓存/索引与页面投影单轨；对象 S/F/E 及适用 U 齐备 | ContractGraph、metadata、codegen、对象状态机与存储真实集成证据一致 |
| D3 UX 与页面 | 87 个横向矩阵行无 `○`；仍不能证明页面成熟度；横向静态合规与商业成熟度必须分开 | 核心页成熟度≥P4，交集主战场=P5；对象语义、IA、状态、token、模板、双色、断点、iOS、无障碍一致 | 真机/截图审查 + 横向质量门禁 + 重构前后旅程回归 |
| D4 非功能 | 启动阶段遥测和 API RT 拦截已有；通用页面 TTI、ANR watchdog 与统一离线策略不足 | 页面/接口性能预算、分页缓存、弱网恢复、幂等、灰度与回滚同时冻结；不以后补方式处理 | P50/P95/P99、错误率、恢复率及容量证据在 beta/gamma/prod 可读 |
| D5 可观测与运营 | 路由级 page_open/page_return、结构化异常、frame jank、Prometheus 中间件已有；真实 SLS/ANR/页面 TTI/多域行为仍有缺口 | 每页曝光/停留/异常/TTI/ANR/恢复页；每关键业务最多 3 个黄金指标；二级指标可下钻到页面、对象状态、operation、错误码 | 真实采集→传输→ETL→SLS/Prometheus→dashboard/alert 全链可回放，不允许 fake |
| D6 测试 | 当前磁盘 App local_contract 483、api_integration 9、user_acceptance 87；coverage map 通过，但 RTC 特性树扁平化并行改动仍有重复/缺失 acceptance，test specs 未通过 | 状态机、关系、权限、生命周期、页面-对象一致性、交集事实与隐私、重构回归三层齐备 | alpha contract、beta remote、gamma-local Patrol、prod gray canary 证据绑定 acceptance |

## 3. 每个专项会话必须产出的 A～G

1. **A 版块定位**：用户目标、Journey/Scenario、交集定位。
2. **B 业务对象底料**：核心/关联对象、聚合与上下文、关系和基数、生命周期、metadata、API、服务、存储、事件、权限、指标、测试。
3. **C 页面清单与成熟度**：全部页面/路由、P0～P5、证据、视觉核验状态及保留/精修/适度重构/完全重构/新增/合并/删除决策。
4. **D 对象—功能—页面双向矩阵**：对象找页面、页面反查对象；指出无承载对象、假对象、错对象、入口/结果断裂。
5. **E D1～D6**：每维包含当前规格、目标规格、任务和验收标准。
6. **F 业界标杆**：对 P0～P3 页面实时检索 2～4 个标杆，注明来源和检索日期；只提炼原则。
7. **G 可复制启动提示词**：明确本节底料、Out of Scope、交付物和出口证据。

专项会话最终还必须完整交付：业务对象全景、聚合关系、生命周期、双向矩阵、页面评级、重构决策、标杆对比、交集矩阵、问题页面清单、逐重构页目标功能/UX/任务/验收。

## 4. 覆盖与去重

### 4.1 Canonical metadata / control-plane 逻辑域 → 功能版块

磁盘当前存在 14 个业务对象 `business_object_map.yaml`，另有 `_control_plane/platform/control_plane.yaml` 作为平台控制面逻辑域，因此本文审查总口径为 **14 个 canonical 业务域 + 1 个 platform 控制面域 = 15 个逻辑域**。`contracts/metadata/chat` 与 `circle` 没有对象图，按 M6/M8 作为 generated/历史出口目录复核，而不是新增 canonical 域；`_control_plane/product` 是现有 ops/content/recommendation 对象的控制面投影，不另算第 16 域。

| metadata 域 | 主版块 | 交叉消费 |
|---|---|---|
| assistant | M11 | M6、M5 |
| content | M3、M4、M16 | M9、M10、M12 |
| entity | M9 | M3、M5、M8、M10 |
| integration | M18 | M4、M5、M10 |
| messages | M6 | M8、M11、M13 |
| notification | M13 | M6、M11、M14 |
| ops | H1 | 全部版块 |
| realtime | M7 | M6、M11、M13 |
| recommendation | M3 | M5、M8、M9、M10、M17 |
| rtc | M7 | M6、M10 |
| search | M5 | M3、M8、M9、M11、M17、M18 |
| social | M8 | M3、M6、M10、M18 |
| tag | M17 | M1、M3、M4、M5、M8、M9、M10、M12 |
| user | M1、M12 | M3、M6、M7、M8、M9、M10、M11 |
| platform control plane | H1、H2 | 配置、告警、发布、灰度、审计 |

### 4.2 Go 服务 → 功能版块

| 服务 | 主版块 | 备注 |
|---|---|---|
| assistant-service | M11 | assistant runtime / consent / subscription |
| chat-service | M6 | message、conversation、group |
| circle-service | M8 | circle / member / group unit |
| content-service | M3、M4、M16 | post、media、interaction |
| entity-service | M9 | homepage / review / claim |
| integration-service | M18 | location / external integration |
| notification-service | M13 | AppMessage / delivery |
| platform-ops-service | H1 | 配置、治理、观测控制面 |
| product-ops-service | M14、H1 | 运营事件、分享、增长 |
| realtime-gateway | M7 | 同时服务 chat/assistant/notification realtime |
| rtc-service | M7 | call session / media control |
| search-service | M5 | cross-domain search / index |
| tag-service | M17 | taxonomy 发布投影查询 |
| user-service | M1、M12 | account / persona / relationship / profile |

非 Go 运行依赖：`recommendation-service` 归 M3/H1；`rec-model-service` 归 M3；`coturn`、`livekit-sfu` 归 M7；`legal-static` 归 M15；`seed-box` 归 H2 环境证据。

### 4.3 Journey → 功能版块

| Journey | 主版块 | 协同版块 |
|---|---|---|
| identity-entry-and-continuation | M1 | M2、M15 |
| cold-start-safe-handoff | M2 | H1 |
| content-discovery-to-consumption | M3 | M9、M10、M12 |
| cross-domain-search | M5 | M3、M6、M8、M9、M18 |
| app-root-navigation-safety | M2 | M3 |
| message-social-connection | M6 | M8、M11、M12、M13 |
| circle-entity-group-collaboration | M8 | M6、M9、M16 |
| assistant-omnipresent-private-assistant | M11 | M3、M5、M6、M8、M12、M13 |
| external-acquisition-and-deeplink | M14 | M2、M3、M9、M15 |
| intersection-action-to-companionship | M10 | M6、M7、M8、M9、M12、M17、M18 |
| profile-private-activity-history | M12 | M3、M14、M16 |

### 4.4 版块索引与交集定位

| ID | 版块 | 交集定位 | 商用审查重点 |
|---|---|---|---|
| M1 | 身份与登录 | 无需承载 | 身份续接、凭据、Persona、合规同意 |
| M2 | 应用壳与冷启动 | 无需承载 | 有限时间终态、恢复、导航、深链 |
| M3 | 内容发现与消费 | 核心承载 | 发现解释、消费、互动回流 |
| M4 | 内容创作与发布 | 场景增强 | 草稿、媒体、标签/实体/地点关联、原子发布 |
| M5 | 搜索 | 核心承载 | 跨域检索、证据、筛选、结果行动 |
| M6 | 消息与聊天 | 场景增强 | 打招呼升级、会话、群与消息生命周期 |
| M7 | 音视频通话 | 无需直接展示 | 行动阶梯终点、可信鉴权、媒体恢复 |
| M8 | 圈子与社区 | 核心承载 | 同好聚集、成员治理、群单元、协作 |
| M9 | 实体主页 | 核心承载 | 对象身份、口碑、认领、想去与交集 |
| M10 | 交集与同趣配对 | 核心主战场 | 事实证据、推断边界、行动与关系沉淀 |
| M11 | 小趣助手 | 场景增强 | grounding、consent、主动投递 |
| M12 | 我的主页与关系 | 核心承载 | Persona、关注/拉黑、联系人、私有历史 |
| M13 | 通知与推送 | 场景增强 | 源对象引用、已读、设备投递、回流 |
| M14 | 分享增长与深链 | 场景增强 | 对外分发、归因、安装后还原 |
| M15 | 设置与合规 | 无需承载 | 账号、权限、外观、协议与 legal-static |
| M16 | 评论与互动 | 场景增强 | 评论树、反应、删除/封禁同步 |
| M17 | 标签与兴趣画像 | 核心基础 | taxonomy、兴趣表达、交集证据 |
| M18 | 位置与地点集成 | 场景增强 | POI、模糊位置、隐私、地点对象提升 |
| H1 | 可观测接线 | 横切 | ANR、TTI、恢复页、SLS/Prometheus |
| H2 | 测试治理 | 横切 | 三层、四环境、acceptance 真实性 |

### 4.5 与并行轨道的去重

| 并行轨道 | 该轨道负责 | 本文/专项版块负责 | 不得重复 |
|---|---|---|---|
| 业务对象商用闭环 12 批 | R-OBJ 系列对象 Facet、metric、通知、AB、生产装配 | 页面—对象一致性、版块旅程、体验和三层证据 | 不另建 Repository、metric 目录或第二风险清单 |
| 运维运营平台 | SLS/Prometheus/Alertmanager、ETL、配置、发布、灰度与控制面 | 各页面/operation 的采集接线、黄金指标与下钻维度 | 不另建日志平台或环境拓扑 |
| 推荐商用二期 | 召回、排序、objectCards、channel、训练/Serving | App 消费、推荐解释、行为回流、交集事实展示 | 不复制推荐策略和模型真相源 |
| 交集对象专项 | intersection kind/action/read model/算法与服务实现 | M10 页面表达、入口、隐私、行动与 UAT | 不另建第二套交集枚举或聚合 |

## 5. 页面覆盖规则

- 页面事实源：[`page_object_contract.yaml`](../quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml)。
- 横向矩阵：87 行，其中 3 行 T0 helper/barrel，84 行需要独立或父级验收。
- 专项会话必须覆盖本版块全部 `lib/ui/**/pages/*_page.dart`、`welcome_screen.dart`、`components/**/*_page.dart` 与 `lib/app/shell/*.dart` 归属行。
- 嵌入式 sheet/overlay（分享面板、创建入口、PublishLocationSearchPage）不因不占矩阵行而免审；应挂在父页面对象—功能矩阵。
- “对象无独立页面”不是自动缺口：若对象按生命周期应由嵌入控件、设置页或只读投影承载，专项会话需证明其承载完整；无法完成必要操作才判 GATE_BLOCK。

## 6. 并行会话统一启动与退出

复制某版块 G 段后，专项会话必须：

1. 先读该版块 A～F、相关 feature-tree、metadata object map、page object contract 和 backlog。
2. 做现状复核，不把本文预评级当最终结论。
3. P0～P3 页面实时检索标杆；视觉必须真机/截图核验，否则保持“视觉未核验”。
4. 发现新长期风险先向用户复述事项/原因/影响，经确认后才写 backlog。
5. 最终按规格达成、测试证据、E2E、产品/UX、运营观测、门禁和剩余风险做 Exit Review。

---

## H1 可观测接线基线

> 本节将在 §8 完整展开；所有 M1～M18 的 D5 必须引用 H1，不得自建第二套采集、指标或错误目录。

## H2 测试治理基线

> 本节将在 §9 完整展开；所有 M1～M18 的 D6 必须引用 H2，并补本版块对象/页面差异。

## 7. 功能版块专项底料

### M1 身份与登录

> A～G 见 §10。

### M2 应用壳与冷启动

> A～G 见 §11。

### M3 内容发现与消费

> A～G 见 §12。

### M4 内容创作与发布

> A～G 见 §13。

### M5 搜索

> A～G 见 §14。专项会话已完成（2026-07-20）：交付 [`search-commercial-maturity-plan.md`](search-commercial-maturity-plan.md)（对象全景 / 双向矩阵 / P0–P5 评级 / 标杆对比 / 交集规划 / WP-H~L 工作包）；关键裁定：交集 `connectionState/intersectionReason` 为死契约字段（WP-J 接 content-service `IntersectionService`）、`rankReasons` wire 大小写漂移已修、页面评级 P2+/P3/P3 均保留收口不重构。

### M6 消息与聊天

> A～G 见 §15。

### M7 音视频通话 RTC

> A～G 见 §16。

### M8 圈子与社区

> A～G 见 §17。

### M9 实体主页

> A～G 见 §18。

### M10 交集与同趣配对

> A～G 见 §19。
>
> **2026-07-20 专项分析已完成**：施工真相源见 [`docs/intersection-commercial-maturity-plan.md`](intersection-commercial-maturity-plan.md)（十项交付物 + D1~D6 + 整改工作包 WP-IX-0～5）；新增风险 R-IX08/R-IX09/R-IX10 已登记 backlog；§19 预评级由该报告复核定稿（launcher 维持 P1 完全重构，impact 证据列表页与约伴承接判 P0 新增，视觉未核验保持标注）。

### M11 小趣助手

> A～G 见 §20。

### M12 我的主页与关系

> A～G 见 §21。

### M13 通知与推送

> A～G 见 §22。

### M14 分享增长与深链

> A～G 见 §23。

### M15 设置与合规

> A～G 见 §24。

### M16 评论与互动

> A～G 见 §25。

### M17 标签与兴趣画像

> A～G 见 §26。

### M18 位置与地点集成

> A～G 见 §27。

## 8. H1 详细规格

### H1-A 当前链路与证据

| 观测面 | 当前事实 | 证据 | 商用判断 |
|---|---|---|---|
| 未捕获异常 | `runZonedGuarded`、`FlutterError.onError`、`PlatformDispatcher.onError` 与 fingerprint 已接入；上一进程 native crash 通过 marker 在下次启动补报 | `quwoquan_app/lib/app_bootstrap.dart`、`lib/core/observability/runtime_diagnostics.dart` | 基础能力存在；native crash 不是实时上报 |
| 卡顿 | `SchedulerBinding.addTimingsCallback` 按 120 帧聚合，50ms 为 jank、200ms 为 severe | `runtime_diagnostics.dart` | 能观测帧卡顿；不能等同 ANR |
| ANR | 当前 Android/iOS 生产代码未发现持续主线程 heartbeat/watchdog 与 ANR outcome 事件 | `android/**`、`ios/**` 及 `runtime_diagnostics.dart` 扫描 | **GATE_BLOCK 候选**：图一要求的 ANR 率/总量尚无直接采集证据 |
| 页面生命周期 | `page_open`、`page_return(durationMs)` 由路由 observer 统一采集 | `app_page_access_navigator_observer.dart`、`page_access_log_util.dart`、`app_telemetry_catalog.g.dart` | 页面曝光/停留底座已具备 |
| 页面 TTI | 首页 feed 有 `home_feed_first_screen_tti_ms`；启动有四段耗时；未发现通用页面 TTI contract | `feed_performance_observability.dart`、`home_multi_form_feed.dart`、`startup_telemetry.dart` | 详情、搜索、会话、实体、助手等关键页仍需统一口径 |
| API RT | `CloudHttpClient` 全路径 latency observer 写 runtime access 事实 | `lib/cloud/runtime/http/cloud_http_client.dart`、`runtime_api_latency_dispatcher.dart` | 已有统一入口；对象 dashboard 消费不完整 |
| 事件目录 | 当前 codegen 有 page、startup、exception、product action、performance、operation、RTC、realtime、video QoE 共 10 类事件 | `contracts/metadata/ops/event_record/event_catalog.yaml` → `app_telemetry_catalog.g.dart` | 新事件必须 metadata-first，禁止页面自造名字 |
| 服务 RED | Go 服务统一 HTTP middleware 产出 request、duration histogram、inflight、response bytes 和 error code | `quwoquan_service/runtime/observability/**` | 基础 RED 已具备 |
| Prometheus 目标 | compose 服务与 search/rtc 已登记；realtime-gateway 因实现未就绪被明确排除 | `quwoquan_ops/observability/monitoring/prometheus.yml` | 与 R-OPS-OBS-STACK 同源，生产演练未闭合 |
| 数据落点 | 目标链路为 App/Service → gateway/collector → SLS；alpha 使用协议替身，beta/gamma release/prod 才能形成真实 SLS 证据 | `docs/ops_capability_environment_consumer_matrix.md` | R-TELEMETRY-001、R-OPS-LOG-COLLECTOR、R-OPS-RUNTIMELOG-DELIVERY 未关闭 |
| 对象指标 | content/assistant/circle/chat/user 已有部分对象告警；其余对象与通用 metric→alert/dashboard coverage 尚未闭合 | R-OBJ-001 | 不能用服务级 HTTP 指标冒充对象健康 |

`runtime_exception` 产品事件不能被解释为“所有页面异常自动覆盖”：当前通用未捕获/已处理异常主要走独立 RuntimeLogger `/ops/runtime-logs`，而产品目录事件主要用于启动或显式投影。页面错误面展示、运行时异常和业务 operation 失败是三类事实，必须分别采集再以 trace 关联。

### H1-B 统一数据轨

1. **产品遥测轨**：`AppTelemetryReporter → /ops/events → EventBatchAppender → raw/hourly rollup`，只用于产品使用和 App QoE。
2. **Runtime 轨**：Dart/Go/Python/Portal 结构化日志 → RuntimeLogBatchAppender/collector → SLS；异常以 `code + fingerprint + operation/surface` 聚合。
3. **服务 RED 轨**：Prometheus histogram/counter；不得从页面事件反推服务错误率和 P99。
4. **Behavior 轨**：行为事实 → content-service → Mongo/Redis/outbox → 推荐 HotPath；不得同时写产品事件并被两个消费者生效。
5. **控制面轨**：配置、发布、告警处置和回滚经 typed control-plane object；Portal 不拥有第二套状态。

当前 SLS 声明实际涉及产品 raw、启动 raw、runtime raw、hourly rollup **4 个 Logstore**；runbook/backlog 中仍有“三个 Logstore”旧文字，真实资源创建前必须先统一数量、保留期和 RAM 权限。

### H1-C 每页与每对象强制字段

- 页面事件：`sessionId`、`pageName/surfaceId`、`routeId`、`appVersion`、`networkClass`、`occurredAt`。
- operation 事件：`operationId`、`objectId/objectState`、`result`、`durationMs`、`failReasonCode`、`requestId/traceId`、`recoveryAction`、`disruptionLevel`。
- 发布维度：`environment`、`rolloutStage`、`serviceVersion/configDigest`；生产只由服务端/发布上下文补充，不信任客户端自报。
- 交集事件：`intersectionKind`、证据类别、事实/推断标志、展示/行动结果；不得记录无权查看的关系明细。
- 隐私：禁止原始手机号、正文输入、完整 callStack、坐标级点击热力和无界 userId label。按用户检索日志应使用受控审计查询，不进入 Prometheus label。

### H1-D 黄金指标规则

每个关键业务最多 3 个一级黄金指标：

1. **有效完成率**：对象进入目标有效状态的数量 / 合法发起数量；失败、取消、幂等重放必须可区分。
2. **Time-to-Value P95**：从用户发起到目标状态可见/可用的耗时；同时保留 P50/P99 诊断。
3. **价值行动或恢复率**：交集/推荐解释后的有效行动率，或失败后的恢复成功率；两者按版块二选一，避免 KPI 膨胀。

二级指标只能用于定位一级指标，必须可下钻到页面步骤、对象状态、operation、错误码、网络与版本。运营“页面热力”使用 `pageName × action × result` 强度矩阵，不采集坐标级点击。

### H1-E 任务清单

- **H1-1 ANR/主线程失活**：先定义跨平台 `app_anr_outcome` metadata 事件和去重语义，再由 platform 防腐层实现 Android/iOS heartbeat/watchdog；Web/OHOS 无能力时结构化降级。避免把 200ms severe frame 直接标为 ANR。
- **H1-2 通用页面 TTI**：在 page object contract 登记关键可用条件，统一 `navigation_start → first_usable_content`；空态/错误态也必须结算，不允许只在成功数据时上报。
- **H1-3 恢复页展示率**：对 `AppPageErrorState`、router recovery、bootstrap recovery 建 `surface + errorCode + recoveryAction + outcome` 事实，得到“地球页/恢复页展示率”和恢复成功率。
- **H1-4 投递可靠性**：按 R-OPS-RUNTIMELOG-DELIVERY 补 priority dequeue、TTL/DLQ/backoff、422 poison record 隔离与投递指标；按 R-OPS-LOG-COLLECTOR 补 stdout collector/spool。
- **H1-5 对象 metric coverage**：沿 R-OBJ-001 建通用 `commercial operation → metric → dashboard → alert` 机器门，逐 M1～M18 收口。
- **H1-6 真实 SLS 与生产演练**：只按 R-TELEMETRY-001 和 R-OPS-OBS-STACK 的环境步骤执行；协议替身通过不得标记 release/prod ready。
- **H1-7 文档单轨**：异常排查 skill 与 runbook 统一到当前 SLS 单轨；ES 只保留明确的本地分析用途，不得被描述为生产异常真相源。
- **H1-8 realtime 观测实证**：`realtime-gateway` 已有第一方实现，但 Prometheus 配置仍以“实现未就绪”为由排除；先证明 `/metrics`、运行制品和健康，再加 target 并做真实告警演练。

### H1-F 验收标准

- `local_contract`：事件 schema、脱敏、高基数保护、ANR 去重、TTI 终态结算、恢复页 outcome、日志 DLQ/backoff。
- `api_integration`：App/Service batch 幂等、部分 ACK、断网补传、collector spool、SLS fake 协议；真实 beta release/gamma release 另产受控 SLS 证据。
- `user_acceptance`：Android/iOS 真机可控卡死、慢页、恢复页、离线后恢复；Portal 可在 SLO 内看到同一 trace/fingerprint。
- Prometheus：每个 ready operation 的 metric 有 dashboard 与 alert 消费；realtime-gateway 未接入前相关版块不得宣称实时面全绿。
- prod gray-initial：真实触发→通知→ack→resolved、Prometheus readback、回滚 receipt 全链通过。
- backlog：H1 不自行关闭 R-TELEMETRY-001、R-OPS-*、R-OBJ-001/002；只有原条目验收证据齐全后回写。

## 9. H2 详细规格

### H2-A 当前分层与诚信状态

| 证据层 | 当前磁盘 | 当前自动入口 | 主要缺口 |
|---|---:|---|---|
| App `local_contract` | 483 个 `*_test.dart` | `gate_repo.sh --scope app` 阻断运行 | 数量大不代表对象状态机/权限均覆盖；旧 bridge/allowlist 文件当前已不存在，backlog 旧口径需按磁盘重审 |
| App `api_integration` | 9 个 | 不在普通 PR app gate；需环境变量和真实/本地 Remote | 仅 assistant 5、content/chat/integration/intersection 各少量，覆盖严重不均 |
| App `user_acceptance` | 87 个 | 非 Patrol 不由普通 app gate 全量运行；Patrol 走 gamma 设备入口 | 当前已有 RTC reconnect/answer-hangup，用例存在不等于真机 hosted 证据 |
| Service local/API | 各服务目录 + canonical bridge | service gate 与专项目标 | circle/rtc/tag 缺 `tests/local_contract`；realtime-gateway 缺 `tests/api_integration` |
| notification 内层 | domain/application 当前无 `_test.go` | 依赖外层 tests | 核心状态机缺就地测试，不能只靠 HTTP happy path |
| acceptance traceability | `verify_test_coverage_map.py` 通过；`verify_test_specs.py` 当前失败 | repo gate | RTC 扁平化并行改动中出现 acceptance 重复 YAML 文档与节点文件瞬时缺失；R-OPS-ACCEPTANCE-PHANTOM 未关闭 |

14 个 Go 服务根 `tests/{local_contract,api_integration}` 当前合计约 **60/152** 个测试文件；这不包含 `internal/**/__local_contract_test.go`。因此 circle/rtc/tag “无 local 根目录”不能写成“完全无本地测试”，notification 也不是“两层零测试”；真正要补的是对象/边界缺证据，而不是为数字整齐新建空 wrapper。

### H2-B 测试对象标准

每个核心对象至少覆盖：

- 状态机每条合法迁移、非法迁移、重复命令、并发冲突、删除/封禁/恢复。
- 对象关系的建立、解除、级联与引用失效；读模型和写模型在同一水位下语义一致。
- owner/member/admin/guest/blocked/anonymous 等权限矩阵及 PII/SECRET 不出站。
- command → authoritative store → outbox/event → projection/cache/index → App Slice 的 E2E。
- 页面加载/空/部分/错误/权限/失效/离线/恢复/取消/supersede 状态与对象状态一致。
- 交集事实来源、推断标识、无权限证据隐藏、冷启动无交集与误推断负例。
- 重构前后主旅程、深浅色、token、无障碍、iOS 返回/Sheet、compact/regular/expanded。

### H2-C 三层职责与禁止项

- **local_contract**：metadata/codegen、domain/application 规则、Mock parity、Provider/Widget、错误恢复与 capability profile；不访问真实云。
- **api_integration**：generated client/Remote、真实 API、真实存储、事件/outbox、缓存/索引一致性；不允许裸 HTTP、自 seed、内存 adapter 冒充。
- **user_acceptance**：production Remote composition、真实页面和设备旅程、权限/弱网/性能/灰度；路径存在性或 fixture-only 不计通过。
- 禁止动态 skip、`example.invalid` 成功、只检查 2xx、不验证状态存储、把 local_contract 命名成 integration。

### H2-D 四环境证据

| 环境 | 数据与组合 | 必须证明 | 不能证明 |
|---|---|---|---|
| alpha | contract-seeded Mock / fake-SLS 协议 | schema、规则、页面状态、错误/恢复、确定性 fixture | 真实服务、真实 SLS、真机商业可用 |
| beta-local | Remote + 本地端云拓扑 | generated client、API、存储、event/outbox、弱网模拟 | hosted 网络、生产凭据和生产容量 |
| gamma-local | 同构 Remote mirror + self-hosted device | 全旅程、设备差异、媒体/RTC、本地发布前回归 | 远端 hosted；gamma 已无远端环境 |
| prod-hosted gray-initial | 不可变 prod 制品 + 真实数据面 | 远端集成、curated media、SLO、告警、回滚、canary | 未放量前的全量业务量级 |

### H2-E 任务清单

- **H2-1 覆盖地图**：为 M1～M18 建 `object transition/relationship/page state → local/api/UAT` 映射；严禁用文件数代替覆盖。
- **H2-2 补物理目录**：circle/rtc/tag 建真实 local_contract；realtime-gateway 建 API integration；notification domain/application 补状态机测试。不得只建空目录或 wrapper。
- **H2-3 App api_integration 扩面**：按版块至少覆盖一条读取、一条命令、一条结构化失败及其 Mock parity；settings/welcome 无远端业务时应明确 `—`，不能机械造测试。
- **H2-4 acceptance 对账**：保持 `verify_test_specs`/coverage map 全绿，并逐 R-OPS-ACCEPTANCE-PHANTOM 的 planned 路径补真实文件或删除错误声明；“23 份 acceptance 含幽灵路径”是历史审计快照，不得冒充当前重跑结果。关闭条目需回写证据。
- **H2-5 统一远端 preflight**：沿 R-TST05 让 stackctl/CI 注入 URL/token/Secret，缺凭据 fail-fast；不得转成动态 skip。
- **H2-6 旧口径校准**：当前 `test_legacy_source_allowlist.yaml`、`test_directory_inventory.yaml` 与 bridge generator 已不在磁盘；沿 R-TST04/R-TST07 先修 backlog/spec 的陈旧叙述，再以当前物理路径、旧 T/L 命名和动态 skip 扫描决定真实 burn-down，禁止沿用历史数字。
- **H2-7 发布配置**：PR 继续阻断静态+local；nightly/release_candidate 跑 gamma-local 全量；prod gray-initial 跑最小高信号 Remote/UAT/SLO，不把 900s 主链塞满低信号用例。

### H2-F 验收标准

- 每个 M 版块的 A～G 都有三层测试矩阵；适用层无空白，`—` 有业务理由。
- API integration 的字段、状态码、错误码、权限和边界在 local_contract 有对应 Mock/Provider/Widget 断言。
- acceptance 中所有 `tests[].file`、recorded/report case 均可定位；`verify_test_specs.py`、`verify_test_coverage_map.py` 通过。
- 不存在新增 fake、动态 skip、缺环境静默通过；远端前置缺失返回可解释 GATE_BLOCK。
- 环境报告记录 artifact/config digest、环境、设备、case id、开始/结束时间和失败证据；可从 acceptance 反查报告。
- R-TST04/05/07 与 R-OPS-ACCEPTANCE-PHANTOM 未满足原验收前保持未关闭。

## 10. M1 详细规格

### M1-A 版块定位

- **用户目标**：游客完成欢迎、同意、登录、账号恢复与 Persona 选择；关闭登录返回安全状态，成功后继续原动作。
- **树绑定**：Journey `identity-entry-and-continuation`；Scenario `identity-entry-persona-continuation`；L2 `onboarding-and-identity-entry`、`auth-profile-snapshot`、`persona-follow-graph`、`runtime-client-foundation`。
- **交集定位**：无需承载。登录页只收集必要身份和同意，不显示交集；Persona 只建立后续关系主体。
- **当前裁决**：R-AUTH-001、R-OBJ-006 未关闭，故不能因登录页面横向质量维全绿而宣称商用。

### M1-B 业务对象底料

| 对象 | 价值与关系 | 聚合/生命周期 | 页面/API/存储 | 当前问题 |
|---|---|---|---|---|
| `UserAccount` | 账号、安全与所有 Persona 的 owner；媒体引用 `MediaAsset` | `user.account` 聚合；匿名/活跃/受限/注销需专项复核 | `user/user_profile`；user-service；Postgres | 对象映射把账号与 profile 投影放在同源目录，专项需核对边界；R-OBJ-006 |
| `AuthenticationChallenge` | OTP/第三方认证的一次性挑战 | 创建→发送→验证/过期/锁定→消费 | `user/authentication_challenge/{aggregate,fields,service,errors}.yaml` | 正式 SDK/凭据未注入（R-AUTH-001） |
| `AccountSession` | 登录态、设备和续接凭据 | 签发→活跃→刷新→撤销/过期 | `user/account_session/**`；secure storage + user-service | 多设备撤销、恢复和 telemetry 需实证 |
| `CredentialBinding` | 手机/社交凭据与账号 N:1 | 绑定→验证→活跃→解绑/失效 | `user/credential_binding/**` | 绑定冲突和账号合并页面承载待核验 |
| `Persona` | 公开业务动作主体，N:1 归属账号 | 创建→激活→更新→退役/删除空 Persona | `user/persona/**`；`persona_management_page.dart` | 退役、主 Persona 切换、引用保留需 E2E |
| `UserSettings` | 账号/Persona 外观与偏好 | 读取→CAS 更新→冲突恢复 | `user/user_settings/**`；M15 页面 | 与 M15 共管，避免把设置状态塞回 Account |
| `DeviceRegistration` | 会话、通知与可信设备关联 | 注册→刷新→失效/撤销 | `user/device_registration/**` | 缺 `errors.yaml`；push deferred 归 M13 |
| ConsentRecord | 证明同意的协议/隐私版本 | 当前寄宿 user profile/storage，尚非 canonical object | 随登录写入、审计保留 | 需裁决为账号拥有审计事实或独立 append-only fact |

关键关系：`UserAccount 1:N Persona`、`UserAccount 1:N CredentialBinding/AccountSession/DeviceRegistration`；业务 command 必须携带 account actor 与 active persona，不得继续用含混 `userId`。

### M1-C 页面清单与成熟度预评级

| 页面/承载 | 主对象/状态 | 预评级 | 初步决策 |
|---|---|---:|---|
| `lib/ui/user/pages/login_page.dart` | Challenge、Session、CredentialBinding；返回账号/OTP/社交能力 | P3（视觉未核验） | 适度重构：保留双目标导航与渐进头像，补真实 SDK、账号冲突/恢复和真机证据 |
| `lib/ui/user/pages/persona_management_page.dart` | Persona 列表、激活、创建、更新、退役 | P2（视觉未核验） | 适度重构：把全生命周期、并发更新与退役后回流做完整 |
| `lib/ui/welcome/pages/welcome_screen.dart` | 启动品牌页；对象数据不在此页，身份四态规格与实现冲突 | P2（视觉未核验，主归 M2） | 保留启动动画，先统一“纯启动页/身份入口”规格边界 |
| `lib/ui/settings/pages/settings_account_security_page.dart` | CredentialBinding、AccountSession 与账号安全动作（主归 M15） | P3（视觉未核验） | 保留；补设备/会话、最后凭证保护与真机 UAT |
| 登录页内 OTP/社交授权/协议 sheet | Challenge/Consent 的嵌入状态 | P3（视觉未核验） | 保留单主动作，核验失败恢复与 accessibility |

### M1-D 对象—页面双向初查

- `AuthenticationChallenge`、`AccountSession` 适合嵌入登录页，不要求独立管理页；但所有过期、锁定、撤销、账号冲突状态必须可见可恢复。
- `CredentialBinding` 已由账号安全页承载绑定列表/解绑；仍需核验最后凭证保护、多设备 Session 与错误恢复。
- `DeviceRegistration` 是后台对象，无独立页面合理；用户应在账号安全面看到可信设备/撤销结果，当前承载待核验。
- 登录成功续接依赖 `AuthContinuation`；仅有 fallback/pop 而无成功目标或关闭安全态，直接 GATE_BLOCK。
- `PersonaManagementPage` 实际操作 Persona，但 page object contract 只绑定 `user.user_account`；需改为 Persona 及必要的账号摘要 Slice。
- Welcome 的正式页面合同是 objectless 启动品牌页，而 onboarding 规格仍把它描述成身份四态入口；两者必须二选一并统一。

### M1-E 六维度

| 维度 | 当前规格 | 目标规格 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 双目标登录规则已固化；R-AUTH-001 阻断真实商业登录 | 欢迎→同意→登录→Persona→原动作续接无循环 | 注入受控 SDK/Secret；补账号冲突、挑战过期、会话撤销 | 关闭后再 pump 不重弹；成功恢复每类 continuation；Android/iOS 真机 |
| D2 | user 对象图存在；Repository/手写 transport 仍有 R-OBJ-006 | Account、Persona、Challenge、Session、Credential 拆为≤10方法 Facet | metadata-first 清错误/actor/状态机；generated dispatch | ContractGraph + Go/Dart codegen + Postgres/Redis 集成 |
| D3 | 横向维全绿；视觉与 Persona 全状态未核验 | 登录核心页≥P4；简洁单主动作、双色/iOS/无障碍完整 | 真机截图审查；清剩余硬编码文案；Persona IA 复核 | compact/regular/expanded、浅/深色、VoiceOver |
| D4 | 启动/登录有耗时基础，第三方 SDK/弱网预算未冻结 | 点击→可操作登录 P95、OTP、SDK callback、续接均有预算 | 定义 timeout、幂等、重试、取消与灰度回滚 | beta 弱网/重复 callback；prod gray SLO |
| D5 | page access 底座；user 对象告警已部分补 | 3 指标：有效登录完成率、点击到续接 P95、失败恢复成功率 | 事件绑定 challenge/session/continuation outcome | SLS 与 user-service metric 对账，错误可下钻 |
| D6 | local_contract 较多；真实 SDK/凭据 UAT 受阻 | 状态机、凭据冲突、权限、注销/撤销、续接三层齐备 | 补 Remote API 与真机 provider 测试 | alpha fake SDK、beta Remote、gamma-local 真机、prod canary |

### M1-F 标杆候选

Apple Account/Sign in with Apple（隐私与系统授权）、微信登录（回流与授权失败）、小红书登录（内容社区轻入口）、Airbnb 账号恢复（多凭据与安全）。专项仅提炼单主动作、授权解释、恢复与账号合并原则，不复制品牌视觉。

### M1-G 并行会话启动提示词

> 完成 M1 身份与登录全面分析。先读本文 §0～§6、§10，以及 identity-entry Journey、user business object map、登录无死循环规则和 R-AUTH-001/R-OBJ-006。严格执行“业务对象中心、页面成熟度与交集差异化强制分析”全部要求，交付 10 项产物与 D1～D6 当前/目标/任务/验收。必须真机/截图核验视觉，否则标“视觉未核验”。Out of Scope：不重建 H1 观测平台、不重复业务对象批次的 Facet 实现；只提出接口并与对应轨道对齐。发现新长期风险先请求用户确认。

## 11. M2 详细规格

### M2-A 版块定位

- **用户目标**：点击图标后在有限时间内进入可用 Shell；配置、路由、首帧或网络异常时进入可解释、可恢复、安全终态；边缘返回与深链符合平台习惯。
- **树绑定**：Journey `cold-start-safe-handoff`、`app-root-navigation-safety`；Scenario `cold-start-safe-handoff-and-telemetry`、`global-route-edge-pop-contract`、`immersive-media-edge-swipe-back`、`home-edge-swipe-exit-guard`，并协同 `external-inbound-deeplink-return`。
- **交集定位**：无需承载；壳只分发导航与上下文，不生成交集。

### M2-B 业务对象底料

| 对象/机制 | 生命周期 | 页面/API/存储 | 当前问题 |
|---|---|---|---|
| Startup state machine | native pre-Flutter→Dart→first frame→router→shell→content→terminal/recovery | `lib/app/startup/**`、`app_startup_runtime.dart`、匿名 `/ops/startup-events` | R-OPS-STARTUP-IDEMPOTENCY；ANR 与通用 TTI 见 H1 |
| Route/Surface descriptor | metadata route→generated path/page→GoRouter→surface | `_shared/ui_surfaces.yaml`、app pages/routes codegen | 深链/路由不得手写第二表 |
| AuthContinuation | 受限入口→登录→成功目标/关闭安全态 | `lib/core/auth/**` | 与 M1 共同验收 |
| ConfigSnapshot | stage→publish→activate/rollback→ACK/drift | `ops/config_layer`、platform-ops-service | R-OPS-CONFIG-PLANE-PROD |
| App page context | enter→active→return/dispose | page object contract、page access observer | TTI/恢复页 outcome 不完整 |

### M2-C 页面/壳预评级

| 页面/壳 | 预评级 | 初步决策 |
|---|---:|---|
| `lib/app/shell/main_app_shell.dart` | P3（视觉未核验） | 适度精修；核验首次访问初始化、游客门禁和根退出 |
| `bottom_navigation.dart` | P3（视觉未核验） | 保留；核验五项 IA、中央动作与无障碍 |
| `object_detail_global_bottom_nav.dart` | P3（视觉未核验） | 保留；核验对象页与主壳同源 |
| `web_app_install_banner.dart` | P2（视觉未核验） | 适度重构；补下载来源、失败与归因 |
| `web_main_app_shell.dart` | P3（视觉未核验） | 适度精修；核验宽屏 IA、SEO/安装回流 |
| `web_main_app_shell_auth.dart` / `_state.dart` | 非独立页面 | 保留 part；验收归父壳 |
| `lib/ui/welcome/pages/welcome_screen.dart` | P2（视觉未核验） | 保留动画；先统一 M1/M2 所有权，再核验 3s/6s 与恢复终态 |
| `app_router_recovery_page.dart`、`bootstrap_recovery.dart` | P2（非矩阵独立页，视觉未核验） | 适度重构；统一恢复语义与 outcome |
| 入站深链解析/延迟恢复承载 | P0 | 先补 resolver、原生注册、pending replay 与安全 fallback；不先造品牌页 |

### M2-D 双向初查

- Shell 无业务对象是正确边界；若壳直接拼 Feed/Profile/通知假数据则 GATE_BLOCK。
- `ConfigSnapshot` 不需要 App 编辑页，但 App 必须消费已签名配置并上报 ACK/drift；缺失不能静默默认。
- DeepLink 不是独立页面对象；每个可分享目标必须解析到 canonical route，并在无权限/已删除时提供安全终态。
- Web install banner 存在页面承载，但安装后还原原目标尚属 M14 验收，不能把“能打开商店”当闭环。
- 当前 App 生产代码未发现 `DeepLinkResolver/PendingInboundTarget`，Android manifest 也未发现通用 VIEW/BROWSABLE/App Links 注册；iOS 登录 SDK callback 不能替代通用内容深链。`external-inbound-deeplink-return` 当前按能力面 P0/GATE_BLOCK 处理。

### M2-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 冷启动状态机和边缘手势规格较完整 | 任何失败在 6s 内有可恢复终态；深链、登录、返回无环 | 对齐恢复页、deep link、AuthContinuation | 启动 UAT + route fuzz + background/foreground |
| D2 | Route/surface/codegen 有单轨；Config ACK 覆盖不全 | 壳零业务真相，所有 route/config typed | 清手写 route、补 governed service ACK | metadata/generator drift gate |
| D3 | 横向矩阵全绿 | 壳/欢迎/恢复≥P4，Web/移动同 IA | 真机截图、动态字体、reduced motion、键盘导航 | iOS/Android/Web 三端 |
| D4 | 3s/6s 预算已有 | first frame、shell、first usable、route recovery 分段 SLO | 冷/暖启动、低端机、离线、缓存预算 | P50/P95/P99 + OOM/ANR |
| D5 | 启动四段事件、page access 已有 | 3 指标：安全终态率、点击到首个可用内容 P95、恢复成功率 | 修 R-OPS-STARTUP-IDEMPOTENCY；接 H1 ANR/TTI | 同 batch 幂等、部分 ACK、真机 Portal 可见 |
| D6 | 启动 local/UAT 较强 | native journal→Flutter→SLS、边缘返回、深链三层齐备 | 补 hosted deep link/恢复 canary | alpha deterministic、gamma device、prod gray |

### M2-F 标杆候选

Apple HIG Launching、Instagram/小红书冷启动与恢复、Safari/Universal Links、iOS Navigation/edge swipe。重点比较“首屏不是启动完成”、失败终态、深链还原和返回手势，不照搬品牌动效。

### M2-G 并行会话启动提示词

> 完成 M2 应用壳与冷启动全面分析。读取本文 §0～§9、§11、对应两个 Journey、cold-start/native-edge-gesture/external deep-link specs 及 R-OPS-STARTUP-IDEMPOTENCY/R-OPS-CONFIG-PLANE-PROD。执行完整对象中心强制分析，覆盖全部 shell/welcome/recovery/deep-link 承载与 10 项交付物。Out of Scope：不重建运维发布平台、不改业务页面内容模型；将采集/配置需求交给 H1/运维轨。未真机渲染不得给 P4。

## 12. M3 详细规格

### M3-A 版块定位

- **用户目标**：从频道/推荐流看到可信内容，理解为什么值得看，进入图片/视频/文章消费，互动并可回到作者、实体、圈子或交集行动。
- **树绑定**：Journey `content-discovery-to-consumption`；Scenario `content-feed-open-detail`、`content-detail-profile-handoff`、`immersive-media-edge-swipe-back`。
- **交集定位**：核心承载。交集用于解释发现、帮助判断并促成互动，不得把模型相似度冒充共同事实。

### M3-B 业务对象底料

| 对象 | 关系/生命周期 | 页面/API/存储 | 当前问题 |
|---|---|---|---|
| `Post` | Persona 作者；关联 MediaAsset、Homepage、Tag、source Post、pinned Comment；草稿/提交→发布→更新→删除/审核 | `content/post/**`；content-service Mongo；Feed/Detail projections | R-OBJ-007 超大文件；发布与消费读模型需一致 |
| `MediaAsset` / `MediaOriginalAccessFact` | Post N:N 媒体；上传→可用→绑定→受限/删除 | `content/media_asset/**`；对象存储+Mongo | 播放 QoE、原图访问授权 |
| `ContentReaction` | Persona×Post 的点赞/收藏等关系 | `content/content_reaction/**` | 取消、计数最终一致、推荐回流 |
| `RecommendationExposureFact` / `FeedbackFact` | Feed 曝光与反馈事实 | `recommendation/**`；推荐/内容投影 | R-OPS-BEHAVIOR-CONSISTENCY、R-OBJ-004 |
| `IntersectionVisitState` | 用户对交集 feed/对象的已读水位 | `content/intersection_visit_state/**` | `errors.yaml` 缺失候选，归 M10 共同核验 |

### M3-C 页面预评级

| 页面 | 主对象 | 预评级 | 决策 |
|---|---|---:|---|
| `lib/ui/discovery/pages/home_page.dart` | Post Feed、Exposure、频道 | P3（视觉未核验） | 适度重构：推荐解释、空/错/降级、频道一致性 |
| `lib/ui/discovery/pages/unified_media_viewer_page.dart` | PostReadPresentation、媒体 | P2（视觉未核验） | 适度重构：P6 豁免需重新裁决，QoE/无障碍/交集行动 |
| `lib/ui/discovery/pages/work_browser_entry_page.dart` | WorkBrowserItem/Post | P3（视觉未核验） | 精修：删除/无权限/队列恢复 |
| 文章 reader/pageflip 宿主（嵌入 viewer） | Post(article) | P2（视觉未核验） | 结构重构须守 pageflip 单几何真相源；R-OBJ-007 |

### M3-D 双向初查

- Post 全生命周期的“编辑/删除/审核中/被下架”由 M4/M16/M3 分担；消费页必须正确投影，不得把已删除内容渲染为普通网络失败。
- Exposure/Feedback 为后台事实，无独立页合理；但 Feed 每个可见卡必须产生去重曝光且行为可回流，缺失即 GATE_BLOCK。
- Feed 关联 Homepage/Persona/Circle 时只能消费 typed Slice；UI 拼 author/entity/circle 临时对象即 GATE_BLOCK。
- recommendation model release 不直接展示；页面解释必须标明事实交集与推断推荐。
- `UnifiedMediaViewerPage` 仍直接 `context.push('/user/$userId')`，绕过 generated route；这是明确路由真相源漂移。
- `ui_surfaces.yaml#homeFeed` 未登记实际首读 `GetFeed`，却登记大量互动/上传 operation；surface 与用户主任务不一致。
- Feed P95 在业务规格与 metadata 存在 200ms/500ms 双口径候选，专项必须冻结单一 SLO。

### M3-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | Feed/Viewer/作者跳转存在 | 发现→消费→互动→对象/关系回流无断点 | 补删除/封禁/权限/离线/交集行动 | UAT 覆盖每内容类型和终态 |
| D2 | Post 对象图完整度高 | 写聚合、Feed/Detail Slice、Exposure/Feedback 清晰分层 | 清 R-OBJ-007 中混合状态/渲染职责；核对计数一致性 | Mongo/Redis/outbox/API integration |
| D3 | 横向维绿，viewer P6 豁免 | Feed/Viewer/Reader≥P4；交集解释区=P5 | 真机视觉、双色、字幕/VoiceOver、pageflip 证据 | 视觉基线+帧缓冲/pageflip test |
| D4 | Feed TTI、video QoE 已有 | Feed/详情/文章 first usable、滚动帧、媒体 ready 预算 | 通用 TTI、分页预取、缓存/弱网恢复 | 低端机 P95、内存、掉帧、断网 |
| D5 | Feed TTI/QoE/部分行为存在 | 3 指标：有效消费完成率、打开到可用 P95、交集/推荐解释后有效行动率 | 曝光幂等、内容深度、互动 outcome 接 H1 | SLS/Behavior/Prometheus 三轨对账 |
| D6 | local/UAT 多，App Remote 证据薄 | Post Feed/Detail/Reaction/Exposure 三层齐备 | 扩 API integration；修 acceptance planned path | alpha parity、beta real store、gamma media、prod canary |

### M3-F 标杆候选

小红书发现流/笔记、抖音沉浸视频、微信读书/Apple Books 长文阅读、Reddit 社区上下文。重点借鉴内容优先、状态恢复、播放 QoE、推荐解释；不照搬无限刺激或社交图暴露。

### M3-G 并行会话启动提示词

> 完成 M3 内容发现与消费全面分析。读本文 §0～§9、§12、content/recommendation object maps、page object contract、content Journey、R-OBJ-007/R-OPS-BEHAVIOR-CONSISTENCY。执行完整强制分析并覆盖 Feed、Viewer、Work Browser、Article Reader 及嵌入态。交集必须区分事实/推断并给下一步行动。Out of Scope：推荐算法/模型训练由推荐二期负责；pageflip 修改必须另按专属规则。输出 10 项交付物、页面真机评级和三层证据。

## 13. M4 详细规格

### M4-A 版块定位

- **用户目标**：从创作入口选择文章/图片/视频，管理草稿和媒体，关联地点/实体/圈子/标签，原子发布并看到可恢复结果。
- **树绑定**：discovery-content 的创作/发布相关 L2/L3；与 content-display Journey、identity continuation 和 circle collaboration 协同。
- **交集定位**：场景增强。标签、实体、地点和圈子关系帮助内容被正确发现，但创作主任务不能被交集模块挤占。

当前 AppRoot registry 没有独立“内容创作与发布” Journey/Scenario；不能继续借消费 Journey 冒充创建入口的 UAT 归属。

### M4-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `Post` / publish intent | 本地草稿→提交意图→服务端待发布→published/failed/deleted | create/article/video/local draft | 幂等、失败恢复；R-OBJ-007 |
| `MediaUploadSession` | init→upload→complete→bind→abort/expire | camera/picker/editor + Remote coordinator | 原子性与孤儿清理 |
| `MediaAsset` | captured/local→uploaded→bound→available/restricted | 媒体组件 | 本地路径不得进入 Remote |
| `Location` | 外部引用查询→选择→写入 Post value | publish location selector | R-CR04 UI 层服务/模型分层债 |
| `CirclePostPlacement` | Post 与 Circle 的发布关联 | publish circle select | 圈子权限/撤回同步 |
| Tag/Homepage refs | 选择/验证后写入 Post | create confirm/profile pickers | 必须由 tag/entity typed query 验证 |

### M4-C 页面与组件预评级

| 页面/组件 | 预评级 | 决策 |
|---|---:|---|
| `create_page.dart` | P2（视觉未核验） | 适度重构：状态机/文件拆分/发布恢复 |
| `article_typography_page.dart` | P2（视觉未核验） | 适度重构：预览与最终 reader 同源 |
| `local_draft_page.dart` | P3（视觉未核验） | 精修：冲突、损坏草稿、删除/恢复 |
| `publish_location_selector_page.dart` | P2（视觉未核验） | 适度重构并迁出 UI service/model（R-CR04） |
| `video_editor_page.dart` | P2（视觉未核验） | 适度重构：导出、取消、失败、能力降级 |
| `publish_circle_select_page.dart` | P2（视觉未核验） | 适度重构：权限/成员状态与提交结果 |
| `camera_capture_page.dart` | P3（视觉未核验） | 精修：权限、录制中断、无声降级 |
| `create_media_picker_page.dart` | P3（视觉未核验） | 精修：相册权限、重入与上限 |
| `desktop_image_picker_page.dart` | P2（视觉未核验） | 适度重构：文件系统错误/大目录性能 |
| `image_editor_page.dart` | P3（视觉未核验） | 精修：多图保序、可撤销 |
| `one_tap_movie_preview_page.dart` | P2（视觉未核验） | 重评 P6 豁免；补导出/失败/取消 |
| `settings_inset_form_page.dart` | 非业务页 | 保留模板，验收归使用方 |

### M4-D 双向初查

- 本地草稿不是云端 Post；二者必须由 publish intent/idempotency 显式衔接，UI typedef 不能反向成为聚合。
- MediaAsset/UploadSession 无独立管理页合理，但每个 orphan/abort/expire 结果必须在创作页反馈并可清理。
- Location 是外部引用，不应被 `CreateLocationOption` UI 模型拥有；R-CR04 是明确分层缺口。
- Post moderation/publish pending 的结果承载需核验；发布后只 toast 不进入详情/结果回流属于 GATE_BLOCK。
- `createWorkspace` surface 当前重复登记 `CreateOutboundShare/PlacePostInCircle`，页面对象合同又未完整绑定 MediaUploadSession/MediaAsset/CirclePostPlacement；需先清 surface/object 映射再判页面完成。
- Post 已 accepted 但 Circle placement 异步失败时，UI 不得宣称“已发布到圈子”；结果必须拆分并可恢复。

### M4-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 各子流与发布 roundtrip 已有部分证据 | 草稿→编辑→上传→原子发布→结果/恢复完整 | 补幂等重入、部分上传、审核中/失败 | 图片/视频/文章 UAT |
| D2 | typed wire 已接；R-CR04、超大文件仍在 | Post/UploadSession/Asset/placement 外部引用边界清晰 | 迁 location port；拆状态机；删 deprecated | metadata/codegen + store/outbox |
| D3 | 横向维绿 | 创作主链≥P4；媒体工具 P4；简洁单主动作 | 真机/横竖屏/键盘/权限/双色核验 | 设备与视觉回归 |
| D4 | 上传协调器有 operation telemetry | 首预览、编辑、上传、发布、导出预算；后台/弱网恢复 | chunk/retry/abort、内存、长任务模式 | 大文件/弱网/取消/恢复 |
| D5 | 上传与部分发布行为已有 | 3 指标：有效发布率、开始到内容可见 P95、失败恢复成功率 | 统一 intent/upload/post correlation | App/SLS/service/outbox 对账 |
| D6 | local/UAT 较多，App API 仅一条发布 roundtrip | 三类型发布、关联对象、失败原子性三层齐备 | 扩 beta API、gamma 真机媒体 | 无半成品、无本地路径出站 |

### M4-F 标杆候选

小红书发布、Instagram 多媒体编辑、抖音视频发布、Apple Photos/Files picker。借鉴渐进披露、非破坏编辑、后台上传与失败恢复，不复制模板和滤镜资产。

### M4-G 并行会话启动提示词

> 完成 M4 内容创作与发布全面分析。读取本文 §0～§9、§13、content/social/tag/integration object maps、创作 acceptance、R-CR04/R-OBJ-007。执行完整对象—生命周期—页面分析，覆盖 6 个业务页、5 个媒体页和嵌入 sheet。Out of Scope：不替 M17/M18 重做 taxonomy/location 服务；只定义调用和一致性。输出 10 项交付物，所有重构页含性能预算、灰度回滚和三层验收。

## 14. M5 详细规格

### M5-A 版块定位

- **用户目标**：在统一入口查找内容、圈子、会话、主页、人物与地点，理解结果来源，筛选并进入目标对象或小趣继续探索。
- **树绑定**：Journey `cross-domain-search`；Scenario `global-search-query-and-filter`、assistant search handoff。
- **交集定位**：核心承载。交集用于解释“为什么与你相关”和支持关注/加入/联系；搜索相关性分不得伪装为事实交集。

### M5-B 业务对象底料

| 对象 | 生命周期/关系 | 页面/API/存储 | 当前问题 |
|---|---|---|---|
| `SearchQuery` | 发起→路由 provider→聚合/部分结果→完成/失败 | `search/query/**`；search-service | 跨域部分失败和权限过滤 |
| `RecentSearchState` | add→list→remove/clear | `search/recent_search_state/**` | 私有数据生命周期 |
| `SearchFeedbackFact` | impression/click/empty/refine 追加事实 | `search/business_object_map` | 与推荐/运营归因对齐 |
| `SearchRecommendationSignalFact` | 推荐信号事实 | search/recommendation | 不得与产品 event 双重生效 |
| `SearchIndexView` | 各域对象投影→索引→tombstone/rebuild | `search/search_index_view`、ES/OpenSearch | `readiness`/错误和重建长稳见 R-S06 |
| `Location` / Homepage candidate | 地点结果可提升正式主页 | M18/M9 | 临时地点 card 无独立 operation 是已登记边界 |

### M5-C 页面预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `global_search_page.dart` | P3（视觉未核验） | 适度精修：灵感空/错、历史隐私、跨域 IA |
| `search_network_results_page.dart` | P2（视觉未核验） | 适度重构：部分结果、筛选、交集解释与行动 |
| `location_place_landing_page.dart` | P1（视觉未核验） | 先补/裁决 `location.place` 正式对象，再完全重构或合并到 Homepage |

### M5-D 双向初查

- R-OBJ-005 已记录为解决：客户端合成热门已删除；专项必须加回归负例，不能把“返回空集合”继续包装成合成成功。
- `SearchIndexView` 无页面正确；其 stale/rebuild/tombstone 必须反馈成结果 freshness/失效语义，而非 UI 继续展示旧对象。
- 地点 landing 使用 route extra 是临时结果承载；若提供收藏/评论/关注等正式操作，必须先提升为 Homepage 或正式 Location 对象。
- 搜索结果页面必须保留源对象 owner；UI 聚合 Map/临时字段即 GATE_BLOCK。
- `location.place` 当前只有 shared search taxonomy/route 语义，没有 canonical object packet、Store、event 或生命周期；landing 仅靠 route extra，冷启动/刷新/提升为 Homepage 后无法稳定重取。
- `globalSearchNetworkResults` surface 仍登记 `GetNearbyLocations/SearchLocations/SubmitPostPublication` 等偏离结果页主任务的 operation，且 page object 未完整绑定 Homepage/location/assistant 结果对象。

### M5-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 三页与跨域路由存在 | query→筛选→结果→对象/小趣行动，部分失败可恢复 | 补 provider partial、无权限、索引 stale | 跨域 Search UAT |
| D2 | Query/Recent/Feedback/Index 对象已登记 | query command、provider Slice、index projection、feedback fact 分离 | 补 errors/readiness；清聚合 Map | ES + 源库 tombstone 集成 |
| D3 | 横向维绿 | 搜索核心页≥P4；交集结果解释=P5 | 真机键盘、动态筛选、空/错、双色 | iOS 搜索交互+无障碍 |
| D4 | 服务 histogram 基础存在 | 首结果 P95、分页、取消旧 query、缓存/去抖预算 | query cancellation、partial timeout、索引容量 | 并发/长词/弱网/冷索引 |
| D5 | 页面/地点部分埋点 | 3 指标：有效搜索成功率、提交到首个可操作结果 P95、结果到有效行动率 | impression/click/refine/empty 同 queryId | SLS、search metric、feedback 对账 |
| D6 | local 较多，App API integration 为零 | Query/Recent/Index/Feedback 三层齐备 | 补 Remote+ES、索引重建与 UAT | beta ES、gamma journey、prod canary |

### M5-F 标杆候选

微信全局搜索（跨域分组）、小红书搜索（内容/用户/地点）、Slack 搜索（过滤与结果上下文）、Apple Spotlight（系统搜索与隐私）。借鉴分组、筛选、部分失败和来源解释，不复制热词运营策略。

### M5-G 并行会话启动提示词

> 完成 M5 搜索全面分析。读取本文 §0～§9、§14、cross-domain-search feature tree、search object map、M17/M18 边界、R-S06 与已解决 R-OBJ-005。执行完整强制分析，实时对标 2～4 个产品，输出对象全景、索引生命周期、页面双向矩阵、P0～P5、交集事实/推断、3 个黄金指标与三层测试。Out of Scope：不重做推荐排序或标签 taxonomy；不恢复客户端合成热门。

## 15. M6 详细规格

### M6-A 版块定位

- **用户目标**：从消息首页、联系人、搜索、圈子/主页或打招呼请求进入 1v1/群聊，可靠收发消息、管理群和小趣成员，并在离线后恢复。
- **树绑定**：Journey `message-social-connection`；Scenario `message-direct-and-greeting-upgrade`、`message-group-entry-matrix`、`message-assistant-in-conversation`。
- **交集定位**：场景增强。交集只用于解释“为什么可联系/为什么推荐此群”，不能绕过关注、互关、拉黑与打招呼门禁。

### M6-B 业务对象底料

| 对象 | 关系/生命周期 | 页面/API/存储 | 当前问题 |
|---|---|---|---|
| `Conversation` | 关联 creator Persona、Circle/CircleGroup、Homepage、last Message；create→active→update→dissolve | `messages/conversation/**`；chat-service Mongo | `messages` 是 canonical，`metadata/chat` 历史出口需清理 |
| `ConversationMembership` | Conversation×Persona/assistant；invite/join→role/admin→remove/leave/transfer | `messages/conversation_membership/**` | 当前无 `errors.yaml`，错误语义完整性待补 |
| `Message` | create/send→accepted→delivered/read/failed/recalled/retained | `messages/message/**` | 无 `errors.yaml`；删除/撤回是否有正式 command 需核验 |
| `ConversationUserState` | mute/pin/read cursor/draft 等用户私有状态 | `messages/conversation_user_state/**` | 无 `errors.yaml`；多端 CAS 与同步 |
| `MessageReceiptFact` | delivered/read append-only fact | `messages/business_object_map.yaml` | 事实真实性、顺序与隐私 |
| `ChatInboxView` | conversation/user/notification 聚合读模型 | message home | 读模型不得成为写真相源 |
| `GreetingRequest` | sender→pending→replied/ignored/blocked/cancelled/expired | `user/greeting_request/**` | 与正式 Conversation 升级要原子/幂等 |

当前 canonical 源是 `metadata/messages/**`，`metadata/chat/openapi.yaml` 只能视作 generated 出口。实现与大量 API 测试虽已存在，chat operation 商用状态仍普遍 blocked；不能用 CR 或页面矩阵替代 readiness。

> **2026-07-20 群治理收口进展**（群聊商用化阶段 0/1 会话）：
> ① 成员级授权已服务端强制（此前 AddMembers/RemoveMember 任何登录用户可调用）：AddMembers 须为活跃成员+新成员互关/拉黑 gate（圈子绑定群跳过）、RemoveMember 角色矩阵（owner 可移任何非 owner，admin 仅可移普通成员，禁 self-remove）；
> ② 新增 `LeaveConversation` 自愿退群语义（owner 须先转让，错误码 `group_owner_must_transfer_before_leave`）并原子切换 App 退群路径；
> ③ 群公告权威化：`Conversation.announcement` 字段 + `UpdateAnnouncement` 命令 + `system_announcement` 消息触达（此前 GroupHome 硬编码空串）+ 新建 `chat_announcement_page`；
> ④ 群治理开关权威化：`nameEditableByAdminOnly` 字段 + `UpdateGroupGovernanceSettings` 命令 + UpdateConversationTitle 动态授权消费；`qrCodeJoinEnabled`/`joinRequiresApproval`/隐私盾假开关随 JoinRequest 对象链未落地而下线；
> ⑤ 状态与事件单轨：status `deleted`→`dissolved`、`ConversationArchived`→`ConversationDissolved`（realtime fanout）、+`ConversationMemberLeft`；错误码 +`group_full`/`conversation_dissolved`；
> ⑥ `ListConversationTimestamps`/`BatchGetConversations` 由声明未实现转为已实现（App 本地缓存同步链真实消费方）；manifest 清理 SearchConversations/SearchMessages 死配置；
> ⑦ 实时扇出接收者由单页 512 截断改为分页全量（对齐 maxGroupSize=1000）；
> ⑧ 设置页补移出成员入口（owner/admin「−」模式）；建群候选行透出 metFrom 事实交集证据；
> ⑨ 证据：chat-service +`group_governance_authorization__security` / `group_announcement_governance__contract` 两个 api_integration 文件（授权负例+生命周期+读写对称回归），App +设置页治理契约 4 例、公告页 4 例、cloud_mock 群治理 parity 6 例；`member-add-remove-policy`、`group-settings`、`group-candidate-source-orchestration`（新建档）acceptance 已回填 implemented+recorded；告警组 +建群 5xx/群治理命令 5xx/P95 三规则。

### M6-C 页面预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `chat_page.dart` | P3（视觉未核验） | 适度精修：消息/联系/通知三个读模型与 IA |
| `greeting_inbox_page.dart` | P3（视觉未核验） | 精修：全状态、过期与升级会话 |
| `chat_conversation_page.dart` | P2（视觉未核验） | 适度重构：消息状态机、离线 outbox、附件/语音/小趣 |
| `chat_settings_page.dart` | P3（视觉未核验） | 精修：群来源、能力、失败恢复 |
| `start_group_chat_page.dart` | P2（视觉未核验） | 适度重构：候选来源、关系门、结果回流 |
| `transfer_ownership_page.dart` | P3（视觉未核验） | 保留模板；补并发/权限终态 |
| `group_member_search_page.dart` | P3（视觉未核验） | 保留 EmbeddedSearch；补 stale roster |
| `group_manage_page.dart` | P3（视觉未核验） | 精修：成员/设置一致性 |
| `group_admins_page.dart` | P3（视觉未核验） | 精修：角色上限与并发 |

### M6-D 双向初查

- Notification 维度复用消息首页而不建独立通知中心是已裁决的产品边界；M13 需证明站内信全生命周期在此完整承载。
- Message/Receipt/UserState 都不需独立页，但 Conversation Page 必须显示发送中、失败、重试、送达、已读、撤回/不可操作等真实状态。
- GreetingRequest 与 Conversation 是两个聚合；未回复请求直接生成普通会话或污染 inbox 即 GATE_BLOCK。
- 群设置页只能调用 Conversation/Membership commands；由 UI 列表直接改角色/成员本地状态即 GATE_BLOCK。
- `page_object_contract.yaml` 对 chat 页面主要只绑定 Conversation/UserAccount，未完整登记 Message、ConversationMembership、ConversationUserState；页面能运行不等于对象投影合同正确。

### M6-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 消息、打招呼、群管理页面较全 | 入口→请求/会话→消息→回执→群治理→离线恢复无断点 | 补所有 message/user state/role 终态 | 1v1、群、assistant、offline UAT |
| D2 | 六对象图已登记；辅助对象错误契约不齐，page-object 绑定偏粗 | Conversation/Membership/Message/UserState/Receipt/Inbox 边界严格 | 补 errors/page binding，治理 `metadata/chat` generated 出口，核对 delete/revoke command | ContractGraph/page-object gate + Mongo/Redis/outbox |
| D3 | 模板复用较好 | 核心会话≥P4；关系证据提示为 P5 增强但不抢主任务 | 真机视觉、动态字体、IME、横竖屏、附件无障碍 | iOS/Android/宽屏 |
| D4 | realtime/outbox 有局部能力 | 首列表、开会话、发消息 ACK、reconnect P95 与容量预算 | 排序/分页、附件上传、断线/重放、背压 | 长列表、弱网、重复/乱序 |
| D5 | route page access、SendMessage result、语音观测已有 | 3 指标：有效送达率、发送到对端可见 P95、失败恢复成功率 | page/action/receipt/realtime 同 trace | SLS + chat metric + outbox 对账 |
| D6 | local/UAT 多，App API 仅 roster parity | 六对象状态机和 Remote 错误三层齐备 | 扩发送、回执、成员、打招呼 API integration | beta Mongo/Redis、gamma realtime、prod canary |

### M6-F 标杆候选

微信消息/群管理、iMessage 送达与失败恢复、Telegram 多端同步、Slack 搜索/线程与离线。借鉴状态反馈、顺序和群治理，不复制通讯录扩张或暴露共同关系。

### M6-G 并行会话启动提示词

> 完成 M6 消息与聊天全面分析。先读本文 §0～§9、§15、message/social/user/realtime/notification object maps、message-social Journey 与 R-CLOUD01/R-OBJ-002/003。覆盖 9 个页面和所有嵌入消息状态，执行完整对象中心强制分析。交集只能解释入口，不得改变关系门。Out of Scope：RTC 媒体归 M7、push provider 归 M13、助手推理归 M11。输出 10 项交付物、真机视觉与三层 E2E。

## 16. M7 详细规格

### M7-A 版块定位

- **用户目标**：从合法会话/关系入口发起或接听 `audio/video` 通话，管理参与者、
  静音、摄像头、屏幕共享与 PiP，在网络变化后恢复或得到明确终态，并回到原会话看到
  `system_call_log`。
- **树绑定**：L1 `chat-conversation` → L2 `realtime-call` → L3
  `one-to-one-call/group-call/call-experience/media-infrastructure`；承接
  `message-social-connection`，并作为 `intersection-action-to-companionship` 的合法行动终点。
- **验收意图**：L2 SIT、L3 GWT/contract、AppRoot UAT；主证据为
  `api_integration + user_acceptance`，local_contract 只做支撑。
- **当前总评**：**P2+ / commercial partial**。在线单通道、typed Facet、CallSession
  持久化与会话记录已有证据；离线来电、媒体 QoE、Gamma 运行制品仍阻断 P4。
- **交集定位**：无需在通话舞台直接展示。交集只在上游关系门禁与来电/入会前提供信任证据。

### M7-B 业务对象底料

| 对象/机制 | 关系/生命周期 | Canonical 承载 | 商用判断 |
|---|---|---|---|
| `CallSession` | `initiated→ringing→connecting→in_call→ended`；关联 Conversation/Circle/initiator；内部 version CAS + receipt/outbox | `rtc/call_session/**`；rtc-service Mongo/Redis；五个 typed Facet | 主对象已收敛；`callType` 只为 `audio/video`，无录制字段 |
| `CallParticipant` | CallSession owned entity；`invited/ringing/connecting/connected/left/timeout`；最多 32 | CallSession 内嵌文档与 typed presentation | 禁止独立 Store/Facade；展示资料由 user/chat reader + LiveKit 组合 |
| `Conversation` / `Message` | `CallEnded` durable event→幂等投影 `system_call_log` | chat-service + 会话消息气泡 | 当前通话历史主形态；独立 ListCalls 页面 deferred |
| realtime `Connection` | Bearer→一次性 ticket→upgrade/auth_ack→heartbeat→disconnect/expire | `realtime/connection/**`；realtime-gateway/Redis | R-CLOUD01 只剩 Gamma/Prod 运行证据；RTC 不再自建第二信令 |
| `CallRinging` delivery | durable stream→设备 presence→在线 realtime→750ms 展示 ACK；离线/未 ACK 才 PushKit/FCM | rtc event + NotificationDeliveryJob + integration/platform boundary | **R-RTC01**：M2 后端与 native 正在落地；Web 仅前台站内来电 |
| LiveKit Room / TURN | CallSession 1:1 Room；短期 token 绑定 room/participant/grants；媒体 connected 回报聚合 | rtc-service external port + LiveKit/coturn | 真实 Gamma 运行制品受 SLS Secret 阻断；弱网/容量需设备证据 |
| `rtc_media_qoe` | 媒体终态事件→`rtc_qoe` hourly rollup→golden metrics→alert/rollback | ops event catalog / SLS / LiveKit Prometheus | **R-RTC02**：emitter、rollup 与告警合同已落地；Gamma/Prod series/readback 未闭合 |
| relationship capability / trust evidence | 1v1 mutual+!blocked 门禁；`known/possibly_unknown` 来电/入会提示 | user named capability + rtc-service 最终复核 | 交集/presence 不得授权，通话页不常驻共同关系 |

Canonical operation 分组：lifecycle（Initiate/Answer/Reject/Cancel/Hangup）、participant
（Join/Leave/Invite/ReportMediaConnected）、media（ToggleMute/ToggleCamera）、screen-share
（Start/Stop）、query（GetCall/ListCalls）。Token 随 Initiate/Answer/Join 响应返回；在线事件统一
经 realtime-gateway。

### M7-C 页面预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `incoming_call_page.dart` | P2（视觉未核验） | 适度重构：payload 首帧、来源/信任、过期/多端竞态；离线 Push 未闭合前不能升 P4 |
| `outgoing_call_page.dart` | P3（视觉未核验） | 精修：CancelCall、忙线、关系失效、30s no_answer 与 Answer 竞态 |
| `voice_call_page.dart` | P2+（视觉未核验） | 适度重构：真实音频路由、后台、重连、错误恢复与 QoE |
| `video_call_page.dart` | P2（视觉未核验） | 适度重构：真实 track、PiP hangup、screen share、权限/能力降级与 QoE |
| `call_participant_picker_page.dart` | P3（视觉未核验） | 精修：候选能力、32 人、部分邀请结果；不得展示未建合同的链接入会 |

评级是静态业务成熟度，不是页面横向质量维。未做真机/截图与媒体证据，任何页面都不得升 P4。

### M7-D 对象—功能—页面双向矩阵

| 对象/状态 | 功能 | 页面/后台承载 | 反向约束 |
|---|---|---|---|
| CallSession initiated/ringing | 发起、取消、接听、拒绝、无应答 | incoming/outgoing + realtime-gateway | 页面不得本地构造会话或用 `voice` type |
| Participant connecting/connected | 媒体建连与在会成员 | voice/video/picker + LiveKit | Answer 成功不等于 connected；必须 ReportMediaConnected |
| Participant mute/camera | 媒体控制 | voice/video control bar | 本地图标不能替代 Facet/LiveKit 结果 |
| screenShareUserId | 开始/停止/互斥 | video page | 同时一人；权限失败结构化降级 |
| CallSession ended | 收尾、返回会话、历史 | 五页 + chat `system_call_log` | 不建独立历史假页，不重复投影 |
| realtime Connection | 在线事件 | shell coordinator（无独立页） | 只能投递，不能授权 |
| offline delivery | 后台/锁屏/被杀来电 | platform callback + incoming page | 当前 P0 链路，不能以 payload contract 代替 |
| media QoE | 黄金指标与回滚 | 无用户页；SLS/dashboard/alert | 当前 P0 观测链，不得造不存在的 PromQL |

CallParticipant 没有独立页面/Store 是正确边界；LiveKit/TURN 没有普通用户页也是正确边界。
真正缺口是状态、权限、设备回调和指标证据，而不是机械造页面。

### M7-E 核心断点与六维度

#### M7-E1 当前核心断点

1. **R-RTC01 离线来电**：PushKit/FCM、DeviceRegistration endpoint、展示 ACK 尚未形成真实 provider→设备→Answer/Reject 全链；Web Push 不在 M2。
2. **R-RTC02 媒体 QoE**：emitter/rollup/SLS+LiveKit 告警合同已落地，真实 series、dashboard readback 与发布演练仍缺。
3. **Gamma 准出**：full workload 因缺
   `~/.config/quwoquan/product_telemetry_sls/gamma.env` 按预期 fail-closed。
4. **状态证据**：timeout 与 ReportMediaConnected 已有实现/局部测试，但新三层 planned 证据尚未完整 recorded。
5. **体验证据**：PiP hangup、screen-share 互斥/设备权限与真实媒体 UAT 尚未 recorded。
6. **历史 IA**：会话 `system_call_log` 是当前主形态；独立 ListCalls 页面明确 deferred。

#### M7-E2 D1～D6

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 功能 | 在线 1v1/多人、reconnect、system_call_log 已有局部证据 | 合法入口→ring→connected→media/control→end→会话回流；离线也能可靠叫起 | timeout/connected、offline push、PiP hangup、screen share | audio/video/群/1v1/多端竞态 UAT |
| D2 对象 | CallSession/Participant/Connection 单轨已成形 | 五 Facet、CAS/receipt/outbox、realtime per-persona/device、chat projection 全同源 | 清所有旧口径；保持 child 只经 aggregate；补 readiness 证据 | Mongo/Redis/LiveKit/chat/realtime contract |
| D3 UX | 五页 P2～P3，视觉未核验 | 核心页 P4；来电信任清晰、舞台无交集干扰、错误可恢复 | 真机截图、权限、横竖屏、动态字体、PiP/screen-share | iOS/Android/Web capability profile；OHOS 安全降级 |
| D4 非功能 | service SLO 有；媒体指标不可读 | command/query、media connect、中断/恢复、32 人容量与热控有预算 | emitter/rollup、弱网/TURN/后台、容量 | P50/P95/P99、低端机/网络切换/32 人 |
| D5 观测 | rtc outcome/realtime connect + QoE emitter/rollup + HTTP/LiveKit/SLS 告警合同 | 3 个媒体黄金指标 + 服务 RED + 离线来电到达/漏接诊断 | 完成 push delivery 与 Gamma/Prod readback | SLS/Prometheus/LiveKit/provider 对账 |
| D6 测试 | 多个 local/API/UAT 存在，但关键 planned 未 recorded | 状态机、权限、设备、媒体、观测三层齐备 | 按 L2/L3 acceptance 新路径补测试与报告 | Alpha contract、Beta Remote、Gamma device、Prod canary |

### M7-F 黄金指标、四环境与交集策略

#### M7-F1 一级黄金指标

| 指标 | 计算语义 | 建议商用门槛 | 当前状态 |
|---|---|---|---|
| 有效媒体接通率 | 合法 accepted/joined 尝试中，至少两人 connected 并进入 in_call | ≥98%，最终由 metadata/SLO 冻结 | emitter/rollup/alert 已落；缺 Gamma 分母 readback |
| 接听/加入到媒体可用 P95 | Answer/Join 成功到 ReportMediaConnected | ≤3s（强网建议） | connectTimeHistogram + SLS alert 已落；缺真实 series |
| 非预期媒体中断率 | 已 in_call 会话中排除主动正常结束后的异常中断占比 | ≤2%（建议） | connection_lost rollup + SLS/LiveKit alert 已落；缺发布演练 |

重连次数、重连成功率、TURN 使用、networkQuality、callType、版本只作为二级诊断。
callId/userId 不能成为 Prometheus label。

#### M7-F2 四环境准出

| 环境 | 准出证据 | 当前状态 |
|---|---|---|
| Alpha | pure contracts、隔离 mock bundle、Facet parity、状态/错误/Widget；production 无 Mock 可达 | 局部可用，不证明真实媒体/Push |
| Beta | Remote generated client、真实 rtc-service Mongo/Redis、关系门禁、receipt/outbox、LiveKit adapter、chat projection | partial，按环境报告复核 |
| Gamma-local | Android/iOS 设备上的 offline push、timeout/connected、网络切换、PiP hangup、screen share、QoE 原始证据 | blocked：SLS Secret + R-RTC01/02 |
| Prod-hosted `gray_initial` | 真实 provider、SLS/Prometheus readback、三指标、告警 ack/resolved、回滚 receipt | pending |

#### M7-F3 交集策略

- **授权层**：只认 relationship capability 与 block 事实；交集/presence/在线状态不授权。
- **解释层**：来电/入会前消费 `known/possibly_unknown`、来源会话/群等最小信任证据。
- **舞台层**：建连后不展示共同兴趣、共同关注数、交集列表或推荐理由；只显示参与者、媒体、
  网络和安全状态。
- **行动回流**：通话结束回 Conversation `system_call_log`；关系沉淀仍由 user/chat 源对象负责，
  RTC 不创建第二份关系。

### M7-G 标杆与专项启动提示词

FaceTime、微信通话、WhatsApp Call、Google Meet。只借鉴接通反馈、系统来电、弱网恢复、
权限渐进、PiP 与参与者治理；不复制联系人发现、系统私有能力或会议型功能堆叠。

> 以 `contracts/metadata/rtc/**`、CR-20260719-121、L2 spec/design/acceptance 与
> R-RTC01/R-RTC02 为真相继续 M7。覆盖 CallSession/Participant、五 Facet、
> realtime-gateway、LiveKit/TURN、五页面、system_call_log、offline push、PiP hangup、
> screen share 与 media QoE。禁止恢复 RTC 私有信令、聚合 Repository/production Mock、
> 录制承诺或 `voice` callType；不得在没有 emitter/series 时补假告警。输出对象/页面双向矩阵、
> 真机视觉、三层测试与四环境准出证据；未验证项保持 partial/pending。

## 17. M8 详细规格

### M8-A 版块定位

- **用户目标**：发现并理解圈子，加入/退出、浏览内容/讨论/成员，管理圈子和群单元，从实体主页/搜索进入协作。
- **树绑定**：Journey `circle-entity-group-collaboration`；Scenario `circle-entity-group-handoff`、`message-group-entry-matrix`，协同 companionship draft。
- **交集定位**：核心承载。圈子是同趣关系的长期沉淀面；交集需给出事实证据和加入/讨论行动。

### M8-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `Circle` | owner Persona、Homepage、Conversation、default CircleGroup；create→active→update→archive | `social/circle/**`；circle-service Mongo | canonical 域为 social；`metadata/circle` 历史出口 |
| `CircleSectionConfig` | Circle owned；配置内容区 | Circle settings | 只能经 Circle aggregate |
| `CircleMembership` | Circle×Persona；request/join→active/role→leave/removed | detail/member UI | 辅助对象无 `errors.yaml` |
| `CircleGroup` / Membership | 组织群单元→绑定 Conversation；request/approve/reject/leave | 圈子→群聊 | 与 ad-hoc Conversation 边界 |
| `CircleFile` | 圈子文件生命周期 | 当前页面承载待核验 | 对象存在但功能/页面可能缺失 |
| `CirclePostPlacement` | Post 在 Circle 中的关联/排序 | Circle feed/publish select | 删除/封禁同步 |
| `CircleSearchItemView` | 搜索投影 | M5 | 无写语义 |
| `CircleBehaviorFact` | impression/dwell/join/leave append fact | 无独立页 | 与产品 event 分轨 |

### M8-C 页面预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `home_circles_hub_page.dart` | P3（视觉未核验） | 精修：发现/内容/圈子边界 |
| `circles_page.dart` | P2（视觉未核验） | 适度重构：列表来源、空/错与筛选 |
| `circle_detail_page.dart` | P3（视觉未核验） | 适度精修至 P5：身份、交集、加入、内容/讨论/成员 |
| `circle_edit_settings_page.dart` | P2（视觉未核验） | 适度重构：生命周期/权限/保存冲突 |
| `circle_stats_page.dart` | P2（视觉未核验） | 适度重构：指标真相、权限、时间窗 |
| `circles_hub_page.dart` | T0 barrel | 删除或保留薄 export；不独立评级 |

### M8-D 双向初查

- `CircleFile` 已建对象但当前 5 个独立页面中无明确文件管理承载；专项需判断它是已发布能力还是应 deferred/删除。若商业规格要求而无入口，为 GATE_BLOCK。
- CircleGroup 主要通过 chat/group 页面承载合理，但 Circle Detail 必须清楚展示群单元来源和权限。
- 当前群页只覆盖通用 Conversation 治理，未证明 CircleGroup 的创建/编辑/归档与 CircleGroupMembership 的申请/审批/拒绝状态；若规格要求这些 operation 对用户可达，现状为 GATE_BLOCK，而不是“由 chat 页面天然承载”。
- ad-hoc group 只属于 Conversation；把它写成 CircleGroup 或让 chat 直接写 CircleMembership 均 GATE_BLOCK。
- behavior fact 无页面正确；圈子统计页必须读真实聚合，不得用 fact/mock snapshot 拼指标。
- CirclePostPlacement 的 pin/feature 等管理员 command 需核对真实 UI；operation 存在但无可达动作同样属于旅程断点。

### M8-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 圈子发现/详情/编辑/统计存在 | 发现→加入→内容/讨论→群协作→退出/归档完整 | 裁决 CircleFile/Group/Activity；补权限终态 | owner/member/guest/blocked UAT |
| D2 | 9 对象图清楚；错误契约和历史域残留 | social 为唯一 owner，owned/config 与 group/Conversation 边界清晰 | 补 errors，清空壳域，核对事件/删除策略 | Mongo/Redis/outbox/Chat integration |
| D3 | 详情已有交集 IA | 详情=P5，其余核心页≥P4 | 真机视觉、模板、成员/统计信息架构 | 双色/断点/iOS/无障碍 |
| D4 | 列表/详情有分页基础 | 详情首用、成员/内容分页、join command、统计查询预算 | 缓存失效、并发加入、归档传播 | 大圈容量、弱网、长列表 |
| D5 | join/leave/impression/dwell 已部分接 | 3 指标：有效加入率、打开到可参与 P95、加入后有效互动率 | Circle metric/Behavior/Page 三轨对账 | 对象告警+运营漏斗 |
| D6 | App local/UAT 有，App API 零；service local 目录缺 | Circle/Membership/Group/Placement 三层齐备 | 建真实 local/API，跨 chat/entity UAT | beta stores、gamma group journey |

### M8-F 标杆候选

豆瓣小组、Reddit Communities、Discord Server、微信社群/群聊。借鉴成员治理、内容组织、角色与持续关系；不复制匿名失控或把群聊等同圈子。

#### M8-F.1 标杆对比详表（检索日期 2026-07-20）

| 标杆产品 | 对标页面/旅程 | 功能完整性 | 信息架构 | 关键交互 | 异常恢复 | 可借鉴原则 | 不适合照搬 |
|---|---|---|---|---|---|---|---|
| 豆瓣小组（help.douban.com/group） | 小组主页/加入/管理 | 组规、审批加入、组长-管理员-成员三级、置顶（≤10）、精华人工标记、踢出/永久封禁、转让组长 | 帖子流为核心 + 组规/公告置顶 | 申请加入→审批；置顶/精华由管理员人工操作 | 拒绝有理由、可再申请 | 三级权限 + 审批状态机 + 人工精华（非算法） | Web 论坛纯文本形态、匿名发帖 |
| Reddit Communities（reddithelp.com） | Subreddit 主页/规则/欢迎 | Community Highlights 置顶轮播（≤6，可设过期）、Rules widget、加入后 Welcome Message、public/restricted/private 三态、Post Guidance 预警 | 头图+简介+规则侧栏+帖子流 | Join 后自动弹欢迎引导；发帖前规则预警 | 私有社区可申请加入 | 加入即引导（Welcome Message）、置顶轮播带标签/过期、可见性三态 | 桌面侧栏 widget 体系 |
| Facebook Groups（facebook.com/help） | 群组主页/Admin Tools | feature sets 按需开关（事件/投票/文件/群聊/徽章）、post format 管控 | Admin Tools 单入口收口全部管理 | 管理操作全部聚合在一个管理面 | — | 管理中心单入口聚合（与现有 CircleEditSettingsPage 同构，可强化） | 商业售卖功能集 |
| 小红书小红圈/群聊广场（界面新闻 2025-12） | 圈子主页/进圈 | 圈内图文/视频/语音、口令进圈、圈主招募制、群聊广场申请加入 | 圈子↔群聊双载体互导 | 口令/申请加入、圈子沉淀+群聊高频互动 | — | 圈子（沉淀）与群聊（高频）双载体分工——与本项目 Circle↔CircleGroup↔Conversation 模型一致，可作为叙事依据 | 极端私域（搜索不可达）、电商导向 |

对照结论：趣我圈缺的不是对象模型（membership/group/file/placement 全有），而是①加入后引导与治理体验（欢迎语/圈规展示/圈子级审批页/精华置顶的用户可见承载）；②传播回流（分享深链/邀请，2026-07-20 已接线）。

### M8-G 并行会话启动提示词

> 完成 M8 圈子与社区全面分析。读取本文 §0～§9、§17、social/messages/entity object maps、circle Journey 与相关 acceptance。执行完整强制分析，重点裁决 CircleFile、CircleGroup、Membership 与 Conversation 的对象—页面承载。圈子详情目标 P5，交集必须为可证事实并给出行动。Out of Scope：消息传输归 M6、实体主档归 M9、附近/线下活动未建正式聚合前不得用 UI Mock。输出 10 项交付物。

### M8-H 2026-07-20 商用化排查结论与执行规划（对象中心强制分析）

> 本节为 M8 专项排查（业务对象中心、页面成熟度与交集差异化强制分析）的正式落点；执行主线见 Phase 0～5。

#### M8-H.1 排查主线结论

- **领域模型确实围绕业务对象建立**：canonical 真相源在 `contracts/metadata/social/circle*` 七对象 packet（`metadata/circle/` 仅 codegen 出口）；circle-service 全分层实现、17 个 api_integration、50 错误码、outbox/投影/缓存/告警齐备。对象关系与生命周期基本合理。
- **页面未完整承载对象与旅程（GATE_BLOCK 清单）**：
  1. `CircleMembership.joinPolicy=approval` 有 pending 态但**无圈子级 Approve/Reject 命令**（审批命令只在 CircleGroupMembership），owner/admin 无审批页——对象状态无页面承载。
  2. `CirclePostPlacement.pinned/featured` 有命令与事件但**无用户可见承载**（内容 tab 不展示置顶/精华，管理菜单无操作入口）——operation 存在但旅程不可达。
  3. 分享/复制链接/举报为 toast 占位、无邀请入口（2026-07-20 已接线：系统分享深链 `AppPublicContentLinks.circleWebUrl` + 统一举报链路 `ContentReportTargetType.circle` + 邀请复用分享通道）。
  4. `referralSource` 12 个进圈入口仅 1 处传递，进圈归因失效（2026-07-20 已修复：11 入口全部显式归因 search/authorProfile/entityPage/chatLink/myIntersections/organicFeed）。
  5. hub 频道页 `listHomeCircleDiscoveryFeed` 为客户端 N+1 假聚合（500 圈 × 逐圈 feed 凑 200 条）+ 端侧全量过滤 + 默认垂类 `campus` 硬编码——需云侧聚合 discovery feed operation。
  6. `SectionStorage`（557 行）生产零消费（2026-07-20 已按 metadata `ui_config` sectionTypes [chat,storage] 接线 discussion tab）；`SectionInteraction`（246 行）metadata 无此 section、含假语义硬编码（已删除）；mock sectionConfig 四板块与 metadata 闭集漂移（已修复为 works/members/chat/storage）。
  7. recommendation-service **零 circle 事件消费**（events.yaml 声明 consumer 但实现 0 文件），圈子推荐闭环断裂。
  8. `GetCircleFeed` 云侧返回 `[]map[string]any` 弱类型透传（R04）。
- **验收与四环境空心**：circle-community 特性树 22/25 acceptance 为 pending 骨架；App 端 circle api_integration 为零（孤儿 runner）；circle-service 缺 `tests/local_contract` 目录（H2-2）；detail 页 UAT pages 级为「证据存在性元测试」；R-IX05（四主页真实数据）未关闭——gamma 探针（2026-07-20 复核）：`/circles` 与 `/circles/{id}/feed`（photo 圈）populated，`fixture_circle_tech_01` feed 空，`/impact` 与 `/content/intersections/object` 需 viewer 鉴权（匿名 401 属预期）。
- **用户感知「完全不可用」定性**：主因是四环境真实数据链路未闭环（部分圈 feed 空、impact/交集需登录态种子）+ hub N+1 首屏性能 + 分享/审批/精华旅程断裂，而非页面骨架缺失。

#### M8-H.2 页面成熟度定级更新（2026-07-20，代码证据）

| 页面 | 评级 | 决策 | 主要缺口 |
|---|---:|---|---|
| `circle_detail_page` + `CircleShell` | P2~P3 → 目标 P5 | 中度补齐 | 分享/举报/邀请（已接线）、置顶/精华承载、审批反馈、真实数据 |
| `home_circles_hub_page` | P1~P2 → 目标 P4 | 数据链路完全重构 | N+1 假聚合、端侧过滤、raw Map 穿透、曝光埋点（已补） |
| `circle_edit_settings_page` | P3 → 目标 P4 | 适度优化 | 979 行 state 拆分、埋点（已补）、审批队列入口 |
| `circle_stats_page` | P3 → 目标 P4 | 轻量精修 | 埋点（已补）、指标真相 |
| 入圈审批管理页 | P0（缺失） | 新建 | 圈子级审批命令 + owner/admin pending 队列页 |
| 圈规/欢迎引导承载 | P0（缺失） | 新建（借鉴 Reddit Welcome Message + 豆瓣组规） | Circle 聚合补 rules/welcome 字段 |

#### M8-H.3 交集差异化规划矩阵

| 页面/场景 | 主对象 | 需要交集 | 交集证据 | 用户价值 | 表达 | 行动 | 冷启动 | 指标 |
|---|---|---|---|---|---|---|---|---|
| 圈子主页「我的交集」卡 | Circle×viewer | 核心承载 | sharedCircle/followeeInObject/coVisitedEntity 等事实（云侧 primaryText） | 决策：是否加入 | 统一 `ObjectIntersectionSection`（primarySpans 蓝字下钻） | 加入圈子/进入讨论 | 无交集时空态文案，不伪造 | 交集曝光→加入转化率 |
| 圈子主页「圈子影响力」卡 | Circle | 场景增强 | CircleImpact 真实读路径（R-IX05） | 解释：圈子帮助他人连接的能力 | ObjectImpactPreviewCard | 查看影响力时间线 | 无 impact 不渲染 | 影响力查看→互动率 |
| hub 推荐模块 | Circle 候选集 | 场景增强 | 推荐召回（Phase rec 消费落地后） | 发现 | 卡片 + 推荐理由（仅事实） | 进圈 | 垂类兜底 | hub 曝光→进圈率 |
| 编辑/统计/审批管理页 | Circle 治理 | 无需承载 | — | — | — | — | — | — |

#### M8-H.4 执行规划（Phase 0～5）与验收锚点

- **Phase 0 规格冻结**（本节 + acceptance 改写）：`member-role-permission`（圈子级审批）、`behavior-ingestion`（rec 消费）从骨架 GWT 改写为真实验收。
- **Phase 1 detail 断点修复（已完成 2026-07-20）**：分享/复制链接/举报/邀请接线；11 入口 referralSource 归因；hub/stats/edit 曝光+停留埋点（hub/stats 走行为通道、edit 走 product_action journey）；section_chat 死分支与硬编码清理；section_interaction 删除；section_storage 接线；mock/编辑页默认板块对齐 metadata 闭集。验收：`test/local_contract/ui/circle/**` + `test/local_contract/cloud/circle/**`。
- **Phase 2 hub 数据链路重构**：metadata 新增 circle discovery feed 聚合 operation（服务端垂类/我的过滤+游标分页）→ 替换端侧 N+1；读侧迁 generated client；`GetCircleFeed` typed 投影。性能预算：hub 首屏 P95 ≤ 800ms（单次聚合请求）、分页游标、feed 缓存 TTL 60s。
- **Phase 3 治理与传播**：圈子级 `ApproveCircleMembership/RejectCircleMembership`（metadata→codegen→Go→审批页→通知回流）；置顶/精华内容 tab 承载 + 管理菜单入口；Circle 聚合 rules/welcome 字段 + 加入成功引导卡；recommendation-service circle 事件消费。
- **Phase 4 三层测试与四环境**：App api_integration 从零建（detail/feed/membership/impact/intersection 直连 gamma-local）；circle-service `tests/local_contract` 目录；UAT 真实化；gamma strict → beta → prod gray-initial，证据回写 R-IX05。
- **Phase 5 观测运营**：黄金指标（有效创建率、加入转化率含审批通过率、成员 7 日活跃率、圈内发帖率、交集解释后有效行动率）；circle 专属 Grafana dashboard；`commercial_defaults` 按 B4 证据翻牌。

## 18. M9 详细规格

### M9-A 版块定位

- **用户目标**：搜索/内容跳转到地点、学校、事物等主页，识别对象身份与来源，关注、评价、查看内容/圈子/交集，完成建议、认领、维护或状态上报。
- **树绑定**：`circle-entity-group-collaboration`、`content-detail-profile-handoff`、`intersection-action-deepening-on-object`；homepage discovery/review/content journey。
- **交集定位**：核心承载。主页解释“你和这个对象为何有关系”，并连接想去、关注、圈子、内容、同趣行动。

### M9-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `Homepage` | source candidate→publish→active→claim/update→offline/reload；owner Account/Persona | `entity/homepage/**`；entity-service Mongo | R-HSE02 热重载、R-HSE03 拓扑 |
| `HomepageClaimRequest` | create→pending→approved/rejected/withdrawn | claim page | 申请人/审核人、材料隐私 |
| `HomepageReview` | create→active→edit/delete/moderate | detail review sheet | 与 rating summary 最终一致 |
| `HomepageStatusReport` | submit→pending→resolved/rejected | status report page | 运维/审核回流 |
| `HomepageSearchItemView` | Homepage 索引投影 | picker/search | tombstone/freshness |
| SubjectFollow / co-wishlist signal | Persona 与 Homepage 关系 | detail + M12/M10 | Follow 真相在 user；想去语义需单轨 |
| Wishlist intent | “想去/计划去”→`coWishlistedEntity` 的事实源 | 当前仅 behavior/内部投影，尚无 canonical 用户写对象 | 实体 UI 未发现 add/remove 入口；seed 能产出交集不等于真实用户可形成意图 |

### M9-C 页面预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `suggest_homepage_page.dart` | P2（视觉未核验） | 适度重构：候选重复、来源、审核反馈 |
| `homepage_picker_page.dart` | P3（视觉未核验） | 精修：搜索、空/错、选择语义 |
| `homepage_claim_page.dart` | P2（视觉未核验） | 适度重构：材料隐私、状态、撤回/补交 |
| `homepage_maintenance_page.dart` | P2（视觉未核验） | 适度重构：版本冲突、权限、预览 |
| `homepage_status_report_page.dart` | P2（视觉未核验） | 适度重构：处理状态和结果回流 |
| `homepage_detail_page.dart` | P3（视觉未核验） | 适度精修至 P5：交集、口碑、内容/圈子、行动 |
| `homepage_introduction_page.dart` | P3（视觉未核验） | 精修：来源透明、外链安全、失效 |

### M9-D 双向初查

- Homepage 五对象均有页面或嵌入承载；但 Claim/StatusReport 的审核结果回流、撤回/补交是否完整需核验。
- Follow 属 user.SubjectFollow，Homepage 页面不得维护第二份关注状态；review 属 entity，Post 评论不能替代。
- Location 搜索 landing 只有临时对象；用户执行正式关注/评价前必须提升/解析到 Homepage。
- `HomepageSearchItemView` 无独立页合理；索引 tombstone 后 picker/detail 必须同步失效。
- ClaimRequest/StatusReport 当前主要有提交页，需核对状态查询、补材料/撤回和审核结果回流；只提交不返回生命周期结果是 GATE_BLOCK 候选。
- Homepage Detail 若没有正式 wishlist add/remove，M10 的 `coWishlistedEntity → start_companion` 只能由 seed 证明，不能作为用户旅程完成证据。

### M9-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 七页覆盖主流程；数据发布仍有 HSE 风险 | 发现→详情→关注/评价/交集；建议/认领/维护/上报均有结果回流 | 修热重载；补 claim/report 全状态 | viewer/owner/reviewer UAT |
| D2 | 五对象图与页面映射较完整 | Homepage 主档、Review/Claim/Report、Search view 分工清晰 | 核对状态机、follow/wishlist refs、拓扑 | Mongo/import/event/search integration |
| D3 | 详情已有交集 IA；静态调查曾发现 entity 文案高风险 | Detail=P5，管理/表单≥P4 | 重新跑中文文案门禁；真机视觉/模板/隐私 | 双色/断点/iOS/无障碍 |
| D4 | 真实 prod 主页导入已有历史证据 | detail/intro/review P95、图片/CDN、热重载、缓存预算 | releaseId invalidation、分页、CDN fallback | 双省容量、弱网、缓存一致 |
| D5 | detail/review 部分行为已有 | 3 指标：有效对象访问率、打开到可行动 P95、交集解释后关注/想去/加入率 | homepage/review/follow/intersection 同 trace | entity metric+SLS+Behavior 对账 |
| D6 | App local/UAT 较多；service domain 零测试历史缺口 | Homepage 五对象、导入/索引/页面三层齐备 | 补 domain 状态机、Remote、双省动态 UAT | beta import、gamma T3、prod canary |

### M9-F 标杆候选

Google Maps/Apple Maps Place、豆瓣条目、携程景点、Wikipedia/小红书地点页。借鉴身份来源、口碑、认领与地点行动；不照搬星级商业排序或泄露用户足迹。

### M9-G 并行会话启动提示词

> 完成 M9 实体主页全面分析。读取本文 §0～§9、§18、entity/user/content/social object maps、homepage specs 和 R-HSE02/03/04/06/07。覆盖 7 页、review sheet、follow/wishlist/交集关系、导入与索引生命周期。执行完整强制分析，详情页目标 P5。Out of Scope：省级内容生产由 Data 会话、票务转化由 R-COMMERCE-001 专项、平台部署由 Ops。输出 10 项交付物与双省/四环境证据要求。

## 19. M10 详细规格

> 2026-07-20 专项会话已按本节完成全链路排查与规划冻结；本节保留为底料，最新裁决与工作包以 [`docs/intersection-commercial-maturity-plan.md`](intersection-commercial-maturity-plan.md) 为准。

### M10-A 版块定位

- **用户目标**：理解自己与人、内容、圈子、实体之间可证实的共同点，从“围观”逐步进入关注、收藏、讨论、联系、同行等行动，并沉淀为可管理关系。
- **树绑定**：Journey `intersection-action-to-companionship`；Scenario `intersection-action-deepening-on-object`、`companionship-and-nearby-connection`、`contact-label-driven-connection`。
- **交集定位**：核心主战场。所有适用页面的目标是 P5，但不得把推荐相似度包装成事实。

### M10-B 业务对象底料

当前 canonical object map **没有 `Intersection` 聚合根**。这是合理候选设计：交集是多源事实/推断的物化读模型，行动写入仍由 Follow、CircleMembership、Conversation、Wishlist/Visit 等源对象拥有；专项会话必须验证而不能默认。

| 对象/投影 | 关系/生命周期 | 承载 | 当前问题 |
|---|---|---|---|
| Intersection projections | representative actor、reason、evidence、point、target、action hint、inbox summary | `recommendation/model_release/projections/intersection_*.yaml` | R-IX01/02 模型分与 per-candidate 物化未闭合 |
| `IntersectionVisitState` | viewer×inbox/read watermark；open→seen | `content/intersection_visit_state/**` | 错误契约和多端水位需核验 |
| `RecommendationExposureFact/FeedbackFact` | 交集/推荐展示和反馈事实 | recommendation | R-OPS-BEHAVIOR-CONSISTENCY |
| `SubjectFollow` / `PersonaRelationship` | 关注、互关、拉黑等事实边 | M12 | 交集不可改写权限门 |
| CircleMembership / Conversation | 加入、讨论、联系等行动 owner | M8/M6 | action hint 只导航到正式 command |
| coWishlistedEntity signal | viewer×Homepage 共想去事实投影 | M9/M12/recommendation | 已有 gamma-local 局部证据，四主页/环境未全闭 |
| `InterestMatchOpportunity`、trip/meetup | 规划中的重行动机会 | 尚无 canonical object packet | R-PLAZA-001；不得用 launcher/Mock 冒充 |

### M10-C 页面/场景预评级

| 页面/场景 | 预评级 | 决策 |
|---|---:|---|
| `lib/ui/intersection/pages/object_intersection_list_page.dart` | P3（视觉未核验） | 适度精修至 P5：事实/推断分层、证据下钻、行动 |
| `lib/ui/interest_match/pages/interest_match_page.dart` | P1（视觉未核验） | 当前仅 launcher；保留为诚实导流或待正式 Opportunity 对象落地后完全重构 |
| Profile/Circle/Homepage 内 `ObjectIntersectionSection` | P3（视觉未核验） | 统一精修至 P5；禁止分叉渲染链 |
| Feed/Search 交集解释 | P2（视觉未核验） | 适度重构：显式推断标识、来源与行动 |
| `my_intersection_inbox_page.dart` | P3（视觉未核验，主归 M12） | 精修时间线、已读水位与回流 |

### M10-D 双向初查

- 交集 read model 无独立写聚合合理；若 UI 直接“修改交集”或把 projection 当写真相，GATE_BLOCK。
- `InterestMatchOpportunity`、trip、meetup 尚无对象与状态机；launcher 仅导流，不能被列为能力完成。重行动上线前必须补风控、双向同意、青少年与位置隐私。
- ObjectIntersectionSection 已同源是积极基线；任何主页私有 reason mapper、action 表或 icon 表回归均 GATE_BLOCK。
- 交集为空是合法状态；不得用 objectType fallback、静态文案或模型推荐伪造共同事实。
- 当前 `start_companion` 只把交集上下文带到普通建群页并用于 banner/埋点；候选仍来自普通群候选，且未证明 `login/realName/minorMode/blocked/rateLimit` 安全门执行。没有共同想去对象的双用户候选/请求/接受拒绝状态机，不能称“约伴闭环”。

### M10-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 对象页/列表/inbox/launcher 存在；重行动 deferred | 证据→理解→合法行动→关系沉淀无断点 | 裁决最薄 C0；重行动对象未落地前保持 honest launcher | 无交集/有交集/行动成功失败 UAT |
| D2 | projection 集齐；无 Intersection 写聚合 | 源事实 owner、projection、action owner 三层清晰 | 补 per-candidate、状态机/水位、删第二 reason/action 表 | event→projection→UI→command E2E |
| D3 | 共享组件已存在 | 主页/列表/inbox 统一 P5；launcher 不伪装 | 真机视觉、句内证据、隐私遮蔽、冷启动 | 跨 5 展示位一致性 |
| D4 | 读路径零同步打分已锁定 | 异步物化、首屏/列表 P95、缓存/水位/分页预算 | 禁止 per-candidate RPC；增量物化与 stale 策略 | 大候选、低互动、重放 |
| D5 | 交集曝光/访问/行为部分存在 | 3 指标：可解释交集覆盖率、展示到可行动 P95、解释后有效行动率 | 事实/推断、kind、action outcome 同 trace | SLS/Behavior/projection 对账 |
| D6 | 多 local，gamma 曾有局部证据 | 事实真实性、隐私、冷启动、行动权限三层齐备 | 补负例、四主页 Remote、gamma T3、prod canary | 无伪事实、无越权、同一 seed 可重放 |

### M10-F 标杆候选

LinkedIn mutual connections、Facebook Groups/common friends、Airbnb 同行协作、豆瓣同好/小组。借鉴证据解释与关系行动，不照搬社交图公开、联系人扩张或“你可能认识”黑盒。

### M10-G 并行会话启动提示词

> 完成 M10 交集与同趣配对全面分析。读取本文 §0～§9、§19、intersection projection registry、R-PLAZA-001、R-IX01～05、R-ID 系列、三个 Scenario。执行完整强制分析，必须证明每条交集是事实还是推断、证据权限、冷启动与 action owner。覆盖列表、launcher、四主页共享组件、Feed/Search/inbox。Out of Scope：深排模型由推荐轨、trip/meetup 未建对象前不得实现 UI 假能力。输出 10 项交付物和五展示位统一验收。

## 20. M11 详细规格

### M11-A 版块定位

- **用户目标**：在首页、内容、搜索、个人页和群聊唤起同一个小趣；获得基于当前对象和可信来源的回答，明确授权后订阅主动投递，并可反馈纠错。
- **树绑定**：Journey `assistant-omnipresent-private-assistant`；四个 Scenario：context grounding、chat topic、search handoff、proactive subscription。
- **交集定位**：场景增强。小趣可解释交集证据，但不得自行创造用户关系或维护第二套对象事实。

### M11-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `AssistantConversation` | Account owner；create→active→summarized/closed | personal conversation | 会话与 chat Conversation 不能混同 |
| `AssistantRun` | source surface/object→running→streaming→completed/failed/cancelled | conversation/half sheet | pageObject 可引用 Post/Comment/Circle/Homepage/Conversation/Message/Persona/Location |
| `AssistantTurnView` | Run event projection | transcript | 只读投影，不接受 UI 写 |
| `SkillSubscription` | create→active/paused→tick→expired/cancelled | skill center/management | 主动投递频控、静默和目的地 |
| `SkillConsent` | grant→active→revoke；按 actor 隔离 | management/inline gate | R-CLOUD02 仅剩 gamma 负测 |
| `AssistantInteractionEvent` | feedback/copy/share/correction append fact | feedback UI | PII/文本保留与学习边界 |
| `AssistantScorecardFact` | run/event→metric score | 无页面 | 运营/质量投影，不是回答真相 |

### M11-C 页面预评级

| 页面/场景 | 预评级 | 决策 |
|---|---:|---|
| `assistant_management_page.dart` | P3（视觉未核验） | 精修 consent、订阅、权限与失败关闭 |
| `assistant_reference_webview_page.dart` | P2（视觉未核验） | 适度重构：来源安全、失败、回到回答 |
| `personal_assistant_conversation_page.dart` | P3（视觉未核验） | 适度精修：stream/工具/引用/取消/恢复 |
| `assistant_skill_center_page.dart` | P2（视觉未核验） | 适度重构：真实 catalog、订阅状态、空/错 |
| assistant half sheet/history/feedback 嵌入场景 | P2～P3（视觉未核验） | 与全屏 conversation 共用对象与状态，不得另建逻辑 |

> 2026-07-20 进展（CR-20260720-129）：会话生命周期查询面（List conversations/turns）、
> CancelAssistantRun、历史抽屉（assistantHistory surface 真实承载）、停止生成、
> 重新生成接线、本地会话双模型删除、技能中心最近会话云端化已落地并三层测试绿；
> conversation 页向 P4 推进的剩余项为 token 级流式（R-ASSIST-004）与真机视觉核验。

### M11-D 双向初查

- AssistantRun 已允许多种 pageObject 引用；页面只上传结构化 snapshot，禁止 raw UI Map 或小趣复制 Post/Homepage 数据。
- SkillConsent 无独立页不构成缺口，management/inline gate 可承载；但授权失败开放或本地合成成功直接 GATE_BLOCK。
- Scorecard 无用户页正确；Portal/运营只读聚合，不能影响单次回答事实。
- chat 内 assistant 是 `ConversationMember(memberType=assistant)`；个人 assistant conversation 不应被伪装成 chat Conversation。

### M11-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 四场景有规格和页面/UAT | 任意入口→grounding→回答/行动→反馈；订阅→合法投递 | 补 gamma consent、来源失效、投递撤权 | 页面/群聊/搜索/主动投递 UAT |
| D2 | 7 对象图完整度高 | Conversation/Run/View/Consent/Subscription/Event/Score 明确 | 核对文本保留、actor、tool command 边界 | Mongo/PG/Redis/event integration |
| D3 | 页面横向维绿 | conversation≥P4；交集/引用解释可达 P5 增强 | 真机 stream、键盘、引用、错误/取消、双色 | accessibility + snapshot |
| D4 | Run latency 字段与告警已部分有 | TTFT、首个可用回答、完成、工具、取消预算 | backpressure、断流恢复、token/成本、降级 | 慢模型/工具失败/离线 |
| D5 | interaction/scorecard 事实存在 | 3 指标：有效回答完成率、提问到首个可用回答 P95、回答后有效行动/满意率 | run/turn/tool/event 同 trace | SLS + assistant metric + learning 对账 |
| D6 | App API integration 相对最好、真实页面 UAT 已补 | consent/stream/tool/投递/反馈三层齐备 | 补 gamma/prod、撤权实时负例、引用安全 | alpha deterministic、beta stores、gamma device |

### M11-F 标杆候选

ChatGPT、Perplexity、Apple Intelligence/Siri、Slack AI。借鉴引用、流式状态、取消、权限和反馈；不复制无来源回答、跨应用过度授权或品牌交互。

### M11-G 并行会话启动提示词

> 完成 M11 小趣助手全面分析。读取本文 §0～§9、§20、assistant object map、四个 assistant Scenario、R-CLOUD02。覆盖 4 个页面和 half sheet/history/feedback/chat mention，执行完整强制分析。所有 grounding 必须回到源对象，交集证据不可由模型伪造。Out of Scope：LLM/模型平台优化、通知通道实现分别归模型/M13；本会话定义契约与用户体验。输出 10 项交付物、真机视觉和 consent/stream 三层证据。

## 21. M12 详细规格

### M12-A 版块定位

- **用户目标**：查看/编辑自己的 Persona 主页，理解他人主页，管理关注、拉黑、联系人与标签，查看私有足迹/互动历史，并从一次互动沉淀为持续关系。
- **树绑定**：Journey `profile-private-activity-history`、`intersection-action-to-companionship` 的 `contact-label-driven-connection`，协同 identity/profile redesign。
- **交集定位**：核心承载。关系事实、派生称谓和私有标签帮助回流与沉淀；不得公开私有历史或用标签解锁权限。

### M12-B 业务对象底料

| 对象 | 关系/生命周期 | 页面 | 当前问题 |
|---|---|---|---|
| `Persona` | Account 1:N；active/retired | my/other/edit profile | 主档与页面 bundle 同步 |
| `ProfileUpdateProposal` | proposed→confirmed/applying→applied/rejected/expired | edit/profile review sheet | 并发/响应丢失恢复 |
| `PersonaRelationship` / `RelationshipDirection` | follow/block/mutual 派生 | profile、blocked、stats | Direction 是 projection/value，不应独立写 |
| `SubjectFollow` | Persona→user/circle/homepage subject | object pages/profile | 跨对象关注唯一 owner |
| `GreetingRequest` | 非互关联系升级 | profile/chat | 归 M6 协同 |
| `ContactDiscoveryRecord` | 本地哈希→match→expire/delete | phone contacts | 原始手机号不得上传 |
| Visit/interaction views | footprint/share/comment/activity 私有投影 | inbox/footprint/comments | mine-only 与 retention |
| `CreatorRuntimeProfile`/FollowingSubject/UserLifeItem/UserWork | 创作者/关注/人生/作品投影 | profile bundle | 已裁决：Post/Persona 派生投影不拥有公开 API（`api_routes: []` + commercial gap_id），页面经 user_profile canonical query 读取，不再视为「有定义无实现」缺口 |

恢复后复验确认：`user.edit_profile` 与 `user.career_interest` 已切到 canonical `UpdateUserProfileCommand`，并补 `user.persona` 对象绑定；`make verify-app-page-horizontal-quality` 当前通过。旧 `ProfileEditUpdatePayload` 漂移不再作为当前 GATE_BLOCK。

2026-07-20 三路排查（App 页面 / 云侧契约 / 规格交集）补充的对象级结论：

- **对象登记完整**：user 域 `business_object_map.yaml` 覆盖 Persona、UserAccount/user_profile、PersonaRelationship（+RelationshipDirection owned_entity）、SubjectFollow、UserSettings、AccountSession、GreetingRequest、ProfileUpdateProposal 等聚合根；关系模型为「单向 follow 布尔 + block 布尔 + GreetingRequest 状态机承担待确认语义」，是有意设计而非缺口。
- **生命周期跨域缺口（GATE_BLOCK 级）**：① 拉黑读路径无服务端强制——feed 的 block 过滤依赖客户端传 `X-Blocked-User-Ids`（可绕过），`ListUserPosts` 无 viewer×author block 拦截；content-service `persona_follow_projection` 消费 PersonaBlocked 事件但只清 follow、不记录 blocked 对，且只服务推荐特征（2026-07-20 已按「投影补 blocked 记录 + ListUserPosts 服务端拦截」收口，见 M12-E D6）。② 无注销/封禁级联：无 DeleteAccount operation，UserSuspended 事件无发布者与跨域消费（独立里程碑，backlog R-UPROF-002）。
- **错误契约**：`persona_relationship/errors.yaml` 原仅 1 码（follow_blocked），应用层 `invalidRelationshipArgument` 硬编码中文；2026-07-20 已补 `invalid_pair` 码并回归 errors.yaml 单源。
- **他人评论查询裁决**：V5 冻结 IA 中他人主页 Tab 为 `[记录|互动]`（互动走 profile_interaction 按 subAccountId 参数化），不存在「TA 的评论」Tab；`ListCommentsByAuthor` 仅 me 范围是正确契约，`profile_comments_page` 是我的私有收发页，**无需**新增按任意 subAccountId 的评论查询 operation。
- **统计计数**：同步 increment + 每命令全量 COUNT reconcile，无事件驱动读模型，高关注量用户有规模风险（独立里程碑，backlog R-UPROF-003）。

### M12-C 页面预评级

2026-07-20 代码级复评（16 页全部有路由/surface 注册、状态覆盖普遍齐备；视觉仍未真机核验）：

| 页面 | 评级 | 决策 |
|---|---:|---|
| `profile_stats_page.dart` | P3～P4 | 保留精修（本域样板：分页/搜索/权限卡/21 处埋点齐备） |
| `my_profile_page.dart` / `other_profile_page.dart` | P3 | 适度精修：分享落地（曾 shareComingSoon 占位）、他人页补 dwell；壳层 4 文件约 1630 行拆分预警；他人页/交集目标 P5 |
| `my_intersection_inbox_page.dart` | P3～P4 | 精修 + SIT5 准出（交集核心承载，商用目标 P5；数据为真实云端事实非 mock） |
| `my_footprint_page.dart` | P3 | 精修：`profile_footprint_tab` 相对时间硬编码中文与独立页 l10n 双轨需收敛 |
| `edit_profile_page.dart` / `career_interest_page.dart` | P2～P3 | 适度精修：QR FutureBuilder 无 error 分支、两页零曝光/停留埋点（违反 R20） |
| `add_contact_page.dart`、`contact_search_result_page.dart`、`contact_confirm_page.dart` | P3 | 保留精修（能力位降级、journey 埋点已具备） |
| `my_qr_code_page.dart` / `scan_contact_qr_page.dart` / `phone_contacts_page.dart` | P3 | 精修：my_qr_code 零埋点 |
| `blocked_users_page.dart` | P3 | 保留精修（本域数据流最规范：对象级 typed Facet） |
| `persona_management_page.dart` | P2（矩阵唯一 T7 原型行） | **中度重构**：创建/编辑为 CupertinoAlertDialog 内嵌表单原型，改正式表单页（2026-07-20 已重构为 `SettingsInsetFormPageScaffold` 全屏表单，三层测试绿） |
| `profile_comments_page.dart` | — | 已随评论系统重做专项删除（2026-07-20，页面/provider/测试/路由同步清理；评论收发由互动 Tab profile_interaction 单轨承载），不再单独评级 |

死代码：`OtherProfilePageRouteExtra`（只消费无构造者）、`MediaViewerToolbar`（无实例化）应删除（2026-07-20 已删除）。旅程断点：评论区头像/昵称不跳作者主页（2026-07-20 已补：一级评论与二级回复头像均跳作者主页并带乐观首屏）、主页分享 3 处 `shareComingSoon` 占位（2026-07-20 已落地系统分享：昵称+简介+metadata link_templates 公网主页链接，含 journey 埋点，占位文案删除）。

### M12-D 双向初查

- `CreatorRuntimeProfile`、UserLifeItem、UserWork 是否是当前商用用户目标需专项裁决；若只在 metadata 有定义、无明确页面价值，应 deferred/删除而非强造页面。
- 私有 footprint/互动历史只允许 owner 访问；他人主页出现这些投影为 GATE_BLOCK。
- 关系四层（事实边、权限门、派生称谓、私有标签）必须分开；私有标签/派生称谓不得变成会话授权。
- 联系人添加的搜索、扫码、手机号匹配是多入口同一目标，页面重复与回流应合并检查。
- Edit/Career 当前使用 `ProfileCommandWriter.updateUserProfile(UpdateUserProfileCommand)`；后续必须保持与 ProfileUpdateProposal 的职责边界，不得恢复旧 DTO。
- 联系人搜索、确认页与打招呼收件箱的 P5 交集证据依赖 `R-IX02` 的 per-candidate 事实投影；在该投影完成前只展示服务端显式返回的 `summaryIntersections`，禁止使用 viewer 级聚合近似、关系态或推荐分数合成“共同关注/共同圈子”事实。
- 添加联系人五页与联系首页在真机浅色/深色、动态字体、紧凑/大屏和 VoiceOver 证据齐备前保持 P2～P3，不因横向静态门禁全绿直接上调 P4/P5。

### M12-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 页面覆盖广 | profile→关系动作→私有历史→持续关系无断点 | 裁决低价值对象；补删除/退休/隐私终态 | owner/other/blocked/private UAT |
| D2 | user 对象多、部分错误契约缺失；资料编辑 command/page binding 已收口 | Account/Persona/Relationship/Follow/Discovery/Projection 边界清晰 | 保持 `UpdateUserProfileCommand` 单轨；补 errors、拆超限 Facet、清手写 route（R-OBJ-006） | page-object gate + Postgres/Mongo/Redis + generated dispatch |
| D3 | 主页 IA 已重构 | 主页/交集=P5，其余核心≥P4 | 真机视觉、信息密度、统一入口/返回 | 双色/断点/iOS/无障碍 |
| D4 | bundle/page cursor 部分具备 | profile first usable、关系 command、历史分页/缓存预算 | 并发 proposal、offline action、图像加载 | 大关系集、弱网、缓存一致 |
| D5 | profile enter/dwell、关系动作较多 | 3 指标：有效资料完成率、打开到可行动 P95、交集到关系形成率 | profile/relationship/history 同 actor/trace | user metric+SLS+Behavior 对账 |
| D6 | local/UAT 丰富，App API 薄；gamma patrol 无 user/profile 旅程 | 关系、隐私、联系人、proposal、历史三层齐备且进设备矩阵 | 扩 API integration、删除/拉黑级联负例、gamma patrol 补主页旅程 | beta stores、gamma device、prod canary |

2026-07-20 收口记录（用户主页商用化专项）：
- 拉黑读路径服务端强制：content-service `persona_follow_projection` 补 blocked 对记录 + `ListUserPosts` viewer×author block 拦截，api_integration 负例覆盖。
- `persona_relationship/errors.yaml` 补 `invalid_pair` 码，删除 Go 侧硬编码中文文案。
- App 断链收口确认：`profile_interaction_tab` 已消费 `profileInteractionQueryFacetProvider`、`profileCommandWriterProvider` 已被 edit_profile/career_interest 消费、`accountSession` 子 Facet 已被登录/设置消费；`UserProfileRepository`（33 方法）全量拆分保留在 R-OBJ-006 专项轮。
- 环境证据缺口：SIT2（followers/following handler 消费 query + row relationshipCapability、circle ListUserCircles 消费 query）pending_evidence；prod-hosted gray edge 0/2 healthy（R-IX05）是「真机不可用」观感的直接根因。

### M12-F 标杆候选

微信个人页/联系人、Instagram Profile、LinkedIn Profile/Connections、iOS Contacts；内容社区侧补小红书个人主页（沉浸头部 + 关注/粉丝/获赞统计 + 笔记/收藏/赞过 Tab + 双列瀑布流 + 吸顶 TabBar，检索日期 2026-07-20）与即刻个人主页（置顶动态、个人相册、精选日记、最近访客、头像趣味交互）。借鉴隐私分层、资料编辑、关系入口、联系人权限、沉浸头部信息架构与分享主页标配能力；不复制公开社交图、强制通讯录上传、即刻会员体系与公开「赞过」Tab（隐私取向不同）。趣我圈差异化锚点是交集卡（「我与TA的交集」「TA打动的人」四层事实模型 + 27 kind 注册表 + 云侧结论句单源），为标杆产品均无的可证可行动能力。

### M12-G 并行会话启动提示词

> 完成 M12 我的主页与关系全面分析。读取本文 §0～§9、§21、user object map、profile/relationship specs、R-OBJ-006。覆盖上述 15 个页面与 proposal sheet，执行完整强制分析，重点核对关系四层、mine-only 历史和对象生命周期。Out of Scope：登录归 M1、评论对象归 M16、标签 taxonomy 归 M17。输出 10 项交付物；对无用户价值的 metadata 对象允许提出 deferred/删除，不机械造页面。

## 22. M13 详细规格

### M13-A 版块定位

- **用户目标**：收到来自评论、点赞、关注、打招呼、圈子治理和助手订阅的可信通知，在消息首页查看、已读、跳回源对象；外部 push 不可用时诚实降级站内信。
- **树绑定**：message-social、assistant proactive delivery；协同所有产生通知的源对象 Journey。
- **交集定位**：场景增强。通知可说明因何交集触发，但不得暴露无权查看的关系证据。

### M13-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `Notification` | source event→created→delivered/acked/read；owner UserAccount | Chat 首页“通知”维度 | 七源站内信已部分闭环 |
| `NotificationDeliveryJob` | pending→attempting→delivered/retry/dead/deferred | worker，无用户页 | `errors.yaml` 缺失；push deferred |
| `ExternalInteraction`/Attempt/DLQ | provider 请求与尝试/死信 | integration-service | APNs/FCM 未实现 |
| `DeviceRegistration` | token register→refresh/revoke | 后台/账号安全 | push token 未闭环 |
| source objects | Comment/Reaction/Post/Follow/Greeting/Circle membership/Assistant subscription | 跳转目标 | sourceId/target/provenance 要 typed |

### M13-C 页面预评级

| 页面/场景 | 预评级 | 决策 |
|---|---:|---|
| `chat_page.dart` 通知维度 | P3（视觉未核验） | 保留站内信复用；精修过滤、已读、失效目标 |
| 系统 push tap/deep link | P0（外送 deferred） | 不做假入口；凭据/对象/安全到位后新增平台边界 |
| 通知设置（若产品要求） | 待规格 | 先定义 per-channel/per-source setting 对象；不得先加静态开关 |

### M13-D 双向初查

- 无 `lib/ui/notification` 不自动判缺口：用户决策已选择复用 chat 通知维度；只要 Notification 全状态和回流完整即可。
- push 外送明确 deferred；不得显示“已开启推送”或用本地成功顶替 provider receipt。
- DeliveryJob 是后台对象，不需要页面；但 dead/deferred 必须进入运营告警，用户端显示站内信可用边界。
- 源对象删除/权限变化后，通知点击必须进入解释性失效态而不是 404/raw error。

### M13-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 七源→站内信→消息页已部分收口；push deferred | source event→inbox→read→target/失效完整 | 补所有源、幂等、权限变化；push 保持诚实降级 | 每源 UAT |
| D2 | Notification/Job 对象与 source refs 存在 | source owner、notification、delivery、external attempt 分层 | 补 Job errors、device token 决策 | Mongo/Redis stream/outbox/integration |
| D3 | 通知复用 chat IA | inbox≥P4，信息简洁、来源可信、无敏感预览 | 真机视觉、长文/多源、动态字体 | 双色/无障碍/隐私 |
| D4 | worker 有重试基础 | inbox first usable、event→visible P95、批量已读、积压容量 | DLQ/backoff/TTL、离线同步 | 大积压、重复事件、弱网 |
| D5 | notification journey 已有曝光/点击 | 3 指标：有效投递率、事件到站内可见 P95、通知到目标有效行动率 | source/notification/target 同 trace | stream/Mongo/SLS 对账 |
| D6 | service 外层证据有，domain/application 就地测试零 | 七源、幂等、权限、read、失效、deferred push 三层齐备 | 补内层状态机和 App Remote/UAT | beta Redis/Mongo、gamma device |

### M13-F 标杆候选

微信服务通知/消息中心、GitHub Notifications、Reddit Inbox、iOS Notification Center。借鉴来源、聚合、已读和深链失效，不复制无关推送轰炸。

### M13-G 并行会话启动提示词

> 完成 M13 通知与推送全面分析。读取本文 §0～§9、§22、notification/integration/user object maps、R-OBJ-003 当前部分收口状态。执行完整强制分析，覆盖七源事件、chat 通知维度、read/unread/target、DeliveryJob 和 push deferred。Out of Scope：未取得 APNs/FCM 凭据前不实现/伪验收 push；源对象业务规则归各 M 版块。输出 10 项交付物与逐源三层矩阵。

## 23. M14 详细规格

### M14-A 版块定位

- **用户目标**：把 Post/Homepage/Circle/Profile 以卡片、海报、链接或口令分享到站外，接收者点击后回到对应对象；未安装时完成安装并还原目标。
- **树绑定**：Journey `external-acquisition-and-deeplink`；Scenario `outbound-object-share-distribution`、`external-inbound-deeplink-return`、`public-web-seo-install-conversion`。
- **交集定位**：场景增强。可在获授权时展示“谁/什么把你们连接起来”，但分享卡默认不能泄露私有交集。

### M14-B 业务对象底料

| 对象/机制 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `OutboundShareFact` | object/share intent→channel dispatch→success/fail→attribution | share sheet + content service | 分享事实与 UI 结果/第三方 callback |
| Share token/attribution | issue→resolve→expire/revoke | deep link resolver | 需以 metadata route/template 为真相 |
| `VisitRecord` | inbound target visit 聚合 | ops/product-ops | 不得替代行为/推荐事实 |
| public object projection | Post/Homepage/Circle/Profile 的公开最小字段 | Web/SEO page | 三 Scenario 仍 draft |
| install handoff | click→store/web→first launch→restore target | Web banner/native link | 安装后还原是关键断点 |

### M14-C 页面/场景预评级

| 承载 | 预评级 | 决策 |
|---|---:|---|
| 统一分享 panel/sheet（挂各对象页） | P2（视觉未核验） | 适度重构：真实 channel、状态、隐私、归因 |
| `web_app_install_banner.dart` | P2（视觉未核验） | 适度重构：平台能力、可信下载、目标保留 |
| `web_main_app_shell.dart` 公开对象/安装入口 | P2（视觉未核验） | 适度重构：SEO、对象失效、安装回流 |
| DeepLinkResolver（非页面） | N/A | 保留 runtime 单轨；补全 target lifecycle |

### M14-D 双向初查

- OutboundShareFact 无独立页合理；每个分享入口必须绑定正式 objectId/type 和公开 projection。
- 若分享卡由 UI 临时拼标题/图/URL、或硬编码业务 path，GATE_BLOCK。
- public web 对象页未形成独立矩阵行不代表已实现；三 Scenario 为 draft，必须如实评级。
- 目标对象删除、私密、封禁或分享 token 过期时，必须安全失败并提供 App 首页/公开替代去向。

### M14-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | share journey 有 UAT，三 Scenario 仍 draft | 分享→站外→深链/安装→原对象→行动完整 | 冻结 MVP 渠道和 deferred deep link；补失效/权限 | 已装/未装/登录/对象删除 UAT |
| D2 | OutboundShareFact/route surface 有基础 | token、public projection、Visit/Attribution 各自 owner | metadata-first link template/expiry/command | resolve API + storage/TTL |
| D3 | sheet/banner/web shell 已有承载 | 分享面板和公开页≥P4 | 真机/浏览器/预览卡视觉、无障碍 | iOS/Android/Web/各渠道 |
| D4 | 无完整 SLO 证据 | 生成卡/解析 link/首开还原 P95，缓存/防滥用 | token TTL、CDN、fallback、rate limit | crawler/并发/弱网 |
| D5 | share observability 部分存在 | 3 指标：有效分享率、点击到目标可用 P95、分享带来的有效行动率 | channel/token/object/referral 同 trace | client→web→service→SLS 对账 |
| D6 | forward share UAT 有 | object/channel/install/deeplink/permission 三层齐备 | 补 Remote、平台 links、SEO crawler、prod domain | beta resolver、gamma device、prod canary |

### M14-F 标杆候选

小红书分享卡/口令、微信 Universal Link、Airbnb listing share、Apple Universal Links/Smart App Banner。借鉴对象预览、安装还原和安全 fallback，不复制平台品牌资产。

### M14-G 并行会话启动提示词

> 完成 M14 分享增长与深链全面分析。读取本文 §0～§9、§23、external-acquisition Journey、OutboundShareFact/VisitRecord/page route metadata、R-LEGAL-001 公开条款边界。执行完整强制分析，覆盖分享 sheet、Web banner/shell、resolver、已装/未装/对象失效。Out of Scope：支付/票务归 R-COMMERCE-001；平台发布基础设施归 Ops。输出 10 项交付物、当前可验证版本标杆与多平台 UAT。

## 24. M15 详细规格

### M15-A 版块定位

- **用户目标**：管理资料/账号入口、权限、外观、拉黑与助手等设置，查看版本、协议、隐私、权限说明和第三方 SDK 清单，并安全退出/切换账号。
- **树绑定**：identity Journey 的 consent/legal 边界、runtime client foundation；legal-static 发布能力。
- **交集定位**：无需承载。设置和协议页面不得机械增加交集。

### M15-B 业务对象底料

| 对象/机制 | 生命周期/关系 | 页面 | 当前问题 |
|---|---|---|---|
| `UserSettings` | read→CAS update→conflict/retry | settings/notifications/privacy/calls/dark mode/blocked keywords | 已统一到 typed QueryReader/CommandWriter 与对象 Slice |
| AccountSession/CredentialBinding | switch/logout/revoke | settings account security + account actions | 退出需清 actor queues 与本地密钥 |
| Permission state | notDetermined→granted/denied/restricted→settings return | permissions page / platform coordinator | 当前 permissions page 标注“预留”，需裁决是否空壳 |
| Consent/Data Rights | consent version→active→withdraw/export/delete request | login/about/未来数据权利承载 | 查询、撤回、导出、注销状态机和结果页未完整冻结 |
| Legal document release | draft→review→publish→rollback/expire | about→legal document WebView；legal-static | R-LEGAL-001 |
| Package/App version | build artifact fact | about page | 不手写版本 |

恢复后复验确认：`settings.home/dark_mode/notifications/privacy/calls/blocked_keywords` 已绑定 `user.user_settings` 及对应 View，账号安全页绑定 UserAccount/CredentialBinding/AccountSession；此前 UserSettings page-object 所有权漂移已收口。

### M15-C 页面/模板预评级

| 页面 | 预评级 | 决策 |
|---|---:|---|
| `settings_page.dart` | P3（视觉未核验） | 精修 IA、账号动作和真实入口 |
| `settings_permissions_page.dart` | P1（视觉未核验） | 若仍为只读预留则完全重构或删除；不得保留无能力空壳 |
| `settings_dark_mode_page.dart` | P3（视觉未核验） | 保留模板，精修 scope/CAS |
| `settings_notifications_page.dart` | P3（视觉未核验） | 保留并精修乐观更新回滚、免打扰与跨端收敛 |
| `settings_privacy_page.dart` | P3（视觉未核验） | 保留并精修可见范围、陌生人私信和助手授权 |
| `settings_calls_page.dart` | P3（视觉未核验） | 保留并精修铃声、振动、群通话与平台能力降级 |
| `settings_account_security_page.dart` | P3（视觉未核验） | 保留并补设备/会话与最后凭证保护的真机验收 |
| `blocked_keywords_page.dart` | P3（视觉未核验） | 保留为 PrivacySettings 子页，核验上限、并发与恢复 |
| `my_reports_page.dart` | P2（视觉未核验） | 适度精修举报状态、分页、目标失效和结果解释 |
| `settings_about_page.dart` | P3（视觉未核验） | 精修 legal release、版本、失败恢复 |
| `user/pages/legal_document_page.dart` | P2（视觉未核验） | 适度重构：可信域、缓存/离线、发布版本和失败 |
| `components/settings_form/settings_inset_form_page.dart` | 模板本体 | 保留；所有适用设置页必须复用 |

### M15-D 双向初查

- permissions page 若只展示“预留”而没有真实能力/用户价值，符合提示词的“视觉存在但业务无价值”GATE_BLOCK 候选，应重构或删减。
- Legal 文档不是普通内容 Post；只能读取 legal-static 已审签制品，WebView 禁止脚本/任意跳转。
- dark mode 是 UserSettings，不能仅改本地 provider 而不处理多端 scope/版本冲突。
- setting row 只是导航，不得承载临时业务真相；拉黑/assistant/profile 各由源版块对象拥有。
- 通知、隐私、通话、凭证和关键词设置已有正式页面；剩余核心缺口是账号注销、数据导出、撤回同意等数据主体权利的对象/页面/终态。
- legal-static 主体、地址、客服电话、ICP 与法务审签状态需以真实 manifest 复核；About/WebView 可打开不等于 R-LEGAL-001 已通过。

### M15-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 10 个设置页覆盖主要对象能力，权限预留页与数据主体权利仍有缺口 | 每个 row 有真实目标/状态；协议可达；退出/注销/导出/撤回完整 | 裁决权限页；闭 R-LEGAL-001；补数据主体权利和 logout/switch | settings journey + legal release UAT |
| D2 | UserSettings 与账号安全 page-object 已收口；legal 为静态制品 | settings CAS、credential/session、platform permission、legal release 四边界清楚 | 保持对象绑定；补 Consent/Data Rights；禁止第二 legal URL 表 | page-object gate + user-service + legal artifact contract |
| D3 | Inset 模板全覆盖 | 核心设置≥P4，静态页简洁可访问 | 真机视觉、动态字体、长文、外链 | 双色/断点/iOS/VoiceOver |
| D4 | 静态/轻量 | settings read/write、legal first paint、缓存/离线预算 | ETag/签名、WebView timeout、权限返回重检 | 弱网/旧文档/冲突 |
| D5 | route page access；行为埋点可按隐私减量 | 3 指标：有效设置完成率、打开到状态可用 P95、失败恢复率 | operation_result + legal load outcome | 不采集协议正文/设置敏感值 |
| D6 | local/API 覆盖随对象页扩展，真机 UAT 仍薄 | settings CAS、账号安全、权限 profile、legal artifact、数据权利三层齐备 | 补 10 页行为 UAT；无远端页明确 `—` | alpha capability、beta settings、gamma device |

### M15-F 标杆候选

iOS Settings、微信设置/关于、Signal Privacy、Apple Legal/Privacy pages。借鉴分组、系统权限跳转、账号危险动作与法律版本，不复制无关功能堆叠。

### M15-G 并行会话启动提示词

> 完成 M15 设置与合规全面分析。读本文 §0～§9、§24、UserSettings/Session metadata、legal-static release 和 R-LEGAL-001。执行完整强制分析，重点判断 permissions page 是否空壳并作删除/重构决策；设置页无需交集。Out of Scope：各目标业务页内部功能归对应 M 版块；不在 App 内复制法律正文。输出 10 项交付物、真实 legal 制品与设备权限 UAT。

## 25. M16 详细规格

### M16-A 版块定位

- **用户目标**：在图片、视频、微趣和文章等 Post 场景中按热门/最新查看二层评论，
  发布评论或回复，执行赞/踩、置顶、复制、举报和删除（按服务端权限），并从互动记录或
  通知准确回到原评论。
- **树绑定**：`content-discovery-to-consumption / content-comment-interaction` →
  `discovery-content / publish-comment-reaction / comment-thread` V4；协同
  `content-service`、`notification-service`、user 关系事实投影和 App Runtime。
- **交集定位**：场景增强。只展示服务端可证实的 `viewerRelation` 和 `authorLiked`
  事实；不以关系改变 canonical 热评顺序，不暴露关系证据来源或私有关系图。
- **范围裁决**：评论不支持编辑，避免修改历史讨论语义；仅支持作者 CAS 软删。推荐负反馈、
  拉黑与屏蔽关键词分别归 FeedbackFact、PersonaRelationship、UserSettings，不在 Comment
  聚合或评论页面维护第二套状态。

### M16-B 业务对象全景

| 对象/投影 | 定义与边界 | 生命周期/关系 | 用户承载 | 唯一真相源 |
|---|---|---|---|---|
| `Comment` aggregate root | 单条一级评论或回复；只引用 Post/MediaAsset/persona，不内嵌这些聚合 | `active→deleted`；`active→hidden→active`；`active/hidden→tombstoned` | 统一 Comment surface、个人互动 | `content/comment` metadata + Mongo `comments` |
| `ContentReaction` aggregate root | persona × comment 的 `like/dislike/none` 互斥关系 | set/change/clear，独立事务与 outbox | 评论行赞踩 | `content/content_reaction` |
| `Report` aggregate root | `targetType=comment` 的举报与处置，不在 Comment 内复制 Case | created→resolved/dismissed；`delete_content` 处置驱动 HideComment | 举报原因面、我的举报、Ops | `content/report` |
| `Post` aggregate root | Comment 的宿主与 owner 权威；Comment 不加载完整 Post 聚合执行 query | PostDeleted 事实触发全量评论 tombstone | 各内容 viewer | `content/post` |
| `MediaAsset` aggregate root | 评论附件的已验证媒体引用；Comment 只保存 media id | ready/unavailable 等由媒体域治理 | 输入附件、评论附件 | `content/media_asset` |
| `CommentPageSlice` read model | 聚合 Comment、reaction、reply summary、capability、attachment、关系事实 | opaque cursor；`hot/latest` 服务端 keyset | 所有评论宿主 | CommentQueryFacade |
| `CommentCount`/`hotScore` projection | 可由 Comment/Reaction 事实重建，不是新聚合 | outbox relay 幂等收敛 | 标题计数、热评顺序 | Mongo projection + checkpoint |
| `persona_follow_projection` | user 域关系事实的 content 只读副本 | 单向关注/互关/拉黑投影 | `following/friend` badge 与服务端过滤 | user 事件 → content projection |
| `AppMessage` projection | CommentCreated/PinChanged 的通知投影 | unread/read；目标失效时结构化失败 | 消息中心与评论深链 | notification-service |
| `comment_author_rate_limit_locks` | Store 内部事务串行化设施，不是公开业务对象 | 短 TTL；与 Comment 创建同事务 | 无页面 | CommentAggregateStore |

### M16-C 对象关系与聚合边界

```text
Post 1 ── N Comment
Comment(root) 1 ── N Comment(reply，最多两级)
Comment N ── N MediaAsset（typed reference）
persona 1 ── N ContentReaction ── 1 Comment
persona 1 ── N Report ── 1 Comment
Comment lifecycle facts ──> count/hotScore/AppMessage projections
user relationship facts ──> persona_follow_projection ──> CommentPageSlice
```

- Comment command 只在 Comment aggregate + receipt + rate-limit lock + outbox 的 Mongo
  transaction 内提交；Post、Report、ContentReaction 和 MediaAsset 均通过对象专属
  Facet/Reader/Event 协作，禁止跨聚合共事务。
- `bottom sheet`、个人互动和通知只是同一 Comment 对象的不同 surface，不拥有 Comment
  副本、排序、权限或计数。
- `hotScore=(likeCount-dislikeCount)+2*replyCount` 是事件触发、权威数据重算的可修复投影；
  禁止 Redis 排行、端侧重排或 `$inc` 重放漂移。

### M16-D 核心生命周期

```text
CreateComment
  -> active
  -> 作者 DeleteComment(expectedVersion) -> deleted（终态）
  -> operator HideComment(expectedVersion) -> hidden
       -> operator RestoreComment(expectedVersion) -> active
  -> PostDeleted projector -> tombstoned（终态）
```

- `deleted/tombstoned` 不可恢复；`hidden` 只在作者私有互动投影显示状态，公开列表不可见。
- 回复必须归一到一级 `parentCommentId`；删除、隐藏、恢复回复都触发父评论 replyCount 与
  hotScore 重算。
- Report 处置是跨对象命令触发，不直接改 Comment collection；重复事件与已满足状态幂等。

### M16-E 对象—功能—页面完整性矩阵

| 用户任务 | 对象/命令/查询 | 统一 Comment surface | 个人互动 Tab | 通知中心 | 我的举报/Ops | 当前结论 |
|---|---|---:|---:|---:|---:|---|
| 浏览/分页/切换热门最新 | CommentPageSlice/ListComments | ✓ | — | — | — | 本地已闭；真实 Mongo explain/设备待复验 |
| 展开二级回复/定位 | ReplyPageSlice/ListCommentReplies | ✓ | 跳回宿主 | 跳回宿主 | — | typed 链路已闭 |
| 评论/回复/@/图片 | CreateComment + MediaAsset | ✓ | — | — | — | typed 输入已闭；真实媒体 UAT 待复验 |
| 赞/踩/取消 | ContentReaction | ✓ | 回源执行 | — | — | 服务端权威回读 |
| 置顶/取消置顶 | PinComment/UnpinComment | owner capability | — | 置顶通知 | — | CAS 已闭 |
| 复制/举报/删除 | Report/DeleteComment | capability action sheet | 回源执行 | — | 举报进度/处置 | 动作与登录续接已补 |
| IP属地/作者赞过/关系 | CommentPageSlice display projection | ✓ | ✓ | — | — | 服务投影和 UI 已补；窄屏视觉待证 |
| 治理隐藏/恢复 | HideComment/RestoreComment | 结构化失效 | 状态回流 | 结果回流 | operator | 本地链路已补；环境回放待证 |
| Post 删除级联 | PostDeleted→tombstone | 结构化失效 | 结构化失效 | 结构化失效 | 审计 | projector 已补；真实 Mongo 回放待证 |

### M16-F 页面成熟度与处置决策

| 页面/场景 | 预评级 | 决策 |
|---|---:|---|
| `lib/ui/content/comments/**` 统一评论 surface | P2→目标 P4 | 保留并精修；所有宿主复用同一 provider/facet，补语义、窄屏、动态字体与真实视觉 |
| `comment_input_overlay.dart` | P3→目标 P4 | 保留；typed @ 候选、emoji、图片、草稿和登录续接，不新增语音/固定账号假入口 |
| `lib/ui/user/widgets/profile_interaction_tab.dart` | P3→目标 P4 | 保留；只消费 author/post-owner typed Slice，动作回源 Comment Facet |
| `lib/ui/settings/pages/my_reports_page.dart` | P3→目标 P4 | 保留；展示 Report 生命周期与目标失效，不泄露 reviewer 内部信息 |
| notification → `MediaViewerCommentContext` | P3→目标 P4 | 保留；评论/回复/@/置顶统一深链、定位和失效态 |
| `profile_comments_page.dart` | 已删除 | 不恢复；与个人互动 Tab 重复且会形成第二 IA/状态源 |
| 独立 Comment detail page | 不新增 | 二层讨论依附 Post 上下文，统一 surface 足以承载；通知只深链回宿主 |
| Portal moderation（非 App） | 协同专项 | 只消费 Report/Comment 治理对象，不直写 comments |

P4 准入必须同时具备真实功能、完整异常/恢复、无障碍/多断点、观测和真机证据；当前尚无
V4 Gamma 截图与设备矩阵，因此不得把静态代码评为 P4。

### M16-G 行业对标与可执行原则

| 标杆 | 可借鉴 | 本产品落地 | 明确不复制 |
|---|---|---|---|
| 小红书 | 热门/最新、作者赞过、IP属地、举报进度 | 两档服务端排序、authorLiked、属地快照、我的举报 | 黑盒推荐排序、无事实社交标签 |
| 抖音 | 轻量二层线程、强输入反馈、通知回流 | 统一 bottom surface、草稿保留、深链定位 | 无限滚动本地拼序、入口堆叠 |
| Bilibili | UP 主互动标记、置顶、好友关系提示 | authorLiked、CAS pin、viewerRelation | 多层嵌套与客户端权限推断 |
| Reddit/YouTube | 稳定线程 identity、moderation、目标失效 | typed identity、四态治理、结构化失效 | 无限层级、未经解释的 shadow-ban |

可执行原则：默认热评但只提供「热门/最新」；所有 badge 均来自事实；所有 destructive
动作由 capability 控制并二次确认；错误保留内容/草稿并提供恢复；通知必须回到原对象而非
泛化详情页。

### M16-H 交集差异化矩阵

| 差异化点 | 权威事实 | 展示/动作 | 冷启动/无事实 | 指标与防滥用 |
|---|---|---|---|---|
| 我关注的人 | viewer→author 单向 follow | 轻量「已关注」badge，可进入作者主页 | 不显示 | badge CTR、误认反馈；不改变排序 |
| 互相关注 | 双向 follow | 「好友」badge，增强回复信任 | 不显示 | 好友评论互动率；不暴露共同关系链 |
| 作者认可 | Post owner 对 Comment 的 like | 「作者赞过」badge | 不显示 | 作者赞后有效对话率；只读 reaction 事实 |
| 已拉黑/被拉黑 | block projection | 服务端过滤评论、回复摘要和计数 | projection 不可用 fail closed | 过滤命中率与投影滞后；端侧不得自行拼装 |

`same_circle`、相似兴趣和模型推断不进入 V4 badge；未来若引入，必须先有可验证对象事实、
隐私边界和独立验收，不能复用 `viewerRelation` 偷渡。

### M16-I 六维度与运营指标

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 功能 | V4 主要代码已落，环境证据不完整 | browse→create/reply→reaction/report→notification→失效完整 | 逐 GWT 关闭 partial/pending | author/viewer/reporter/operator UAT |
| D2 架构 | Comment/Reaction/Report 独立对象 | metadata→generated client→Facet→Store/Event 单轨 | 扫 legacy/旧三档/动态 Map/第二计数 | ContractGraph + DDD/CQRS gate |
| D3 UX | 静态约 P2/P3 | 统一评论 surface 达 P4 | 320px、200%字体、键盘、light/dark、语义与焦点测试 | golden/像素 + Gamma iOS/Android/Web profile |
| D4 性能 | keyset 与事务频控已实现 | list P95<800ms；reply/command P95<500ms；无 N+1/COLLSCAN | 两档 explain、热帖容量、并发频控与投影滞后 | 真实 Mongo 10k/100k 数据集 |
| D5 运营观测 | lookup/部分服务指标和告警已补 | 评论创建成功率、提交到可见 P95、有效互动率、举报创建率、72h结案率、hotScore/outbox/属地数据新鲜度 | dashboard/alert/runbook 同 operation/trace | Prometheus/SLS readback 与告警演练 |
| D6 测试环境 | local_contract 已覆盖主链 | local/API/UAT 对称，alpha/beta/gamma/prod 同 commit/Graph hash | Remote API、通知流、设备、AOT/SBOM、prod canary | release gate 全绿 |

核心业务指标：评论入口→打开率、打开→提交完成率、提交到可见 P50/P95、评论后 24h 有效
回复率、赞踩转化、举报有效创建率、72h 结案率、通知点击回原评论成功率、结构化恢复成功率。
护栏指标：429 命中率、版本冲突率、outbox lag/DLQ、hotScore 收敛滞后、投影过滤失败、
IP lookup error/not_found/data age、App 评论 surface crash/ANR/掉帧。

### M16-J 任务清单与验收标准

1. **规格与契约**：V4 spec/design/acceptance、Journey、CR、M16、metadata 同源；旧
   `recommended/most_liked`、CommentDto/PostService 评论旁路和虚假 recorded 路径为零。
2. **服务主线**：四态 aggregate、事务频控、hotScore、Report→Hide、PostDeleted→
   tombstone、关系/作者点赞批量投影、通知去重和 ip2region 双栈生产装配全部有 local
   contract；真实 Mongo/API 验证 CAS、keyset explain、并发、重放和失效。
3. **App 主线**：所有宿主只装配 `RemoteContentCommentFacet`；排序、typed @、附件、
   草稿、复制/举报/删除、登录 continuation、badge 和深链均有 Widget contract；错误消费
   RuntimeFailure，不切 Mock、不乐观构造残缺 Comment。
4. **体验准出**：44pt 触控、button/selected 语义、320px/200% 字体无裁切、键盘返回恢复、
   light/dark 和弱网保留数据/草稿通过 golden/语义/Gamma 设备验证，成熟度达到 P4。
5. **运营与发布**：指标、告警、dashboard、runbook、45 天 IP 数据门、canary
   `1%→50%→100%` 与回滚阈值可演练；alpha fixture 与 prod kernel/AOT/SBOM 物理隔离。
6. **准出定义**：`local_contract`、`api_integration`、`user_acceptance` 和触发范围 gate
   全绿，四环境报告绑定同一 commit 与 ContractGraph hash；否则 Story 维持 `GATE_BLOCK`。

### M16-K 专项执行提示

> 完成 M16 评论与互动 V4 商用收口。读取本文 §0～§9、§25、comment-thread V4、
> Comment/ContentReaction/Report metadata 与已解决 R-CMT01～03 历史。按对象生命周期、
> 页面主任务和三层证据执行，不以代码目录切分。不得恢复 legacy DTO/Map、旧三档排序、
> count-delta、profile_comments 独立页或生产 deterministic IP resolver。Out of Scope：
> Post 消费页整体归 M3、通知通道基础设施归 M13、Portal moderation 平台归 Ops。

## 26. M17 详细规格

### M17-A 版块定位

- **用户目标**：首次进入时可选择或跳过兴趣先验，之后用受治理的兴趣、职业、地点/对象分类描述自己和内容，获得可解释搜索/推荐/交集；反馈错误标签但不在客户端创造 taxonomy。
- **树绑定**：persona-follow-graph、interest onboarding prior、search/recommendation/tag governance；协同所有带 `tagRefs` 的对象。
- **交集定位**：核心基础。Tag 是交集证据的词汇表，不是“交集事实”本身。

### M17-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `TagTaxonomyRelease` | stage→validate→activate→retire/rollback | Ops/Data，无普通用户页 | tag-service local_contract 目录缺；发布环境证据 |
| `TagNodeView` | release 投影；parent/ancestor/lifecycle | career_interest/edit_profile/create/search filters | 只读 projection |
| `ObjectTagIndexView` | object→tagRefs 投影 | search/recommendation | stale/tombstone 与源对象同步 |
| `TagFeedback` | actor→report action append fact | 内嵌纠错/反馈 | 需要用户入口是否商用必需 |
| User/Post/Circle/Homepage tag refs | 源对象引用 taxonomy | 多页面 | tagRef 只引用 active release 节点 |

### M17-C 页面/场景预评级

| 承载 | 预评级 | 决策 |
|---|---:|---|
| `user/pages/career_interest_page.dart` | P3（视觉未核验） | 保留嵌入式 tag 选择，精修搜索/层级/上限 |
| `user/pages/edit_profile_page.dart` 标签区 | P3（视觉未核验） | 保留；与职业/兴趣页同一状态 |
| `content/entry/pages/create_page.dart` tag refs | P2（视觉未核验） | 适度重构：建议/选择/验证与发布 |
| Search/Circle/Homepage 的 tag 过滤/展示 | P2～P3（视觉未核验） | 统一 label/lifecycle，不复制词典 |
| 独立“标签管理页” | 当前无 | **不自动判缺口**；先证明嵌入承载能完成用户目标 |
| 首次兴趣先验选择/跳过 | P0 | 新增或嵌入 welcome/post-login；先修 Story scope 自相矛盾 |

### M17-D 双向初查

- TagTaxonomyRelease 是运营/数据对象，无用户 App 页面合理；需要 Portal/CLI 发布与审计，不应为它造 App 页面。
- TagNodeView 通过资料编辑/创作/筛选嵌入承载合理；如果用户无法查看/修改自身兴趣或处理失效 tagRef，才是 GATE_BLOCK。
- ObjectTagIndexView 是 projection，无写页面；UI 直接提交 label 而非 tagRef 或维护本地标签表为 GATE_BLOCK。
- TagFeedback 当前是否有真实入口需核验；若 metadata 声明商用 command 但无任何消费，应裁决 deferred/删除或补最小纠错入口。
- `user.career_interest`/`user.edit_profile` 已改用 `UpdateUserProfileCommand` 且 page-object gate 通过；后续不得恢复 `ProfileEditUpdatePayload` legacy 名称。
- `interest-onboarding-prior` 功能说明/GWT 要求用户“选择或跳过并写入先验”，但 out-of-scope 又声明本轮不实现 App 页面或画像写入；这是规格自相矛盾，当前无首次兴趣承载不能被职业兴趣编辑页替代。

### M17-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 资料/创作有 tag 选择；release/feedback 用户闭环不明 | 用户能表达/修改兴趣，失效标签可迁移，错误可反馈 | 核对 onboarding、TagFeedback、retired node UX | 新用户/编辑/发布/失效 UAT |
| D2 | 4 对象图清晰；tag 有域级平铺结构，两个消费页的 command binding 已修复 | release→node/index projection→source refs→feedback 单轨 | 保持 canonical command；收敛目录/Facet；禁止 label 写入 | page-object gate + Mongo release/index + source validation |
| D3 | 无独立页，嵌入多处 | 适用选择器≥P4，交集解释标签=P5 增强 | 统一 tag picker/chip、层级、无结果 | 双色/断点/动态字体 |
| D4 | taxonomy 读多写少 | release activate/index rebuild、picker search P95、缓存 TTL | 增量索引、active release cache、回滚 | 大 taxonomy、切换 release |
| D5 | TagFeedback fact 存在 | 3 指标：有效兴趣完成率、打开到候选可用 P95、标签驱动有效行动率 | release/tagRef/object/action 同 trace | tag-service/recommendation/SLS 对账 |
| D6 | App tag local 有；service local 目录缺 | release/reader/index/feedback/失效 refs 三层齐备 | 建 tag-service local/API、嵌入页面 UAT | alpha bundle、beta Mongo、gamma journey |

### M17-F 标杆候选

Pinterest Interest Picker、LinkedIn Skills、Spotify Taste/Profile、Apple Photos taxonomy（只借鉴层级与搜索）。不复制不透明画像或让系统推断直接成为用户自述事实。

### M17-G 并行会话启动提示词

> 完成 M17 标签与兴趣画像全面分析。读取本文 §0～§9、§26、tag business object map、domain taxonomy、使用 tagRefs 的 user/content/social/entity metadata。执行完整强制分析，重点裁决“无独立标签页”是否合理、TagFeedback 是否有价值、release/失效迁移。交集必须区分标签词汇与真实共同关系。Out of Scope：推荐模型归推荐轨、数据 taxonomy 内容生产归 Data。输出 10 项交付物和跨页面统一 picker 方案。

## 27. M18 详细规格

### M18-A 版块定位

- **用户目标**：在创作、搜索、资料和交集场景选择/理解地点，获得可靠 POI 结果；在隐私许可下使用模糊位置增强发现，不把实时精确位置泄露给无权主体。
- **树绑定**：创作 location、cross-domain search 的地点结果、intersection companionship draft；ExternalIntegration supporting context。
- **交集定位**：场景增强。位置只能形成经授权、模糊化、可撤销的证据，不能推断“附近同趣”事实。

### M18-B 业务对象底料

| 对象 | 生命周期/关系 | 承载 | 当前问题 |
|---|---|---|---|
| `Location` | external reference；query/resolve→select→expire/refresh | publish location、search landing、profile region | 无 authoritative store 合理；provider/freshness 要显式 |
| `ExternalInteraction` | submit→pending/processing→completed/failed/expired→recover | integration-service | 统一承载第三方请求，不只 location |
| `ExternalInteractionAttemptFact` | provider attempt append fact | 无用户页 | latency/error/recovery 脱敏 |
| `ExternalInteractionDeadLetterFact` | final failure→recover/closed | Ops | 需告警/人工恢复 |
| Post.publishLocation / Homepage.location | 源对象拥有的 value/reference | M4/M9 | 精确度、来源与删除策略 |
| Position evidence | viewer/object 的模糊位置交集投影 | M10 | 附近/companion 仍 deferred |

### M18-C 页面/场景预评级

| 页面/场景 | 预评级 | 决策 |
|---|---:|---|
| `content/entry/pages/publish_location_selector_page.dart` | P2（视觉未核验） | 适度重构；迁出 UI service/model（R-CR04） |
| `search/pages/location_place_landing_page.dart` | P2（视觉未核验） | 适度重构；临时地点与 Homepage 提升边界 |
| `user/pages/edit_profile_page.dart` 地区选择 | P3（视觉未核验） | 保留 tagRef 行政区，不与实时位置混用 |
| 系统定位 permission primer/错误态 | P2（视觉未核验） | 统一 platform capability 与结构化恢复 |
| 附近同趣/结伴 | P0（正式对象未落地） | 保持 deferred；禁止创建候选列表假页面 |

### M18-D 双向初查

- `Location` 是 external reference，无独立详情页合理；正式内容/评价/关注需提升到 Homepage。
- `CreateLocationService`/`CreateLocationOption` 仍位于 UI 是 R-CR04 明确分层债，不能作为业务真相。
- 用户地区 tagRef、发布地点、实时/模糊位置是三个不同概念；混成一个 `location` 字符串为 GATE_BLOCK。
- ExternalInteraction Attempt/DLQ 无 App 页面正确，但必须进入 H1/Portal 观测；UI 只见结构化结果和恢复。
- 附近同趣涉及双向同意、青少年、精确度和保留期；未建对象/风控前必须 P0/deferred。

**新增长期风险候选（尚未登记 backlog，需用户确认）**：`integration/location/fields.yaml` 将精确 `latitude/longitude` 标为 `PUBLIC + log_policy: allow`，`metadata/log_kv_policy.yaml` 对 nearby 的 `lat/lng` 使用 `plain`，`integration-service/internal/application/location_service.go` 又把原值写入 `geo.lat/geo.lng` span；同时 `content/post/fields.yaml` 的 `location: GeoPoint` 为 PUBLIC/allow，而 `privacy.yaml` 要求 location 仅城市级脱敏。原因是外部 POI、Post 位置与日志/trace 没有统一“精确输入、粗粒度输出、日志禁明文”边界；影响是精确位置泄露、跨用户追踪和附近/交集无法合规上线。

### M18-E 六维度

| 维度 | 当前 | 目标 | 任务 | 验收 |
|---|---|---|---|---|
| D1 | 发布地点/地点 landing/地区存在；附近能力 deferred | query→选择→源对象保存→详情/失效完整；模糊位置显式同意 | 修 R-CR04；裁决 provider/permission/retention | 拒绝/受限/超时/无结果 UAT |
| D2 | Location external ref + ExternalInteraction 三对象图，但坐标 classification/log/trace 与 Post privacy 冲突 | provider port、attempt/DLQ、Post/Homepage value 边界清晰 | 迁 application port；精确坐标改 PII/drop-or-coarsen；补 privacy/error/freshness | 隐私扫描 + generated client + provider fake/real |
| D3 | 两个核心页 P2 | location selector/landing≥P4 | 真机地图/列表、键盘、权限、无障碍 | 双色/断点/iOS/platform profiles |
| D4 | 外部 provider 易受限 | 首结果 P95、缓存/去抖、超时、限流、离线最近位置预算 | Retry-After、TTL、fallback、坐标精度 | 弱网/限流/大结果/无 GPS |
| D5 | location journey 与 external attempt 有基础，但现有 trace 明文坐标 | 3 指标：有效地点选择率、查询到可选结果 P95、地点证据后有效行动率 | query/provider/result/object 同 trace，精确坐标日志/metric/trace 为零 | 隐私泄漏扫描 + App/SLS/integration metric 对账 |
| D6 | App location API integration 1 个 | provider、权限、external state/DLQ、源对象写入三层齐备 | 扩 beta provider contract、gamma device；隐私负例 | 不上传精确位置、无假 POI |

### M18-F 标杆候选

Apple Maps Place/Search、Google Maps Places、Instagram location tagging、iOS Location permission primer。借鉴搜索、精度提示和权限；不复制实时轨迹、默认后台定位或位置社交曝光。

### M18-G 并行会话启动提示词

> 完成 M18 位置与地点集成全面分析。读取本文 §0～§9、§27、integration object map、Location service/errors、R-CR04、R-PLAZA-001。执行完整强制分析，严格区分用户地区 tagRef、发布地点、Homepage 地点和实时/模糊位置；覆盖 selector、landing、profile region、permission 与 DLQ。Out of Scope：附近/trip/meetup 正式聚合未落地前不实现；taxonomy 归 M17。输出 10 项交付物、隐私矩阵和三层/真机证据。

## 28. 全量审计与退出清单

### 28.1 页面覆盖勾稽

| 矩阵分组 | 行数 | 版块归属 | 结论 |
|---|---:|---|---|
| `lib/app/shell/*.dart` | 7 | M2 | 5 个壳/组件已预评级，2 个 T0 part 归父壳 |
| `lib/ui/welcome/pages/welcome_screen.dart` | 1 | M1/M2 | 已预评级 |
| discovery/content viewer | 3 | M3 | `home_page`、`unified_media_viewer_page`、`work_browser_entry_page` 已预评级 |
| assistant | 4 | M11 | 全部已预评级，half sheet/history/feedback 作为挂靠面补充 |
| chat | 9 | M6 | 全部已预评级 |
| circle | 6 | M8 | 5 个独立页已预评级，1 个 T0 barrel 归父页 |
| content/entry | 6 | M4 | 全部已预评级 |
| entity | 7 | M9 | 全部已预评级 |
| intersection | 1 | M10 | 已预评级 |
| rtc | 5 | M7 | 全部已预评级 |
| search | 3 | M5/M18 | 全部已预评级 |
| settings | 10 | M15 | 全部已预评级；其中权限页仍为预留空壳候选 |
| interest_match | 1 | M10 | 已预评级为当前 launcher P1 |
| user | 18 | M1=2、M12=14、M15=1、M16=1 | 全部已预评级 |
| components | 6 | M4=5、M15=1 | 5 个媒体页已预评级；1 个设置模板按组件验收 |
| **合计** | **87** | **18 个 M 版块** | 计数与横向质量矩阵一致；排除 3 个 T0 后 84 个独立验收行；page-object gate 当前通过 |

页面预评级均为静态结论；专项会话完成真机/截图审查前，不得把 P3 自动升级为 P4，也不得把交集相关页面自动升级为 P5。

### 28.2 对象与服务覆盖勾稽

- 14 个 canonical 业务对象域 + platform 控制面逻辑域均在 §4.1 有 owner；`chat`/`circle` 历史目录分别由 M6/M8 复核 generated 出口边界。
- 14 个 Go 服务均在 §4.2 有主版块；recommendation/rec-model、LiveKit/TURN、legal-static、seed-box 以运行依赖单列。
- 11 条 Journey 全部在 §4.3 有主版块和协同版块。
- 每个 M1～M18 均具备 A～G 七段，共 126 个小节；H1/H2 给出跨版块统一门。
- 对象无独立页面的 TagTaxonomyRelease、DeliveryJob、Exposure/Feedback facts、索引/投影等均给出“后台对象/嵌入承载”的理由，未机械造页。
- 已明确的 GATE_BLOCK 候选包括：通用入站深链 P0、权限预留空壳、首次兴趣先验 P0、`location.place` 无正式对象、未落地 InterestMatchOpportunity/trip/meetup、CircleGroup 生命周期承载、Credential/Device 安全管理边界、push deferred、通用 ANR/TTI，以及精确位置明文日志/trace；专项会话必须复核后修复、删除或经用户确认登记 backlog。

### 28.3 并行执行波次

| 波次 | 可并行会话 | 合流条件 |
|---|---|---|
| W0 横切冻结 | H1、H2 | 先冻结事件、黄金指标、三层与环境证据模板 |
| W1 基础对象与壳 | M1、M2、M3、M5、M6、M8、M11、M15、M17、M18 | 各会话只产分析/规格或在独占路径实现；共享 metadata 变更进入合流队列 |
| W2 复合旅程 | M4、M7、M9、M12、M16 | 分别消费 W1 的 tag/location、chat/realtime、content/entity、identity/relationship、content/notification 决策 |
| W3 差异化与回流 | M10、M13、M14 | M10 等源对象/证据边界冻结；M13 等源事件；M14 等 route/public projection |
| W4 商用准出 | 全版块 verify | 11 Journey UAT、对象 metric、SLS/Prometheus、gamma-local、prod gray canary 汇总 |

“可并行”不等于可同时修改同一真相源。以下文件为串行合流面：

- `contracts/metadata/_shared/page_object_contract.yaml`、route/surface/event catalog；
- `journey_scenario_registry.yaml`、跨域 acceptance、ContractGraph manifest；
- `docs/outstanding_risks_backlog.md`；
- `quwoquan_ops/environments/*.yaml`、Prometheus/Alertmanager 统一配置；
- generated files与 codegen output manifest。

每个共享面只设一个 owner 会话；其他会话提交变更需求与 patch 摘要，由 owner 统一 metadata→verify→codegen。拓扑 YAML 必须原子写并先解析，避免 R-HSE04 重演。

### 28.4 每个会话的商用准出清单

- [ ] 用户目标、核心/关联对象、关系基数、聚合边界和生命周期已重新证明。
- [ ] 对象→页面与页面→对象双向矩阵完整，无假对象、错对象或无入口能力。
- [ ] 页面逐一给出 P0～P5、视觉证据和保留/精修/重构/新增/合并/删除决定。
- [ ] P0～P3 页面已实时检索 2～4 个标杆，记录来源与日期，提炼原则而非抄袭。
- [ ] 交集定位为核心/增强/无需承载之一；事实、推断、隐私、冷启动和行动均有结论。
- [ ] D1～D6 均有当前规格、目标规格、任务和验收，不以文件存在代替完成。
- [ ] 关键业务一级黄金指标不超过 3 个；二级指标能定位页面、状态、operation、错误和版本。
- [ ] local_contract、api_integration、user_acceptance 与 alpha/beta/gamma-local/prod-hosted 证据匹配。
- [ ] 触发范围门禁绿；真实外部凭据/设备/hosted 证据缺失时如实 GATE_BLOCK。
- [ ] 新长期风险已先获用户确认再写 backlog；关闭既有风险已回写状态、日期与证据。

### 28.5 本文验证记录

- `python3 quwoquan_ops/gate/scaffold/verify_test_specs.py`：**失败**；RTC 特性树扁平化仍在并行写入，已观测到同一 acceptance 拼接两个 YAML 文档，以及 `call-experience/acceptance.yaml` 瞬时缺失。正确收口应合并重复 Story 节点并恢复一节点一份有效 acceptance，不能用空 acceptance 绕门。
- `python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py`：通过。
- `verify_page_horizontal_quality_matrix.py`：通过；`verify_page_matrix_scan_complete.py`：通过（87 paths，inventory aligned）。
- `make verify-agent-context-contract`：通过。
- `git diff --check -- docs/functional_module_commercial_maturity_matrix.md specs/feature-tree/runtime/runtime-client-foundation/page-horizontal-quality-matrix.md`：目标范围通过。
- `make verify-app-page-horizontal-quality`：通过（87 pages、72 routes、77 surfaces、70 objects；矩阵与 inventory 对齐）。
- 仓库全量 `git diff --check` 仍被其他并行改动阻断：RTC Story spec 有 trailing whitespace，另有 `post_service_config_search.go:96` EOF 空行；本任务未覆盖这些文件，未擅自覆盖并行工作。
- 文档为分析/规格增量，未修改 codegen、metadata、页面或服务代码，因此未运行 Flutter/Go 业务测试；各专项实现必须按触达范围补跑。

### 28.6 诚实结论

- **领域模型是否围绕业务对象建立**：canonical object maps 与生产分层已形成较强基础，但错误契约、历史目录、超限 Facet、未落地重行动对象和外部能力证据仍阻止“零技术债”结论。
- **对象关系和生命周期是否合理**：Post、Conversation、Circle、Homepage、Call、Assistant、Notification 等主对象关系已显式；交集作为跨源投影而非写聚合是合理候选，但必须通过专项验证源事实、行动 owner 和删除/权限传播。
- **页面是否完整承载旅程**：87 行横向治理已登记，不等于业务完整。InterestMatch 当前只是 launcher，首次兴趣采集无承载，Settings permissions 仍是预留空壳，CircleGroup/claim/report 结果链需复核，push/附近/线下能力明确 deferred。
- **哪些应重构**：本文每节 C 段已给初判；P1/P2 页面优先完全/适度重构，P3 页面先真实视觉和旅程核验，核心页目标 P4，交集主战场目标 P5。
- **业界差距**：主要不在颜色/字号，而在对象全生命周期、失败恢复、真实远端/设备证据、ANR/TTI、跨域回流和可运营指标。
- **不可简单复制的差异化**：以受权限约束的多对象事实为证据，把“为何相关”连接到合法行动，再沉淀为 Persona 关系、Circle membership、Conversation、Visit/Wishlist 等源对象；普通内容社区若只有黑盒相似度和静态标签，无法复制这条可解释、可行动、可回流的对象链。

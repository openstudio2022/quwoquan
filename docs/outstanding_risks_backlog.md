# 遗留事项与风险待办清单（Outstanding Risks Backlog）

> 单一真相源。每次会话起手式必须先审视本清单未解决项；新风险需先向用户复述并获得确认后登记；问题解决后必须打勾并补证据，避免遗漏。

## 使用规则

- 每条遗留事项使用 `- [ ]` / `- [x]` 复选框维护。
- `状态` 字段必须明确写为 `待办`、`进行中` 或 `已解决（日期 + 证据）`。
- 新增事项时，必须补齐 `区域`、`原因`、`影响`、`涉及文件`。
- 标记已解决时，必须写清验证证据，例如测试、门禁、截图、回放、日志或发布记录。
- 发现新风险但未经用户确认，不得直接登记为正式事项。

## 模板

- [ ] R-XXX 标题
  - 区域: App / Service / Data / Ops / Portal
  - 域: `<domain>`
  - 原因: ...
  - 影响: ...
  - 涉及文件: `path/to/file`
  - 状态: 待办

## 法律合规与商业化条款（Legal / Commercial Terms）

- [ ] R-LEGAL-001 商业化能力上线前必须补充专项条款并通过 legal-static 发布门禁
  - 区域: App / Service / Ops / Portal
  - 域: `platform-ops-governance/security-privacy-audit`
  - 触发条件: 未来上线付费、会员、订阅、虚拟币/积分、打赏、广告、电商、退款/发票、自动续费任一能力前必须触发。
  - 原因: 当前 `quwoquan_service/services/legal-static/source/versions/2026-07` 协议按免费社区版本拟定，明确不覆盖付费交易、广告投放、电商履约、退款发票和自动续费等商业化权利义务；`2026-06` 作为历史不可变版本保留。
  - 影响: 若商业化能力先于专项条款上线，将造成用户告知不足、同意版本不完整、双端审核材料缺失、争议处理与退款/发票/续费规则无依据。
  - 涉及文件: `quwoquan_service/services/legal-static/source/manifest.yaml`、`quwoquan_service/services/legal-static/source/versions/**`、`quwoquan_ops/cli/legal_static.py`、`quwoquan_app/lib/core/auth/auth_legal_config.dart`
  - 验收: 追加对应协议文档或条款版本，更新 manifest checksum，`stackctl package --env gamma --kind legal-static` 与 `stackctl verify --env gamma --kind legal-static` 通过；prod 前完成 legal-static URL 探测与法务审核。
  - 状态: 待办（2026-06-26 用户确认；首发免费社区版本作为已知缺口保留）

## 身份认证与商用登录（Authentication）

- [ ] R-AUTH-001 商用登录正式凭据与受控 SDK 尚未注入发布密钥系统
  - 区域: App / Service / Ops
  - 域: `user-identity-profile-relationship/onboarding-and-identity-entry`
  - 原因: 微信、支付宝、QQ 正式 App 配置以及阿里云三网统一认证客户端方案密钥、服务端 AccessKey 和控制台受控 SDK 二进制目前只有配置键契约，尚无 CI/CD 密钥注入与真机成功记录。
  - 影响: alpha 仅能由独立 runner/fixture 验证；beta/gamma/prod 缺真实凭据时 user-service 启动失败，不能宣称商用 UAT 完成。
  - 涉及文件: `docs/external_service_registry.yaml`、`quwoquan_app/android/app/build.gradle.kts`、`quwoquan_app/ios/Podfile`、`quwoquan_service/services/user-service/configs/prod/config.yaml`、`specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/acceptance.yaml`
  - 未完成清单: 发布密钥与受控 SDK 注入；Android/iOS prod 真机的成功、取消、不可用、超时和回滚 smoke；通过生产网关完成不泄露 secret、authCode 或 token 的留证；**衍生：无版本 API 镜像冷启动**（见下）。
  - 验收: 发布密钥系统注入 `QWQ_ALIYUN_PNVS_SECRET_INFO`、`ALIYUN_DYPNS_ACCESS_KEY_ID/SECRET`、`QWQ_WECHAT_APP_ID`、`WECHAT_OAUTH_APP_ID/SECRET`、`QWQ_ALIPAY_CALLBACK_SCHEME`、`ALIPAY_OAUTH_APP_ID/PRIVATE_KEY/PLATFORM_PUBLIC_KEY/MERCHANT_PID`、`QWQ_QQ_APP_ID`、`QQ_OAUTH_APP_ID` 与受控 SDK；Android/iOS prod 真机分别完成成功、取消、不可用、超时及回滚 smoke，并留存无 secret/authCode/token 泄露证据。
  - 衍生验收（API path 去版本，CR-20260717-109）: 密钥注入后必须 `stackctl package --env gamma --include-services` → `stackctl up --env gamma --skip-app` **冷启动**（禁止只靠 `docker cp` 热替换二进制宣称关闭）。探针：`GET {api}/config/app` 非 404；`GET {api}/v1/config/app` **404**；抽样 `POST {api}/search`、`GET {api}/homepages/search`、`GET {api}/circles` 同口径（新 path 可达或业务码，旧 `/v1/...` 一律 404）。证据：`.qwq_output/env/gamma/runs/**/report.json` + `make verify-api-path-runtime ENV=gamma`（或 `python3 quwoquan_ops/cli/probes/verify_api_path_runtime_unversioned.py`）落盘 JSON。若响应为 404 且 URL 仍含 `/v1/` 或 Caddy matcher 未更新，一律算 path 专项失败，不得挂靠本项其它 OAuth/SDK 缺口。
  - 状态: 进行中（2026-07-16：已从 metadata、user-service、四环境配置和 App response/UI 删除 OTP pass-through、sandbox allowlist、dev resolver、debugCode、Mock/Sandbox OAuth provider；alpha public plane 与非生产固定测试码已按真实 challenge、哈希、过期、限流、错误次数和一次性消费语义收口；真实短信改由短时 AES-256-GCM `codeRef` 在 integration-service provider 调用前内存解封，明文与 `codeRef` 不进入 outbox/attempt ledger/log/metric；provider 模式内部提交已强制 service principal + scope + HTTPS/mTLS client，校验服务端 CA、出示客户端证书且缺材料 fail-closed；prod 默认源码集排除 nonprod adapter，Remote 环境缺三方 OAuth、阿里云号码认证、短信密封密钥或 mTLS 证书材料时启动失败。最新 `stackctl up --target gamma-local --skip-app` 报告 `.qwq_output/env/gamma/runs/20260716T031439Z-up-gamma-local/report.json` 已真实证明缺 `WECHAT_OAUTH_APP_ID` 时镜像启动前 fail-closed；未注入占位凭据。`verify_login_dependency_config`、生产 wiring/package purity、mTLS local contract、user/integration-service local/API 测试与 App 登录定向测试为本地工程证据；beta/gamma/prod 正式凭据、真实 mTLS 证书注入、短信及社交 provider 后台结果、Android/iOS 真机 UAT 与回滚演练仍未取得，故不得关闭。2026-07-17：仓内 API path 已无版本且门禁加宽；gamma 仅有二进制热替换举证，**正式无版本镜像冷启动衍生验收未关闭**。本轮诚实 GATE_BLOCK：`stackctl up --env gamma --skip-app` → `.qwq_output/env/gamma/runs/20260716T180533Z-up-gamma/report.json`（package `--include-services` 已成功；compose 在缺 `ALIPAY_OAUTH_MERCHANT_PID` 时 fail-closed，镜像冷启动未进入；不得用热替换宣称关闭）。密钥注入后按衍生验收重跑 package/up + `make verify-api-path-runtime ENV=gamma`）

## 同趣 / 找同趣 · 兴趣配对（原同频/广场 Plaza）

- [ ] R-PLAZA-001 同趣（找同趣/兴趣配对）后端聚合与重行动风控待正式化（旧 plaza/connection 原型已下线）
  - 区域: App / Service
  - 域: `interest-match` / `circle-community/companionship-and-nearby-connection`
  - 原因: 2026-06-30「交集行动重建」已完成端侧原型下线与前台重建：删除 `lib/ui/plaza/**`、`lib/cloud/services/connection/**`、`plaza_text_constants.dart`、`connectionRepositoryProvider`、`/plaza/*` 路由、`connection_plaza_seed.yaml`；「同趣 / 找同趣 / 兴趣配对」改为 `lib/ui/interest_match/pages/interest_match_page.dart` 发现启动器（导流 `/search`、`/search/network`、`/profile/intersections` + 曝光埋点，不自建 Mock 候选），入口已从底栏常驻 tab 迁至底栏 `+` 动作面板「兴趣配对」。剩余未完成：`InterestMatchOpportunity`/`companionship` 后端 aggregate、附近 LBS、双向同意/实名/青少年风控、trip/meetup metadata+Go、api_integration + user_acceptance。
  - 影响: 附近同趣 / 结伴同行 / 线下局的真实聚合与风控闭环仍 deferred；当前「同趣」launcher 只承接发现 + 导流到既有真实面，不渲染伪造的人/圈/地结果列表。
  - 涉及文件: `quwoquan_app/lib/ui/interest_match/**`、`specs/product/intersection-action-deepening-and-social-ia.md` §0、`specs/feature-tree/journey_scenario_registry.yaml#companionship-and-nearby-connection`、`specs/gates/metadata_driven_ui_gap_inventory.yaml`（interest-match 域 launcher）
  - 验收: circle 域 trip/meetup metadata+Go 实现 + `InterestMatchOpportunity` 投影 + RuntimeFailure 错误码；`make verify-app-page-horizontal-quality` + api_integration + user_acceptance 关键路径；附近/重行动隐私风控 + 青少年模式落地后才可进 beta/gamma/prod。
  - 状态: 进行中（2026-06-30：旧原型已删除 + 「同趣」launcher 已落地；本轮入口从底栏 tab 迁至 `+` 动作面板「兴趣配对」；后端 companionship 聚合与重行动风控仍 deferred。本轮证据：`flutter analyze` 改动文件 0 issue；`flutter test test/app/shell/main_app_shell_widget_test.dart test/ui/content/entry/widgets/create_entry_sheet_widget_test.dart test/ui/content/entry/create_entry_information_architecture_widget_test.dart test/ui/content/entry/create_entry_runtime_flag_test.dart test/local_contract/ui/interest_match/interest_match_page__local_contract_test.dart test/local_contract/app/app_appearance_default_text_style__local_contract_test.dart` 通过；`make verify-app-page-horizontal-quality` 通过。历史证据：`dart analyze` 改动文件 0 error；`flutter test test/local_contract/interest_match/`；`make verify-app-page-horizontal-quality` / `make verify-app-mock-isolation` / `make verify-metadata` / `make codegen-app` 幂等）

## 搜索体验（Search）

> 路径口径（2026-07-17 path unversioned，CR-20260717-109）：下列**已解决**条目中出现的 `/v1/search`、`/v1/content/...`、`/v1/homepages/...` 等为**当时证据路径**；现行无版本 API 以 `quwoquan_service/contracts/metadata/**/service.yaml` 为准（如 `/search`、`/content/feed`、`/homepages/search`）。`rankingVersion=search-v1` 等非 HTTP path 字段保持不变。
- [x] R-001 搜索结果封面宽高比仍按内容类型固定，缺少真实封面尺寸驱动
  - 区域: App
  - 域: `search`
  - 原因: `PostSearchItemView` 当前不提供封面 `width/height`，结果页只能按图片 `1:1`、视频 `16:9` 给定基础比例，再依赖 `PostPreviewCard` 的 `9/16~16/9` clamp 防止长图或横幅无限长。
  - 影响: 结果流虽然已消除无限长与大留白，但卡片瀑布流仍无法按真实素材比例排布，视觉表达受限。
  - 方案: R-S06 在 remote 模式由 `RemoteSearchRepository` 透传云侧 `coverWidth/coverHeight`，结果页 masonry 卡片用真实宽高比排布（仍保留 `9/16~16/9` clamp 防长图无限长）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/lib/core/services/remote_search_repository.dart`
  - 状态: 已解决（2026-06-16；remote 模式云侧封面尺寸驱动，随 R-S06；mock 模式仍按内容类型基础比例，属本地预览态）

- [x] R-002 搜索结果降级横幅仍是死逻辑
  - 区域: App
  - 域: `search`
  - 原因: `_buildDegradeBanner()` 恒返回 `null`，`withDegradeBanner()` 目前不会渲染任何降级提示。
  - 影响: 远端降级或能力受限时，`degradeSignals` 无法向用户表达，存在可观测与体验缺口。
  - 方案: 结果页聚合各分域 `SearchResponse.degradeSignals`；有可见结果时不遮挡媒体流，无结果时展示 typed 降级横幅（消息来自 signal.message）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 证据: `_mergeDegradeSignals` + `_hasRenderableResultsForActiveTab` + `_buildDegradeBanner`；widget 测试 `degrade signal 不压过媒体结果` / `degrade signal 在无结果时展示降级横幅` 通过。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 已解决（2026-06-16）

- [x] R-003 交集 Tab 的关系理由与互动数据仍依赖确定性 mock 和本地回退拼装
  - 区域: App
  - 域: `search`
  - 原因: 当前仍通过 `_deterministicCount`、`_fallbackConnectionCardModels()`、`_fallbackDiscoverCardModels()` 等逻辑合成交集理由、点赞数、评论数和回退内容。
  - 影响: `beta/gamma/remote` 环境若不补齐真实交集数据契约，端云展示与本地 alpha 行为会不一致。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 方案: WP-C 收口——交集分组唯一真相源改为云侧 `connectionState` 闭集（connected / unconnected / intersection_lead），交集句严格只读 `intersectionReason.primaryText`，无 primaryText 不展示；删除 `_deterministicCount`、`_fallbackConnectionCardModels`、`_fallbackDiscoverCardModels`、`_friendActionLabel`、`_knownIntersectionEntity`、`_discoverContentReason`。
  - 证据: `rg` 确认上述符号在 `search_network_results_page.dart` 全部移除；新增 `_IntersectionContractSearchRepository` 契约测试断言 connectionState 分组 + 只读 primaryText + 无违禁词；`flutter test test/ui/search/pages/search_network_results_page_widget_test.dart` 10/10 通过。
  - 状态: 已解决（2026-06-16）

- [x] R-004 相关搜索词仍由客户端硬编码生成
  - 区域: App
  - 域: `search`
  - 原因: `_relatedSearchTerms()` 直接拼接 `$query 攻略`、`$query 拍照机位`、`$query 交集` 等词条，尚未接入 metadata 或服务端推荐来源。
  - 影响: 相关搜索结果不具备真实推荐语义，也会形成第二真相源风险。
  - 方案: R-S06 在 remote 模式优先消费云侧 `relatedTerms`（缺失才回退端侧派生）；R-S07 在 search-service 由 `queryheat` 真实计算并经 handler 写入响应（实际内容取决于 `rm_search_term_heat` 热力读模型是否接 Mongo）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/lib/core/services/remote_search_repository.dart`、`quwoquan_service/services/search-service/internal/application/queryheat/`
  - 状态: 已解决（2026-06-16；remote 模式接云侧 relatedTerms + 服务端 queryheat 计算，随 R-S06/R-S07；mock 模式回退端侧派生属本地预览态）

- [x] R-005 搜索默认页 inspiration 数据生产与消费不一致
  - 区域: App
  - 域: `search`
  - 原因: 默认页当前只消费 `guessKeywords`、`hotCircles`、`hotLocations`，但 `search_coordinator.dart` 仍持续 hydrate `inspiration.people` 与“我的交集” chips，之前相关死 UI 已被删除。
  - 影响: 存在无人消费的数据生产与维护成本，容易误导后续开发继续沿用旧结构。
  - 涉及文件: `quwoquan_app/lib/ui/search/providers/search_coordinator.dart`
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 证据: coordinator 不再写入 `people`；`flutter test test/ui/search/pages/global_search_page_widget_test.dart` 9/9 通过。
  - 状态: 已解决（2026-06-16）

- [x] R-006 搜索 mock 仓库仍残留旧术语禁用词
  - 区域: App
  - 域: `search`
  - 原因: 搜索 UI 范围内已清理“共同兴趣 / 同趣的人 / 共同圈子 / 交集发现流”，但 mock 仓库仍有残留词汇。
  - 影响: 后续若该 mock 数据重新进入展示路径，会回归旧术语并造成文案不一致。
  - 方案: `search_repository.dart` 用户 snippet 由「共同兴趣相关」改为「推荐关注」。
  - 涉及文件: `quwoquan_app/lib/core/services/search_repository.dart`
  - 证据: `rg '共同兴趣' quwoquan_app/lib/core/services/search_repository.dart` 无命中；`flutter test test/ui/search/search_repository_test.dart` 通过。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」）。
  - 状态: 已解决（2026-06-16）

- [x] R-007 搜索结果页与默认页的行为埋点、停留、归因链仍需专门核实
  - 区域: App
  - 域: `search`
  - 原因: 本轮主要解决 UI/布局与技术债问题，尚未逐项核对搜索默认页、结果页在曝光、停留、`referralSource`、`feedRequestId` 等方面是否满足全链路要求。
  - 影响: 搜索漏斗、推荐归因链和运营观测可能存在断点。
  - 方案: `global_search_page` / `search_network_results_page` 进入时 `trackImpression`（`ReferralSource.search` + `feedRequestId`），离开 `dispose` 时 `trackDwell`；tracker 引用在 init 帧缓存避免 dispose 后读 ref。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/global_search_page.dart`、`quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`
  - 证据: 两页 widget 测试全绿（9 + 11）；contentId=`global_search`/`search_network_results`，tags 含 entrySurfaceId 与 tab/query。
  - 纳入规划: WP-B App 体验收口（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」），并归入 cross-domain-search-journey SIT 的埋点归因链验收。
  - 状态: 已解决（2026-06-16；T2 widget 通过，T4 journey 仍待 WP-G 准出一并补录）

- [x] R-008 搜索结果页内容空集与实体置顶仍保留硬编码 demo 回退
  - 区域: App
  - 域: `search`
  - 原因: 远端内容为空时 `_fallbackContentItemsForQuery()` 仍返回带外链图与编造点赞数的演示内容；`_entityTopResult()` 对 `厦门大学` 等保留硬编码实体卡与 `26.8万关注 · 1.2万内容` 伪 meta。属 `lib/ui` 域名假数据，违反 mock 隔离（R15/R30）。
  - 影响: beta/gamma/prod 若服务端无结果，端会展示编造内容与伪统计，形成第二真相源并误导验收；与交集消费收口（R-003 已解决）不同，属一般搜索 demo 残留。
  - 方案: 删除 `_fallbackContentItemsForQuery` 与硬编码实体 fallback；实体 meta 只读 hit payload 计数；空集走真实空态（与 R-002 降级横幅协同）。
  - 涉及文件: `quwoquan_app/lib/ui/search/pages/search_network_results_page.dart`、`quwoquan_app/test/local_contract/ui/search/pages/global_search_page_widget__local_contract_test.dart`
  - 证据: fallback 符号已删除；`flutter test test/ui/search/pages/search_network_results_page_widget_test.dart` 11/11 通过。
  - 状态: 已解决（2026-06-16）

## 搜索端云一体（专用 ES/OpenSearch + search-service）

> 架构决定：专用 ES/OpenSearch 集群 + 复用 `runtime/search/es` 库 + 新建可部署 `search-service`（`FallbackBackend(Primary=ES, Fallback=native)`）。真相源 CR：`specs/changelog/CR-20260615-037-search-dedicated-es-service-landing.yaml`。
>
> ⚠️ **版本控制状态（2026-06-16 复审）**：本节绝大多数搜索增量代码仍处 **git untracked**，尚未纳入版本控制——包括整个 `quwoquan_service/services/search-service/`（含 go.mod/go.sum）、`quwoquan_service/contracts/metadata/search/`、`quwoquan_service/runtime/search/es/*`、各域 `*_search_projection.go` 与 `internal/infrastructure/searchindex/`、`content-service` 的 `search_signal_consumer.go`、App 端 `remote_search_repository.dart` 与 `generated/search/*.g.dart`、`quwoquan_service/services/search-service/deploy/`、对应 CR/spec。功能链路本地已验证可用，但**「已解决」状态仅代表功能就绪**；本轮按用户选择 `git_scope: verify_only` 不做提交，版本落盘（git add/commit）归属用户。在干净检出上运行 CI/全量 gate 须先由用户提交这些文件。不另建第二份清单，仅在此注明。

### 已落地（cloud backend，2026-06-16，已验证）

- [x] R-S01 真实 ES 客户端 + 装配（ES primary / native fallback）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/runtime/search/es/{http_client,index_schema,assembly,indexer}.go` 与对应 `*_test.go`；`go test ./runtime/search/...` 全绿（含 ES httptest、lossless round-trip、outage fallback）。
  - 状态: 已解决（2026-06-16；`go test ./runtime/search/...` ok）
- [x] R-S02 search 域 metadata-first（query/feedback 日志 + _shared/search_contract 字段扩展）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/contracts/metadata/search/query/{aggregate,fields,events,storage,service}.yaml`；`_shared/search_contract.yaml` 增 `relatedTerms/rankingVersion/requestId/rankReasons/coverWidth/coverHeight`；`make verify-metadata` 绿。
  - 状态: 已解决（2026-06-16；verify-metadata 通过）
- [x] R-S03 可部署 search-service（当时 `/v1/search`、`/v1/search/feedback`；现行 `/search`、`/search/feedback`；以及 `/healthz`、`/metrics`）
  - 区域: Service
  - 域: `search`
  - 证据: `quwoquan_service/services/search-service/**`；`go build/vet/test ./...` 全绿；真实启动冒烟：health 200 / search 200（含 requestId+rankingVersion+provenance）/ 空 query 400 / feedback 202 / metrics 200；ES-down+native fallback 退化 200、纯 ES 无 fallback 诚实 503。
  - 状态: 已解决（2026-06-16；contract test + 本地 boot 冒烟）
- [x] R-S04 部署登记（六 manifest + 端口槽 + 四环境 ES config 段）
  - 区域: Ops
  - 域: `search`
  - 证据: `process_domain_mapping`/`process_domain_plane_mapping`/`module_package_mapping`/`reliable_task_module_catalog`/`workload_topology_inventory`/`local_env_port_manifest` 均登记 `search-service`(domain=`search`，planned standalone-workload，beta=gamma=prod 一致)；全部部署门禁验证器绿（deployment_domain_mapping/workload_topology/module_package/reliable_task_catalog/permission_scope/gamma-local↔prod consistency+isomorphism/prod_plane_access_isolation/runtime_packaging/service_config_layout/service_env_contract/deploy_kustomization/engineering_directory/opsx_ff_8services）。
  - 状态: 已解决（2026-06-16；部署验证器全绿）

### 待办（端云接线，闭环 R-001/R-003/R-004）

- R-S05 各域 → `es.Indexer` 单一索引灌数管线（按域拆分；content/entity/circle/user/location）
  - 区域: Service / Data
  - 域: `search`
  - 原因: 当前 search-service 召回链路就绪，但生产侧索引尚未灌数；alpha 走 native，beta/gamma/prod 的 ES 索引需各域投影写入后才有真实结果。
  - 影响: 未灌数前 `/search`（当时证据路径为 `/v1/search`）在 ES 模式返回空，端到端结果不可用。
  - 机制基线（content 切片确立，后续各域复用）: 共享投影函数（域内 application 层，与该域 native CandidateSource 同源） + infrastructure 写时 `Projector`（实现各服务 `application.Projector`，按 publish/update/visibility-change upsert、unpublish/delete/ineligible delete，失败只结构化告警不阻塞主写路径，挂在已有 projector fan-out 末位） + `Backfill`（`EnsureIndex`→列全量→共享投影→`Writer.Bulk` 批量）+ `es:` config 段（`SEARCH_ES_*` 注入、disabled=no-op）。
  - [x] R-S05a content 域灌数（`content.search_index_worker` 落地）
    - 区域: Service
    - 域: `content` → `search`
    - 证据: 共享投影 `application.ProjectPostToSearchDocument`（`post_retrieve.go`，与 `PostCandidateSource` 同源）；写时投影器 `services/content-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`；装配进 `cmd/api/main.go`（fan-out 末位 + `es:` 五环境 config + `SEARCH_ES_*` 注入 + boot EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt`（本切片文件为空）/`go vet ./services/content-service/... ./runtime/search/...`/`go test ./services/content-service/... ./runtime/search/...` 全绿；alpha（es disabled）真实 boot 冒烟主路径不受影响；`verify_reliable_task_catalog` + `verify_module_package_mapping` 绿（模块早已声明，无需新增 manifest）。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05b entity 域灌数（entity.homepage → 同一 `searchindex` 机制 + 共享投影）
    - 区域: Service
    - 域: `entity` → `search`
    - 证据: 共享投影 `application.ProjectHomepageToSearchDocument`（`homepage_search_projection.go`，与 `SearchHomepages` native 召回同源；anchor 字段 `entityId/entityName`，objectType `entity.homepage`→target `entity`）；写时投影器 `services/entity-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现新引入的 `application.Projector`，发布/认领更新 upsert、下线/失格 delete，ES 故障只告警不阻塞，mutation 内 deferred-emit 释放锁后再投影）；装配进 `cmd/api/main.go`（`WithProjector` 末位 + `es:` 五环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 本切片文件全 clean；根 module 下 `entity-service` package 与 `runtime/search` 的 `go vet`/`go test` 全绿。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05c circle 域灌数（circle.circle / circle.group）
    - 区域: Service
    - 域: `circle` → `search`
    - 证据: 共享投影 `application.ProjectCircleToSearchDocument` + `CircleSearchEligible` + `circleSearchCategoryID`（`circle_search_projection.go`，`SearchCircles` 重构为同源消费，删除死代码 `asStringSlice`）；写时投影器 `services/circle-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现 `repository.EventPublisher`：`CircleCreated/CircleUpdated` reconcile、`CircleArchived` delete、其余忽略；读回经 `CircleReader`；ES 故障只告警不阻塞；backfill 走 `CircleStore.List` 游标分页）；装配进 `cmd/api/main.go`（`WithEventPublisher` + `es:` 五环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 全 clean；`go vet`/`go test ./services/circle-service/... ./runtime/search/...` 全绿（含 `tests` 集成包）。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05d user 域灌数（user.profile）
    - 区域: Service
    - 域: `user` → `search`
    - 证据: 新建共享投影 `application.ProjectUserProfileToSearchDocument` + `UserProfileSearchEligible`（`user_search_projection.go`，objectType `user.profile`→target `user`；昵称→Title、bio→Summary、`IdentityTags` 经 `parsePgTextArray`→Tags、粉丝+作品数→Popularity、anchor 字段 `authorId/authorName/authorDisplayName`；合格集=accountState active 且 status active）；写时投影器 `services/user-service/internal/infrastructure/searchindex/{projector,backfill,assembly}.go`（实现 `application.UserEventPublisher`，`UserProfileUpdated/UserAvatarUpdated/UserRegistered` 读回 reconcile、失格/缺失 delete、读回错误不误删、ES 故障不阻塞；`ComposePublisher` 把 MQ 主发布器与 search 投影器组合——主发布器错误透传、search best-effort）；backfill 经新增 `PgProfileStore.ListProfilesForIndex`（keyset 分页、26 列完整扫描含 identity_tags）；装配进 `cmd/api/main.go`（ES 启用时组合到 `userEventPublisher` 末位 + `es:` 六环境 config + `SEARCH_ES_*` 注入 + EnsureIndex/health ping）；backfill cmd `cmd/search-backfill`。`gofmt` 本切片文件全 clean（`cmd/api/main.go` 仅预存 Integration struct tag 错位未动）；`go vet ./services/user-service/... ./runtime/search/...` 绿；`go test` 中 `searchindex`/`application`/`cmd/api` 等包全绿。`tests` 集成包有 18 个失败，已用 HEAD 基线（stash 我的改动后复跑）证明为**预存**（real-Postgres 契约测试因 `identity_tags` 列 NULL 无法扫入 `*string`、迁移计数 15 vs 16、登录路由 404 等，均与本切片无关），我的改动零新增失败。
    - 状态: 已解决（2026-06-16）
  - [x] R-S05e location 成为统一检索第一方对象 —— 已解决（保留 geo 维度 + 叠加 location.place target）
    - 区域: Service / Data / App
    - 域: `content`(第一方地点快照) → `search`
    - 事项: location 对象要在 `/search`（当时 `/v1/search`）出真实结果，需在 `runtime/search` 检索契约新增 `TargetLocation`/`ObjectTypeLocation`，并联动 `AllTargets`/`TargetForDocument`/`ObjectTypesForTargets`、search-service `DefaultResultTargets`、metadata `_shared/search_objects.yaml`、App 端 target 枚举。
    - 方案（用户拍板 force_target）: 保留并复用并发会话已落地的**跨对象 geo 维度**（`GeoNear`/`RetrieveFilters.Near`/`RetrieveHit.Geo/DistanceKm/PlaceName`/`nearMatch`/`Document.Geo`/ES geo mapping），仅做**加性**扩展，不删改其语义；叠加一类复用该维度的第一方对象 target `location.place`。改写 `search_objects.yaml` 原“location 不是 target、第一方地点即 entity.homepage”不变量为：geo 是跨对象维度（保留）+ `location.place` 是复用该维度的第一方对象，仅覆盖“被内容引用但未绑定 `canonicalEntityId`/`primaryHomepageId` 的自由文本地点”；已绑定者由 entity.homepage 承载（同一地点只出现一次，单一真相源）。
    - 单一真相源: 地点绑定 canonicalEntity（成为 entity.homepage）→ `DerivePlaceRef` 不再产出该 ref，其 location.place 在失去最后一篇自由文本引用后被删除；geo 机制只有一套。
    - 灌数实现: content-service 新增第一方地点快照存储 `place_snapshots`（派生读模型，posts 为唯一写真相源，按引用集去重）；`placeindex.{store,projector,backfill}` 写时增量维护 + 全量重建；共享投影 `application.ProjectPlaceToSearchDocument` + 身份函数 `CanonicalPlaceID`（normalize(locationName)+粗 geohash，不用第三方 poiId）；DDD 分层：ES 只在 `infrastructure/placeindex`。
    - 证据: metadata `make verify-metadata` 绿；`make codegen-app` 重生 `search_registry.g.dart`（`SearchObjectType.locationPlace`/`RetrieveTarget.location`/section locations/ai_target location→location.place）且幂等；Go `gofmt -l` clean、`go vet`、`go test -count=1 ./runtime/search/...`、`./services/content-service/internal/{application,infrastructure/placeindex}/...`、search-service `./tests/...` 全绿；content-service cmd（api/search-backfill）build OK；alpha ES-disabled 路径 nil-safe（place projector 仅在 `searchBuilt.Client != nil` 构造，`Project` 守 `a.place != nil`）；App 端 `dart analyze`（search 范围）clean，全量 analyze 的 80 条 error 全部属于并发会话 intersection 重构（与本任务无关，见剩余风险）。spec/acceptance/CR 见 `search-object-taxonomy-and-provider-registry/{spec.md,acceptance.yaml}` 与 `specs/changelog/CR-20260616-038-location-first-party-search-object.yaml`。
    - 状态: 已解决（2026-06-16）
    - 衍生待办: location.place 落地页（detail/route）归属与渲染已定（见 R-S05e-1，2026-06-16 WP-D 落地：临时地点卡 + 提升为 entity.homepage CTA）；gamma ES 灌数后 `/search`（当时证据 `/v1/search`）召回 location.place 的 T3 集成随 search-service 集成补录。
  - [x] R-S05e-1 location.place 落地页归属与渲染（衍生自 R-S05e）
    - 区域: App / Service
    - 域: `search` / `entity`
    - 事项: location.place 命中后点击进入的 detail/route 未定；需明确其落地页是临时地点卡还是“提升为 entity.homepage”的引导入口，并定义 route_id/surface_id（metadata-first，禁止 UI 硬编码）。
    - 影响: 当前 location.place 可被检索召回，但点击落地体验未定义；不阻塞召回主链路。
    - 方案（WP-D，已采纳计划推荐）: 落地为**临时地点卡 + “提升为实体主页”引导 CTA**，符合 spec 单一真相源（未提升=location.place、已提升=entity.homepage）。命中详情来自搜索结果 payload，经 `LocationPlaceLandingPageRouteExtra` 透传，落地页本身**无独立后端 operation**；提升动作复用 `suggestHomepage` surface。
    - 实现: metadata-first 在 `_shared/app_routes.yaml`（`locationPlaceLanding` `/locations/{placeId}`）+ `_shared/ui_surfaces.yaml`（surface `locationPlaceLanding` owner=search、`operation_ids: []`）定义；`make codegen-app` 重生 `app_route_paths.g.dart`（`AppRoutePaths.locationPlaceLanding`）+ `app_ui_surfaces.g.dart`（`AppUiSurfaces.locationPlaceLanding`）；新页 `lib/ui/search/pages/location_place_landing_page.dart` + router wiring；`search_network_results_page` 交集已连接地点改走 `_IntersectionTargetType.locationPlace` → 落地页（不再误导 homepage 详情）。
    - 证据: `make verify-metadata` 绿；`make codegen-app` 幂等重生路由/surface 常量；新页 + 改动文件 `flutter analyze` 0 issues；`flutter test test/ui/search/pages/location_place_landing_page_widget_test.dart` 3 用例全绿（渲染名称/地址/临时徽标/CTA、CTA 跳 suggestHomepage 带地点名、JourneyEventTracker enter 曝光 + promote_click 上报）；页面横向质量矩阵 + `metadata_driven_ui_gap_inventory.yaml` 已登记。
    - 状态: 已解决（2026-06-16，代码 untracked 待用户提交）
- [x] R-S06 App 接搜索 API（当时证据 `/v1/search`；现行 `/search`；RemoteSearchRepository + provider 模式切换 + 结果页读云侧字段）
  - 区域: App
  - 域: `search`
  - 方案: 新增 `quwoquan_app/lib/core/services/remote_search_repository.dart`：result 模式 POST `CloudRuntimeConfig.gatewayBaseUrl + SearchApiMetadata.searchQueryPath`，统一走 `CloudHttpClient.postJsonObject`（codegen path/operation/surface 常量、零硬编码 URL/path、无裸 http.Client、无自建重试、错误经 `CloudException`/`runtimeFailure` 结构化）；objectTypes 复用 `RetrieveRequest.fromSearchRequest().targets` 单源映射并剔除 chat（避免误发本地命名空间对象）；解析 `RetrieveResponse` 透传 `rankReasons/rankPosition/coverWidth/coverHeight/connectionState/intersectionReason/relatedTerms`（`SearchHit`/`SearchResponse` 仅按 `RetrieveToolContract` 契约最小加性补承载字段）。`searchRepositoryProvider` 按 `appDataSourceModeProvider` 切换（remote→Remote、mock→本地扇出 composite）。结果页 `search_network_results_page.dart` 仅改「全部/媒体/相关搜索」消费区（masonry 用云侧 `coverWidth/coverHeight` 真实宽高比、`rankPosition` 排序、`rankReasons` 首条作理由、`relatedTerms` 优先于端侧派生），未触碰 intersection tab 任何符号。网关：当时 Caddy 登记 `@api_search /v1/search*`→`search-service:18095`（2026-07-17 后现行 matcher 为无版本 `/search*`）；seed-box 加 `SEARCH_UPSTREAM_HOST/PORT` 透传。
  - 证据: scoped `dart analyze`（search_repository / remote_search_repository / retrieve_request / search_hit_payload / search_coordinator / search_network_results_page 共 6 文件）= 0 error / 0 warning（仅全仓同款 `prefer_initializing_formals` info）；部署验证器全绿（deployment_domain_mapping / workload_topology / module_package / gamma-local↔prod consistency / topology_regression）。受并发 intersection 重构外部阻塞，App 全量 `flutter analyze/test` 暂不可跑（错误全在 object_intersection，0 条涉及 search），T2 widget / T3 集成待 intersection 合流后补（见 R-IX07）。
  - 状态: 已解决（2026-06-16；scoped analyze + 部署验证器；端到端搜索真实冒烟见衍生待办 3；当时证据 path `/v1/search`，现行见 metadata `/search`）
  - 衍生待办: (1) remote 模式实体顶卡/location 仍请求旧 `integration.location_poi`（不映射任何云 target），需切 `entity.homepage`/`location.place`——因改动与 intersection 共享的 `_locationResults`，待并发 intersection 重构合流后协调（与 R-IX06 联动）；(2) 云侧 `relatedTerms` 填充已由 R-S07 在 search-service handler 落地（早前 R-S06 观测到的“未填充”系 R-S07 改动前旧 handler，现已闭合）；(3) local-gamma 运行栈未实例化 search-service → 见衍生待办 3（已发起环境 worker）。
- [x] R-S07 反馈/relevance 闭环 + 搜索词热力（query_popularity/cooccurrence/trending）注入排序
  - 区域: Service / Data
  - 域: `search`
  - 方案: search-service `internal/application` 定义 `FeedbackSink`/`QueryLogSink` 端口 + 强类型 `QueryLog`/`FeedbackEvent`，`infrastructure/feedbackstore` 落 `storage.yaml` 的 Mongo 集合（建 TTL+查找索引，`searchRequestId` upsert）；`/search`（当时证据 `/v1/search`）命中后 `handler.go` 旁路 best-effort 记 `SearchQueryLogged`（不阻断主路径、无空 catch）；`/search/feedback`（当时 `/v1/search/feedback`）落反馈。搜索词热力：`application/queryheat`（归一化/去重/时间衰减/CTR 加权）产出 `TermHeat` + `RelatedTerms`，`infrastructure/queryheatstore` 周期 `Rebuild` upsert 派生读模型 `rm_search_term_heat`（TTL 86400s，metadata 声明 + 合约测试断言代码常量逐字一致）。排序透明化：`runtime/search/retrieve.go` 给 `RetrieveHit` 加 `RankReasons/RankPosition`（`rankAndMerge` 统一累积、分页后 1-based 编号、`RetrieveHitMap` 同源），`application/ranking.go` 按 AB 分桶决定 term-heat 加权重排并重编号，`handler.go` 写 `relatedTerms/rankingVersion/experimentBucket` 信封。SLO/指标/告警/AB：`searchmetrics`（promauto histogram 分位数 + 计数，标签含 experiment_bucket）、`configs/observability/search_slo.yaml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`（quwoquan_search 组）、`application/experiments.go`（一致性哈希稳定切桶 control/term_heat）。
  - 证据: `make verify-metadata` ✓；`gofmt -l` clean；`go vet ./runtime/search/...` OK；`go test -count=1`：search-service `application`/`application/queryheat`/`tests`（含 envelope + TTL 合约）✓、`runtime/search` + `runtime/search/es` ✓、`assistant-service .../tool`（RetrieveHitMap 消费者向后兼容）✓；SLO/告警 YAML `yaml.safe_load` OK。
  - 状态: 已解决（2026-06-16；verify-metadata + go test + 合约测试）
  - 衍生待办: 见 R-S07-5（搜索词信号注入在线推荐 Feed 排序，平台级跨服务增量，已 backlog 化）。
- [x] R-S07-5 搜索词信号注入在线推荐 Feed 排序（衍生自 R-S07，平台级跨服务增量）
  - 区域: Service / Data
  - 域: `search` → `recommendation`/`content`
  - 事项: 让 R-S07 产出的搜索词热力/相关性（`rm_search_term_heat` + `SearchQueryLogged`）参与**推荐首页 Feed**排序（非搜索结果页——结果页排序已用 term-heat 闭环）。
  - 原因: 需新建 `search-service → content-service` 跨服务事件传输（Redis 发布端 + content-service 订阅 + `RecommendFeatureProjector` 消费 + `feature_registry` 注册搜索特征 + `recpolicy` 因子 + `RuleScorer`）；半成品落地会形成无消费者的死特征（违反 R24/R26 零技术债红线）。本项已按独立平台增量闭环。
  - 影响: 已由搜索查询/term-heat 信号经 Redis Stream 发布到 content-service，投影进推荐特征宽表，并被 FeatureStore 与 RuleScorer 真实消费；推荐 Feed 可消费搜索会话信号，搜索结果页排序仍沿用 R-S07 term-heat 闭环。
  - 涉及文件: `quwoquan_service/services/search-service/**`（Redis 发布）、`quwoquan_service/services/content-service/internal/infrastructure/recommendation/**`、`quwoquan_service/services/rec-model-service/scripts/feature_registry.yaml`、`quwoquan_service/runtime/recpolicy/**`、`quwoquan_service/runtime/redis/**`。
  - 证据: `make verify-metadata`、`make verify-ml-features`、`python3 scripts/verify/verify_redis_keyspace.py`；`go test`/`go vet` 覆盖 search-service、content-service 推荐投影、`runtime/recommendation`、`runtime/recpolicy`、`runtime/redis`；Redis routes 与 `rec_policy_baseline.gen.go` 已重新生成。
  - 真实 T3 证据（2026-06-16 local-gamma 复验，补齐双服务端到端）: 先清理 `db0` 手工 XADD orphan（误判根因），再带 `X-User-Id: fixture_user_current` 冒烟 `POST :19280/v1/search`（成都火锅/九寨沟/鼓浪屿）。**发布**：`db1` stream `events.search.recommendation_signals` XLEN 2→5（+3，每次 result 检索一条）；**消费**：consumer group `content-service` `pending=0, entries-read=5, lag=0`；**投影**：`quwoquan_content.rm_recommend_feature`（userId=fixture_user_current）`userFeatures.searchTermAffinity` 含本轮全部查询词（九寨沟=1.27、成都火锅=1、鼓浪屿=1 等），`searchTermUpdatedAt=2026-06-16T06:27:47.885Z` 与冒烟同刻。证据落盘 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_signal_t3_report.json`。误判纠正：上一轮查 `db0`（只有 orphan）且冒烟未带 `X-User-Id` 导致 `recommend_feature.go` 对空 userId `return nil` skip —— 系**验证方法缺陷，非代码缺陷**。
  - 剩余风险（长稳项）: 真实多分片 OpenSearch + Redis cluster-mode 下的延迟/可靠性差异未压测；`RuleScorer` 实际把 `searchTermAffinity` 计入推荐 Feed 排序的线上 A/B 收益未度量（纳入 WP-F 推荐信号长稳，见 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 已解决（2026-06-16；T1/T2 + 真实双服务 T3 端到端闭环已证；线上排序收益与真集群差异作长稳项）
- [x] R-S06-S 端到端搜索真实冒烟（当时证据 `/v1/search`；现行 `/search`；衍生待办 3：local-gamma 实例化 search-service）
  - 区域: Ops
  - 域: `search`
  - 事项: local-gamma 实际运行栈已通过 stackctl 实例化 `search-service`（容器 `search-service:18095`，host `19280`，ES `quwoquan_objects`），并经 Caddy 网关完成当时 `/v1/search` 与 `/v1/search/feedback` 真实冒烟（现行无版本 `/search`、`/search/feedback`）。
  - 影响: 搜索 T3（端云集成）已补齐真实链路证据；当时 `/v1/search` 返回 ES-backed hit 与排序信封，`/v1/search/feedback` 返回 202 accepted（现行 path 见本节路径口径）。
  - 涉及文件: `quwoquan_ops/environments/local-gamma/**`、`quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml`、`quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`、local-gamma stackctl 运行栈真相源。
  - 状态: 已解决（2026-06-16；证据：`python3 quwoquan_ops/cli/stackctl.py package --env gamma --include-services` → `.qwq_output/env/gamma/runs/20260616T041350Z-package-gamma-local`，含 `service package ready: QWQ_OUTPUT_ROOT/env/gamma/packages/service/search-service`；`python3 quwoquan_ops/cli/stackctl.py up --env gamma --skip-app` → `.qwq_output/env/gamma/runs/20260616T041612Z-up-gamma`，backfill `quwoquan_objects total=672 indexed=671 skipped=1` + places `posts=672 referenced=5 places=4`；`python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope full` → `.qwq_output/env/gamma/runs/20260616T042515Z-health-gamma-local`，15/15 healthy，`search-service -> 200`；`python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all` → `.qwq_output/env/gamma/runs/20260616T042741Z-verify-gamma-local`，15 checks passed；真实网关冒烟 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_smoke_report.json`：`POST https://gamma-api.quwoquan-env.test/v1/search` 返回 200、`requestId=search.req.1781584024537428163`、`rankingVersion=search-v1`、`hitsCount=5`、首条 `成都医学院`，`POST /v1/search/feedback` 返回 202 accepted）
  - 独立复核: 另一环境 worker 以 ES-enabled 路径复核 local-gamma，`stackctl up --target gamma-local --skip-app` 13 容器 healthy，`stackctl verify --env gamma --kind all` 10 checks passed；经网关 `POST http://127.0.0.1:19000/v1/search` 返回 200、真实 ES hit=5、`rankingVersion=search-v1`、`experimentBucket=term_heat`、hit 含 `rankReasons/rankPosition`；空 query 返回结构化 400，`/v1/search/feedback` 返回 202。
- [ ] R-S06-S-1 local-gamma ES 模拟环境性能与真集群差异
  - 区域: Ops
  - 域: `search`
  - 原因: Apple Silicon/Colima 下 local ES 使用 `platform: linux/amd64` 模拟以避开 arm64 JVM 初始化期 SIGILL；本地冷启动约 3-4 分钟，单次 `_bulk` 较慢，回填需较小 batch。
  - 影响: 不影响搜索功能正确性，但 local-gamma 启动与回填性能不能代表 CI/真实 ES/OpenSearch 集群；真集群需用原生镜像/托管集群重新校准 batch 与启动 SLA。
  - 涉及文件: `quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml`、`quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh`、ES/OpenSearch 部署配置。
  - 本轮交付（方法学 + 目标值，已落盘）: ①冻结高并发负载模型 `search_slo.yaml#load_model`（suggest/result/feedback/indexing 四类，baseline/peak/spike 的 RPS/并发/分位数/错误率/降级率/freshness/Redis lag 目标）；②容量校准方法学 + 按数据规模的 ES 拓扑推荐（shard 10–50GB 避免 oversharding、单节点 replicas=0/生产≥1+≥2 data node、≥半内存留 page cache、refresh 30s、bulk 校准、query cost guard）写入 `search-storage-topology-and-elasticity/spec.md#容量校准`；③local 证据：单节点 1shard/1replica 永久 yellow（replica unassigned）属模拟工件。
  - local-gamma 验证入口（2026-06-17 补齐）: `python3 quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py` 聚合 stackctl gamma verify、ES health/index/shards/threadpool、小型 warm/cold/mixed/feedback 并发压测、单节点 repeatability、故障/回滚证据存在性，报告 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_r_s06_s1_local_gamma_report.json`。该报告固定声明 `r_s06_s1_closed_by_local_gamma=false`，只证明 local-gamma 方法学与单节点稳定性，不替代真集群 measured。
  - 未闭合（真实缺口，需真集群）: measured RPS/P95/P99、饱和点、最大稳定 RPS、推荐 shard/replica/节点规格与 refresh/bulk/circuit 实测阈值必须在真集群/prod-sim 原生 ES/OpenSearch 回填；本环境无真集群，属发布前阻断。压测/profiling 证据见 `QWQ_OUTPUT_ROOT/env/repo/runs/search-load/search_load_analysis.md` 与 `QWQ_OUTPUT_ROOT/env/repo/runs/search-load/search_e2e_hotpath_profile.md`（local 单节点 ES 为唯一瓶颈，result/suggest 高并发 NO-GO）。
  - 可重复性多副本兜底（并入本项）: 跨副本 `_score` 漂移需 ES `preference`（viewer/session/query 稳定派生路由）兜底；需通过 Searcher 透传查询参数实现，local 单节点无副本无法验证，随真集群里程碑实现验收。local 单节点重复查询已 0 跳变（`QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_repeatability_golden_diff.json`），稳定排序/AB 粘性已由单测闭环。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」与 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 待办（负载模型/容量方法学/ES 拓扑推荐已冻结、local-gamma 单节点稳定性与重复查询 0 跳变已证；剩余真集群 measured RPS/P95/P99/饱和点/shard·replica·refresh·bulk 实测阈值严格依赖真 ES/OpenSearch 集群或 prod-sim，归属 WP-E 索引长稳·发布前阻断，非本地可采集）
- [ ] R-S06-S-2 搜索索引写时增量与 ES 重启恢复长稳验证
  - 区域: Service / Ops
  - 域: `search` / `content`
  - 原因: 本轮 T3 已证明起栈 host 端 backfill 后 `/search`（当时证据 `/v1/search`）可返回真实 ES hit；但 `content.search_index_worker` 写时投影器的常驻增量同步、ES 重启后索引一致性与补偿恢复尚未做长稳 T3。
  - 影响: 不影响当前搜索冒烟与静态门禁，但长期运行、内容更新、ES 重启或索引重建后的数据一致性仍缺运行证据。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/searchindex/**`、`quwoquan_service/services/content-service/internal/infrastructure/placeindex/**`、`quwoquan_service/runtime/search/es/**`、local-gamma stackctl 健康/回填脚本。
  - 部分证据（2026-06-16 ES 重启恢复 T3 已补）: 在运行中的 local-gamma 上 `docker restart elasticsearch`，ES 约 108s 恢复；索引 `quwoquan_objects` 文档数 **675→675 持久**；重启后经 search-service `/v1/search?q=成都` 恢复到与基线**完全一致的 TopN**（首条 `成都医学院`、5 命中、零降级信号）；count 与文档化 backfill（671 indexed + 4 places ≈ 675）一致。证据落盘 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_index_restart_recovery_t3.json`。单节点 + replicas=1 → cluster 永久 yellow（replica unassigned）属 local-gamma 单节点模拟工件（生产用 ≥2 data node + replicas≥1 转 green），非缺陷。
  - 部分证据（2026-06-16 故障/回滚演练补充）: `quwoquan_service/scripts/search/search_rollback_rehearsal.py` 在 gamma-local 对 ES/Redis/search-service 三类故障注入 + 回滚到已知良好态。**ES 宕机** → search-service fail-closed 返回 typed `503 SEARCH.MIDDLEWARE.unavailable`（`nature:transient`+用户文案，3.5ms 快速失败不挂起），ES 重启（~105s）后检索恢复一致 TopN；**Redis 失败** → 检索主路径仍 200/5 命中（信号发布 best-effort 不阻塞），content-service 消费侧保持 healthy，重启 6.1s 恢复；**search-service 不可用** → 受控连接拒绝（非超时挂起），重启回滚 6.1s 后 healthz 200 + 检索恢复；演练后 `stackctl health --target gamma-local --scope service` 8/8 healthy。证据落盘 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_rollback_rehearsal_report.json` + `.qwq_output/env/gamma/runs/search_rollback_rehearsal.md`。
  - 未闭合（保持待办）: ①写时增量长稳——内容 publish/update/下线触发常驻投影器的增量同步与持续 soak（需 content-service 写路径鉴权 + 长时运行）；②backfill 幂等再跑收敛同一 count；③真集群恢复 SLA 与 green（归 R-S06-S-1）。
  - 纳入规划: WP-E 索引长稳（搜索商用规划复审；见 `specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/spec.md`「后续 /dev 工作包登记」与 `search-storage-topology-and-elasticity` GWT2 planned）。
  - 状态: 待办（ES 重启恢复 + 索引持久 + 故障/回滚演练分项已证；剩余写时增量常驻投影器长稳 soak[需写路径鉴权 + 长时运行]、backfill 幂等再跑收敛、真集群恢复 SLA[归 R-S06-S-1]，归属 WP-E 索引长稳，需运行环境长稳，非本会话单点可闭）
- [x] R-S06-S-3 search-service 单一根 Go module 依赖图可复现性
  - 区域: Service / Ops
  - 域: `search`
  - 原因: 历史上 `search-service` 等七个服务以嵌套 `go.mod/go.sum` 切断根编译图，根门禁无法证明全部服务可构建，容器还依赖 local replace 与多套锁文件。
  - 影响: 依赖版本、漏洞修复与编译证据可能跨 module 漂移；新环境或 CI 可能因锁文件缺失失败。
  - 处置: 2026-07-12 删除全部服务嵌套 module；服务仍保留独立二进制和部署单元，但统一由 `quwoquan_service/go.mod` 管理依赖并从根 package path 构建。scaffold 与 Dockerfile 同步禁止嵌套 module 回归。
  - 门禁: `python3 quwoquan_service/scripts/verify/verify_go_single_module.py` 已接入 service gate；`verify_search_service_module.sh --with-tests` 改为验证根 module、搜索服务生产编译和完整测试。
  - 验证证据: `go mod verify`、`make build`、`go test ./internal/metadata/... ./runtime/operation/... -count=1`、`bash scripts/search/verify_search_service_module.sh --with-tests` 均 exit 0。
  - 状态: 已解决（2026-07-12；唯一根依赖图、全部生产包构建和 search-service 根 module 测试已绿）

## 灵魂交集统一（端云，intersection-unification）

> 真相源 spec：`specs/feature-tree/object-homepage-network/intersection-unified-experience/`。WP-0/WP-1/WP-2 + WP-3（UCB 探索 + MMR 多样性）+ WP-4（交集特征回流 + ranking-signal-fusion 单点注入）已在主线完成（见各自单测/契约/verify 证据）。以下为我（代理）在授权下登记的、需独立或平台级会话推进的剩余事项，均附正确设计，杜绝在读路径或主线塞入错误耦合。

- [ ] R-IX01 AffinityReasons 概率分通道改由模型分驱动（异步物化，禁止读路径同步 RPC）
  - 区域: Service / Data
  - 域: `recommendation` → `content`
  - 原因: 当前 `MongoIntersectionSource.AffinityReasons` 用「圈子热看 / 关注的人在看」启发式按近度返回内容，未经评分服务 `/score`（当时证据 `/v1/score`）模型打分；`affinityIntersectionScore` 特征字段尚未真实填充。
  - 正确设计: 不得在 summary/list/feed 读路径同步调用 `/score`（当时 `/v1/score`；会破坏 WP-2 确立的事实读模型零打分、并对读路径引入模型服务硬依赖与尾延迟）。应由异步评分作业（或 challenger/shadow 离线管线）对 affinity 候选打分后，把 `affinityIntersectionScore` 与排序写入 `rm_viewer_object_intersection` 的 affinity 段，读路径仍零计算消费。
  - 已收口（2026-06-16 WP-F 不变量固化）: 读路径「零同步打分 + affinity 分数直出不重算」已固化为契约测试 `quwoquan_service/services/content-service/internal/application/intersection/intersection_readpath_invariant__local_contract_test.go::TestIntersectionService_ReadPathZeroSynchronousScoring`——断言 `Feed` 对 `FactReasons/AffinityReasons` 各恰好拉取一次（无 per-candidate 重复打分循环）、不触达 `ObjectReasons`，预物化 `Strength`/`modelReasonBucket` 原样直出；`Summary/List` 只走事实通道。`IntersectionSource` 接口方法签名本身不含 scorer 参数，从类型层面保证读路径无模型服务硬依赖。该不变量防止未来回归到把 `/score`（当时 `/v1/score`）拉进读路径的错误设计。
  - 影响: 事实通道（已回流）不受影响，融合与排序主链路安全。读路径零同步打分已被契约测试锁定。
  - 进展（2026-06-19，切片⑥ 部分前移，见 R-ID06）: affinity 通道已从「裸 count 启发式」升级为确定性 Graph 边权真算（`edgeWeight = relationStrength × interactionFrequency × recencyDecay`，在 `ReadModelIntersectionSource.AffinityReasons` 物化，纯算术、零评分服务调用），`affinityIntersectionScore`（edgeWeight）不再恒 0；读路径零同步打分不变量保持。**剩余**：真正的 `/v1/score` 模型概率分（深排多任务）写入 affinity 段，属深排平台轨（与 R-IX03 合并推进），非确定性图权可替代。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`、`read_model_intersection_source.go`(affinity 边权真算)、`intersection_graph_materializer.go`、`viewer_object_intersection_store.go`、`runtime/recommendation/scorer.go`(RemoteModelScorer)、`internal/application/intersection/intersection_readpath_invariant_test.go`(不变量契约)、异步评分作业。
  - 状态: 待办（读路径零同步打分不变量已固化[契约测试锁定]、affinity 确定性 Graph 边权真算已落地[R-ID06]；剩余 `/v1/score` 模型概率分异步写入 affinity 段——确定性图权不可替代，并入深排平台轨 R-IX03）
- [ ] R-IX02 viewer×object 关系交集 per-candidate 信号物化（P1 kind + 关系级精排融合的前置）
  - 区域: Service
  - 域: `recommendation` → `content`
  - 原因: 现有读模型/特征回流是 viewer 级聚合；真正「这条候选的作者是我与某对象的共同关注 / 来自我与好友共访实体」的 per-candidate 关系交集信号缺一个按社交图谱预计算的关系投影。WP-2 的 P1 kind（sharedFollowees/coVisitedEntity 等逐对象事实）与「关系级」精排融合都依赖它。
  - 正确设计: 新增按 viewer 预计算的关系交集投影（或扩展 `rm_viewer_object_intersection` 存逐 object 的关系事实），由社交图谱 + 共访/共评事件增量维护；读路径零计算消费；精排可在候选侧读取该 per-candidate 关系强度。
  - 影响: 未做前 P1 关系类 kind 仅在 ObjectReasons（单对象主页）可得，feed/list 的关系级 per-candidate 融合用 viewer 级揭示偏好近似（已交付，安全但非逐候选关系事实）。
  - 涉及文件: `quwoquan_service/contracts/metadata/recommendation/model_release/projections/`、`services/content-service/internal/infrastructure/recommendation/`、`runtime/recommendation/scorer.go`。
  - 状态: 待办（viewer 级聚合近似已交付[feed/list 安全]、P1 关系 kind 在 ObjectReasons 可得；剩余 per-candidate 关系交集投影需按社交图谱 + 共访/共评事件增量预计算，归属关系投影/数据工程预计算轨，非本会话单点可闭）
- [ ] R-IX03 深度排序模型平台轨（MMoE/PLE/ESMM 多任务、双塔 ANN 在线服务、Thompson/IPS 反事实闭环）
  - 区域: Service / Data
  - 域: `recommendation`
  - 原因: 业界大厂精排的多任务深度模型、双塔向量召回在线服务、bandit reward 闭环与 IPS 去偏训练，是多周/多月平台工程，非单会话可闭环。
  - 现状安全基线: 多目标 LightGBM + champion/challenger + shadow 评估 + 晋升门禁 已是生产安全基线；WP-3 已补 UCB 曝光感知探索（去偏 + 冷启动，确定性可复现）与 MMR 多样性重排（policy 可选）。
  - 影响: 不阻塞主链路；为持续优化的长期能力上限。
  - 涉及文件: `quwoquan_service/services/rec-model-service/**`、`runtime/recommendation/**`、`services/rec-model-service/scripts/**`。
  - 状态: 待办（生产安全基线已落地：多目标 LightGBM + champion/challenger + shadow + 晋升门禁 + UCB 探索 + MMR 多样性；剩余 MMoE/PLE/ESMM/双塔 ANN/Thompson·IPS 闭环属多周-多月深排平台工程，不阻塞主链路，归属推荐平台长期轨）
- [ ] R-IX04 精品池召回源（featured / 高完成率内容专用候选通道）——前置缺失：无 featuring 写入能力
  - 区域: Service / Data / Ops
  - 域: `content` → `recommendation`
  - 原因: WP-5 已在排序侧落地场景路由 + premium 预设（弱化纯热度、强化完成/停留/相关性，homepage/similar 场景启用），但召回侧尚无「精品池」专用候选通道。
  - 关键前置（2026-06-16 核实）: `Post.Featured`/`FeaturedAt` 字段在 `post.go` 已声明；本轮已补 circle-service 圈内动态精选写入（`FeatureCirclePost` 更新 `posts.featured/featuredAt`），但这只是圈子 feed 管理能力，不等同于 product-ops/编辑体系的全局「精品池」准入能力。若现在直接把普通 `featured` 字段当作全局精品池唯一来源，仍会把圈内运营动作与全站精选召回混为一谈，形成第二语义债。
  - 进展（2026-06-25 P1d）: product-ops 已补全局精品池写入入口，强制 `scope=global`、质量准入、审计 ID、过期时间、回滚 token 与下架剔除状态；圈内精选仍不能替代全站精品。剩余闭环是把 product-ops 全局精品池投影到 content-service 推荐读模型，再启用 `PremiumPoolSource`。
  - 下一轮规划（2026-06-25 continue-dev）: P1d-2 已裁决为下一轮主切片，正式落点是 `premium-stream-recommendation` 的 `GWT2_premium_pool_readpath`。设计边界为 product-ops 只拥有运营准入事实，content-service 只读投影拥有推荐可读模型，runtime recommendation 只消费 `PremiumPoolSource` 候选；feed 读路径禁止同步查 product-ops、质量模型、数据工程任务或 `/v1/score`。
  - 进展（2026-06-25 continue-dev 开发切片）: 已新增 `rm_premium_pool` projection metadata、fail-closed 投影字段构造、product-ops `PremiumPoolEntryUpserted/RolledBack/TakedownEjected` 事件发布、content-service `PremiumPoolProjector/PremiumPoolEventConsumer`、`PremiumPoolSource` 场景门控、content-service 接线与 `disable_premium_pool_source` 回滚开关；feed view 补 `sourceTaskId` 下发用于数据工程归因。当前仅证明本地事件投影与读路径契约，真实 product-ops API → Redis `events.ops.*` → content-service Mongo `rm_premium_pool` → `/v1/content/feed` 的 api_integration、Gamma/UAT 与 replay/AB 真实样本仍未闭合。
  - 进展（2026-07-02 交集 v3 F）: 已补 `GatePremiumStreamSource` 与 feed 层 `premium_stream` repository fallback 禁用，保证精品流 fail-closed：非 `PremiumPoolSource` 召回源不会污染 premium stream，expired/rolled_back/takedown 三类 ineligible 不再泄漏。local-gamma seed/probe 已证明 `rm_premium_pool` eligible 样本经 `/v1/content/feed?type=premium` 返回且 `recallPath=premium_pool`；为避免曝光治理导致重复 probe 假阴性，seed 使用唯一 probe user。验证：`go test ./services/content-service/internal/infrastructure/recommendation ./services/content-service/internal/application/feed ./services/content-service/tests -run 'Test(GatePremiumStreamSourceBlocksGenericSource|PremiumPoolSourceGatesToPremiumStream|ListFeed_PremiumStreamDoesNotUseRepositoryFallback|ListFeed_PremiumStreamRoutesToSimilarPresetSurface|IntersectionFeedbackCooldown)' -count=1` 通过；`LOCAL_GAMMA_SKIP_FIXTURE_SEEDS=0 quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh --skip-build` 通过并落盘 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/premium-pool-seed-report.json`。
  - 正确顺序: product-ops「全局精选/编辑加权」写入能力（已补）→ 在 `rm_discovery_feed`（或 `rm_premium_pool`）投影补 featured scope + 质量分 → 建 `PremiumPoolSource`（按场景自门控，RecallPath=`premium_pool`，装配 engine sources 末位）。
  - 影响: 未完成 content-service 投影读取前，精品场景的「优中选优」仍由排序侧 premium 预设承担（已上线，数据驱动）；召回候选仍是通用池。不阻塞主链路。
  - 涉及文件: `services/product-ops-service/**`(featuring 写入)、`services/content-service/internal/infrastructure/recommendation/`、`contracts/metadata/.../projections/`。
  - 状态: 进行中（排序侧 premium 预设[场景路由 + 完成率/停留/相关性加权]已上线、圈内精选写入已补、product-ops 全局精品写入前置已补，P1d-2 本地事件投影与读路径基座已补；2026-07-02 已证明 content-service `PremiumPoolSource` 真实数据启用 + premium stream fail-closed + local-gamma seed/probe。剩余为 product-ops API → Redis `events.ops.*` → content-service `rm_premium_pool` 的真实跨服务事件链、replay/AB 分桶、prod gray 与真机 UAT。归属 content/product-ops 前置能力轨，不阻塞主链路）
- [ ] R-IX05 四主页云侧真实数据 + DDD 收口（WP-6，客户端+跨服务，字段漂移已收口）
  - 区域: App / Service
  - 域: `entity` / `circle` / `user`
  - 原因: 实体/人物/圈子/我的四主页的「云侧真实内容拉取」尚未全部脱离 seed/mock：实体主页需脱硬编码 seed 真实拉 content；用户/我的主页 `AuthorImpact` 与圈子主页 `CircleImpact` 需要 api_integration/user_acceptance 证明真实读路径。
  - 已收口（2026-06-16）: 客户端交集/四主页切片的破坏性字段漂移已修复：`IntersectionReason` 消费方从旧 `displayText/label/sharedCount` 迁到 `primaryText/connectionSummary/totalPointCount`；删除已删 `ObjectIntersection*` import 与孤儿二源 mapper `tag_intersection_mapper.dart`；`CircleImpactItem`/`AuthorImpactItem` UI 与 Mock 改读 `primaryText`；Go 侧 `CircleImpact`、`AuthorImpact`、entity fallback reason 输出字段对齐到 `primaryText/totalPointCount`。圈子 feed 管理的 `PinCirclePost`/`FeatureCirclePost` 已从 NO-OP 改为通过 `FeedStore` 持久化更新 `posts.pinned/pinnedAt`、`posts.featured/featuredAt`，并发布 `CirclePostPinned`/`CirclePostFeatured` 事件。`PostCount` 已从 seed-only 改为真实跨服务事件回写：content-service `PostPublished/PostDeleted/PostSettingsUpdated` payload 携带 `circleIds` 与 `addedCircleIds/removedCircleIds`，circle-service 订阅 Redis `events.content.*` 并按 published 状态门控增减 `circles.postCount`、同步失效缓存。`WeeklyActiveCount` 已从 seed-only 改为行为驱动窗口回写：`ReportBehavior` 对已加入成员刷新 `CircleMember.LastActiveAt`，按 `lastActiveAt >= now-7d` 重新计数后写 `circles.weeklyActiveCount`，不使用 `$inc`。`CircleImpact`/`AuthorImpact` 结论句已抽到共享 `runtime/impact`，服务只下发 `primaryText`，端不再拼装。验证：`go build ./services/content-service/... ./services/circle-service/... ./runtime/impact`、`go build ./...`（entity-service）、`go test ./runtime/impact ./services/content-service/internal/application/... ./services/content-service/tests ./services/circle-service/...`、`go test ./internal/application/...`（entity-service）、`go run ./tools/verify_metadata/ contracts/metadata` 均绿；`flutter analyze lib/` 无 error（剩余为既有 warning/info）。
  - 现状: 服务端推荐/交集引擎（WP-0~5）已完成并验证，为这些主页提供统一 Explain（`primaryText`/`connectionSummary`/affinity 标签）与场景路由（homepage→premium）。实体/用户/我的主页结构已具备 Remote path + provider + 契约 DTO；圈子主页的字段对齐、Pin/Feature、PostCount、WeeklyActive、CircleImpact 结论句均已接入真实写/解释路径。剩余主要是 beta/gamma/prod 真数据灌入与 api_integration/user_acceptance 端到端验收。
  - 影响: 编译级字段漂移不再阻塞；四主页在 beta/gamma/prod 仍可能展示 seed/mock 派生数据，需各域服务真实数据与 impact 回写后才能端到端闭环。
  - 涉及文件: `quwoquan_app/lib/ui/{entity,circle,user}/**`、`services/{entity,circle,user}-service/**`、`contracts/metadata/{social/circle,content/post}/projections/*impact*`。
  - 衍生待办（2026-06-16 gamma-local 实测）: 当时 `docker-compose.gamma-local.yaml` 只含 content/chat/user/assistant/product-ops/tag/search/rec-model 服务，不含 `entity-service` 与 `circle-service`；经网关当时 `/v1/homepages/*` 返回 404「local-gamma mirror route is not ready」，故四主页 detail（`/v1/homepages/{id}/object-page-bundle`）与圈子 impact（`/v1/circles/{id}/impact`）的 gamma-local api_integration 暂不可冒烟。content 交集 GET 路由（`/v1/content/intersections/object|summary`、`/v1/content/intersections`）已在运行栈内并强制 viewer 鉴权；populated 交集分组（connectionState / intersectionReason.primaryText）需网关可识别的真实 token + 已 seed 的 viewer 关系，当前匿名探测返回「需要登录」。证据：`QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/search_intersection_smoke.json`（`/v1/search` 200 ES-backed 杭州西湖、`/v1/content/feed` 200、`/v1/content/feed/intersections` 200 空、交集 GET 路由 viewer 鉴权）。本轮（gamma 远端退役真相源收敛，2026-06-16）：按「gamma 已取消远端、合入 local-gamma mirror + prod 生产灰度」口径，`quwoquan_ops/environments/environment_topology_manifest.yaml` 的 `gamma` 块（publicBases/hostAllowlist/artifactPolicy.allowLocalHosts/distribution/forbiddenHostTokens）与 `quwoquan_app/configs/gamma/app_runtime.yaml`、`quwoquan_service/services/chat-service/configs/gamma/config.yaml` 已从远端 `118.31.239.122:1900x` 收敛为本地 `127.0.0.1:1900x`，并重打包 git 纳管的 gamma app/service env artifact（chat/platform-ops/product-ops，残留远端 IP 归零），与文档既定口径（`environment_matrix.md`、`prod_plane_access_isolation.yaml`、environment-ops SKILL）一致。证据：`verify_environment_topology_manifest`/`verify_gamma_local_prod_isomorphism`/`verify_env_artifact_isolation`/`verify_prod_package_purity` + `content_media_url_test`(8/8) + `verify_retired_terms_zero`/`verify_concept_naming` 全绿。结论：entity/circle 的接入目标明确为 **local-gamma compose**（非远端 gamma），真实远端集成由 **prod gray-initial** rollout stage 承接。
  - 复核（2026-06-25 continue-dev）: 当前仓库已静态包含 `entity-service` 与 `circle-service`：`docker-compose.gamma-local.yaml` 有两服务 build/image/health/port 配置，`quwoquan_ops/environments/local-gamma/Caddyfile` 当时有 `/v1/homepages*` 与 `/v1/circles*` 网关路由（2026-07-17 后现行为无版本 `/homepages*`、`/circles*`），stackctl package 输出包含两服务；`bash quwoquan_service/scripts/contract/verify_contract_metadata.sh` 通过（仅保留既有 search/user_profile response_entity warnings），`docker compose -f quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml config` 通过。风险不能关闭：`python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all` 仍在 `gamma-local-t3` 因 gateway health `SSL: UNEXPECTED_EOF_WHILE_READING` gate_block，`gamma-local-environment-page-smoke` 因缺少 Patrol CLI 失败；api_integration 尚未证明 `/v1/homepages/{homepageId}/object-page-bundle`、`/introduction`、`/related-groups`、`/v1/circles/{circleId}/impact`、`/v1/content/intersections/object?objectType=homepage|circle` 的 populated 结果与 viewer 鉴权 seed。
  - 下一轮目标（2026-06-25 规格化）: 新增 L3 `object-homepage-gamma-real-data-closure` 接管剩余闭环，按 P0 规格/契约、P1 gamma health、P2 seed+api_integration probe、P3 App Remote、P4 observability+user_acceptance/UAT 推进；优先修运行健康和种子探针，不新增并行交集 API，不用 App mock 冒充真实服务。
  - 复核（2026-07-01 交集 v3 CDE 准入，M0 契约底座落地后）: `stackctl verify --env gamma --kind all` 静态 10 checks 全绿（topology/config/packaging，report `.qwq_output/env/gamma/runs/20260701T131219Z-verify-gamma-local`）；`--tier t3` 仍 `gate_block`，本会话根因为 **docker daemon（colima）未启动** → gateway `Connection refused`（Errno 61，`QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/t3_report.json` health/productOpsHealth 均 Connection refused），比历史 TLS `SSL: UNEXPECTED_EOF_WHILE_READING` 更前置（栈未拉起）。`colima`（`/opt/homebrew/bin/colima`）与 `patrol`（`~/.pub-cache/bin/patrol`，未在 PATH）均已安装但 daemon 未启动。结论：E 端云 api_integration/UAT 本会话 **runner-blocked**，闭合需人工 `colima start` + `stackctl up --env gamma` + seed viewer 关系 + gateway TLS 起 + patrol page-smoke。M0 契约底座（safetyGate/gateKeys/moment/行动阶梯 actionKeyMeta/subject/feedbackKinds）已就位并端云 codegen + 门禁全绿，为 E 闭合后 C0/C 提供可消费契约（`start_companion`/`coWishlistedEntity` 数据源门由 kind status=deferred 表达，无源不伪造）。
  - 复核（2026-07-02 交集 v3 E/C0）: 本轮已启动 local-gamma 并完成 seed viewer 关系 + content/intersection API probe；`coWishlistedEntity` 从 `entity_wishlist_events` 真实来源产出，metadata 已由 deferred/R4 推进到 active/R2，App Remote smoke 在 gamma-local 观测到 `coWishlistedEntity` 与 `start_companion` action hint；`start_local_gamma_mirror.sh --skip-build` 完整通过并落盘 `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/intersection-seed-report.json`。该复核关闭 2026-07-01 的 docker-daemon/seed-runner 阻断，但 R-IX05 仍覆盖四主页全域真实内容/impact/user_acceptance，不能整体关闭。
  - 复核（2026-07-02 运维复验，E gamma infra + api_integration 解阻塞实证）: 独立环境会话确认 colima（macOS Virtualization.Framework，docker server v27.4.0）已运行、gamma-local 16 容器全部 healthy（uptime≈8h）；`curl` 直连 `content-service:19220/healthz` 与网关 TLS `--resolve gamma-api.quwoquan-env.test:19000/healthz` 均 200，历史 `SSL: UNEXPECTED_EOF_WHILE_READING` 与 2026-07-01 `Connection refused`（Errno 61）均消失。`stackctl verify --env gamma --kind all` 静态 10 checks 全绿（`.qwq_output/env/gamma/runs/20260702T154438Z-verify-gamma-local`）；`--tier t3` 11 checks 全绿，历史 gate_block 的 `gamma-local-t3` 现 **status: passed**（`.qwq_output/env/gamma/runs/20260702T154556Z-verify-gamma-local` + `QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/t3_report.json`）：网关/product-ops health 200、seed passed（content=32 / circle=89 / user=15 / entity homepage_20），四主页端点 `/v1/homepages/homepage_20/object-page-bundle`、`/introduction`、`/homepages/search` 均 200（正是 2026-06-25 记录未证明的端点），content feed/comments、circle、chat、user `/v1/me`+`/profile/fixture_user_current` 均 200，content/chat/product-ops api 契约测试全 passed。交集真实数据经直连 API probe 复核仍在：summary totalCount=5（dims=relationship/location/content）、fact list sourceRefs 含 sharedFollowees/sharedCircle/coVisitedEntity/coCommented、object `sys_travel_9003_sub_01` 含 `coWishlistedEntity` 且 actionHints[0]=(`start_companion`,`companion`)。**权威 api_integration 证据**：`flutter test test/api_integration/ui/intersection/intersection_remote_smoke__api_integration_test.dart --dart-define=RUN_LOCAL_GAMMA_REMOTE_SMOKE=true`（直连 127.0.0.1:19220）**2/2 全绿**（`RemoteIntersectionRepository reads seeded gamma intersections` + `CloudHttpClient feed smoke keeps recommendation attribution`）。结论：E gamma 交集真实数据闭环的 infra + api_integration 已解阻塞并绿。剩余仅 runner 限制与 UAT，未伪造通过：(1) `stackctl health` 命令报 8/19——gamma 公共域名解析到 `198.18.0.253`（`/etc/hosts` 只有 alpha、无 gamma loopback，`sudo` 需密码本会话无法非交互修复），但 verify t3 内部走 `--resolve` 已证服务链路健康，属探测方法/hosts 映射工件而非服务宕机；(2) media-origin 宿主进程（19110）未运行→媒体 health 探测失败，网关经 `/srv/media` file_server 直供不受影响；(3) t4 `gamma-local-environment-page-smoke`（user_acceptance）需 patrol CLI（`~/.pub-cache/bin/patrol` 未在 PATH）+ 设备/模拟器，本会话未跑。
  - 复核（2026-07-05 continue-dev）: `python3 quwoquan_ops/cli/stackctl.py health --target gamma-local --scope service` 已 **8/8 healthy**（`.qwq_output/env/gamma/runs/20260705T114515Z-health-gamma-local/summary.md`），说明当前交集链路所依赖的 service scope 不再受历史 hosts/media 探测噪声阻断；同轮修复实体主页 `HomepageContentPreview` 误读不存在 `id` 字段的问题，统一改读 `postId` 后，`flutter test test/ui/entity/pages/homepage_detail_page_widget_test.dart test/ui/circle/widgets/circle_shell_widget_test.dart test/components/object_page/object_intersection_card_test.dart test/components/object_page/object_intersection_section_test.dart` 48/48 绿。另，`.qwq_output/env/gamma/runs/20260705T052227Z-verify-gamma-local` 中 `contract-seeded-mock-tests` 失败已定位为 `contract_seeded_mock_repository_test.dart` 默认分页上限断言偏差（非交集远端阻断），修正后 `flutter test test/local_contract/cloud/services/contract_seeded_mock_repository__local_contract_test.dart --no-pub --dart-define=CONTRACT_FIXTURE_PROFILE=full` 14/14 绿；全量 `stackctl verify --tier all` 本轮未重跑，仍保留 page-smoke/UAT 未闭合事实。
  - 复核（2026-07-05 continue-dev，page-smoke 解阻断）: `quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py` 已补齐本地 target 设备侧地址重写（`.quwoquan-env.test` → `.localhost`）、`APP_CURRENT_USER_ID` 显式透传、iOS simulator `root.crt` 注入，以及 `test/user_acceptance/patrol/environment/basic_viability__user_acceptance_test.dart` 中视频探针从历史 mock `v1` 改为真实 gamma fixture `fixture_video_001`。证据：① `python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py --env-name gamma-local ... --platform ios --device-id DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB` **passed**（`QWQ_OUTPUT_ROOT/env/repo/runs/device-matrix/environment-smoke/gamma-local-real.json`，`environment_basic_viability_smoke` 8s 绿）；② `python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all` **16 checks 全绿**（`.qwq_output/env/gamma/runs/20260705T133026Z-verify-gamma-local`）。剩余未闭合已收敛为两类：A. `python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py --strict-all` 仍因 `app_gamma_seed_manifest.json` 中 assistant/creator_pool/integration/notification/rtc 的 `verifiedEndpoints` 被记为 `not_ready` 而 `gate_block`，manifest 尚未只聚焦当前交集四主页闭环；B. 人工 probe 显示 `/v1/homepages/homepage_26/related-groups`、`/review-summary`、`/v1/circles/fixture_circle_photo/impact|members` 已 populated，但 `/v1/circles/fixture_circle_photo/feed` 与 `/v1/content/intersections/object?objectType=homepage|circle&objectId=...` 对当前 runtime id 仍空，四主页 populated real-data 与 prod-hosted gray 真实远端仍不能诚实宣称关闭。
  - 复核（2026-07-06 continue-dev）: 本轮继续把 R-IX05 压缩到“gamma-local 已绿、prod-hosted 未闭”这一层：① `python3 quwoquan_app/scripts/gamma/run_local_gamma_t3.py --strict-all --verification-scope object-homepage-gamma-real-data-closure` **passed**（`QWQ_OUTPUT_ROOT/env/gamma/local/gamma-local/process/t3_report.json`），homepage/circle bundle/detail/impact/object-intersection Story strict 全绿；② 展示层 W3 已收紧为“无 `primaryText` 不渲染、前台不再补写主句”，旧 `EvidenceGroup` 支路已删除，相关 Flutter 测试全绿；③ `flutter test test/api_integration/ui/intersection/intersection_remote_smoke__api_integration_test.dart --dart-define=RUN_LOCAL_GAMMA_REMOTE_SMOKE=true` **2/2 全绿**，真实补证 `getMyIntersectionSummary -> markIntersectionsVisited -> getMyIntersectionSummary` 远端清零链路；④ `flutter test test/user_acceptance/pages/entity/homepageDetail/homepageDetail_page__user_acceptance_test.dart test/user_acceptance/pages/circle/circleDetail/circleDetail_page__user_acceptance_test.dart test/user_acceptance/journeys/circle/circle_detail_journey__user_acceptance_test.dart` 全绿；⑤ 修复 `my_intersection_inbox_page.dart` 缺失 `resolvedIntersectionReasonKind` import 后，`python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py --env-name gamma-local ... --platform ios --device-id DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB --report QWQ_OUTPUT_ROOT/env/repo/runs/device-matrix/environment-smoke/gamma-local-real.json` 再次 **passed**，随后 `python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all` **16 checks 全绿**（`.qwq_output/env/gamma/runs/20260705T235459Z-verify-gamma-local`）；⑥ 只读拉取 `http://127.0.0.1:19220/metrics` 已观测到 `intersection_feed_candidates_total`、`intersection_feed_filtered_total`、`intersection_cooldown_exposure_reported_total`、`intersection_inbox_visit_total`。当前主阻断收敛为 prod-hosted：`python3 quwoquan_ops/cli/stackctl.py health --target prod-hosted --scope edge` 仍 **0/2 healthy**（`.qwq_output/env/prod/runs/20260705T235900Z-health-prod-hosted`，api/product-ops `/healthz` 均报 `SSL record layer failure`），因此真实 prod-hosted gray smoke 仍未闭环。
  - 状态: 进行中（字段漂移/客户端编译断点/Pin·Feature 持久化/PostCount 跨服务回写/WeeklyActive 窗口回写/Impact Explain 归一已解决并验证绿；2026-07-06 已把 gamma-local 侧进一步压实为 Story strict 绿、visit->summary 远端清零链路绿、entity/circle user_acceptance 绿、page-smoke 绿、全量 `stackctl verify --env gamma --kind all --tier all` 16 checks 绿。剩余主阻断已收敛为 prod-hosted gray：edge health 0/2 healthy（SSL record layer failure），故真实远端 smoke 与 R-IX05 关闭仍未完成）
- [x] R-IX06 搜索六场景端侧收口 + 术语退场关注者（WP-7，客户端，部分由 R-S06/R-S07 覆盖）
  - 区域: App
  - 域: `search` / `user`
  - 原因: 搜索 hit 真实 `connectionState` 闭集 + `intersectionReason` 子集、搜索交集 Tab 去本地拼装、实体页双交集源收口单源、术语「关注者」退场为「粉丝/关注/成员」、交集 G2 单句，均为端侧文案/装配收口。
  - 现状: 搜索云侧读模型/接线已在 R-S05/R-S06/R-S07 详细跟踪；服务端交集理由闭集（kind §5.4 + connectionState）已由 WP-0~2/WP-4 在云侧统一。端侧搜索交集 Tab 的本地拼装去除已收口（见 R-003 已解决）：交集分组唯一真相源改为云侧 `connectionState` 闭集，交集句严格只读 `intersectionReason.primaryText`，无 primaryText 不展示，删除 `_deterministicCount`/`_fallbackConnectionCardModels`/`_fallbackDiscoverCardModels`/`_friendActionLabel`/`_knownIntersectionEntity`/`_discoverContentReason`，并补 `_IntersectionContractSearchRepository` 契约测试（10/10 green）。术语退场为「粉丝/关注/成员」在 user/circle/entity widgets 切片内同步。
  - 影响: 搜索结果页交集理由/连接态的客户端合成已去除（第二真相源风险闭合）；剩余 R-008 跟踪的一般搜索 demo 回退（空集 fallback、硬编码实体置顶）与术语退场逐页核对。
  - 涉及文件: `quwoquan_app/lib/ui/search/**`、`quwoquan_app/lib/components/object_page/**`、`quwoquan_app/lib/ui/{user,circle,entity}/widgets/*`（术语）。
  - 证据（2026-06-19 复核）: ①搜索交集 Tab 本地拼装去除已解决（R-003 已 [x]）：分组唯一真相源为云侧 `connectionState` 闭集，交集句只读 `intersectionReason.primaryText`；②R-008 一般搜索 demo 回退已解决（R-008 已 [x]）：`_fallbackContentItemsForQuery` 在 `lib/` 零残留，`_entityTopResult()` 已改为真实读路径——遍历真实 `_locationResults` 中 `objectType==entityHomepage` 且标题匹配 query 的 hit，`meta` 由 `_entityMetaFromHit(hit)` 只读 `hit.payload` 的 `followerCount/contentCount`（无值则空），无「厦门大学/26.8万关注·1.2万内容」硬编码伪 meta；③术语「关注者」退场：`rg "关注者" quwoquan_app/lib --glob '*.dart'` 零命中，已全部退场为「粉丝/关注/成员」；④R-S06/R-S07 端云读模型联动前提已满足（R-S06、R-S07、R-S07-5、R-S06-S 均已 [x]）。
  - 状态: 已解决（2026-06-19；搜索交集 Tab 本地拼装去除[R-003]、R-008 一般 demo 回退[空集 fallback 删除 + 实体置顶只读 hit payload]、术语「关注者」lib/ 零残留退场、R-S06/R-S07 端云读模型联动均已闭合）
- [x] R-IX07 交集统一端到端验收：T3/T4 + 观测/SLO/灰度 + 全量 make gate（WP-8）— 四环境 stackctl 分层验证闭环（真机 patrol 巡检归 CI 设备矩阵）
  - 区域: App / Service / Ops
  - 域: `recommendation` / `search` / 多域
  - 原因: 服务端推荐/交集引擎（WP-0~5）的 T1（契约/静态）与 T2（模块/单测）证据已绿（content-service 全量 `go test`、`runtime/recommendation`、`runtime/recpolicy`、`verify-metadata`、`verify-ml-features`）。端云一体 T3（端云集成）、T4（用户旅程）、`make codegen-app` + 全量 `make gate` 需在客户端切片（R-IX05/R-IX06）与各域服务一并落地后统一验收。
  - 收口证据（2026-06-19 四环境 stackctl 分层验证，开发机实测）:
    - `stackctl verify --env {alpha,beta,gamma,prod} --kind all` 四环境各 10 checks 全绿（topology+config+packaging 契约/纯度/URL 隔离）。
    - `stackctl verify --env {alpha,beta,gamma,prod} --tier {t1,t2,t3}` 四环境逐层全绿（T1=10 / T2=12 / T3=11 checks，含端云集成）。
    - T4 用户旅程（widget 级）：端侧 `flutter test test/ui/user/journeys/{my_profile,other_profile,profile_tab_navigation}_journey_test.dart` + `my_intersection_inbox_page_test.dart` = 22 测全绿。
    - T4 真机巡检（`environment-page-smoke` → `run_environment_patrol_smoke.py`）接线验证：四环境 `STACKCTL_PAGE_SMOKE_DRY_RUN=1 stackctl verify --tier t4` 各 12 checks 全绿（命令构造 / dart-define 注入 / 拓扑 URL / token 接线正确）。真机执行（patrol CLI + 连接的 iOS/Android 设备）归 self-hosted 设备矩阵 CI `.github/workflows/app-env-device-matrix-self-hosted.yml`，开发机无设备无 patrol CLI，不在本地真实执行。
    - 顺手修复（零技术债）: `quwoquan_app/lib/core/media/avatar_image_url.dart` 的 `_isArchivedSeedAvatarObjectKey` 误把真实 `archived-avatar/user/user_<id>` 头像纳入 mock 种子回退重写，破坏 HEAD 既有契约 `chat_avatar_url_resolution_test.dart`（alpha tier T4 阻断）；删除该错误分支（仅 `s/mock/**` 与 `archived-avatar/seed/**` 回退），`avatar_image_url_test`/`content_media_url_test`/chat 头像/cached image 共 37 测全绿，alpha tier=all 转绿（15 checks）。
  - 已收口（2026-06-16 WP-E 观测）: 交集业务 SLI 漏斗指标已落地——`intersection_feed_candidates_total{channel,class,rank_state}`、`intersection_feed_filtered_total{channel,reason}`、`intersection_cooldown_exposure_reported_total`、`intersection_inbox_visit_total{dimension}`、`intersection_inbox_filtered_total{reason}`（DDD-clean：recorder 接口在 application、Prometheus 实现在 `infrastructure/intersectionmetrics`、main.go 注入），funnel 发射有单测 `intersection_metrics_test.go`。HTTP 延迟/错误/可用性走 `runtime/observability` http_server_* 中间件按 route 过滤。SLO 声明 `configs/observability/intersection_slo.yaml`（P95/可用性/重复曝光率/保鲜过滤率/展示完备率/事实占比/清零量 + 三级回滚分层），告警组 `quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_intersection`（4 条）。端侧曝光/点击/转化归因字段在 `content_behavior_tracker.dart` + `intersection_attribution_test.dart`（T2 绿）。
  - 影响: 观测/SLO/告警/回滚分层已定义并有真实指标源；剩余 gamma 真实采样需 R-IX05 拓扑/鉴权 seed；T4 用户旅程与全量 `make gate` 待客户端切片合流。
  - 本轮 gate 实测（2026-06-16 三 scope 复跑）: **三 scope gate 全绿** —— `bash quwoquan_ops/gate/gate_repo.sh --scope service` → `[gate] OK`（`/tmp/gate_service_next.log`）；`--scope data` → `[gate] OK`（`agent-tools` 输出末行 `[gate] OK`），本轮修复 `quwoquan_data/tests/local_contract/release/test_directory_evidence_gate__local_contract_test.py` 两个 happy-path fixture（`test_gate_entity_homepage_writes_review_sidecars`、`test_gate_passes_clean_object`）补齐实体主页 `2.quality/quality_analysis.json` + 百科底稿 + asset `sourceRef/sourceAssetRef/termsUrl`，与本轮收紧的 `build/homepage.py` 实体主页证据校验（quality sidecar + 图片权利链）对齐，`directory evidence gate tests passed (18)`；`--scope app` → `[gate] OK` / `APP_GATE_EXIT=0`（`/tmp/gate_app_next.log`）。**此前 R-IX07 把全量 `make gate` 阻断归因到仓库级术语门禁的描述已失效**：`python3 quwoquan_app/scripts/runtime/verify_retired_terms_zero.py` → `OK`、`python3 quwoquan_app/scripts/runtime/verify_concept_naming.py` → `[concept-naming] OK`，两处此前红灯均已转绿（上一轮 allowlist + 改词收口）。**全量 `make gate` 已绿**：`make gate`（部署/拓扑验证器 + global increment + agent context + 三 scope + portal 构建）→ `[gate] OK` / `FULL_GATE_EXIT=0`（`/tmp/gate_full_next.log`，4945 行；日志内两处 `download Gate FAILED`/`task run FAILED` 系负路径测试 `test_handle_download_blocks_unsafe_images_before_persist` 等的预期断言输出，非真实门禁失败）。
  - 涉及文件: `specs/feature-tree/object-homepage-network/intersection-unified-experience/acceptance.yaml`、`specs/feature-tree/global-search-experience/.../acceptance.yaml`、各域 T3/T4 测试、`quwoquan_data/tests/local_contract/release/test_directory_evidence_gate__local_contract_test.py`、`quwoquan_data/scripts/build/homepage.py`、`quwoquan_service/services/content-service/configs/observability/intersection_slo.yaml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`。
  - 状态: 已解决（2026-06-19；四环境 `stackctl verify --kind all` + `--tier t1/t2/t3` 全绿，端侧 T4 旅程 widget 测试 22 测绿，T4 真机巡检接线 dry-run 四环境绿；observability/SLO/告警/三 scope `make gate` 此前已绿）。唯一非本地可执行项：T4 真机 patrol 巡检需 self-hosted Mac runner + 连接设备 + patrol CLI，归设备矩阵 CI 执行（非业务缺口，开发机环境前置缺失，不在本地伪装执行）。

## 交集定义与应用 Phase 0（intersection-definition-and-application）

> 真相源 spec：`specs/product/intersection-definition-and-application.md`。交集契约对齐（A–E）的 Phase 0 已落地；以下为用户确认后登记的两项「交集漂移」延后事项，均不阻塞 A–E 端侧契约与 UI 实现，附精确交接坐标，按独立排期推进。

- [x] R-ID01 交集漂移 a：content-service reason 级 Label/DisplayText/SharedCount 未移除
  - 区域: Service
  - 域: `content`
  - 事项: content-service 的 Go `IntersectionReasonView` 仍保留已被契约（§18.1）删除的 `Label/DisplayText/SharedCount` 三个 reason 级字段，Explain 管线仍依赖它们做计数聚合（如 followeeVisited）。
  - 原因: 移除需改 `followeeVisitedReason` 计数语义（`SharedCount=n` → 单聚合点 `Count=n`）+ `anchorAggregateCount` bridge 分支 + 4 个 Go 测试（含 `viewer_object_intersection_store_contract_test.go` 直接断言 `r.SharedCount`）；Phase 0 为避免半成品破坏 `go test` 而诚实延后。
  - 影响: 纯服务端内部清理；端侧 Dart DTO 已无这些字段，不影响 A–E 任何端侧契约与 UI 实现；属技术债，可独立排期。
  - 验证证据/交接: 精确改动集见 `specs/product/intersection-definition-and-application.md` §20.6。
  - 证据（2026-06-19 复核）: ①契约 `quwoquan_service/contracts/metadata/recommendation/model_release/projections/intersection_reason.yaml` 第 34 行明确「本契约已零兼容删除 displayText / label / sharedCount（§18.1 一次性收口）」，reason 级三字段在契约层已移除；②Go `services/content-service/internal/application/intersection/intersection_views.go` 的 reason 级结构 `IntersectionReasonView` 已无 `Label/DisplayText/SharedCount`，`intersection_hydration.go` 注释「R-ID01：不再有 reason 级 SharedCount」；③测试 `tests/intersection_source_contract_test.go` 残留的 `DisplayText` 断言全部是 **point 级** `IntersectionPointView.DisplayText`（如 `shared.DisplayText`/`commented.DisplayText`），`intersection_source.go` 的 `Label/DisplayText` 也只赋给 `IntersectionPointView`（point 级合法字段，不在 §18.1 reason 级删除范围）；④结论：§18.1 要求删除的 reason 级三字段已全部移除，Explain 紧凑结论句唯一来源为 `primaryText`，契约与代码一致。
  - 状态: 已解决（2026-06-19；契约 intersection_reason.yaml §18.1 零兼容删除 reason 级 displayText/label/sharedCount，IntersectionReasonView 无三字段，残留 DisplayText 断言均为 point 级合法字段）
- [ ] R-ID02 交集漂移 e：4 个交集 operation 缺 response_body schema（Slice 1 已交付框架能力+绑定，剩余 Go/OpenAPI epic）
  - 区域: Service
  - 域: `content`
  - 事项: 保留的 4 个交集 operation（`GetMyIntersectionSummary` / `ListMyIntersections` / `MarkIntersectionsVisited` / `GetObjectIntersections`）未在 metadata 显式声明 `response_body` schema。
  - 原因: 当前仓库 metadata 全仓无 `response_body` 能力（`rg response_body contracts/metadata` 零命中），responses 由 Go handler 隐式承载，需先做 metadata 框架增强而非单点引入。
  - 影响: 不阻塞 A–E——projection consumers + 描述已声明 `read_model`，端侧 Remote 已按 `read_model` 正确解析；属契约显式化的框架级增强，需统一排期。
  - 验证证据/交接: 见 `specs/product/intersection-definition-and-application.md` §20.5。
  - 本轮收口（2026-06-20，Slice 1 = 框架能力 + 首批绑定 + 门禁 + 端侧消费）:
    1. **框架能力（verify_metadata）**: `tools/verify_metadata/main.go` 先修复 `validateServiceEntities` 空转 latent bug（原解析不存在的 `routes` 键→对所有 `api_routes` 零校验），再引入 `response_body`/`response_body_kind` 强校验：kind∈{object,page,ack}；ack 禁带 body、object/page 必带 body；`response_body` 必须命中全仓 `projections/*.yaml` 的 `read_model`/`client_projection.dart_class` 闭集（新增 `loadProjectionReadModels` 全仓索引）。原 `response_entity` 误报由 14→4（仅剩既有命名错配），`go test ./tools/verify_metadata` 绿。
    2. **首批绑定（service.yaml）**: `content/post/service.yaml` 5 个 operation 声明 `response_body`/`response_body_kind`：`GetMyIntersectionSummary`=object→`IntersectionInboxSummary`、`ListMyIntersections`/`GetObjectIntersections`=page→`IntersectionReason`、`MarkIntersectionsVisited`=ack（无 body）、`ListAuthorImpactEvidence`=object→`AuthorImpactEvidencePage`（R-ID03 端侧接入协同绑定，2026-06-20 补）。
    3. **端侧 codegen（codegen_app_metadata）**: `routeDef` 加 `ResponseBody`/`ResponseBodyKind`；`collectProjectionReadModelDartClass` 建 read_model→dart_class 全仓索引；`renderDomainAPIMetadataDart` 生成 `operationToResponseModel`/`operationToResponseKind` 两张静态映射（content 实表 3+4 项，其余 13 域空表统一字段）。codegen 幂等（重生无新增漂移），`go test ./tools/codegen_app_metadata` 绿。
    4. **门禁**: 新增 `quwoquan_app/scripts/runtime/verify_metadata_response_body_vs_codegen_app.py`（四维交叉校验 metadata↔codegen↔projection＋反向 orphan 检测），已串 `quwoquan_ops/gate/gate_repo.sh` app 段；证伪通过（非法 kind→FAIL）。
    5. **端侧消费（防死字段）**: 新增 `test/cloud/integration/intersection_response_body_contract_test.dart`（5 绿），断言生成映射值 == Remote 仓库真实解码运行时类型（object→`IntersectionInboxSummary`、page→`IntersectionReason` 元素、ack→不入 model 表且返回 void）。
  - 剩余 epic（独立排期，本回合不做）:
    a. Go 侧消费 `response_body` 生成响应类型契约/装配（当前 Go handler 仍隐式承载）；
    b. 新建 metadata→OpenAPI 响应 schema 生成器（全仓无 OpenAPI 响应生成）；
    c. content/app codegen 产物漂移门禁（防 Go 响应类型与端侧 DTO 漂移）；
    d. 将 `response_body` 从「首批 4 op」推广为全仓 operation 绑定（框架能力 + 门禁已就绪，可增量逐域绑定，不再是「唯一特例债」）。
  - 状态: 部分收口（2026-06-20；Slice 1 框架能力+5 op 绑定（4 交集 + `ListAuthorImpactEvidence`）+端侧 codegen 映射+一致性门禁（`verify_metadata_response_body_vs_codegen_app: OK (5 response_body operations)`）+合约测试已闭环，端云无断点；剩余 Go 响应 codegen / OpenAPI 生成器 / 产物漂移门禁 / 全仓推广属框架横切 epic，spec §20.5/§20.6.2）
- [x] R-ID03 我打动的人完整分页明细 API 缺失
  - 区域: App / Service
  - 域: `content` / `recommendation` / `user`
  - 事项: `listAuthorImpactEvidence` 完整分页打动明细 API 尚未实现；当前「我打动的人」明细只能展示云侧 `AuthorImpactItem.sampleVisuals` 样本。
  - 原因: 本轮我的主页交集重构只冻结了可交互结论句、样本视觉与 `evidenceSnapshotId`，未新增完整 evidence 分页 operation、服务端读模型与端侧分页列表。
  - 影响: 用户可点击打动数字打开样本明细，但暂时不能查看全量来源名单；端侧必须继续保持「只展示云侧样本，不编造全量」的降级语义。
  - 正确设计: metadata-first 新增 `listAuthorImpactEvidence` operation + 强类型 evidence read model，服务端按 `evidenceSnapshotId`/`impactId` 分页返回真实影响来源；端侧明细 sheet/page 只读该 API，仍复用 `IntersectionTarget` / `IntersectionVisual` / `InteractiveIntersectionText`。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/post/projections/author_impact_evidence_item.yaml`、`author_impact_evidence_page.yaml`、`quwoquan_service/contracts/metadata/content/post/service.yaml`、`quwoquan_service/services/content-service/internal/infrastructure/persistence/author_impact_evidence_store.go`、`internal/application/author_impact_evidence_view.go`、`internal/adapters/http/content_handler.go`、`runtime/impact/explain.go`、`quwoquan_app/lib/cloud/runtime/generated/content/author_impact_evidence_{item,page}.g.dart`
  - 证据: metadata-first 冻结 `AuthorImpactEvidenceItem`/`AuthorImpactEvidencePage` projection + `ListAuthorImpactEvidence` operation（`GET /v1/content/sub-accounts/{subAccountId}/author-impact/evidence?impactId=&evidenceSnapshotId=&cursor=&limit=`）；云侧 `rm_author_impact_evidence`（Mongo，`sourceEventId` 唯一索引保证幂等）+ cursor 分页；`StableImpactID`(SHA1) 对齐 summary `AuthorImpactItem.impactId`；读路径 hydrate 内容标题/封面，结论句经 `runtime/impact.EvidenceText` 隐私安全直出（「有人…」，不泄露 actorId）。T3 集成测试 `author_impact_evidence_contract_test.go` 全绿：契约/隐私（"有人"前缀且无 actorId 泄露）/幂等（同 clientEventId 重放不重复计数）/分页触底（hasMore=false）/空态（未知 impactId 返回空不编造）/summary-evidence count 一致性。`make verify-metadata` + `make codegen-app` 绿，Dart DTO（typed 嵌套 IntersectionVisual/IntersectionTarget）已生成。
  - 端侧接入闭环（2026-06-20，本回合补齐「服务端已就绪但端侧未消费」断点）: ①仓库三层 `UserProfileRepository.listAuthorImpactEvidence({subAccountId,impactId,evidenceSnapshotId,cursor,limit})`——Abstract+Mock（无 seed/未命中 impact 返回空页，不编造）+Remote（经 `ContentApiMetadata.listAuthorImpactEvidencePath` path builder + query `impactId/limit/cursor`，`_decodeObject`→`AuthorImpactEvidencePage`）；②`AuthorImpactEvidenceSheet` 重构为 `StatefulWidget` + 注入 `AuthorImpactEvidenceFetcher` 闭包（DI，脱 Provider 依赖便于测试），首屏拉取 + 触底「加载更多」+ 空态/失败结构化降级（R17，不崩溃）；明细以被影响内容为载体逐条展示（summaryText+时间+样本），整行可点进被影响内容；分页为空/失败回退聚合样本视觉（仅当 `sampleVisuals` 非空），既不编造完整名单也不暴露 actorId；③调用方 `author_impact_card.dart` / `my_intersection_impact_timeline.dart` 经 `userProfileRepositoryProvider` 构造 fetcher 下沉（`ref.read` 延迟到 sheet 打开）；④文案常量入 `discovery_feed_text_constants.dart`。测试：`test/cloud/user/contract/author_impact_evidence_contract_test.dart`（5 绿：response_body kind/model 契约、Remote path/query/解码/cursor 翻页、Mock 无 seed 空安全）+ `test/ui/user/widgets/author_impact_evidence_sheet_test.dart`（5 绿：真实来源行渲染、触底翻页、整行进内容、空态/失败降级、空页+样本回退）+ `author_impact_card_test.dart`（无样本+分页空→空态文案，8 绿）。
  - 状态: 已解决（2026-06-19 服务端③⑤切片闭环；2026-06-20 端侧仓库三层+分页 sheet+调用方接线+端云契约/widget 测试闭环，用户可在「我打动的人」明细下钻查看云侧完整分页来源，无端云断点）

- [x] R-ID04 主页首屏聚合 user homepage-bundle（决策 #1）端云冻结
  - 区域: App / Service
  - 域: `user`
  - 事项: 主页首屏从「串行多请求」收敛为「一次聚合 + 并发补充」的 `GetUserHomepageBundle` 端云能力。
  - 正确设计: metadata-first 冻结 `UserHomepageBundleWire`（嵌套 `SubAccountProfileWire`/`UserProfileStatsWire`/`RelationshipCapabilityWire` + 新增 `UserHomepageTabCountsWire`/`UserHomepageViewerContextWire` + `cacheVersion`）；`GET /v1/user/sub-accounts/{subAccountId}/homepage-bundle`（auth=optional，游客可读公开档案）。红线：user 域只聚合身份域真相，交集卡与打动 evidence 仍由 content 域端侧并发拉取，user 域不做 content 事实第二真相源。
  - 涉及文件: `quwoquan_service/contracts/metadata/user/user_profile/projections/user_homepage_{bundle,tab_counts,viewer_context}_wire.yaml`、`service.yaml`、`quwoquan_service/services/user-service/internal/adapters/http/homepage_bundle_handler.go`、`quwoquan_app/lib/cloud/runtime/generated/user/user_homepage_*_wire_dto.g.dart`
  - 证据（云侧已闭环）: `make verify-metadata` + `make codegen-app` 绿（typed 嵌套 DTO 已生成，path builder `getUserHomepageBundlePath`）；T3 契约测试 `homepage_bundle_contract_test.go` 全绿：本人态（isOwner/relationToTarget=self + stats/tabCounts 等于身份域计数真相）/游客态（isGuest=true 且不下发 relationshipCapability，不造假）/陌生态（relationToTarget=not_following + canFollow=true）/strict 隔离 404/架构红线（bundle 不携带 intersections/authorImpact/evidence/feed 等 content 事实）。
  - 证据（端侧已闭环，切片⑦）: repository 三层（Abstract/Mock/Remote，Mock 用 contract fixture，Remote 走 `getUserHomepageBundlePath` + `CloudResponseDecoder`）+ 强类型 `UserHomepageBundleViewData`（新增 `UserHomepageTabCountsViewData`/`UserHomepageViewerContextViewData`；关系能力**单源化复用既有 `RelationshipCapabilityDto`**，删除冗余 `RelationshipCapabilityViewData` 第二真相源，R24）；provider 经 `appDataSourceModeProvider` 透明切换；`ProfileNotifier.loadProfile` 用 `Future.wait` 一次聚合身份域真相 + 作品/帖子并发补充，**bundle 关系能力 seed 免首屏额外 `getCapability` 串行**；首屏聚合失败保留 `rawError` 经 `runtimeErrorSemantic` 渲染结构化 `AppPageErrorState`+重试（不被乐观壳层静默吞掉，R17/R20）。T1/T2 全绿：`user_profile_repository_contract_test.dart`(46) + `profile_state_provider_test.dart`(4，含「bundle 提供关系能力后不再串行 getCapability」与「失败进入结构化错误态」) + `profile_shell_widget_test.dart`(24，含「首屏聚合失败渲染结构化错误态并提供重试」)；`make verify-app-mock-isolation` / `make verify-app-page-horizontal-quality` / `make codegen-app`（端侧无漂移）全绿。
  - 状态: 已解决（2026-06-18；云侧 metadata+handler+T3 + 端侧 ProfileShell 三层接入，homepage-bundle 端云回路闭环，T1/T2 全绿；T3 端云联调与 T4 旅程随切片⑧四环境验证）

- [x] R-ID05 user-service 基线既有红测（与主页/交集任务无关域，源自基线提交 35f8a75b）— 已全部零技术债修绿
  - 区域: Service
  - 域: `user`（auth / follow / greeting / migration）
  - 事项: `services/user-service/tests` 在干净检出上存在 7 个既有失败测试，均不在主页/交集任务改动集，单独运行（非全包污染）同样失败：
    1. `TestLogin_CreatesOwnerAccountOnFirstUse` / `TestLogin_ExistingCredentialReturnsOwner`：测试打已废弃的通用端点 `POST /v1/auth/login`（404）；基线 35f8a75b 已重构为 method-specific 路由（`/v1/auth/login/phone|wechat|...`）但未更新该 stale 测试。
    2. `TestManagedMigrationsAreIdempotent`：测试硬编码期望 15 个迁移，实际 16（基线已新增 `016_consent_records`，测试常量 stale）。
    3. `TestFollow_Idempotent`：重复 follow 后 `follower_count=2`（期望 1）+ 缺 `follow_duplicate_request_count` 计数——follow 命令幂等性既有缺陷。
    4. `TestGreeting_IgnoreAndCancel`：ignore 后 resend 返回 500（期望 201）——greeting 状态机 resend 既有缺陷。
    5. `TestBlockCascade_ClearsFollowAndPendingGreeting`：互关用户发 greeting 被 `already_contact` 409（测试 setup 与「互关直达私信」新语义冲突，stale）。
    6. `TestListFollowing_PaginationFillsVisibleItemsAfterFiltering`：过滤后分页补齐既有缺陷。
  - 根因定性: 全部由基线提交 `35f8a75b 收敛当前产品与交付基线`（login 路由重构 + 016 迁移）与更早 `13672eb3` 遗留，均在本会话前已存在于 HEAD；本任务 build/vet 与改动文件与之无交集（`git status` 仅命中本任务新增 bundle/handler/test 与 fixture）。
  - 本任务顺手收口（profile 读取域，零技术债）: 已修复并转绿 2 项 —— (a) `scanUserProfileRow` 漏绑 `&e.IdentityTags`（query 选 26 列 scan 仅 25 dest，致 `TestSearchSocialRelations_DoesNotExposeOwnerUserID` 500）；(b) 共享 fixture `createTestProfile` 漏插 `identity_tags`（NULL 无法 scan 进非空 `*string`，致 `TestSubAccountView_GetSubAccountProfile` 等 500）。
  - 影响: 属 auth/follow/greeting/migration 域的提交态 stale 测试与既有逻辑缺陷；不阻塞主页 homepage-bundle/交集/打动 evidence 端云能力（其 T3 已绿）。
  - 解决（2026-06-19，逐个 root-cause + 零技术债修绿，含 2 个真实生产缺陷 + 2 个测试基建缺陷 + stale 修正）:
    1. **migration（stale → 真相源对齐）**: `migration_runner.go` 新增只读导出 `ManagedMigrationFilenames()`；测试改为断言 ledger 行数 == 磁盘受管迁移数（不再硬编码，防再 stale）。
    2. **login×2（废弃端点）**: 统一 `/v1/auth/login` 已重构为 method-specific 路由。后续范围确认 Apple/Passkey 暂不支持，2026-07-12 已从 metadata、App Remote Repository 与 user-service handler 移除 `POST /v1/auth/login/{apple,passkey}`；`TestUnsupportedFutureLoginMethodsAreNotPublic` 断言两路由返回 404，避免将未校验 token 或未实现 assertion 当作凭证。
    3. **follow 幂等（测试基建缺陷）**: `cleanAll` 用 `Drop` 删除 mongo 集合连带删除唯一索引 `idx_follow_unique`，导致首个 follow 测试后所有后续测试幂等失效（insert 不再触发 duplicate key）。改为 `DeleteMany` 清文档、保留 testmain 建立的索引。
    4. **listfollowing 分页（真实生产缺陷，2 处）**: (a) `listEdges` 用 `createdAt $lt` 单键 cursor，bulk follow 同毫秒 createdAt 被整体跳过 → 改 `(createdAt, followerId, followeeId)` 复合 keyset；(b) cursor 选取 off-by-one——以 overfetch 的 limit+1-th 元素作 cursor 又被下一页 `$lt` 排除，每翻页丢 1 条 → 改为最后返回元素作 cursor。
    5. **greeting resend（真实生产缺陷，metadata→codegen）**: `idx_gr_unique_pending` 命名为「仅 pending 唯一」但实际全状态唯一，ignored 旧行挡住 resend（500）。根因：metadata 用 `where:` 键、codegen `IndexDef` tag 为 `condition`，偏条件被静默丢弃。按全仓约定改 greeting storage.yaml `where:` → `condition:`，`make codegen-storage` 重生 014 迁移含 `WHERE status='pending'` 偏唯一索引。
    6. **block cascade（测试前提矛盾 + 断言补强）**: setup 建互关后发 greeting 被正确以 `already_contact` 拒绝（与互关直达私信语义一致）。改为单向 follow（可建 pending greeting），并补「block 级联清 follow 边」断言（GetRelationship.isFollowing=false），honor 测试名 ClearsFollow。
  - 顺手修复连带基建缺陷: `createTestProfile` 的 phone 取 `userID[:16]` 前缀截断，共享前缀 userID（`filtered_target_a/b/c`）碰撞唯一约束 → 改为 `xxhash` 派生紧凑唯一 phone。
  - 验证证据: `go build ./... && go vet ./internal/... ./tests/...` 全绿；`go test ./tests/...` 全包绿（`ok ... 36.5s`，0 失败）；codegen 重生仅影响 greeting 014 迁移（无其他迁移 drift）。
  - 涉及文件: `tests/{credential_contract_test.go,migration_idempotent_test.go,follow_contract_test.go,greeting_request_state_machine_test.go,block_cascade_contract_test.go,helpers_test.go}`、`internal/infrastructure/persistence/{migration_runner.go,mongo_follow_store_ext.go}`、`contracts/metadata/user/greeting_request/storage.yaml`、`internal/infrastructure/migration/014_greeting_requests.up.sql`（codegen 产物）
  - 状态: 已解决（7/7 红测转绿 + 全包绿；2 真实生产缺陷[follow 分页 keyset / greeting 偏唯一索引]、2 测试基建缺陷[cleanAll Drop / phone 碰撞]、3 stale 修正均零技术债收口）

- [x] R-ID06 交集 Graph 边权 / Lifecycle 弱标 / Propagation 多跳异步物化真算（切片⑥）
  - 区域: Service
  - 域: `recommendation` → `content`
  - 事项: `IntersectionReasonView` 的 `edgeWeight`/`lifecycleState`/`previousStrength`/`strengthDelta` 字段此前为占位（metadata 注释「云侧逻辑后置/本期默认 0」），读路径直出恒 0；Graph 边权未真算、生命周期弱标无来源、Propagation 多跳证据未参与加权。
  - 正确设计（读路径零同步打分不变量 R-IX01 保持）: 在 `ReadModelIntersectionSource` 写/刷新路径做确定性异步物化——`edgeWeight = relationStrength × interactionFrequency × recencyDecay`（三因子全部源自理由自身真实信号，纯算术、零评分服务调用）；Lifecycle 状态机以上一次物化快照为增量基线对 edgeWeight 比对落 `new|strengthened|stable|weakened|reactivated` 弱标并回填 previousStrength/strengthDelta；Propagation 多跳由交集点携带的绝对计数（共同好友/共同圈子等可追溯证据）经指数饱和派生 interactionFrequency；affinity 通道复用同一边权真算替换原裸 count 启发式（`affinityIntersectionScore` 不再恒 0）。读路径热命中仅消费快照、零计算、零同步打分。
  - 涉及文件: `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_graph_materializer.go`（新增物化器）、`read_model_intersection_source.go`（写路径接入 + affinity/object 边权真算）、`intersection_graph_materializer_test.go`/`read_model_intersection_source_test.go`（白盒单测）、`tests/viewer_object_intersection_store_contract_test.go`（T3 物化持久化）、`contracts/metadata/recommendation/model_release/projections/intersection_reason.yaml`（注释同步：字段已由异步物化真算填充）
  - 证据: 白盒单测覆盖三因子边权乘积/recency 半衰期衰减+floor/Propagation 绝对计数单调饱和/evidenceCount 取点和/Lifecycle 五态（new→strengthened→stable→weakened→reactivated）/边权确定性有界/identity key 稳定匹配 + 跨重算物化（首读 new→TTL 内 fresh 命中零回算消费已物化字段→过 TTL 重算 strengthened 且 previousStrength=上次 edgeWeight）；T3 真实 Mongo `TestViewerObjectIntersectionMaterialization_PersistsGraphLifecycle` 证明经读模型写路径物化 edgeWeight>0+lifecycle 并精确固化；`go test ./internal/...`（含 recommendation/application）+ `go test ./tests/...` 全包绿；R-IX01 不变量契约测试保持绿（读路径零同步打分未回归）。
  - 状态: 已解决（2026-06-19；切片⑥ 确定性 Graph/Lifecycle/Propagation 物化真算闭环，读路径零计算消费，R-IX01 保持）

- [x] R-ID07 Redis 不可用降级 + 已读水位持久兜底（切片 D）
  - 区域: Service
  - 域: `content`（intersection）
  - 事项: 交集写路径（`ReportExposure` 冷却记忆窗、`MarkVisited` 已读水位）在 Redis 失败时硬向上抛错，会拖垮主请求；已读水位仅存 Redis（ix:watermark，90d TTL），Redis flush/宕机将丢失用户清零状态（红点回弹为未读），无持久兜底。
  - 正确设计: ①写降级不阻断——`ReportExposure`（尽力而为去重信号）Redis 失败仅记降级指标+结构化 warn 日志后返回 nil；②已读水位持久兜底——新增 `WatermarkStore` 接口 + Mongo `rm_intersection_watermark`（`$max` 逐维度单调推进 upsert）作为耐久真相源，Redis 退化为加速读缓存；`MarkVisited` 先写耐久（真相源，仅耐久写失败才向上抛错）、再尽力回写 Redis（失败仅降级）；`watermarks` 读优先 Redis（热路径），失败/缺失回落耐久并尽力回暖 Redis（flush/宕机后读位不丢）；③可观测——新增 `intersection_redis_degraded_total{op}` 指标 + SLO `redis_degraded_rate`/`watermark_durability_fallback_rate` SLI + 告警 `IntersectionRedisDegradedHigh`。
  - 涉及文件: `internal/application/intersection_service.go`（WatermarkStore 接口 + 三方法降级/兜底重写 + logger/store 选项）、`intersection_metrics.go`（ObserveRedisDegraded）、`internal/infrastructure/recommendation/watermark_store.go`（新增 MongoWatermarkStore）、`internal/infrastructure/intersectionmetrics/metrics.go`、`cmd/api/main.go`（注入耐久 store+logger）、`configs/observability/intersection_slo.yaml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`、`intersection_service_test.go`/`intersection_watermark_store_contract_test.go`（T2/T3）
  - 证据: T2 应用层单测 —— Redis 宕机时 `MarkVisited` 降级返回 nil 且耐久持久化+发 `watermark_write` 降级指标；`watermarks` Redis 故障回落耐久读位+发 `watermark_read`；Redis flush（可用但空）从耐久恢复并回暖 Redis（再读命中 Redis、不再触达耐久）；`ReportExposure` Redis 宕机降级返回 nil+发 `exposure_write`；耐久写真失败（Mongo down）仍向上抛错（真相源不静默丢失）。T3 `TestIntersectionWatermarkStore_RoundTripAndMonotonic` 真实 Mongo 往返 + `$max` 单调（旧时间戳被拒不回退）。`go test ./internal/...`+`./tests/...` 全包绿；告警/SLO YAML 语法校验绿。
  - 状态: 已解决（2026-06-19；切片 D 写降级不阻断 + watermark 持久兜底 + 可观测闭环）

- [x] R-ID08 切片⑧全量 gate 暴露的基线既有红测/契约缺口（与主页/交集任务无关域，顺手零技术债修绿）
  - 区域: Service
  - 域: `rtc` / `recommendation`(runtime) / `content`(feed)
  - 事项: 跑服务侧全量 `make gate` + `go test ./runtime/...` + user-service 全量时，暴露 5 处基线既有失败/缺口，均非本任务（交集/主页）回归，但阻断「全量 gate 全绿」：
    - ① RTC 错误码 HTTP 映射漂移：`runtime/errors.HTTPStatusFromError` 是按 code 第三段（`Code.Reason`）枚举的硬编码 switch，而 RTC 码用描述性第三段（`already_in_call`/`call_full`/`cannot_answer`/`invalid_call_action`/`screen_share_conflict`/`call_ended`/`not_participant`/`not_mutual`/`blocked`/`recording_not_allowed`）与 `errors.yaml` 声明的 `http_status` 漂移，全部 fall through 到默认 500。`TestContract_InitiateCall_ConflictWhenActive` 期望 409 实得 500。
    - ② RTC 测试用废弃 callType：`one_to_one_relationship_gate_test.go` 用 `CallType:"voice"`，但域有效类型仅 `audio`/`video`，`TestInitiateCall_OneToOne_AllowsMutual` 因 `invalid call type` 失败（另两测因 mutual/blocked gate 在类型校验前拦截才偶然通过）。
    - ③ 推荐七态漏斗重构后的 3 处陈旧测试：`runtime/registry TestGetEnum`（ContentType 漏 `review`，HEAD 已加该枚举值但测试未同步）、`runtime/redis TestRecAdapter_HotPathIntegration` 与 `runtime/context TestPageContextManager_ForwardsUserActionsToHotPath`（均编码重构前「like→exposed/ExposedIDs」旧语义，新漏斗 like→interaction、`SessionState.ExposedIDs` 有意恒 nil、曝光仅由 feed 下发 `RecordServed` 标记）。
    - ④ feed `feedRequestId` 服务端权威化契约缺测：`contract.yaml` 已声明 scenario `get_feed_issues_server_feed_request_id`（go_func `TestFeedIssuesServerFeedRequestID`，非 pending）但无对应 Go 测试，G11 门禁 BLOCK。
  - 正确设计/修复（零技术债，对齐唯一真相源）: ①把 RTC 全部 reason 段按 `errors.yaml` 声明的 http_status 补进 `HTTPStatusFromError`（conflict→409、call_ended→410、forbidden 组→403），与 metadata SSOT 对齐，并加 `TestHTTPStatusFromErrorSupportsMetadataUserSubKinds` RTC 子用例锁定防回退；②RTC 测试改用有效 `audio`；③3 处陈旧测试重写对齐新七态漏斗 SSOT（`observability_funnel_test.go`）——registry 期望集补 `review`、HotPath 集成测试改为「`RecordServed` 标记曝光 + like 驱动 interaction 标签权重 + 断言 ExposedIDs 恒空」、context 转发测试改用会话标签权重验证转发；④补 `TestFeedIssuesServerFeedRequestID`（首刷 `frq_` 前缀 + rankingVersion/reasonVersion + 回显归因 id 连续）。
  - 涉及文件: `runtime/errors/errors.go`、`runtime/errors/errors_test.go`、`runtime/registry/registry_test.go`、`runtime/redis/adapter_test.go`、`runtime/context/context_test.go`、`services/rtc-service/tests/one_to_one_relationship_gate_test.go`、`services/content-service/tests/post_feed_contract_test.go`
  - 证据: `make gate`（服务侧 scripts/gate.sh）→ `[gate] OK`（assistant/content 17.5s/rtc/product-ops/tag/recommendation python/ML + 元数据/特性树一致性全绿）；`go test ./runtime/...` 全包绿（OVERALL_EXIT=0）；`go test ./services/user-service/...` 全包绿（USER_EXIT=0，确认共享 errors.go 改动无回归）；`go test ./services/rtc-service/...` 全包绿（含两个原失败测试）。
  - 状态: 已解决（2026-06-19；切片⑧服务侧全量 gate 闭环，5 处基线红测/缺口零技术债修绿）

- [ ] R-ID09 我的主页交集/打动服务端读路径契约与高并发风险
  - 区域: App / Service
  - 域: `content` / `user`
  - 事项: `ListMyIntersections` metadata 与端侧已声明/透传 `filter/sourceRef/timeBucket/cursor/limit`，但服务端 handler/application 仍需逐项核实并补齐真实过滤/分页契约；`ProfileInteractionActivities` 当前存在请求期全量扫描 + 循环读 post 的风险；`AuthorImpactEvidence` 明细页存在 Count + N+1 hydrate 读放大风险。
  - 原因: 本轮 UX/UI 收口已完成端侧 `cursor` 扩展位、详情双 tab、fixture 全类型实例化与能力级 SIT 验收，但服务端读路径尚未同步落地全部过滤/分页/性能硬化；高互动账号、热门作者或大内容库下会放大请求成本。
  - 影响: beta/gamma/prod 高并发下可能出现交集筛选分页契约漂移、互动 Tab 请求延迟升高、热门打动明细 Mongo/post store 压力升高；不会影响本轮前端视觉体验和 mock/contract fixture 展示，但会影响真实规模化准出。
  - 正确设计:
    1. `ListMyIntersections` 服务端按 metadata 支持 `dimension/filter/sourceRef/timeBucket/cursor/limit`，无法支持的参数必须显式契约化拒绝，禁止静默忽略；
    2. profile interaction 读路径迁移到分页 read model 或至少补可审计索引/limit clamp，避免全局锁内无限扫描与循环 `FindByID`；
    3. author-impact evidence 分页避免每页重复 Count + N+1 hydrate，至少做到同页 contentId 去重 hydrate、limit clamp、summary count 与 evidence total 一致；
    4. App 侧同一主页停留内 `GetAuthorImpact` 与交集 preview 需要 Provider 级短时去重/缓存，避免 rebuild 重复打服务。
  - 验收标准:
    1. T3 contract 覆盖 `ListMyIntersections` 的 `filter/sourceRef/timeBucket/cursor/limit`；
    2. 高互动测试种子下 profile interaction 不在全局锁内做 O(全量互动) 扫描；
    3. author-impact evidence `limit > 50` clamp、同页 hydrate 去重、summary/evidence count 一致；
    4. App fake repository 计数测试证明同一主页停留内交集 preview 与 author impact 不因 rebuild 重复请求。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/post/service.yaml`、`quwoquan_service/services/content-service/internal/adapters/http/intersection_handler.go`、`quwoquan_service/services/content-service/internal/application/intersection/intersection_service.go`、`quwoquan_service/services/content-service/internal/application/post/post_service.go`、`quwoquan_service/services/content-service/internal/adapters/http/content_handler.go`、`quwoquan_service/services/content-service/internal/infrastructure/persistence/author_impact_evidence_store.go`、`quwoquan_app/lib/ui/user/providers/my_intersection_inbox_provider.dart`、`quwoquan_app/lib/ui/user/providers/author_impact_provider.dart`
  - 本轮部分收口（2026-06-20）:
    1. `ListMyIntersections` handler/application 已消费 `dimension/filter/sourceRef/timeBucket/cursor/limit`，返回 `items/nextCursor/hasMore`；新增 `TestIntersectionService_ListFiltersAndPaginates` 覆盖 sourceRef/timeBucket/cursor/limit。（对应验收 #1）
    2. `AuthorImpactEvidenceStore.ListPageWithTotal` 用 Mongo facet 同页返回 items + total，替换 handler 中 Count + List 双读；同页 contentId hydrate 已保留去重。（对应验收 #3）
    3. **App Provider 级短时去重（A2，闭验收 #4）**: 交集 preview 与 author impact 改用容器作用域 `TtlCache`（无定时器、按 key TTL 去重、`force` 显式绕过），同一主页停留内 rebuild 不重复打服务；`flutter test test/ui/user/providers/intersection_provider_cache_test.dart` 5 绿（preview 重复 load 仅取数一次 / TTL 窗口取消订阅再订阅复用 / force 绕过 / authorImpact TTL 去重 / 不同 userId 各自取数互不串用）。
    4. 验证: `go test ./services/content-service/internal/application ./services/content-service/internal/infrastructure/persistence ./runtime/impact` 绿；`flutter test test/ui/user/widgets/profile_shell_widget_test.dart`、`test/ui/user/providers/intersection_provider_cache_test.dart` 绿。
    5. **share 路径持久化读模型（2026-07-12，验收 #2 部分闭环）**：`type=share` 已从 `ProfileInteractionActivities` 请求期全量扫描迁移到独立 `ShareInteractionOccurrence` Mongo read model，使用 `(targetSubAccountId, occurredAt DESC, interactionId DESC)` / `(actorSubAccountId, occurredAt DESC, interactionId DESC)` 索引与 keyset cursor；seen/read 在同一 store 幂等持久化，服务重建后历史不丢。
    6. share 证据：`go test ./services/content-service/...` 全绿；`profile_share_interaction__local_contract_test.go` 覆盖同时间戳 21 条跨页无重复遗漏；`profile_share_interaction__api_integration_test.go` 覆盖 Mongo 重建后读取与 read 状态。
  - 状态: 部分收口（2026-07-12；验收 #1/#3/#4 已闭，#2 的 share 路径已闭；点赞/评论/浏览等非 share 互动仍沿用旧投影并保留剩余高互动读放大风险）
- [ ] R-ID10 交集 5 展示位统一渲染/交互/图标标准化收敛（两套并行链路收敛到统一组件）
  - 区域: App
  - 域: `content` / `recommendation`
  - 事项: 仓内存在两套并行交集渲染链路——统一链路（首页 feed / 我的主页 / 打动卡 / 圈子打动卡，消费 `primarySpans` + `IntersectionTargetNavigator` + `IntersectionVisualCluster`）与自绘旧链路（记录卡 `IntersectionReasonChip` + 对象页 `ObjectIntersectionCard`/`EvidenceGroup` 自绘行 + 硬编码图标 switch）。自绘链路未消费 `primarySpans`、行/片段不可下钻、归因丢字段、图标绕过 resolver。
  - 原因: 交集补全分阶段落地，统一渲染器/导航器/图标 resolver 先在我的主页与首页 feed 收口，对象页（B 用户 / C 圈子 / D 实体）与记录卡的旧链路尚未收敛。
  - 影响: 用户旅程在对象页/记录卡有断点（交集句不可点、无法名字→对象页 / 数字→下钻）；图标/归因/导航多套真相源，违反 §20.7 统一交互子契约与 §21.5.2 图标单一真相源。不影响数据正确性与端云契约。
  - 正确设计（逐项）:
    - N3: 对象页三页用 `IntersectionStatementRow`（消费 `reason.primarySpans` + `sampleVisuals` + `iconKey`）替换 `ObjectIntersectionCard`/`EvidenceGroup` 自绘行。**证据级前置（2026-06-20 勘察坐实）**：N3 完整价值是 reason 粒度「名字蓝字可点 + 句内头像」，依赖 reason 级 `primarySpans`/`sampleVisuals`。云侧 `content-service` 对象交集已在 `ObjectIntersections → hydratePointSummary → hydrateExplain → hydrateInteractionContract` 完整产出 `primaryText/primarySpans/sampleVisuals/actionHints`（remote 已就位，无需改 go）；但端侧 mock `intersection_repository.getObjectIntersections` 走 `_objectEvidenceGroups` 硬编码 **point 粒度**，`primaryText/primarySpans` 为空。直接换 reason 粒度渲染器会：mock primaryText 空 → 整行降级隐藏 → 破坏 alpha 对象页交集展示与现有 object_page 测试；保持 group 粒度 → 拿不到 reason 级 spans → remote 价值兑现不了（换壳不换核）。故 N3 须先 **env-seed-first**：把云侧 hydration 后的对象交集 reason（含 spans）固化进 `contracts/metadata/content/test_fixtures`，mock 从 fixture 读（删 `_objectEvidenceGroups`），再换渲染器 + 重写 object_page 测试。该增量触 content-service fixtures 域（与 `post_service.go` 并发编辑同域，需避开撞车窗口），不宜与 N1/N2/N4 同轮强推。
    - N4: 对象页/他人主页交集行经 `IntersectionTargetNavigator` 下钻（名字/数字 span 级；section 内部默认下钻不改脏树调用方）。
    - N5: 记录卡 `IntersectionReasonChip` → `InteractiveIntersectionText(spans)` 可点击 + `IntersectionTypeIcon`。
    - N6: 首页 feed `onTrack` 透传 `sourceRef`/`evidenceId`。
    - N7: 「为什么推荐X」埋点通道统一——**纠偏（2026-06-20 证据级）**：初判「统一到 `trackClick`」方向错误。交集证据组点击语义是 `tag_click`（`contracts/metadata/content/post/behaviors.yaml` 已登记 `type: tag_click` / `dart_method: trackTagClick`；推荐 HotPath `runtime/recommendation/hotpath.go` 给 `tag_click` 权重 **1.8**，高于 `click`），统一到 `trackClick(click)` 会把 1.8 强信号降权、改变推荐归因强度（违反 R23/R32 改埋点验三面）。当前 `object_intersection_section._reportReasonTap` 经 `behaviorRepository.reportEvents(action: tagClick)` 直发 **语义正确、tagRefs 回流不丢**，「双通道」实为 `ContentBehaviorTracker` 缺 `trackTagClick` 公开封装（仅内部 switch 处理 `BehaviorAction.tagClick`）。正确收口：在 tracker 补 `trackTagClick`（保 `tag_click` 1.8 权重 + 补 `intersectionSourceRef`/`intersectionEvidenceId` 归因），统一通道不改信号语义，并以契约测试验证推荐权重不变性。降级为不阻断用户旅程的封装统一债（PR_WARN/TECH_DEBT，非 click 降权改造）。
    - N8: 圈子头像簇 `sampleAvatarUrls` → `sampleVisuals` + `IntersectionVisualCluster`。
    - N9: 实体行硬编码 `'ask_xiaoqu'`/产品名 → `IntersectionActionHint.actionKey` 闭集。
    - N10: `referralSource` 按面（profile/circle/entity）精确来源，去 `organicFeed` 硬编。
  - 验收标准:
    1. 对象页/记录卡交集句经统一渲染器（`primarySpans`/统一图标 resolver），无自绘行与硬编码图标 switch；
    2. 名字 span → 对象页、数字 span → 维度下钻、行点击经 `IntersectionTargetNavigator`（与我的主页/首页 feed 同口径），新增 widget/契约测试断言；
    3. 归因字段（`sourceRef`/`evidenceId`/精确 `referralSource`）跨展示位一致；
    4. 删除 `EvidenceGroup` 自绘渲染与 `IntersectionReasonChip` 纯文本路径后，全仓无第二渲染/导航/图标真相源（门禁/grep 守护）。
  - 涉及文件: `quwoquan_app/lib/components/object_page/{object_intersection_card,object_intersection_section,evidence_group,intersection_target_navigator}.dart`、`quwoquan_app/lib/ui/content/widgets/intersection_reason_chip.dart`、`quwoquan_app/lib/ui/content/widgets/record_post_card.dart`、`quwoquan_app/lib/ui/user/widgets/profile_shell_builders.dart`、`quwoquan_app/lib/ui/circle/widgets/circle_shell_builders.dart`、`quwoquan_app/lib/ui/entity/widgets/{homepage_detail_shell_builders,homepage_detail_page}.dart`、`quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_post_cards.dart`
  - 本轮部分收口（2026-06-20）:
    1. N1（断点4）: `object_intersection_list_page` 手写 `switch(UnifiedObjectKind)→context.push` 复制导航逻辑删除，归一 `IntersectionTarget` 后交 `IntersectionTargetNavigator`，保留 `relationKind` 兜底；新增 `test/ui/intersection/pages/object_intersection_list_page_test.dart`（4 组绿）+ navigator 回归 13 绿。
    2. N2（断点5）: `object_intersection_card._ConnectionLeadingIcon._fallbackIcon` 与 `evidence_group.fallbackIconKindFor` 两层硬编码图标 switch 删除，统一 `IntersectionIconResolver.resolve`（`sourceRef`/`dimension` 从 `group.kind` 解析）；object_page 全测试目录 60 绿，全仓 `fallbackIconKind` 无代码引用。
    3. N4（断点2）: `object_intersection_section` 在未传 `onReasonTap`（用户主页 B / 圈子主页 C）时内部默认经 `IntersectionTargetNavigator` 下钻（整行对象级可达，消除「整行仅 track 不可下钻」断点）；传入 `onReasonTap`（实体页 D 自定义开助手）时尊重调用方语义、不叠加默认下钻（不双跳），零改脏树调用方。reason→target 归一逻辑从 N1 list page 顶层函数上移为 `IntersectionTargetNavigator.targetForReason`（B/C/list page 单一真相源，保留 `relationKind` 兜底）。`test/components/object_page/object_intersection_section_test.dart` 新增 2 条 GoRouter host 测试（默认下钻 / 调用方优先不双跳）；object_page 全测试目录 + N1 list page 测试共 69 绿。
  - 第二轮收口（2026-06-21）:
    4. N6: `home_multi_form_feed_post_cards` 两处 `trackClick` 补 `intersectionSourceRef`/`intersectionEvidenceId`，三处 `IntersectionNavAttribution` 补 `evidenceId`（取 `reason.pointSummarySnapshotId`）；新增 GoRouter host span 点击回归（`home_intersection_multiform_feed_widget_test`），15 绿（feed 集合 83 绿）。
    5. N7: `ContentBehaviorTracker.trackTagClick` 公开封装落地（保 `tag_click` 1.8 权重、补全统一交互子契约归因字段，**未**降级为 `click`），`object_intersection_section._reportReasonTap` 改走统一通道；`content_behavior_tracker_test` 新增 `tag_click` 断言，31 绿。
    6. N9: 实体页 D 面 `_handleIntersectionReasonTap` 改消费结构化 `actionHints`（新增端侧闭集常量 `IntersectionActionKeys` + `isAssistant`），删除 `actionType == 'ask_xiaoqu'` 死分支（该值全仓从无产出）；mock `intersection_repository` 改用闭集常量；新增 `intersection_action_keys_test`（11 绿）。
    7. N10: `behaviors.yaml` `referralSource` enum 扩 `my_intersections` + 云 `ReferralSourceMultiplier` 加 `my_intersections: 1.5`（端云三同步 R08，`verify_metadata` 通过）；新增共享 `referralSourceForObjectType`（user→authorProfile / circle→circlePost / entity→entityPage），`object_intersection_section`/`object_intersection_list_page` 改用；`author_impact_card`→authorProfile，3 个「我的」面→`myIntersections`；contract 测试补闭集 + 映射断言。
    8. N8: `circle_header` `memberAvatarUrls: List<String>` → `memberVisuals: List<IntersectionVisual>` 归一到统一 `IntersectionVisualCluster`（形状/降级/「+N」/可点击统一）；`circle_shell_builders._circleMemberClusterVisuals` 优先 `point.sampleVisuals`、过渡期回退裸 `sampleAvatarUrls` 包装（N3 fixture 化后回退分支自消亡）；`circle_header_widget_test` 新增 2 条簇渲染断言，13 绿。
    9. N5: `IntersectionReasonChip` 升级 `ConsumerWidget`——槽①图标归一统一 `IntersectionTypeIcon`（删本组件第二套 `kind` switch `_icon`，消除与 resolver 分叉）；结论句归一统一 `InteractiveIntersectionText(spans)`，对象/计数片段可点击经统一 `IntersectionTargetNavigator` 进对象页、埋点保 `tag_click`（`trackTagClick`）；4 调用方（`profile_works_tab`=authorProfile / `homepage_detail_shell`=entityPage / `section_creations` 文章卡 + `record_post_card`=circlePost）传 `referralSource` 精确归因；`intersection_reason_chip_widget_test` 重写（图标归一 + weightTier 分化读 `InteractiveIntersectionText.baseStyle` + 可点击 span 导航/`trackTagClick` 全归因），15 绿。
    10. 顺手清理: `author_impact_evidence.dart` 行尾箭头 `chevron_right`→`chevron_forward`（pre-existing iOS 语义债，`verify_dart_semantic` 门禁绿）；author impact + 我的交集 21 绿。
    - 第二轮门禁: `verify_dart_semantic` 绿、`verify_ui_mock_isolation` 绿、`verify_metadata` 绿；交集核心测试集合 83 绿。
    - 已知非本轮：`home_circles_hub_page_test`（`home-circle-grid-post-*` key 缺失）与 `homepage_detail_page_widget_test`（「主页暂不可用」失效态文案）2 例失败属 discovery/entity 脏树并发 WIP 漂移，与本轮交集改动无关。
  - 第三轮收口（2026-06-23 · N3 env-seed-first 主体）:
    11. N3（env-seed-first + 删第二真相源）: 对象页「你们的交集」改为唯一经 contract fixture 真实下发。
        - `content/test_fixtures/scenarios/content_scenarios.json` 的 `intersection_core.objectIntersections` 新增 `u_lin`/`c_photo`/`e_pku` 三个 alpha 测试对象，每个为完整 `IntersectionReason`（含 `primaryText` + `primarySpans`〔句内对象名蓝字可点 target〕 + 多 `intersectionPoints`〔关系分层 label/count/sampleAvatarUrls〕 + `connectionSummary`），与 erhai/duanqiao 同 schema、与 alpha/beta/gamma seed 同源。
        - `MockIntersectionRepository.getObjectIntersections` 删除硬编码 `_objectEvidenceGroups` / `_EvidenceSeed` / `_connectionSummaryFor` / `_objectKindForObjectType`（按 objectType 合成事实的第二真相源），改为只读 `intersection_core.objectIntersections[objectId]`；无 seed 命中返回空（不造假、无 objectType 回退）。mock 与 remote 同走 `IntersectionReason.fromMap`。
        - `build_alpha_lite_fixture_bundle.py`：content LITE_REFS 增 `intersection_core`，并裁剪为 `objectIntersections`-only（inbox/channelReasons 仍走端侧行内 canonical 回退，零改 inbox 行为，避免 inbox 测试级联）。`build_gamma_curated_fixture_bundle.py`：新增 `CURATED_OBJECT_INTERSECTION_DROP_IDS` 裁掉三个 alpha 测试对象，gamma 仅保留 `fixture_*` 真实首页对象交集（已校验 gamma-curated 0 命中测试 id）。
        - 重写 `intersection_object_evidence_test.dart`：断言真实 fixture 链路（`intersectionId`/`actionTargetId` 取自 seed、`primaryText` + object span 蓝字可点、`join(primarySpans.text)==primaryText`、关系分层 label、count single-source、`把你们连在一起` 连接句、推荐排在事实后、未 seed 对象〔含合法 user 类型〕返回空证明无 objectType 回退）。`flutter test` 8 绿；object_page/intersection 目录 111 绿；profile shell/tab 41 绿。
  - 状态: 收口（2026-06-23；N1–N10 全部已闭并验证，证据见上）。N3 第二真相源（mock 硬编码 `_objectEvidenceGroups`）已删除，对象页交集唯一经 fixture `IntersectionReason` 真实下发，自带 `primarySpans`（句内对象名蓝字 target + 头像簇）。**渲染/导航已统一**：我的主页「我的交集」与三对象页（用户 B / 圈子 C / 实体 D）**共用同一个** `ObjectIntersectionSection` → `ObjectIntersectionCard`/`EvidenceGroup` + `IntersectionTargetNavigator` + `IntersectionIconResolver` codegen（profile/circle/entity shell builders 同源），整行/名字/数字可下钻、归因 `tag_click` 1.8 权重不变——主页与对象页无渲染分叉，instruction #4「统一到与主页同一 ObjectIntersectionSection」已满足。**残留（独立 UI 视觉升级项，非主页/对象页分叉）**：当前共用的 `ObjectIntersectionCard` 以 `EvidenceGroup`（point 证据组行）呈现，尚未升级为直接渲染 `reason.primarySpans` 的 `IntersectionStatementRow`（句内蓝字+头像，目前仅 `我的交集` inbox/impact 时间线在用）。因主页与对象页同源，此升级须在 `ObjectIntersectionSection` 层**跨面统一**进行（一改全改，避免新分叉），seed 已下发 `primarySpans` 为该升级铺好数据；属可独立排期的全局视觉对齐增量，不构成主页对标缺口。

## 评论系统重做（Comment System Redesign）

> 当前真相源：`contracts/metadata/content/comment/**` 与 `comment-thread/spec.md` V3。2026-07-14 已完成零兼容替换：Comment / ContentReaction 独立对象 Facade、Mongo aggregate+outbox、pinned-first 唯一顺序、App typed Facet、production Remote-only；旧 PostService 评论方法、Memory store、`CommentDto`、动态 Map、三档排序与 count-delta operation 均已删除。R-CMT01 下的 2026-06-20 内容仅保留为失败→修复历史，不再描述当前架构。

- [x] R-CMT01 评论存储为进程内 map + 全局锁，缺 MongoDB/Redis 生产持久化落地
  - 区域: Service
  - 域: `content`
  - 事项: `content-service` 评论读写曾由 `PostService.comments map[string][]map[string]any` 进程内存承载，`storage.yaml` 声明的 MongoDB `comments` 集合与 Redis 缓存未接入 infrastructure 实现。
  - 原因: 进程内实现仅满足 alpha mock + 单实例契约测试，不满足多副本、重启不丢、千万级评论分页与高并发读写。
  - 影响: 进程重启评论全丢、无法水平扩容、深分页/热评论排序大数据量下退化为全量内存扫描排序、跨副本排序漂移。
  - 正确设计: 在 `infrastructure/persistence` 实现 storage-agnostic comment store，一级评论两段 keyset（pinned 段 + 排序段）走复合索引，二级回复按 `(postId,parentCommentId,createdAt,_id)` keyset；application 层只依赖 `domain/comment.Store` 接口，不出现存储驱动 import；`Post.commentCount` 由原子 `$inc` 加速、评论集 DB count 为单一真相源。
  - 验收标准:
    1. 评论读写经 MongoDB store，重启（重连）后评论与排序不丢；
    2. 三种排序在大数据量（≥1e4 评论）走索引分页，无全表内存排序；
    3. 同集合一致性：换排序不换集合/总数；
    4. 多副本下排序由落库字段驱动稳定；
    5. 主请求不再依赖评论 Redis 缓存（移除只写不读 ZSet / 竞态计数器后无降级阻断）。
  - 涉及文件（已落地）: `quwoquan_service/services/content-service/internal/domain/comment/{comment_repository.go,comment_cursor.go,reaction.go,sort_mode.go}`、`internal/infrastructure/persistence/{comment_mongo_store.go,comment_memory_store.go,comment_reaction_mongo_store.go,mongo_post_store.go,post_store.go,post_repository_iface.go}`、`internal/infrastructure/cache/post_cache_repository.go`、`internal/application/{post_service.go,comment_projection.go}`、`internal/adapters/http/content_handler.go`、`cmd/api/main.go`、`contracts/metadata/content/post/{fields,storage,service}.yaml`、`contracts/metadata/_shared/redis_keyspace.yaml`、测试 `services/content-service/tests/{comment_persistence_migration_contract_test.go,comment_keyset_explain_bench_test.go}` 与 `internal/infrastructure/persistence/{comment_memory_store_test.go,comment_keyset_delta_test.go}`
  - 本轮收口（2026-06-20）:
    1. **决断① 排行 ZSet → 删除**：`comment_hot` / `comment_recommended` 排序 ZSet 是只写不读（`ListTopLevel` 直接走 Mongo），per-comment 赞踩计数器读穿回填非原子（stale-backfill 竞态、陈旧 `likeCount`/`recommendedScore` 落库）。判定为写放大无读收益且引入一致性债，整体删除 `infrastructure/cache/comment_cache.go`，从 `redis_keyspace.yaml` 移除对应前缀；排序/计数权威化到 Mongo 复合索引 + `CountDocuments`。`ReactToComment` 计数改为派生自权威成员关系 store（`comment_reactions` 集合），落库分值永不陈旧。
    2. **决断② post 计数热写 → Mongo 原子 `$inc`**：`AddComment`/`DeleteComment` 用 `MongoPostStore.AdjustCommentCount(±1)`（单字段 `$inc`，配 `SetReturnDocument` + 投影）替换每次 `CountDocuments + 整文档改写`；`GetCounters`/`ListComments` 读路径以评论集 DB count 为单一真相源，发现 `Post.commentCount` 漂移时单 `$set` 机会式自愈；`$inc` 失败回退 `reconcilePostCommentCount` 全量对账。未引入 runtime/redis `DecrBy/IncrBy`（避免再加一套跨副本会漂移的计数真相源）。
    3. **决断③ keyset 分页取代 1e4 扫描**：强类型 `comment.Cursor`（`Phase/Score/TimeUnixNano/ID`，base64 JSON 编解码，非 `map[string]any`）；一级两段 keyset（pinned 段 `(pinnedAt,_id)` partial index + 非置顶排序段 `(score,createdAt,_id)`），二级/作者/收到 keyset `(createdAt,_id)`；所有 keyset 服务索引追加 `_id:-1` tiebreak 使排序全索引覆盖。`storage.yaml` 新增 `idx_comments_pinned`（partial `isPinned:true`）/`idx_comments_deleted`（partial `status:deleted`）。
    4. **块2 计数 delta 契约**：`fields.yaml` 评论补 `deletedAt`（软删落时间戳、记录保留可查、count 仍排除 deleted）；`SoftDelete` 真正写入 `deletedAt` 并对已删幂等（不二次扣减）；`comment_projection.go` 输出真实 `deletedAt`；新增 `GetCommentCountsDelta(postId, since)` → `{createdSinceCount, deletedSinceCount, currentTotal, watermark, since}`，半开区间 `(since, watermark]`，watermark 作下次 since 基线避免重复/遗漏；`service.yaml` 声明该接口 metrics/SLO/trace；`make codegen-app` 端侧 `comment_dto.g.dart` 已含 `deletedAt` 供后续端侧消费。
  - 验证证据（2026-06-20，`TEST_MONGO_URI=mongodb://localhost:32775`）:
    - explain 索引覆盖（`TestCommentMongoStore_ListQueriesAreIndexCovered`）：recommended/most_liked/replies 三查询 winningPlan 均 `FETCH ← IXSCAN(idx_comments_recommended|idx_comments_hot|idx_comments_parent_created)`，无 `COLLSCAN`、无阻塞 `SORT`（SORT 仅出现在 rejectedPlans）。
    - ≥1e4 深翻不截断（`TestCommentMongoStore_DeepPageBeyond10kNoTruncation` 10001 条 / 内存 `TestMemoryCommentStore_DeepPageNoTruncation` 12001 条）：全量唯一、无重复、顺序稳定。
    - 翻页不漂移（`TestMemoryCommentStore_LatestKeysetDriftFreeUnderMutation`）：分页中持续 mutate 分值，`createdAt+_id` 不变 keyset 仍不重不漏。
    - delta 半开区间（`TestCommentCountsDelta_ExplainableHalfOpenWindow` + 内存 `TestMemoryCommentStore_DeltaWindowSemantics`）：连续两次 since=上次 watermark，created/deleted 精确不重复计数，currentTotal == 权威 Mongo 非删计数。
    - 并发一致性（`TestCommentCountReconciliation_HighConcurrency`，`-race` 干净）：并发增/删/反应后 `ListComments.totalCount == GetCounters.comment == 权威 Mongo count`。
    - 基准（Apple M5 Pro，docker Mongo over TCP）：`BenchmarkCommentListTopLevel_DeepPage` ~11.3ms/op、`BenchmarkCommentListReplies_DeepPage` ~1.77ms/op（深位 keyset seek，O(pageSize) 与深度无关）、`BenchmarkPostCommentCount_AtomicHotWrite` ~0.94ms/op（含网络往返）。
    - `go build ./...`、`go vet ./services/content-service/...` 通过；`go test ./services/content-service/...` 仅余两项与本任务无关的既有失败（见 R-CMT02）。
  - 状态: 已解决（2026-06-20；评论域已迁出进程内 map，Mongo keyset + 权威 count 落地，证据见上）

- [x] R-CMT02 评论计数加速器最终一致窗口 + delta watermark 依赖服务端墙钟
  - 区域: Service
  - 域: `content`
  - 事项: 历史实现把 Post.commentCount 修复与应用墙钟 `GetCommentCountsDelta` 作为两条独立机制，存在崩溃窗口和多副本时钟边界债。
  - 原因: Comment 写入、Post 计数投影和无消费者的页面增量提示没有统一到对象 outbox 与权威 page total。
  - 影响: 历史上可能出现 Post 投影短暂漂移，并为未被生产 UI 使用的 delta API 长期承担错误边界、DTO、索引和测试成本。
  - 正确设计: Comment aggregate 与 outbox 原子提交；独立 relay 按 checkpoint/retry/replay 投影权威 Comment count 到 Post。页面首屏只比较入口 baseline 与 CommentPageSlice.total，不维护轮询水位。删除无消费者的 `GetCommentCountsDelta` 全链路，不以逻辑时钟或兼容 API延续错误抽象。
  - 验收标准:
    1. Comment commit 与 outbox 原子，relay 失败不丢事件且 checkpoint 只在投影成功后推进；
    2. Post.commentCount 由 Comment count projector 重建，重复事件结果幂等；
    3. metadata、Graph、Service、App pure contract、alpha/test Facet 和生成物均不再包含 GetCommentCountsDelta；
    4. 页面一次性差异提示只使用 entry baseline 与首次权威 page total。
  - 涉及文件: `services/content-service/internal/application/comment/{comment_count_projector.go,outbox_relay.go}`、`internal/infrastructure/persistence/comment_aggregate_mongo_store.go`、`contracts/metadata/content/comment/**`、`quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/content/**`
  - 验证证据（2026-07-14）: Comment outbox/projection local contract、Comment HTTP/Mongo api_integration 与 ContractGraph/codegen 定向门禁；`GetCommentCountsDelta|ContentCommentCountDelta|counts-delta` 生产源码扫描为零。
  - 状态: 已解决（2026-07-14；事件驱动计数投影替代崩溃窗口，无消费者墙钟 delta operation 全链路删除）

- [x] R-CMT03 content-service 既有契约测试两项失败（与评论域硬化无关，working-tree 阻断）
  - 区域: Service
  - 域: `content`
  - 事项: `go test ./services/content-service/tests/` 有两项失败：`TestContractFixtureSeed_ContentAlphaReadsViaHandler`（`content_discovery_core` seedSet 不含 `fixture_photo_001` 评论，断言 comments 非空失败）与 `TestIntersectionSource_EntityObjectProducesFolloweeVisited`（交集文案 `ixsrc_visitor_c来过这里` off-dictionary）。
  - 原因: 二者均由当前 working-tree 中**他项未提交改动**引入：`content_scenarios.json` 共享池重构把 `fixture_photo_001` 评论从 `content_discovery_core` 迁到 `comment_thread_core` seedSet；`intersection_kind_registry.yaml`/`intersection_reason.yaml` 文案词典调整。已用 clean HEAD worktree 复跑证明两测试在干净基线通过，故与本会话评论域/delta 改动无关。
  - 影响: 阻断 content-service `tests` 包整体绿；不影响评论域/计数 delta 正确性（其余全部用例含本会话新增 explain/deep-page/delta/并发用例均绿）。
  - 正确设计: 由 `content_scenarios.json` 共享池重构 / 交集文案词典的负责会话同步修正 seedSet 与词典；或将 `TestContractFixtureSeed` 的评论断言改读包含该评论的 seedSet。
  - 验收标准: clean working-tree 下 `go test ./services/content-service/tests/` 全绿。
  - 涉及文件: `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json`、`quwoquan_service/contracts/metadata/recommendation/rec_model/{intersection_kind_registry.yaml,projections/intersection_reason.yaml}`、`services/content-service/tests/{contract_fixture_seed_contract_test.go,intersection_source_contract_test.go}`
  - 证据: 2026-06-21 R-TST03 收口轮 `go test ./services/content-service/tests/ -count=1` → ok（0.348s）；working-tree 漂移已被他项改动消除，不再阻断。
  - 状态: 已解决（2026-06-21；content-service tests 包当前树全绿，与评论域改动无关的 transient 漂移已消除）

## 内容生产工作流商用化（Content Supply）

> 来源：2026-06-21 内容生产工作流商用化系统性规划（`quwoquan_data/docs/content_supply_commercialization_plan.md`）落地 + 四川景区两工作流真实 e2e + 十→千→十万规模评估。蓝图、三份 spec、Phase 0-4、运行时地基、两工作流 e2e 与规模门均已完成；以下为诚实剩余断点。

- [ ] R-CS01 指令线 homepage source sufficiency 反爬瓶颈
  - 区域: Data
  - 域: `content-supply`（指令维度工作流 / download homepage lane）
  - 原因: homepage lane 要求每实体 ≥1 个符合 `encyclopedia-primary-v2` 的可读主源（Wikipedia、百度百科、搜狗百科、今日头条百科）；四川十级 e2e 中阆中古城、黄龙风景区的百度/搜狗百科被反爬隔离 reject（`home_baidu_baike`/`home_sogou_baike`），`homepage retained sources=0 need>=1` 触发 download gate 失败，ReAct 回退两次仍不满足。官网、政府/文旅门户、OTA、Wikivoyage、360 不再具备主页正文准入资格。
  - 影响: commercial 零失败模式下个别实体 source 不足会阻断整批；十级实测 8/10（80%）成功。百/千级放量需 `allowPartialContent` 替补策略或更强多源 plan，否则成功率随外站反爬波动。
  - 涉及文件: download lane、`quwoquan_data/verticals/travel/sources/source_registry.yaml`、task `workflowPolicy.allowPartialContent`
  - 复核（2026-06-21 真实运行时复盘，代码+e2e10 实证）: 多源候选生成工程已实质建成——`research_plan.py` 已对 homepage 同时产出 official_url + 维基（`_wiki_title_for_entity` 经 canonical+短名+别名解析 + `_wikidata_item_for_entity_search` zhwiki 失败兜底）+ curated `knownHomepageSupportSites` + baidu + sogou；CR-049 已落 partial delivery（`allowPartialContent` 默认 true、单实体主页失败不阻断整批）。对真实批次 e2e10 跑 `verify scale-readiness`：`sourceSufficiency.homepage rate=1.0(8/8 活跃)`、`sourcePlanCategories.encyclopedia=10`，**源充分性在计划层已达标**。黄龙/阆中失败精确定位在 `build_prepare`「homepage input unavailable after build_prepare repair budget」（候选有、但抓取到的正文被反爬探针页污染不可用），已由 partial delivery 处理为 8/10、abandoned=2 excluded from refs。
  - 复核（2026-06-23 五景真实放量验证 e2e5，含 article lane）: 本轮发现并修复一个**article 底稿选源缺陷**（与原 homepage 维度不同）：`task/run.py:_article_source_quality_sort_key` 旧排序键 `(quality, length, image)` **不含目标实体聚焦度**，导致放量时长篇多城游记（如青城山被锁到「问道青城山拜水都江堰」实际聚焦仅 8% 的 base_1、九寨沟锁到聚焦 25% 的 base_3）系统性挤掉聚焦单实体的短游记（青城山 base_2 聚焦 61%、九寨沟 wikivoyage 聚焦 67%），使 article lane 的 `baseDraftFidelity` 门被源错配拖垮。已实现 `_entity_focus_score`（实体名+通名别名在信号行的字符占比）并把聚焦度置于排序首位（5% 分档），确定性验证：青城山 04→05、九寨沟 06→wikivoyage 改派正确；青城山切到聚焦源 base_2 后端到端 fidelity 72.1% 过 review+materialize（修复闭环证明）。残留两个**新维度**（待用户确认是否登记为独立 backlog 项）：(a) 都江堰**采集缺口**——批内无任何聚焦简体 article base（最佳 qunar 仅 17%，维基 93% 但属 home lane 非 article），排序无法凭空造源；(b) wikivoyage 等**简繁混排**底稿聚焦度高但简体成稿 3-gram fidelity 偏低（九寨沟 12.7%），需在 `base_draft.py` fidelity 做繁→简归一化或在选源加脚本兼容度项。e2e5 `scale-readiness` 漏斗：homepage 5/5、image 5/5、article 3/5（乐山/峨眉/青城山过门，都江堰/九寨沟 abandoned）。
  - 复核（2026-07-05 双1k creator commercial gate 伴随复验）: 当前最新百级真实批次 `scale100_elastic_overfetch_2x_0704a`（`.qwq_sandbox/data/runtime/batches/弹性百级复跑-1f7ff8e1__scale100_elastic_overfetch_2x_0704a/_shared/scale100_elastic_report_0704.json`）继续证明 source sufficiency 仍是商用 NO_GO 主因之一：33 active targets 仅产出 64 release posts（34 article + 30 image），`releaseEntitiesWithHomepage=12`、`successRateTarget=0.64`；`abandoned.byStage` 中 homepage `build_prepare` 直接放弃 21、entity source 类放弃 7、content object 放弃 101，主因仍是 `homepage input unavailable after build_prepare repair budget` 与多实体 `entityArticlesPerTarget quota 4 but only picked 0~3 qualified article source(s)`。说明双1k creator 池已 `creator-scale-readiness=go` 不等于内容供给链已过 commercial gate，source admission / homepage/article sufficiency 仍需单独收口。
  - 复核（2026-07-06 homepage MediaWiki same-source hydrate）: 新定位到一个**deterministic 的 homepage 证据丢失子根因**：当 MediaWiki 页面不是以 exact-title 主源进入 `homepage_source_plan.json`，而是经 `verified_homepage_source_unit_reuse` 或 `travel_source_registry` 进入时，planner 之前不会统一补同源 `imageUrls`，导致这些 wiki source 以 `imageEvidenceMode=""` 落盘；下游 `download_fetch -> write_source_unit -> build_prepare` 因 source-plan 无图证而产出 `assetCount=0` / `homepage lane 无可发布图片资产`，即使同一页面用 `download.research_plan._mediawiki_page_images(...)` 可真实取回图（实测：`黄龙风景名胜区` 8 张、`成都武侯祠` 1 张、`都江堰` 8 张）。本轮已把 MediaWiki URL 的 same-source hydrate 收口到 homepage source 进入 plan 的统一入口，并让 reuse source 同样走该 helper；契约证据：`test_verified_homepage_reuse_hydrates_mediawiki_same_source_images` + `test_homepage_registry_wiki_support_hydrates_same_source_images` 新增回归，连同相关旧套件共 64 passed；真实样本证据：throwaway batch `scale100_elastic_overfetch_2x_0704a_hydrate_check` 中，`黄龙` 的 `home_wikipedia_huanglong_scenic_area` 现带 `imageEvidenceMode=same_source` + 8 图，`武侯祠` 的 `home_wikipedia_chengdu_wuhou_shrine` 现带 `imageEvidenceMode=same_source` + 1 图。进一步在**合同对齐的两实体 throwaway task** `旅行/地域/四川省/景区/RCS01主页下游验证0706a` / batch `homepage_verify_contract_1` 上复验，`data download` gate 已通过，`build prepare` 成功生成 `entity_page_input.json`，且 `validate_entity_page_inputs` 为 0 issue；`武侯祠` 虽仍保留 0 图 exact-title `home_wikipedia` source unit（`assetCount=0`），但下游 `baseDraft/sourceRef` 已稳定选到带同源图的 `home_wikipedia_chengdu_wuhou_shrine`（`assetCount=1`），说明当前主线**不需要额外做 primary 选源修正**，planner hydrate 已足以打通这两个样本的 `download_fetch -> build_prepare`。残留边界：`武侯祠`/`黄龙` 的 exact-title `home_wikipedia` 条目仍可能因页面自身无可发布图或页名不对而保持 0 图；外站反爬、exact-title 误页与 release homepage closure 主问题仍未关闭，R-CS01 状态继续保持待办。
  - 复核（2026-07-06 正式 task scoped batch 复验）: 为把上条 throwaway 证明带回商业主线，本轮在正式 task `旅行/地域/四川省/景区/弹性百级复跑0704a` 下新开 scoped batch `homepage_formal_scoped_0706c`，并在对齐的 `.qwq_sandbox/data` 正式运行根中只保留 5 个旧失败样本：`黄龙`、`武侯祠`、`瓦屋山`、`木格措`、`西岭雪山`。链路 `research-plan --lane homepage -> download --lane homepage -> build --stage prepare` 全部跑通，`build prepare` 正确按 active spec 只下发 5 个实体，并为 5/5 落出 `3.compose/entity_page_input.json`。但函数级准入校验 `validate_entity_page_inputs(...)` 结果为 **2 通过 / 3 失败**：`黄龙` 与 `武侯祠` 已被修通，且 `entity_page_input.json` 中 `baseDraft.sourceRef` 明确选到带 same-source 图证的 supporting wiki source（分别是 `home_wikipedia_huanglong_scenic_area` 8 图、`home_wikipedia_chengdu_wuhou_shrine` 1 图）；`瓦屋山`、`木格措`、`西岭雪山` 虽也已生成 `entity_page_input.json` 且 baseDraft 可读，但 `availableImages=[]`，`validate_entity_page_inputs` 仍稳定报 `homepage lane 无可发布图片资产`。这 3 个失败样本当前 `homepage_source_plan.json` 中 exact-title / registry wiki source 仍均为 `imageEvidenceMode=""`，说明**剩余 blocker 已收敛为逐实体 authority source 自身无可发布同源图**，而不是 planner 再次把 same-source 图证丢掉；因此可以把“planner/drop same-source 图证”从 R-CS01 的主要根因中剔除，但 R-CS01 作为整体商业门禁仍不能关闭，因为外站反爬、exact-title 误页与无图 authority source 仍会让更大批次的 homepage closure 继续失败。
  - 复核（2026-07-06 正式 scoped batch fail-closed 前置）: 在 `download/research/auto_plan_writer.py` 新增 homepage front-door：当实体**确实命中 authority encyclopedia seed source**，但所有 accepted homepage sources 都没有 `imageEvidenceMode="same_source"` 且无可发布 `imageUrls` 时，research-plan 立即写入 `sourceUnavailable(lane=homepage)`，并把实体放入 `sourceAvailability.ineligibleTargets`，不再让它们假绿 through download 后拖到 `build_prepare` 才炸。契约证据：`test_homepage_registry_sources_without_same_source_images_mark_target_ineligible` 新增回归通过，并连同相邻 `test_auto_research_article_homepage__local_contract_test.py`、`test_source_plan_registry_guidance__local_contract_test.py`、`test_source_quality_gate__local_contract_test.py` 共 **60 passed**。正式批次证据：对 `.qwq_sandbox/data/runtime/batches/弹性百级复跑-1f7ff8e1__homepage_formal_scoped_0706c` 重新跑 `python3 quwoquan_data/scripts/cli.py data research-plan --task "旅行/地域/四川省/景区/弹性百级复跑0704a" --batch "homepage_formal_scoped_0706c" --entity-ids "黄龙,武侯祠,瓦屋山,木格措,西岭雪山" --entity-type "景区" --lane homepage --force` 后，`_shared/auto_research_plan.json` 现明确落盘 `readyTargets=["武侯祠","黄龙"]`，`ineligibleTargets=["瓦屋山","木格措","西岭雪山"]`，阻断原因为 `homepage authority encyclopedia sources lack same-source publishable image evidence`，下一步统一指向 `manual_homepage_seed_source_or_target_replacement`。同时复验旧反爬污染样本 `su_c5afd8072312e182cdcf/source.md` 可见 `请完成个人中心登录后进行相关操作` 已被 `_common/content_evidence.clean_source_markdown()` 清洗掉（raw=true, clean=false），说明当前残留主阻塞已进一步收敛到**无图 authority source 的 target replacement / curated 替补**，而不是 planner 再丢图证或正文壳文本未清洗。
  - 复核（2026-07-10 两省 P3 source bridge 真实校准与冻结）: 新 Cursor key 与 DNS 恢复后从冻结分片续跑，未重复 prepare、未绕访问控制。100 URL 校准实际结果为 **57 confirmed-ready / 35 inconclusive / 8 no-source / 30 blocked**，成功率 57%、阻断率 30%、延迟 p50/p95/max=472/893/2717ms；338 gray 为 **190 / 128 / 20 / 96**，成功率 56.21%、阻断率 28.4%、延迟 p50/p95/max=616/1751/39761ms。34 片共 338 条已通过 validate 并 freeze，省别 confirmed-ready 从浙江 78→186（新增108、距1200缺1014）、四川76→158（新增82、缺1042）。浙江主清单总量仍仅922，除来源确认外结构性至少还需扩278个候选；因此 P6/P7 继续 GATE_BLOCK。历史 credential missing、DNS ENOTFOUND 与 timeout 事件均保留；Cursor SDK 本轮未返回 usageMeasurementMode，ledger 报 0 token/$0 仅是未测量值。证据已随自治布局迁移到 `.qwq_output/data/runs/migrations/encyclopedia-autonomous-publish-v3-20260711/release-evidence/isolated_unscoped/p3_p5_engineering_20260710/p3_calibration_report.json`；source bridge 证据仍在 `QWQ_OUTPUT_ROOT/data/runtime/source_bridge/p3_gray338_urls_20260710/{validation_report.json,readiness_freeze_report.json}`。
  - 纠偏（2026-07-11 encyclopedia-primary-v2 归一）: 2026-07-10 的“官网/政府可作 primary、Toutiao 仅 supplemental”口径已 superseded。唯一闭集改为 `wikipedia|baidu_baike|sogou_baike|toutiao_baike`，权重 Rank0/Rank1/Rank2/Rank2；Toutiao 使用独立 `sourceKind=toutiao_baike` 与 `toutiao_baike_html` extractor。现存 raw 确定性重验 226 实体，**194 confirmed-ready / 32 inconclusive / 0 no-source / 0 blocked**，主源分布 Wikipedia 102、百度 1、搜狗 0、Toutiao 91；未伪造 URL 或 evidence。
  - 状态: 待办（策略归一已完成；商业阻塞仍为四百科外站反爬、同源图片证据和剩余实体覆盖，不以官网/政府等旁路兜底。证据 `QWQ_OUTPUT_ROOT/data/runtime/source_bridge/encyclopedia-primary-v2-final-raw/validation_report.json`、`.qwq_output/data/runs/migrations/encyclopedia-primary-v2-20260711-post-full/source-policy/audit.json`）
- [ ] R-CS02 十万级放量工程门槛（reliabletask adapter + 吞吐）
  - 区域: Data / Service / Ops
  - 域: `content-supply` / `reliabletask`
  - 原因: `verify scale-readiness` / `site-scale-readiness` 在 `daily_target>=100000` 强制 `queueBackend=reliabletask` + 吞吐 4166.67/h；当前文件队列(`local_file`) + 单会话 ~80/h 仅够十→千级。`object_queue.py` 已定义 `_reliabletask_ref` 路由契约（taskType/queue/dedupeKey/partitionKey），但服务侧 reliabletask adapter（MongoStore+RedisReadyIndex）实际分发未端到端实测；52× 吞吐需外部 cursor-sdk 多 worker ~500 并发 + spend limit + Cursor API 速率配额确认。
  - 影响: 就绪配置 trial 已证明十万级门可过（0 blocker），但生产分发链路未实跑；真实十万级放量前必须落地 reliabletask 分发 + 外部 SDK 编排 + 计费/速率护栏。
  - 涉及文件: `quwoquan_data/scripts/task/object_queue.py`、`quwoquan_service/runtime/reliabletask`、`quwoquan_data/docs/subagent_scheduler_spec.md` §9-10
  - 复核（2026-06-21 真实 e2e10 scale-readiness）: 真实批次 `executionReadiness.queueBackend=""`、`maxConcurrency=0`、`measuredThroughput=null`，百/千级 `decision=no_go`，blocker 含「measured throughput evidence missing」「workflow status must be succeeded」。即吞吐/分发证据只能由真实跑完、烧 token 的放量批次产出，仍受外部 cursor-sdk 多 worker + spend limit + Cursor API 速率配额约束（用户决策项，非会话内可独立闭合）。
  - 复核（2026-06-23 e2e5）: 并发**调度原语已具备**——object-queue 单篇隔离 job（lease/heartbeat/leaseExpiry/notBefore 退避，`queue_runtime_snapshot`）、`task queue work --concurrency N` 本地 worker pool、download lane 实测 5 workers 并发拉 27 source bundles。但本批 `queuePolicy.backend=local_file`，`scale-readiness` 明确 blocker：「daily target >=10000 requires queueBackend=reliabletask」「measured throughput evidence missing; cannot project daily capacity」。即放量级吞吐需切 `reliabletask`（Mongo/Redis）后端 + 真实跑完计时，且 authoring 步受 cursor_sdk 阻断（见 R-CS03），端到端成稿吞吐本轮仍无法实测。
  - 复核（2026-07-10 P5 ReliableTask fleet）: Data→runtime 强类型 adapter 已复用 MongoStore+RedisReadyIndex，幂等键严格为 `entity+carrier+sourceRevision`，并修复失败消息过早 ACK 导致 `retry_wait` 丢失的问题（pending + XAUTOCLAIM）。真实 Mongo 7 + Redis 7 的 100 task 控制面 E2E 100/100 终态、瞬态失败自动恢复率 100%、duplicate publish=0；该实测只证明控制面调度，不是内容 accepted throughput。报告已将指标明确命名为 `controlPlaneTaskThroughputPerHour`，商业 `acceptedContentThroughputPerHour=0`，因此真实日产容量门仍未关闭。
  - 状态: 待办（真实放量门槛，需外部资源授权 + reliabletask 后端 + 解除 cursor_sdk authoring 阻断）
- [ ] R-CS03 作品线真实 token/成本/firstPassRate 未实测
  - 区域: Data
  - 域: `content-supply`（produce author / TokenLedger）
  - 原因: `scaled-e2e prepare` 与 `site-supply trial` 均为结构验证（不烧 token、注入受控吞吐/质量/账本证据）；真实作品 author（cursor sdk）的单位 token、单位通过成本、缓存命中率、firstPassRate 尚无真实 TokenLedger 批次。
  - 影响: 日产十万的商用经济性（单位成本可承受性）未经真实数据验证；scale-readiness commercial 门的 TokenLedger/firstPassRate 维度需真实 author 批次才能过。
  - 涉及文件: TokenLedger、`quwoquan_data/scripts/task/object_queue.py`(`record_usage`)、`quwoquan_data/scripts/verify/scale_readiness.py`
  - 复核（2026-06-21 真实 e2e10 scale-readiness）: 真实批次 `executionReadiness.tokenLedgerCount=0`、`firstPassRate=null`、`expectedObjects.total=0`（e2e10 为 quotas=0 纯实体主页基线，冻结在 content_plan 检查点，结构上不产出 POST，因此无法产生 TokenLedger/firstPassRate/吞吐证据）。要诚实证明放量经济性，必须新跑一个**含内容配额（quotas>0）、Agent 真实创作正文、烧 token、跑完 produce_author→review→materialize→ship** 的真实批次；env preflight 已确认本环境 `CURSOR_API_KEY=present`、`network=ready` 具备真实跑能力。
  - 复核（2026-06-23 e2e5，含 quotas>0）: 新建含配额任务（5 实体 + 5 文章 + 5 图片）并实跑到 review/materialize，但**managed cursor_sdk subagent runner 阻断**：`env doctor` 的 `cursor_startup_probe` 以 `composer-2` 与 `composer-2.5` 均报 HTTP 500 internal error（外部 Cursor API 基础设施/账号侧问题，非本地可控）。因此本轮正文改由**会话模型**创作并确定性 stamp provenance（`agentRunId=cursor-conv-*` + prompt/writingPack/sourceBundle/draft SHA256），质量门全过，但**未经 managed runner ⇒ 无真实 TokenLedger ⇒ `scale-readiness` 仍 blocker「TokenLedger evidence missing」「firstPassRate evidence missing」**。即真实单位 token/成本/缓存命中率/firstPassRate 依旧未实测，根因从「需授权」收敛为「cursor_sdk managed runner 500 阻断」。
  - 复核（2026-06-24 隔离单实体 e2e，`QWQ_DATA_ROOT=/tmp/qwq_e2e` 零污染真实仓库）: **cursor_sdk managed runner 已真实跑通，解除 e2e5 的 HTTP 500 阻断**——把 `QWQ_MANAGED_AGENT_TIMEOUT_SECONDS` 调到 720s 后，build_homepage（都江堰主页 11044B，含《史记·河渠书》/李冰/岷江真实引用，188s 完成）与 produce_author（文章 `都江堰·行前怎么安排` 5169B）均由真实 cursor agent 创作：article `draft_meta.generator=agent`、`model=composer-2.5-fast`、`agentRunId=run-524610ad-...`（真实 run id，非 e2e5 的会话模型 `cursor-conv-*` stamp）。全链路 11 stage 全 completed、failed=[]：explore→baseline→download(真实8源/4图)→build_homepage→build_validate→content_plan→produce_plan→produce_compose→produce_author→produce_annotate(实体标注1 link)→produce_review(media 2/2 passed + review 2/2 approved + 2 包 materialize)。文章质量命中 blueprint 质量门（openingTension/explicitFeelings/decisionPoints/tipsEmbeddingPolicy + cover/wrapRight/closing 多图 + 实体链接）；image 作品 manifest 含完整版权链（creator/license/termsUrl/authorizationProof）。**同时验证去重移除无副作用**：移除图片资产去重链（`_duplicate_source_asset_recompose_refs` 等 + `QWQ_COMPOSE_IGNORE_ASSET_REFS` 旁路）后 produce 域测试 101 passed、e2e 链路全绿。**仍待**：本批未生成 TokenLedger（`record_usage` 未触发），单实体隔离不足以测吞吐/单位成本/firstPassRate，仍需多实体放量批次跑 `scale-readiness` 才能产出商用经济性证据。
  - 本轮 e2e 新发现修复（2026-06-24，用户指令「完成 b/c/d 问题修复」，A 已于发现时修复）:
    - A（已修复）: 文章正文泄漏底稿内部标识 `article_qunar_base_1`（agent 把 prompt 提供的底稿路径片段当溯源写进正文），review gate `check_provenance` 原只查平台名/发布者字段未拦。已加两道防线——`writing_pack.py` prompt 在底稿来源块后明确「禁止把底稿文件名/目录名/source 编号/采集痕迹写进正文标题配文」；`content_review.py:check_provenance` 增 `*_base_N`/`source.md`/`sources/`/`.download` 标识检测（正则命中泄漏样本、不误伤干净正文，produce 101 passed、0 lint）。
    - B（已修复）: entity_workflow 图片作品对齐 route_workflow——`entity_workflow.build_entity_writing_pack` 对 carrier∈{image,gallery} 改调 `write_image_evidence_draft`（幂等删旧正文 + 写 `generator=image_evidence_pack`/`articleContract=structured_image_only`/`selectedAssetIds`），非图片仍走 placeholder。证据：隔离 e2e（`/tmp/qwq_e2e`）真实重跑 `都江堰_image`，draft 由 `generator=pending`+残留 `draft.article.md` → `image_evidence_pack`+`structured_image_only`+正文已删+selectedAssetIds=1；produce 101 passed、0 lint。
    - C（已修复，与去重诉求对齐）: 调研发现「同底稿多作品」基础设施**早已具备**——`handler.py` 已支持 `baseSourceReusePolicy=multi_intent_source_bundle`（`assignments[source]=[posts]` 多值），`content_plan.py:618` 对 `carrier==image` 豁免 one-source-one-work（image 不注册 `base_source_owners`）。真正的过度限制只在 `run.py:_clear_compose_base_draft_assignments` 的 `duplicate_sources` **不分载体**。修复使其载体感知（新增 `image_refs` 参数，由 `_run_produce_compose` 收集 pending image refs 传入）：article+article 复用同底稿仍报 duplicate（反凑数/同质化不放松，与 content_plan「article 一稿一用」一致），image/gallery 参与的同源共用放行（图文同源正常）。**无需改 ledger 结构**。证据：pipeline 188 passed + 新增回归 `test_compose_base_draft_clear_allows_image_work_sharing_article_base`（image 豁免）/ 既有 `..._detects_duplicate_current_plan_sources`（article+article 仍报）；并清理 5 个 import 已删去重符号的死测试（`test_duplicate_source_asset_refs_*`/`test_duplicate_asset_recompose_*`），全仓零残留。澄清：实践中 image 作品写 `sourceCollectionId` 而非 `baseSourceRef`，鲜少触发该门，本修复为防御性载体感知对齐。
    - D（已修复）: `paths.py` 改 `SCHEMA_ROOT = QWQ_SCHEMA_ROOT or _REPO_DATA_ROOT/"schema"`（schema 是受版本控制的契约真相源，跟代码仓库走、不随运行时 `QWQ_DATA_ROOT` 漂移，仍可 env 覆盖）。证据：隔离 `QWQ_DATA_ROOT=/tmp/qwq_isolated_dtest` 下 `SCHEMA_ROOT` 仍解析到仓库 `quwoquan_data/schema`；**删除** e2e 手建软链后 `load_schema('produce','post_manifest')` 仍成功（之前 `Schema not found` 失败点解除），隔离/多环境免软链 schema。
  - 复核（2026-06-24 clean-root 去 few-shot 重跑）: 已按“最小依赖”完成 SOP / templates 精准瘦身——删除 `sop/主页/**/example.md` few-shot 范例、孤儿 `sop/moment.md`、孤儿蓝图 `templates/blueprints/Format/内容角度/主题/风光画报.tmpl.yaml`、纯文档 `templates/shared/style_guide.md` / `templates/shared/image_playbook.yaml` / `templates/_registry/DESIGN_10D.md`；`writing_pack.py` 不再注入 few-shot，`brief.py`/blueprint/writing_pack schema 与命令文档中的 `sopExampleRef` 入口已移除。关键回归：定向 40 tests 通过；`verify_quwoquan_data.sh` 与本轮改动直接相关部分全绿，唯一剩余失败为**用户侧现有脏任务树** `quwoquan_data/tasks/旅行/地域/测试省/景区/*` 的 `task lint`（`effective content.angles 为空`，非本轮 few-shot 清理引入）。在全新隔离根 `/tmp/qwq_e2e_clean_4hUtUj` 仅同步剩余 SOP 骨架（`guide.md` + `article.md` / `image.md` / `video.md` / `scenarios/*.md`）后，`task lint` OK，证明 clean env 不再依赖任何 example few-shot 文件；但真实 `cursor_sdk` managed local workflow 在 `build_homepage` checkpoint **再次**卡住：`task_workflow_state.status=manual_required`、`nextAction=build_homepage infrastructure failed after 3 attempts`、`page.md` 仍为占位。使用同一 `quwoquan_data/.venv` 直接跑 `env preflight --cursor-startup --model composer-2.5-fast --runtime local` 可稳定复现 `InternalServerError / httpStatus=500 / errorCode=internal`，与 batch 内三次 `build_homepage` `internal error` 同源；`verify scale-readiness` 对该 clean batch 给出 `decision=no_go`，blocker 包括 `workflow still waits at checkpoint: build_homepage`、`TokenLedger evidence missing`、`measured throughput evidence missing`、`firstPassRate evidence missing` 与 `daily target >=10000 requires queueBackend=reliabletask`。说明**few-shot 清理与最小 SOP 依赖已验证成立，但 cursor_sdk local 启动面在干净环境下仍未稳定解除 500 阻断**，R-CS03 主项证据不能以“曾经跑通一次”视作关闭。
  - 复核（2026-06-24 startup 500 根因继续收敛）: 已把 `https://api.cursor.com/v1/me` 的直探接入 `env preflight/ready`（`python_runtime.py` 新增 `cursorCloudApi`，`urllib` SSL EOF 时自动 fallback `curl`），避免再把资格问题误判为 `cursor_sdk` 本地逻辑故障。结果表明当前 `CURSOR_API_KEY` 直连 Cloud Agent API 稳定返回 `403 plan_required`，消息 `Cloud Agent is not available for free users. Please upgrade to Pro.`；此前 `cursor_sdk`/bridge 将同类资格错误折叠成 `InternalServerError 500`。真实验证：`quwoquan_data/tests/local_contract/execution/test_cli_environment__local_contract_test.py` 9 passed；`env preflight --json --cursor-startup --model composer-2.5-fast --runtime local` 现直接输出 `cursorCloudApi.status=403`、`errorCode=plan_required`，并跳过误导性的 startup probe。根因已从“local startup 500 不明”进一步收敛为“当前 key/账号不具备 Cursor Cloud Agent 可用资格（或需更换具备权限的 user/service-account key）”。
  - 复核（2026-06-24 新 key + `composer-2.5` clean-root 续跑）: 用户提供新的 `CURSOR_API_KEY` 后，`env preflight --cursor-startup --model composer-2.5 --runtime local` 已全绿：`cursorCloudApi.status=200`、`keyType=user_api_key`、`cursorStartup.status=finished`。沿同一隔离根 `/tmp/qwq_e2e_clean_4hUtUj` 续跑 batch `b1`，managed workflow 已从 `build_homepage` 真正推进到 `WORKFLOW COMPLETE`：主页正文写成并通过 `build_validate`，文章 `都江堰·行前怎么安排` 由真实 agent 创作，随后 `produce_annotate`、`produce_review`、`publish` 全部完成。期间新增发现并修复一层残留发布门：`release_integrity.py` 原把跨 post `asset sha/sourceAssetRef/sourceCollectionId` 复用视为违规，这与用户明确裁定“图文同源/多底稿同图引用均允许，不做去重拦截”冲突；现已移除该 cross-post 去重门，并通过 `quwoquan_data/tests/user_acceptance/quality/test_release_integrity_gate__user_acceptance_test.py` 12 passed 验证。`scale-readiness --mode commercial` 新证据：`workflowState.status=succeeded`、`executionReadiness.tokenLedgerCount=1`、`firstPassRate=1.0`、`runtimeIntegrity.passed=true`、`published=3`（homepage=1/article=1/image=1）。R-CS03 已不再受 Cursor startup / publish gate 阻断。
  - 复核（2026-06-25 多实体 scaled-e2e fanout 全内容端到端）: 从单实体扩展到 **3 实体 source-derived fanout 全内容**（`全内容验证3` 源任务带 `content.quotas`+`allowContentQuotaShortfall`，经 `scaled-e2e prepare→author-runner --orchestrate→finalize→verify`），`QWQ_DATA_ROOT=/Users/zhaoyuxi/qwq_scale`、真实 cursor_sdk local bridge：青城山/都江堰各产 文章+图片+主页（`都江堰·行前怎么安排` 9272 字、`青城山·行前怎么安排` 8554 字真实正文，标题+entityRefs 均指代实体），武侯祠来源不足**诚实弃稿仅图片**（优雅 shortfall，不强凑）；`finalize RC=0`、`verify PASSED(roots=3)`、sample-drift+goldenset 全绿、3 release 均**无 homepage-as-post**。本轮修复 4 个放量级 blocker（均为「门禁绿但其实假/会崩」根因，已纳入军规 [.cursor/rules/17-data-content-acceptance-integrity.mdc](../.cursor/rules/17-data-content-acceptance-integrity.mdc)）：(1) **creator-模板耦合**——`enqueue_ref_job` 硬校验 author 作业 `creatorAssignment` 但 compose 在模板/路由被清空后未冻结 creator，`fanout_dispatch.py` 新增 `_resolve_registry_creator`（`match_creator` 空 blueprint 按载体从 registry 确定性指派完整人设并写回 + 跳过弃稿/`_homepage_only`），并已固化为军规 §5「creator 指派与模板路由解耦」；(2) **TEMPLATES_ROOT 漂移**——`registry.py` 改为版本控制模板库跟代码走（`_REPO_DATA_ROOT/templates` 回退），修复 `QWQ_DATA_ROOT` 漂移致 registry 0 creator 静默空集；(3) **base_draft_ledger 缺失（纵深防御双修）**——`release_integrity.py` 两函数把账本存在性判定延后到统计 `articleCount` 之后、仅认领底稿的文章/主页成品才必需（image/video-only release 合法缺账本，schema 异常仍即报）；同时 `run.py:_run_produce_review` 开头幂等 `save_base_draft_ledger(load_base_draft_ledger(...))` 保证文件始终落盘且 schema 合法（纯图批次 assignments 合法为空）；(4) **media_check envelope 缺失**——`produce_review` 在 review gate 已绿（`all_green`）时短路跳过 `handle_produce` 的 `_stage_review`，而 `media_check` 正是在 `_stage_review` 内产出，导致叶子已 review 的 image-only 内容在发布门因缺 `media_check` envelope 失败；`run.py` 在 `all_green` 分支幂等补跑 `check_images`（CV 人脸/水印/OCR/去重）保证发布门有真实 media_check 证据（scale-100 image-only 实体常见，免手动补）。3 实体 finalize RC=0 后，已建 `s10plan`（10 四川打卡地 source-derived fanout 全内容）并 `decompose freeze` RC=0、`author-runner --orchestrate` 后台推进中（max-workers=6，青城山已到 produce_compose checkpoint）。
  - 复核（2026-06-25 scale-10 端到端 GREEN）: `s10plan` 10 实体全内容跑完——**10/10 实体全部 `succeeded`/`publish`（n=12 checkpoint）**，含真实指代实体的文章+图片+主页，都江堰 `decision_experience` 因实体聚焦源不足（`entity_focus_off_topic=3`）**诚实弃稿**（优雅 shortfall，对齐用户裁定）。首跑 `VERIFY_RC=1`（8 issue）暴露并修复 2 个**放量级治理 blocker**（已纳入军规 [.cursor/rules/17-data-content-acceptance-integrity.mdc](../.cursor/rules/17-data-content-acceptance-integrity.mdc) §3）：(5) **verify 跨计划污染**——`scaled_e2e.py:_scaled_e2e_plan_runtime_issues` 校验 `run_matrix` 时直接信任按 `batchId` 跨任务聚合的 `summary` 并遍历全部 `orchestrators`，历史/并行任务复用同一 `planId`（→ 同一 `fanout_s10plan` batchId，如 stale `四川打卡地全内容放量验证10`）的 `reached:false`/`attemptFailures` 记录被混入造成**假阴性**；已改为按冻结计划成员 `(taskId,batchId)` 过滤、丢弃全局 summary 计数；(6) **孤儿 provisional 残骸**——agent 用临时标题（如都江堰 `岷江堰闸全景`）落地 quality/review 阶段后最终登记标题变化，旧坐标目录成未登记死残骸（无 manifest/无成品）被目录证据链孤儿门 BLOCK；`materialize.py` 新增 `prune_unregistered_post_residue`、在 `run.py:_materialize_reviewed_refs` 物化后按 content_object_index 剪除（带 manifest/成品的未登记对象保留交孤儿门显式 BLOCK，不静默删真实成品）。修复后 **`VERIFY_RC=0`、`[task scaled-e2e verify] roots=10 PASSED`、sample-drift PASSED、goldenset kappa=1.0**。回归：`tests/verify/test_directory_evidence_gate.py`+`tests/produce` 121 passed、`tests/orchestrate` 全绿；6 个 `tests/task`（lint/scaffold/inheritance/content_supply prep）失败为用户清空 SOP/templates/defaults 的预存在 fixture 债，与本轮 `scaled_e2e/materialize/run` 改动无关。scale-10 达平稳+高质量后已建**唯一 planId `s100plan`**（100 真实四川打卡地 discovery、source-derived fanout、max-workers=8），`decompose init/load/freeze` RC=0、`author-runner --orchestrate` 后台放量中。
  - 复核（2026-06-25 scale-50 自检复盘：管线确证 + 编排稳定性根因）: `s50plan`（50 四川打卡地 source-derived fanout 全内容）放量暴露并定位**编排层稳定性**核心问题，**内容管线本身再次确证健全**。证据：自检时 38/50 分区已派发但 `0 succeeded`、全部停 `stopped_at_until/produce_author`，深查发现各分区 leaf author job 在 object_queue 中已 `state=succeeded`（如 蜀南竹海_image），即**正确停泊在「leaf 终态、待 finalize」稳态**；手动补跑 `finalize` 后 **33 分区推到 `succeeded`+`publish`+`Gate PASSED`**，抽样真实指代实体内容（七曲山大庙 1507 字/实体 11 次/2 图、三星堆博物馆 1765 字/19 次/8 图、乐山大佛 2175 字/26 次/8 图），弃稿门正常（蜀南竹海 2 篇文章因 `entity_focus_off_topic`/`text_too_short`/`focus 0.17<0.20` 诚实弃稿）。本轮**新增治理根因**（已纳入军规 [.cursor/rules/17-data-content-acceptance-integrity.mdc](../.cursor/rules/17-data-content-acceptance-integrity.mdc) §7）：(7) **supervisor finalize 触发死锁**——自建监管脚本把 `stopped_at_until`（实为「待 finalize」稳态）误判为「仍活跃需继续 orchestrate」，收敛条件 `active==0` 与 finalize 触发互锁 → 永不 finalize → 跑 2h20m、38 分区离 succeeded 仅差一步却 0 succeeded（白耗 wall-time，token 未白烧：已产真实内容）；(8) **阶段职责混淆**——`finalize` 只做 review/publish 不创作，含未创作文章的分区在 finalize 下只停 `waiting_agent`（实测 15 个），创作必须靠 `author-runner --orchestrate` 跑满 leaf job。正确序列固定为 `author-runner(至 leaf 全终态)→finalize→verify`。(9) **进程保活复确认**——`nohup &` 后台 finalize 经一次性工具调用启动后被 harness SIGKILL（log 停在中途、无 RC、无 traceback），改用 Shell-ID 跟踪后台后存活推进，对齐军规 §6。(10) **并发 bridge 争用**（与上轮一致结论强化）——并发模式多 node bridge 冷启争用致 `Connection refused` 高失败率（≈79%），`QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1` 串行单暖 bridge 后 connection-refused 2 小时仅 +12（之前快速累积），代价是吞吐下降；放量级吞吐仍需 R-CS02 的 `reliabletask` 后端 + 远端 author 池替代本地串行 bridge。
  - 复核（2026-06-25 cs100 自检复盘：编排层 3 修复 + 决定性外部根因 = Cursor 云端 ~60% 5xx）: 进入 scale-100（`cs100`，100 四川打卡地 fanout 全内容）放量,先系统清理上轮死锁残骸（杀 cs100 supervisor/caffeinate/孤儿 bridge 全 0、runtime 复位），并修复 3 个新放量级 blocker（编排路径专属，叶子/produce 路径此前已健壮）：(11) **supervisor caffeinate 死锁**——`qwq_cs_supervisor.py` 用 `subprocess.run(caffeinate -w 自身pid)` 形成互等死锁（caffeinate 等本进程退出、本进程等 caffeinate 返回），cs100 卡死 1.5h 真因；改 `subprocess.Popen` 非阻塞；(12) **编排路径裸 Agent.prompt 无 bridge 稳定化**——`fanout_runner.default_orchestrator_runner` 本地分支此前直接 `Agent.prompt`，无 launch 文件锁/冷却/暖 bridge 复用/ready 延迟/重试，100 分区顺序冷启互抢端口致 `Connection refused`（实测一轮 **294 次**、`orchestrationFailed`、0 收口）；已改为**单一真相源委托** `task.run._default_managed_agent_runner`（与 produce 路径同一套健壮 bridge 生命周期，符合 R25），实测 refused 从 294 → **0**；(13) **编排 agent 调用无超时看门狗**——`_default_managed_agent_runner` 不对 `Agent.prompt` 设超时，本地 bridge 偶发 agent 调用挂起（bridge+python 双 0% CPU、零文件写入、无返回）会**永久阻塞串行队列**；已在编排委托外加独立线程 + 硬 deadline（`QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS`，默认 300s），超时即杀 workspace bridge 解阻并标记为可重试状态交 per-partition 重试。三修复均经 `test_fanout_runner.py`(26)+`test_cli_finalize_author`(配套)+`test_cli_verify_audit` 全绿。**决定性根因（外部，非本仓代码/账号/本地 bridge）**：cs100 一轮 run_matrix **308/308 编排记录全 `reached:false`**，三种失败并存（`startup: internal error` / `orchestrate agent timed out 150s` / `Connection refused`）。分层隔离测试定位：① 内层 `data workflow run --until content_plan` 单分区 **584ms 健康完成**（download_plan/fetch/build_prepare 全自动过，正确暂停 build_homepage 等 agent 写 page.md）；② 本地 bridge `launch_bridge` **0.4s** 正常；③ **5 个最简 `Agent.prompt('Reply OK')`（每次全新 bridge）→ ok=2/err=3，失败率 60%**，错误为 `InternalServerError: internal error` 与 `RemoteProtocolError: Server disconnected`——即 **Cursor 云端 API 当前对本账号高频 5xx/断连**。编排 Ralph 循环需连续数十次成功 agent 调用，单次 60% 失败下完成概率≈0，完整解释 308/308 失败，也解释为何 s50 在更早会话（云端健康时）能产 497 篇。**这是外部瞬时基础设施条件，本仓任何重试/暖 bridge/看门狗都无法把 60% 上游失败率拉到无人值守多步编排所需的可靠度。**
  - 复核（2026-06-27 cs100 续跑：prepare 完成 + author 进行中）: `fresh_cs100verify_20260626` prepare **已到 produce_compose**（17 实体 download+build_homepage+content_plan+compose，63 content objects）；纠正 fanout 批次重复 download 后改走 **fresh 批次单线 author→publish**。`produce_author` 曾推进至 **~20/49** agent jobs（18 完成 + 续跑 2 篇后 SIGTERM 中断）；修复 supervisor：`cs100_fresh_to_gate.sh` **pgrep 模式错误**（误判 task run 已退出）、**stale `controllerYield` 阻断 managed resume**、macOS 无 `flock`/`setsid`（改 pid 锁 + 去掉 gate 内 `env ready` 的 plan_required 误阻断）。挂接 `cs100_author_resume_loop.sh` + `cs100_fresh_to_gate.sh` + `start_cs100_supervisors.sh`（WORKFLOW COMPLETE 后自动 `scale-readiness commercial target=100`，go 后启动 cs1000）。**当前 decision=no_go**（pipeline 未完成）；须从用户 Terminal 启动 supervisor 长跑（agent-shell 子进程易 SIGHUP）。证据口径：旧 data artifact 已清理，不再作为当前入口；复验需以 `QWQ_OUTPUT_ROOT/data/runtime/**/batch/_shared` 重生批次证据与 `QWQ_OUTPUT_ROOT/env/repo/runs/**` 报告为准。cs1000 `cs1000verify_20260626` 170 实体 plan 已 frozen，待 cs100 go。
  - 复核（2026-06-28 里程碑2.1：放量到100 的池/分类法/契约层就绪闭环）: 复盘上一轮 cs100 续跑后，`verify_quwoquan_data.sh` 唯一硬阻断为 `template creator-lint` 失败——根因是**未跟踪的 100 创作者池** `templates/creator_profiles/travel/travel_batch_100_v1/*.creator.yaml` 的 `recommendationTagRefs` 仍用 **2 级短标签**（如 `Topic/旅行/摄影`），且旅行分类法缺 6 个规范叶子。已按 metadata-first 闭环：(1) 在分类法唯一真相源 `bootstrap/taxonomy/bootstrap_tags_topic_verticals_part1.py` 增补 6 个规范叶子（`旅行主题/{美食之旅,亲子游,古镇古村,高原秘境}`、`玩法/{露营,节庆民俗}`，并同步 `expected_size` 14→18、22→25）并材料化到 `publish/tags`；(2) 把 100 池 12 个短标签全部改写为规范 3 级叶子（脚本逐行精确替换，无副作用）；(3) **修正生成器真相源** `_common/creator_pool/constants.py:TRAVEL_TOPIC_REFS` 为规范 3 级路径防回归（重生池不再产 2 级）；(4) 更新 `match_creator` 专精匹配契约测试为正确行为（专精内容命中携该专精标签的池内作者，而非泛化全国 builtin）；(5) `tests/support/data_cli_fixtures.py` 与 `publish_ops/rebuild_directory_layout_sample.py` 的 `source_refs.json` 去掉 `citedSourceRefs/sourcePaths/内联 sourceMarkdown` 对齐「单底稿零参考宪法 v2」；(6) 顺手修复并行 content-service 未跟踪测试 `creator_pool_content_feed_contract_test.go` 的 stub 媒体域名 `cdn.example.com`→`example.com`（对齐同目录既有约定与 `media-release-contract`）。**证据口径**：全量 `verify_quwoquan_data.sh` 端到端 **GREEN**（`[verify-creator-pool-seed-consistency] PASSED canonical=travel_batch_100_v1`、`[template creator-lint] PASSED`、`[media-release-contract] OK`、`[verify-quwoquan-data] PASSED`）；旧 creator readiness artifact 已清理，复验以 `QWQ_OUTPUT_ROOT/env/repo/runs/**` 新报告为准。即**放量到100 所需的创作者池 + 分类法 + 契约/门禁层已就绪**；剩余仍为 (a)(b) 资源/执行项（cs100/cs1000 真实长跑 + reliabletask + 吞吐/import/TokenLedger 商业证据），与 R-CS02 同源，须从用户 Terminal 启动 supervisor 长跑。
  - 复核（2026-06-28 cs100 真实长跑 + composer-2.5 + bulk-repair 恢复 → 商用 readiness no_go）: 用户提供新 key（`crsr_c15e…`）并要求用 composer 模型完成真实长跑。`env preflight --cursor-startup --model composer-2.5`（startup-timeout 300s）全绿后，`fresh_cs100verify_20260626`（17 实体）以 `--managed --runtime local --agent-provider cursor_sdk --model composer-2.5 --max-workers 1 --resume` 真实长跑：download_plan/fetch→build_homepage(14)→content_plan(55 article+14 image)→produce_author(真实 agent，67 finished author jobs)→produce_review。首轮 40/55 materialize，15 篇 review 失败触发 `produce_review bulk failure`（>20% 阈值 `bulk_limit=max(5,int(total*0.2))=11`，设计内拒绝自动批量改写、转人工诊断）。诊断确认 `route_core.SOFT_CHECKS=set()`（生产 profile 无软门，全部硬阻断），失败为真实质量门。设置 `QWQ_PRODUCE_REVIEW_ALLOW_BULK_REPAIR=1` 后 2 个 react-rewind 周期（`MAX_REACT_REWINDS=2`）重写：首轮 review 一次过 40/55（first-pass≈72.7%），composer 重写恢复 9/15 → **49/55 content object materialize（post-repair 物化率≈89.1%）**；系统 `executionReadiness.firstPassRate=null`（门控于 workflow=succeeded，未达成故不出值）。**残留 6 篇为 composer-2.5 真实能力天花板**（feedback 重写后仍卡）：3× `baseDraftFidelity`（54.0%/46.8%/28.4% < 55%，过度脱离底稿另写，直接违背「以原文为基础轻改」）、1× `writingIntentConsistency`（缺 transport/ticket 结构桶）、1× `travelogueDensity` 套路化开头、1× `provenanceRewrite` 泄漏底稿标识 + 开头、1× `creativeGovernance.personaBoundary`（虚拟作者伪装亲历「去过…之后」）。`verify scale-readiness --mode commercial --target 100 --daily-target 100 --min-pass-rate 0.9` → **`decision=no_go`**（旧 cs100verify readiness artifact 已清理，复验以 `QWQ_OUTPUT_ROOT/env/repo/runs/**` 新报告为准）。blockers：`workflow status must be succeeded`（停 manual_required）、`quality target satisfaction 63%<90% (63/100)`、`source-ready object capacity 94<120`、`creator load 超 maxDailyPosts=1`（仅 2 创作者承 55 对象，`qwq_creator_landscape_photographer_001`/`qwq_creator_travel_blogger_chuanxi_001` 过载）、TokenLedger/release/throughput/firstPassRate evidence 缺（均门控于 workflow=succeeded）。**吞吐结论更正**：`throughputProjection.perWorkerObjectsPerHour=32.65`，而 100/天仅需 `requiredObjectsPerHour=4.17` → **单 worker 已 ~8× 余量，吞吐在 100/天不是瓶颈**；串行吞吐仅在 1万/10万级（需 417/4167 obj/h + reliabletask 多 worker）才成阻断，归 R-CS02。**质量结论**：通过的 49 篇 + 14 主页真实指代实体、源接地、过全部商用级硬门；管线/门禁/repair 环/证据链工作正确（drafts 保全、失败精确可诊断）。**进程保活**：复用 nohup+`os.setsid()` 双 fork 守护（PPID=1 独立会话）解除「agent-shell 子进程被 harness SIGKILL」问题，恢复轮在多次工具调用间存活跑完。**cs100 sub-scale 实质**：17 实体仅产 ~63 对象，结构上不足 100/天目标（需更多实体 + 提升 source 准入 + 扩创作者池）。**新发现（图片授权完整性缺口，已用户裁定可作为 cs100 复核子项记录，不另立正式风险）**：`木格措·值不值得去` 文章 3 图同源自 Qunar 单元 `13.article_qunar_base_11`，封面带真实 CC BY-SA 3.0（termsUrl+authorizationProof），但 `detail_6`/`closing_6` 在 download 阶段未捕获任何授权（`index.json` 无 license），`release_integrity._has_rights_proof` 正确拦截。根因：download 逐图 license 捕获不一致（非封面图可无授权流到 materialize）。尝试在 `route_assets._pick_safe_image` 加选图期 license 过滤，但现有 fixture（`test_route_assets_layout.py`）播种无 license 图且真实数据逐图授权不齐 → 过滤会过度拒图、破坏既有内容生产，**已回退**（git diff 空）；正确修法需先在 download 阶段把页/集合级授权传播到该来源所有图，再在选图期过滤，列为待办。
  - 复核（2026-06-28 底稿中心 1:1 内容生产重构落地：契约+代码+测试，质量误杀根因消除）: 复盘上一轮 cs100 实测后，按用户裁定把内容生产从「实体×writingIntent 角度配额」彻底切换为**底稿中心 1:1**（计划 `复核结论(直接回答三问)` P0-P7，无 shim/无兼容旁路）：(P0/P2)**标题取自底稿**——新增 `base_draft.extract_source_title`（剥平台后缀/去噪/最小长度），`_publish_angle` 改为按 `carrier`+`writingIntent` 派生类目（画报/攻略/体验/游记），文章源无标题即上游弃稿；(P1)**枚举合格 source unit→1:1 item**——`run.py:_auto_content_plan` 删除 `entityArticlesPerTarget/imageWorksPerTarget` 角度配额 fan-out，`content_plan.validate_content_plan` 在 `separated_research` 下不再校验 per-target 篇数/`requiredAngles` 角度覆盖（改为车道开关，合格底稿数即篇数）；(P3)**实体降级为多标签**——移除文章/图片 `_entity_focus_issues` 弃稿门，entity_focus 仅保留在「实体→主页（百科源）」路径与选源排序，`entityTags` 取底稿提及实体集合；(P4)**fidelity 正确化（消除误杀根因）**——删除 `base_draft.intent_aligned_base_text`/`load_intent_aligned_base_draft_text` 收窄分母，fidelity 对**整篇单一底稿**度量（保留 0.55/0.995 trigram 留存算法），`route_review`/`route_compose`/`entity_workflow` 消费点改 `load_base_draft_text`——直接消除「6 天多目的地游记被整篇离题分母把 baseDraftFidelity 拉到 28.4%」的系统性误杀；`writing_intent_issues` 降为派生可选标签（空/缺不阻断）；(P5)**单底稿禁跨源**——`baseSourceReusePolicy`/`multi_intent_source_bundle` 复用逃生口在 validator(`content_plan.py`)、`produce/handler.py:_assign_base_draft`、`_common/handoff.py:build_batch_reducer_gate` 三处彻底删除（一源一作品；image 单 sourceCollectionId、禁跨集合资产；保留 `_claim_asset`/`_claim_asset_sha`/`_claim_collection`/`base_source_owners` 反拼接门）；(P6)**快速失败+常驻**——移除 `produce_review` 的 20% bulk-repair 闸门（`QWQ_PRODUCE_REVIEW_ALLOW_BULK_REPAIR`），失败 ref 一律按有界 ReAct 预算（`MAX_REACT_REWINDS=2`）重写，预算耗尽后在 `allowPartialContent` 下由 `_react_rewind` 弃稿仍未过门对象并重跑剩余内容收口（不阻塞批次、不追求 100%；strict 模式保持转人工），常驻 supervisor 维持 `QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS=1`。**测试证据**：重写/新增契约测试均绿——`test_content_plan_distribution`（无 per-target 地板/无角度覆盖）、`test_content_plan_source_gate`（off-entity 多标签接受 + reuse 拒绝 + 跨源资产拒绝）、`test_auto_content_plan`、`test_quality_gates`（writingIntent 可选）、`test_content_object_router`/`test_post_dir_layout`（angle 派生）、`test_task_author_review`（新增预算耗尽弃稿/strict 转人工 2 例 + bulk 有界重试）、`test_content_plan_quality_sort`；删除 obsolete `test_base_draft_intent_align`。`tests/common`+`tests/local_contract/common` 334 passed、`tests/local_contract/produce`+`task` 366 passed（仅余预存在的批序全局态 pytest 同会话污染与 SOP/创作者池/template-lint 路径债，已 stash 对照确认与本重构无关、standalone 全绿）。`verify single-contract-source`/`works-classification` GREEN。grep 确认 `intent_aligned_base_text`/`_entity_focus_issues`/`multi_intent_source_bundle` 逃生口零残留（仅留禁用提示与注释）。**仍待（操作/资源项，归 R-CS02/作者模型）**：真实 cs100/cs1000 长跑产 TokenLedger/firstPassRate/throughput 商业证据、reliabletask 后端、合格源供给与创作者池扩容、download 逐图授权传播——本重构是「让 job 单源、独立、可水平分发 + 消除 fidelity 误杀与 bulk 阻塞」的必要前置，非充分条件。
  - 复核（2026-06-28 P7 验证回归 + scale_readiness 边界裁定）: 对底稿中心 1:1 重构做整轮回归取证（本会话无新增代码改动，纯验证 + 边界澄清 + 回写）。**测试证据（standalone 绿）**：核心重构套件 90 passed（`test_quality_gates`/`test_content_object_router`/`test_post_dir_layout`/`test_auto_content_plan`/`test_content_plan_source_gate`/`test_content_plan_distribution`/`test_task_author_review`/`test_content_plan_quality_sort`）；`scale_readiness`+`site_scale_readiness`+`handoff`+`base_draft_fidelity`+`release_integrity`+`directory_evidence` 84 passed；`tests/produce` 单独 101 passed；`tests/common`+`tests/local_contract/common` 334 passed；orchestrate fanout 5 套件 64 passed。**全部失败均为预存在测试隔离缺陷、与本重构无关、经 standalone 复跑证伪**：(i) `tests/local_contract/produce`+`tests/produce` 同会话 3 例（`test_compose_brief_persists_reassigned_base_source_ref`/`test_route_workflow_generates_real_review_green`/`test_agent_draft_time_facts_are_stable_and_monotonic`）单独跑全绿、`tests/produce` 单独 101 passed；(ii) `batch_asset_registry`/`batch_asset_stability`/`batch_shared_artifacts` 8 例为跨模块 `QWQ_DATA_ROOT` 环境污染 + `globalBatchSeq`/`commandChain` 全局态（CLI 子进程继承最后导入模块的 env），逐文件单独跑 3+5+2=10 全 passed；二者均在重构未触及的批清单/资产登记基础设施，非内容计划/fidelity/单源/快速失败逻辑。**scale_readiness `_expected_objects` 边界裁定（P1 子项收敛为诚实边界，不做破坏性改写）**：`verify/scale_readiness.py:_expected_objects` 仍按 `targetCount × quotas` 投影（quota 在底稿中心下重释为「车道开关 + 每目标上限」而非「每实体产 N 篇」指令），原因——(1) 在 `allowPartialContent=True`（底稿中心默认）下 article/image 配额缺口已降级为 warning 非 blocker（`scale_readiness.py:759-772`），不会误杀底稿中心批次；(2) 真正的底稿中心容量门是源准入口径的 `sourceReadyObjectCapacity`（`scale_readiness.py:744`），与 quota 投影解耦；(3) 生产 spec 仍携带 quota 数字 ⇒ `expected.total>0`，`scale_readiness.py:848` 的「expected content object count is zero」不会误触；(4) 把投影改为 planned/source-unit 口径会破坏既有 quota 耦合契约测试（`scale_readiness_cases/release_closure_cases.py:108` 硬断言「materialized image count 0 < expected 1」需 quota 投影），且对 GO/NO_GO 判定零增益、反而弱化一个有用的容量信号。故保留 quota 投影为「非阻断上限」、以 `sourceReadyObjectCapacity` 为底稿中心容量真相源，是经过权衡的诚实边界而非遗漏。grep 复确认 `intent_aligned_base_text`/`load_intent_aligned_base_draft_text`/`_entity_focus_issues`/`multi_intent_source_bundle` 逃生口零残留（仅留禁用注释 + `baseSourceReusePolicy` 探测→无条件拒绝路径 + 提示词显式禁用语）。**gate-invocation 风格复跑**（`verify_quwoquan_data.sh` 逐文件 `python3 <file>` + 分组 pytest 口径）：重构触及的 6 个独立步骤（quality_gates/handoff/scale_readiness/post_dir_layout/content_object_router/entity_composer）+ 2 个 pytest 分组（fidelity+distribution+source_gate 24 passed、auto_content_plan+task_author_review 等 66 passed）全绿。**`template creator-lint` 环境澄清**：直跑曾报 `tagRef not found: Topic/旅行/出行方式/高铁铁路` 等，定位为**本会话 shell 继承了 stale `QWQ_PUBLISH_ROOT=/Users/zhaoyuxi/qwq_scale_verify/publish`（scale-verify 运行时根，未材料化完整 `Topic/旅行` 子树）**；committed 仓库 `quwoquan_data/publish/tags/Topic/旅行/{出行方式/高铁铁路,旅行主题/文化深度游}` 实际齐全，`QWQ_PUBLISH_ROOT` 指向 committed publish 后 `[template creator-lint] PASSED`——非代码缺陷、与本重构无关，仅提示长跑放量需让 gate 跑在 committed/默认 publish 根而非 stale scale-verify 根。
  - 复核（2026-06-29 底稿中心冒烟试跑 GREEN + cs100 重构后真实长跑启动）: 新 key（`crsr_5ce8…`）`env preflight --cursor-startup --model composer-2.5` 全绿（`cursorCloudApi.status=200`、`cursorStartup.status=finished`）。**冒烟试跑** `creator_smoke_20260629`（3 实体九寨沟/峨眉山/都江堰，`allowPartialContent=true`，`composer-2.5`/`max-workers=1`）`WORKFLOW COMPLETE`：`release verify PASSED`（`旅行__地域__四川省__景区__创作冒烟试跑__creator_smoke_20260629`）、`scale-readiness --mode trial --target 3 decision=go`（旧 creator smoke readiness artifact 已清理，复验以 `QWQ_OUTPUT_ROOT/env/repo/runs/**` 新报告为准；`firstPassRate=55.56%`，诚实部分交付 4/8 文章弃稿后 release 仍 12 对象：3 主页+4 文章+5 图片）；五维度抽检：3 实体主页均 `01.home_wikipedia` 百科源、`generator=agent`；`source_refs.json sources==1` 单底稿宪法通过；fast-fail 弃稿 4 篇（mustIncludeFact 配图同源句 + baseDraftFidelity）不阻塞批次。runtime 中间批次 verify 对弃稿残留 asset registry 报 12 issue（release 面已 PASSED，属预期中间态）。**cs100 重构后新批次** `fresh_cs100verify_20260629`（17 实体源中心 1:1 spec 重建于 `$QWQ_DATA_ROOT`，`creatorPoolRef=travel_batch_100_v1`）：`scaled-e2e prepare` 完成 download 17/17（99 source bundles，3 实体诚实不发布：阆中古城/牛背山/若尔盖花湖），停 `build_homepage`；`cs100_author_resume_loop.sh`（batch 默认改 `fresh_cs100verify_20260629`）后台 managed 长跑已启动。商用 `decision=no_go` 仍待本批次 `WORKFLOW COMPLETE` 后 `scale-readiness --mode commercial --target 100`。
  - 复核（2026-06-30 fidelity 根因修复真实端到端实证 + P5 门禁逐项 + P6 受限并行结论）: 本窗在底稿中心 1:1 重构基础上，定位并修复 **baseDraftFidelity 数学不可达根因**（`route_compose._attach_base_draft_text` 把 `baseDraftText` 截断到 4000 字 + 固定 wordCount 上限 ⇒ 长底稿轻改无论如何达不到 55% 留存）：新增 `base_draft.BASE_DRAFT_PROMPT_MAX_CHARS=24000`（整篇底稿入 prompt，仅书籍级超长设安全上限）+ `clean_base_draft_length` + `base_aware_word_count`（light-edit 文章字数目标跟随清洗底稿长度，分母同源），并以 `test_base_aware_word_count_tracks_long_base_draft` 契约锁定（已提交 4350235dc）。**Phase A**：`verify_quwoquan_data.sh` 干净 env（`-u QWQ_DATA_ROOT` 等）跳过唯一外部污染门后 EXIT=0（`[task lint] OK` 扫仓库、`[template lint] PASSED`、末段 91 passed 含本窗 base_aware/route_brief/RC 全套契约、0 FAIL）；两处红灯均归因**外部/环境**（他流 `fixture_user_*` 注入污染 prefab-user 门 + 本地 `QWQ_DATA_ROOT` sandbox 草稿任务 `测试省/景区全覆盖*` 缺 angles，CI 干净环境不复现），非本任务回归（e79d9bc79）。**Token**：N=3 探针复验 success=3/auth=0/真5xx=0%/bridgeDisconnect=0/P95=19.8s（token 当前有效）。**Phase C 实证（决定性）**：P5 四川批次 `p5_sichuan_20260630` 清陈旧策略串 mustIncludeFact（=现行 L6335 `[]` 输出）+ 重 compose 后，`task run --resume --managed --agent-provider cursor_sdk --model composer-2.5 --until produce_review`（~440s 未超时）重 author→review **7 PASS/1 FAIL**；`base_draft_similarity` 直算硬证据：都江堰多目的地路书 **18.6%→90.8%**、全 8 篇∈[60.2%,96.7%] 全部 ≥55%、**无一 fidelity/mustIncludeFact 失败**（root-cause 修复经真实 composer-2.5 端到端生效）；唯一 FAIL=318川藏游记 `entityCoverage`（fidelity 96.7% 但未提都江堰=content_plan 源-实体错配，硬门正确拦截，非本修复回归）。**Phase D 门禁逐项**：零 Wikimedia 替代图(7/7)、`sourceUrls` 单源(7/7，消解"为何如此多来源")、storySpine 净、文章/实体物理解耦、`verify --scope current` release **PASSED** 均达标；**firstPassRate 0.875<0.9**（1 篇 entityCoverage）；**source.md 图文混排未达**（本批 27 source.md 仅 1 含内联图 ⇒ 文章 `publishMediaMode=text_only`、`assets=[]`，RC3 提取器已代码+契约修复但本批是修复前陈旧源，真实 qunar lazy-load 重下载验证待续，**登记 R-CS10 图文不同源 P0**）。**Phase P6 受限并行（如实 GATE_BLOCK）**：串行（concurrency=1+warm probe+local SDK）可靠（5 篇 ~440s）；concurrency=2 经冻结 `p6_parallel_20260630` plan + `author-runner` **双路径均阻断**——保留 probe 路径报 `Failed to verify existence of branch 'codex/content-ui-directory-restructure' in repository openstudio2022/quwoquan`（fanout 探针校验远端分支，本地分支未推送）；`--skip-startup-probe`（默认/`--runtime local`）2 worker 并发 bridge 冷启**零输出挂起**（300/560s 被杀）；间接并行证据 P0 N=20 并发 bridgeDisconnect=0 + `fanout_runner` 26 测试过（含 connection-refused 恢复）；根因为环境约束（bridge 冷启争用 + 远端分支），修复方向 per-worker 预建 warm bridge / 错峰冷启 / push 分支供 cloud dispatch（旧 scale_fix_stage artifact 已清理；复验以当前 data gate 与 `.qwq_output` 新证据为准）。
  - 复核（2026-06-30 提示词模板化 + 三类解耦放量重构落地 + 真实 composer-2.5 cloud 可达 + managed local runtime 环境阻断）: 本窗按规划 P0-P8 把上一轮 fidelity/P5/P6 修复**产品化**为可放量管线并提交（HEAD 链 b0a4d103a..2244dc3c0）：**P0** 运行时根从 `~/qwq_scale_verify` 归位到项目内 gitignored `.qwq_sandbox`（根变量隔离，`verify --scope current` 不被 sandbox release 污染）；**P1/P1b** 新建 `quwoquan_data/prompts/`（system/task/partials/vars/README）+ `_common/prompt_render.py` 渲染器，article author / entity homepage / image curation / review-repair 全环节改消费 md+`{{}}` 模板（XML 分区 `<role><capabilities><constraints><documents><output_format>`），删除"会话模型"措辞与 review gate 硬门复述，补模板 lint + 渲染契约测试接入 `verify_quwoquan_data.sh`；**P2** figureGroup 连续图合并占位（见 R-CS10 复核）；**P3** 三类彻底解耦（实体=百科多源择优、文章=图文混排≥200/长文≥600 有标题含视频弃稿、图片=专业图库图文分离，download 去实体键控按内容类型路由）；**P4** 图库 registry 合规分级 + 授权完整性硬门（页/集合→逐图 license/credit/termsUrl/authorizationProof）+ 受限如实标注 + 非中文译简体门；**P5** 字数门按形态自适应统一 `route_review`/`verify_content_quality` 口径（`_common/quality_gates.py` 单一真相源）+ 非致命检查降软扣分；**P6** 错峰冷启释放器 + per-worker warm bridge + 冷启并发上限 + cloud orchestrator 硬超时看门狗 + 吞吐/connection-refused 量化（契约测试绿）。**P7b** `verify_quwoquan_data.sh` 跳过两处他流工作树漂移后全量绿、P0-P6 契约门全 PASS。**真实 agent 可达（决定性）**：新 key `crsr_d93f…` 注入后 `env preflight` `cursorCloudApi=ready`（keyType=user_api_key）、`Client.launch_bridge`+`Agent.prompt(CloudAgentOptions, composer-2.5)` 返回 `status=finished` agentId=`agent-6f0049a9-…`（真实 cloud agent 调用成功）。**环境阻断（如实 GATE_BLOCK）**：`cursorStartup runtime=local` 6 次 warm retry 全 `ConnectError: Connection refused`（本沙箱无本地 Cursor agent runtime、cursor-agent 不在 PATH），而 `data workflow run --managed` 在 `_managed_preflight`（run.py:8110-8111）硬要求 `--runtime local` ⇒ **无人托管自动驱动 content_plan/produce_author 在本环境不可用**，故 30-50 中批量 firstPassRate≥0.9 与并行吞吐**本窗仍未实测**（环境性，非实现缺陷）。真实小批（都江堰/青城山）真实下载→build_homepage→build_validate 全绿，主页经真实采纳门（**P5 fidelity 拦截都江堰首版 36.4%<55%→底稿轻改后通过、三件套物化**），batch 已回绕到 `content_plan` 等待态 + `task.yaml` 补真实配额（separated_research 1主页+1攻略+1图片/实体）供续跑；旧 scale_fix_stage artifact 已清理，复验证据以 `.qwq_output` 新运行输出为准。
  - 复核（2026-07-05 双1k creator commercial gate + SDK operator summary）: `travel_photo_1k_v1` 旧 creator readiness 证据曾达 `decision=go`（1200 unique、travel/photo view 均 1000、overlap 800、crossDualTagCoverageRate=1.0、candidatePoolSize=6000）；旧 data artifact 已清理，复验以 `QWQ_OUTPUT_ROOT/env/repo/runs/**` 新报告为准。但**内容执行面与账本仍未满足 commercial go**：当前最新百级真实批次 `scale100_elastic_overfetch_2x_0704a` 的 operator summary（`.qwq_sandbox/data/runtime/batches/弹性百级复跑-1f7ff8e1__scale100_elastic_overfetch_2x_0704a/_shared/sdk_monitoring_report.json`）明确 `passed=false`，核心问题是 `tokenLedger.measurementMode=estimated_from_artifacts`、`managedBatchAudit.failedLaneCount=21`、`lastAgentRun.infrastructureFailures=4`、`watchdog.eventCount=42`；同时 `quality.firstPassRate=0.8438` 仍低于 0.9。说明本轮虽已把 runtime/model/key、startup gate、operator summary、authoritative ledger 写入代码主线，但**旧批次证据仍是估算账本，尚未用新代码重生出 authoritative TokenLedger 的 commercial 批次**；R-CS03 不能关闭，当前应保持 NO_GO。
  - 复核（2026-07-05 Pinterest image-only H100 诚实对账）: 新一轮 H100 Pinterest 图片 lane 已把 source 侧前半段跑通，但**不能据此宣称 H100 完成**。证据：`/tmp/qwq_pinterest_h100_image_20260705_v1/pinterest_h100_manifest_report.json` 漏斗为 `requested=166 / harvested=117 / publishable=117 / rejected=49`；`runtime/site_supply/photography/pinterest/h100_real_pin_4/_shared/attributed_asset_ingest_report.json` 为 `qualified=116 / picked=100 / gate=pass`；`runtime/batches/H100风光摄影-657a8c85__h100_real_pin_4_task_theme_v2/_shared/site_supply_content_plan_report.json` 为 `selected=100 / itemCount=100 / gate=pass`。但该 batch `_shared` 目录当前只有 `content_plan_packet.json`、`site_supply_content_plan_report.json`、`content_object_index.json`，缺少 `env_ready_report.json`、`task_workflow_state.json`、`token_ledger.json`、`ship_report.json` 等真实 runtime/发布证据；独立 preflight 证据 `/tmp/qwq_pinterest_h100_image_20260705_v1/h100_env_ready_local_gpt53.json` 明确 `cursorStartup.ready=false`、错误类别为 `InternalServerError`、`errorCode=internal`、`httpStatus=500`、3 次尝试全失败；本轮又按“默认最新 composer”口径补跑 `/tmp/qwq_pinterest_h100_image_20260705_v1/h100_env_preflight_local_composer.json`，结果 `cursorApiKey.valid=true`、`network.ready=true`、`cursorStartup.model=composer`，但 `attemptCount=3` 仍全部 `InternalServerError/httpStatus=500`，证明阻断已不再是模型漂移而是 local managed Cursor startup 本身；同步生成的 `/tmp/qwq_pinterest_h100_image_20260705_v1/h100_sdk_monitoring_report_composer.json` 也明确 `passed=false`，问题为 `task_workflow_state.json missing`、`token_ledger.json missing`、`env_ready_report.json missing`，并保留 `managedBatchAudit.failedLaneCount=1`、`watchdog.eventCount=42`。因此 H100 目前只能判定为「source/ingest/content-plan 已绿，真实 author/review/release/TokenLedger 未启动且被 local managed cursor_sdk startup 500 阻断」；在拿到真实闭环前，**不得启动 H1000，也不得进入 10k/100k evaluate**。
  - 复核（2026-07-06 本地 composer 同根对账）: 再次用当前环境直跑 `python3 quwoquan_data/scripts/cli.py env preflight --json --cursor-startup --runtime local --model composer`，结果仍是 `cursorApiKey.valid=true`、`network.ready=true`、`cursorStartup.model=composer`，但 3 次尝试全部 `InternalServerError/httpStatus=500`；说明当前 key **可用**，因此用户提供的备用 key 本轮未启用，阻断仍然是 local managed startup 本身。与此同时，按现行 `sdk_monitoring.py`（已禁止自动发现全局 watchdog）并显式绑定同一隔离根 `QWQ_RUNTIME_ROOT=/tmp/qwq_pinterest_h100_image_20260705_v1/runtime` 重生成 `/tmp/qwq_pinterest_h100_image_20260705_v1/h100_sdk_monitoring_report_clean_20260706.json` 后，旧报告里的 `watchdog.eventCount=42` 与 `managedBatchAudit.failedLaneCount=1` 噪音已消失，真正 blocker 只剩 `task_workflow_state.json missing`、`token_ledger.json missing`、`managed_batch_audit.json missing`、`env_ready_report.json missing`。这同时暴露出另一条执行面硬约束：H100/H1000 的 `verify sdk-monitoring`、`verify scale-readiness`、后续 `task run` 必须与 preflight 使用**同一**隔离根（显式设置 `QWQ_RUNTIME_ROOT/QWQ_PUBLISH_ROOT/QWQ_DATA_ROOT`），否则会错误读到仓库默认 runtime 根，形成假报告。
  - 复核（2026-07-06 local/cloud composer 执行面对账）: 为推进 article 商用主线，再次在仓内当前环境执行 `env preflight --json --cursor-startup --model composer` 双运行面核对。`--runtime local` 结果为 `cursorApiKey.valid=true`、`network.ready=true`，但 `cursorStartup` 连续 3 次均 `InternalServerError/httpStatus=500/errorCode=internal`；`--runtime cloud` 结果为 `cursorCloudApi.status=403`、`errorCode=plan_required`、`message="Cloud Agent is not available for free users. Please upgrade to Pro."`。这说明**当前环境下既不能启动 authoritative local managed cursor_sdk+composer，也不能改走 cloud managed composer**。因此本轮无法新生成 commercial 所需的真实 `env_ready_report`、`task_workflow_state`、`token_ledger`、`managed_batch_audit` 批次证据；H100 authoritative 复跑与 H1000 gate 均继续保持阻断，不能假装进入下一阶段。
  - 复核（2026-07-06 H100 Pinterest 批次真实跑完 + commercial100 收口）: **此前「local startup 500 硬阻断、batch `_shared` 证据缺失」的记载已被新事实推翻**——`cursor_sdk+composer` local startup 已恢复（batch `_shared/env_ready_report.json` `ready=true`），Pinterest 图片商业线 H100 批次 `H100风光摄影-657a8c85__h100_real_pin_4_task_theme_v2`（隔离根 `/tmp/qwq_pinterest_h100_image_20260705_v1/`）真实跑完：`task_workflow_state.status=succeeded`、100 篇画报真实发布、`firstPassRate=1.0`、`objectsPerHour=7.099`（100/天仅需 4.17，吞吐有余量）。本轮按 `mode=commercial, dailyTarget=100` 口径完成四项收口：(1) **capacity 116→124**——真实补采 12 条此前因超时/缺作者元数据被拒的 pin（回收 8 条 publishable，1 条与存量 sha256 重复被去重门正确剔除），合并 manifest 后 `ingest-attributed-assets` 重跑 `qualified=124 ≥ 120`、gate pass（`runtime/site_supply/photography/pinterest/h100_real_pin_4/_shared/attributed_asset_ingest_report.json`）；(2) **gamma import + search/reco 下游全链路真实验证**——隔离根 bootstrap 标准标签体系后 `ship --import` 一致性 preflight passed（此前 dry-run 暴露 20 个 dangling tag ref，根因是隔离根从未 bootstrap tags），真实灌入 gamma-local Mongo（`postsUpserted=100`、`feedUpserted=100`、release `status=active`，注意宿主机连 RS 需 `directConnection=true`）；`search-backfill` 重建索引后 gamma search-service `POST /v1/search` 真实命中本批帖（rankPosition=1），`GET /v1/content/feed` top100 中 96 条为本批帖；`site-supply downstream-evidence --write` 五项 checks 全 true、gate pass（`_shared/downstream_e2e_report.json`、`_shared/gamma_import_report.json`、`ship_report.json` importRequested=true）。期间修复 `MongoPostStore.ListAll` 吞解码错误导致 search-backfill 误报 total=0 的缺陷（改逐条解码跳过脏文档并告警，Go persistence/searchindex 测试通过）；(3) **TokenLedger authoritative 前向修复**——确认本地 bridge 终态 `RunResult` 不携带 usage、authoritative 用量只在流式 `turn-ended` 事件上，`task/run.py` 新增 `_prompt_cursor_agent_capturing_usage`（send+events 流捕获 usage）+ `_common/cursor_usage.aggregate_turn_usage`（口径与 `extract_cursor_usage` 一致），local_contract 测试 7 passed；**本批次无法回填**（SDK local store `~/.cursor/sdk-agent-store` 不存在，历史 usage 不可恢复），估算账本按 2026-07-06 用户裁定以 `--accept-estimated-token-ledger` 显式声明接受；(4) **commercial100 readiness**——严格口径 `h100_scale_readiness_commercial100_20260706_strict.json` 唯一 blocker 为 estimated TokenLedger（`decision=no_go`）；按裁定口径 `h100_scale_readiness_commercial100_20260706.json` **`decision=go, passed=true, blockers=[]`**（v4-v6 的 trial+dailyTarget=10000 误口径作废）。剩余外部依赖：authoritative TokenLedger 需用本轮新代码重跑一个 managed 批次产生。
  - 复核（2026-07-07 homepage H100 批次同口径对账）: 主页线 H100 批次（`旅行/地域/中国/景区/全国主页百级0706a` / `h100_real_20260706T232327Z`）已以 `completed_with_reasoned_rejects` 终态收口（54/100 成稿、写稿 14.7 篇/h/worker、全链路 5.58 主页/h），但 token 账本仍为 `estimated_from_artifacts` 口径（H100 均值 6,456 tokens/主页；mw2/mw3 多 worker 探针 10,824–12,444 tokens/主页），沿用 2026-07-06 用户裁定显式接受估算账本。`turn-ended` 流式 usage 采集代码已在主线，但本轮 H100 与 mw 探针批次均未产出 authoritative TokenLedger 批次证据；R-CS03 主项（authoritative 账本批次 + article 线 cs100/cs1000 长跑）维持待办。证据口径：旧 data artifact 报告已清理；复验以 `.qwq_output/data/runs/content_runs/e2e/homepage/h100_real_20260706T232327Z/scale_readiness.json` 及同批 `_shared` 证据为准。
  - 状态: 待办（A/B/C/D 子项、SOP/templates 去 few-shot、Cursor startup、发布门残留去重、多实体 fanout 全内容链路 + 13 个放量级 blocker（creator-模板耦合 / TEMPLATES_ROOT 漂移 / base_draft_ledger 缺失 / media_check envelope 缺失 / verify 跨计划污染 / 孤儿 provisional 残骸 / supervisor finalize 死锁 / 阶段职责混淆 / 进程保活 / 并发 bridge 争用 / caffeinate 死锁 / 编排路径裸 Agent.prompt 无稳定化 / 编排 agent 无超时看门狗）均已定位修复并有真实产物或测试证据；**2026-06-30 fidelity 根因修复经真实 composer-2.5 端到端实证（P5 7/8 PASS、都江堰 18.6%→90.8%、全篇≥55%、无 fidelity/mustIncludeFact 失败）；P5 门禁零 Wikimedia/单源/storySpine 净/物理解耦/release verify 均 PASS；firstPassRate 0.875<0.9（1 篇 entityCoverage 源-实体错配）；P6 受限并行 concurrency=2 因 bridge 冷启争用 + 远端分支校验 GATE_BLOCK（串行可靠、修复方向 = per-worker warm bridge）**；**scale-10 端到端 GREEN（10/10 publish、VERIFY PASSED roots=10）+ scale-50 管线确证 GREEN（33/50 succeeded+publish，真实指代实体）+ 2026-06-26 s10verify trial target=10 decision=go + 2026-06-28 里程碑2.1 池/分类法/契约层就绪（creator-lint GREEN + 全 data gate GREEN + creator_batch100 decision=go）+ 2026-06-28 底稿中心 1:1 重构落地（契约/代码/测试 GREEN，fidelity 误杀根因与 bulk 阻塞消除）+ 2026-06-29 冒烟试跑 trial decision=go（release verify PASSED，单底稿/百科主页抽检通过）**。R-CS03 当前剩余 blocker（2026-06-28 cs100 真实长跑实测细化，重构后修订）：(a) **作者质量天花板**：原 6 篇中 3× baseDraftFidelity 误杀已由 P4「整篇单源度量」消除、writingIntentConsistency 已 P4 降级可选；真实复跑须验证 firstPassRate 是否回升过 90%（**cs100 新批次长跑中，冒烟 firstPassRate=55.56%**）；(b) **cs100 sub-scale**：17 实体 63 对象<100 目标、source 准入 12/17、创作者池仅 2 人过载——放量到 100/天需扩实体+source+创作者池；(c) **商业证据缺口**：release/TokenLedger/measuredThroughput/firstPassRate 均门控于 workflow=succeeded，**`fresh_cs100verify_20260629` 长跑进行中**；(d) **图片授权完整性**：download 逐图 license 捕获不齐，需页/集合级授权传播 + 选图期过滤（已回退过激选图过滤）；(e) 1万/10万级吞吐与 reliabletask 后端归 R-CS02。即 100/天吞吐已非瓶颈（单 worker 8× 余量），商用放量主阻断收敛为作者质量 90% 线（fidelity 误杀已消除）+ 批规模/创作者池 + 图权 download 完整性 + **cs100 新批次 commercial 长跑未完成**。**2026-07-06 更新**：Pinterest 图片线 H100 批次已真实跑完并按 commercial100 口径 `decision=go`（含 capacity≥120、gamma import + search/reco 下游证据、firstPassRate=1.0，见当日复核），startup 500 与 batch `_shared` 证据缺失的旧记载不再成立；R-CS03 剩余主项收敛为 **authoritative TokenLedger 批次证据**（本批为用户裁定显式接受的估算账本，`turn-ended` 流式 usage 采集已进代码主线，需新批次实测）与 article 线 cs100/cs1000 长跑）
- [x] R-CS04 创作侧 tag 投影端云一致缺口
  - 区域: App
  - 域: `content`（创作入口）
  - 原因: 阅读消费侧 tag 内联可点击 + codec round-trip 已闭环；但创作端仍只处理 entity span，正文 `@[label](tag:ref)` 内联未对称投影为 `tagRefs`、编辑态未保留 tag span。
  - 影响: 创作侧产出的正文 tag 内联在发布/编辑往返中丢失，端云 tagRefs 不一致。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`、`quwoquan_app/lib/ui/content/entry/providers/create_editor_provider.dart`
  - 证据: 新增 `tagRefsForPayload(state)`（正文 `span.isTag` 内联剥 `tag:` 前缀 + `settings.tagRefs` Set 合并去重），`buildArticleMarkdownForPayload`/`buildCreatePostPayloadMap` 改用之；编辑态 `_toggleSpansInRange` 由 `isEntity` 放宽为 `isInlineMention` 保留 tag span；`flutter analyze` 4 文件 0 issue、相关 4 测试文件 70 用例全绿（含 entity 不回归）。
  - 状态: 已解决（2026-06-21；App 侧 tag 与 entity 完全对称这一目标已达成。注：端云真正落库 entity/tag refs 受 R-CS06 阻断，App 侧对称是其前置而非终点）
- [x] R-CS06 App 发布侧 semanticMentions 端云契约断裂（entity+tag 内联均不落服务端 refs）
  - 区域: App / Service
  - 域: `content`
  - 原因: 服务侧 `content-service` `semantic.Project` 已对称支持 entity/tag，且把 `tagRefs/entityRefs` 当作 published `semanticMentions` 的只读投影（`post_service` 在 `SemanticMentions` 存在时直接覆盖 refs）。但 App 发布**从不构建结构化 `semanticMentions`**（kind/status/targetRef 数组）；顶层 `tagRefs/entityRefs` 被 wire `createWritableFields` 剥离（非可写字段）；wire codegen 按字段名硬编码把 `semanticMentions/reviewAspects` 误生成为 `String?`，与服务侧期望的 `[]object` 数组不一致（R06/R24 桥接债）。
  - 影响: 端侧创作的 entity 与 tag 正文内联发布后**均无法落到服务端 `post.TagRefs/EntityRefs`**，端云 semanticMentions grounding 链在 App 发布侧断裂，削弱云侧可点击数据来源与推荐 grounding（注：数据工程 materialize 侧已能写 manifest semanticMentions，断点专指 App 用户创作发布路径）。
  - 正确设计: metadata-first——wire 字段类型由 `fields.yaml` 的 `type` 驱动渲染（`[]object`→`List<CloudJsonMap>?`，object/GeoPoint→`CloudJsonMap?`，标量/ObjectId→`String?`），消除按字段名硬编码 switch；App 发布由正文 entity/tag 内联 + settings/homepage 构建 published `semanticMentions` 行并提交；服务侧 `Project` 投影落 `entityRefs/tagRefs`（pending/rejected 不落、published+非法 targetRef 整单拒绝、顶层 refs 与投影不一致拒绝）。
  - 涉及文件: `quwoquan_service/tools/codegen_app_metadata/content_post_mutation_wires_codegen.go`+`main.go`、`quwoquan_app/lib/cloud/runtime/generated/content/content_post_mutation_wires.g.dart`、`quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`、`quwoquan_service/services/content-service/internal/application/post/post_service.go`（`applySemanticMentionPayload`）
  - 证据:
    - 契约: wire codegen 改为 metadata type 驱动 + `_mutationMapList` helper；三处 wire 类（Create/Update/PromoteToWork）`semanticMentions`/`reviewAspects` 由 `String?` → `List<CloudJsonMap>?`，`illustrationAssetId`/`sourcePostId` 等 ObjectId 标量不回归仍为 `String?`；`make codegen-app` 幂等无新漂移。
    - App: `create_page_remote_helpers.dart` 新增 `semanticMentionsForPayload`（entity+tag 内联/settings/homepage → published 行 + `isSemanticTargetRefValid` 镜像服务端校验去非法/candidate），`buildCreatePostPayloadMap` 注入；`flutter analyze` 2 文件 0 issue。
    - 测试: App `publish_payload_contract_test.dart` + `publish_draft_projection_bridge_test.dart` 共 28 用例全绿（含 semanticMentions 结构化数组、投影、去重过滤、wire round-trip、tagRefs/entityRefs 不入 wire）；Go `create_semantic_projection_test.go` 3 用例（published entity+tag 落 refs / pending+rejected 排除 / published 非法 targetRef 拒绝 / 顶层 refs 偏离投影拒绝）+ `content_post_mutation_wires_codegen_test.go` 1 用例（[]object→List<CloudJsonMap>? 等类型映射）全绿；`go build/vet ./services/content-service/... ./tools/codegen_app_metadata/...` 绿。
  - 状态: 已解决（2026-06-21；App 用户创作发布路径 entity+tag 内联经结构化 semanticMentions 端云落 refs，metadata-first 契约对齐，桥接债清除）
- [x] R-CS07 current release 发布面缺实体主页闭环
  - 区域: Data
  - 域: `content-supply`（release publish / homepage lane）
  - 原因: `quwoquan_data/scripts/cli.py verify --scope current` 已收窄为只扫描当前 `quwoquan_data.post_manifest` schema 的 release posts 根；旧无 schema 测试 release 已排除，但当前 schema release 仍存在已发布 post 的主 `entityRefs[0]` 缺同 release 下 `entities/.../page.md` 实体主页产物。`publish.gate` 对 assembled release 要求已发布 post 的主实体主页闭环，`allowPartialContent` 只允许缺计划 post，不允许已发布 post 缺主页。
  - 影响: `make verify` / `verify-quwoquan-data` 被真实发布面质量门阻断；缺实体主页会造成内容消费、搜索承接、推荐交集理由和 entity landing 的端到端链路断点。不能用手写 stub 或放宽 gate 补绿，必须从对应 task/batch 的 homepage lane 重新生产、审核、发布可追溯主页产物，或明确将不完整 release 移出 current 发布面。
  - 涉及文件: `quwoquan_data/scripts/_common/post_verify.py`、`quwoquan_data/scripts/publish/gate.py`、`quwoquan_data/releases/旅行__地域__四川省__景区__全国5A景区source-ready资产闭环验证v18__source_ready_assetrefs_10_20260619_02/`、`quwoquan_data/releases/旅行__主题__网站供给线__维基导游百级真实运营验证__real_*`
  - 证据: `python3 quwoquan_data/tests/user_acceptance/quality/test_verify_scope_semantics__user_acceptance_test.py` 通过；`python3 quwoquan_data/scripts/cli.py verify --scope current` 仍失败，剩余问题包含 `release missing primary entity homepage(s)` 与 `release entity quota: expected 20, got 0`，以及因缺实体闭环导致的 `intersection dimension missing: content`。
  - 复核（2026-07-06 active current surface 复验）: 在当前有效运行根 `.qwq_sandbox/data` 上复跑 `python3 quwoquan_data/scripts/cli.py verify --scope current`，初始唯一失败已不再是实体主页缺口，而是 macOS Finder 噪声文件 `release whitelist: unexpected root entry .DS_Store`。清理 `.qwq_sandbox/data/releases/.DS_Store` 与 `.../旅行__地域__四川省__景区__弹性百级试跑0703a__scale100_elastic_overfetch_2x_0703a/.DS_Store` 后，`verify --scope current` 立即 **PASSED**；同时对 current 面上的两个 release 根分别复验 `publish.gate.gate_publish(...)`：`旅行__地域__四川省__景区__弹性百级复跑0704a__scale100_elastic_overfetch_2x_0704a` 与 `旅行__地域__四川省__景区__弹性百级试跑0703a__scale100_elastic_overfetch_2x_0703a` 均返回 `[]`，说明 active current 发布面已不存在“已发布 post 缺主页闭环”的真实阻断。由此可将 R-CS07 关闭；后续 homepage 商业阻塞继续归属 R-CS01（source sufficiency / no-image authority source / target replacement），不再归因到 current release surface。
  - 状态: 已解决（2026-07-06；证据：`QWQ_DATA_ROOT=.qwq_sandbox/data python3 quwoquan_data/scripts/cli.py verify --scope current` PASSED；`python3 -c "from publish.gate import gate_publish; ..."` 对 0704a/0703a current releases 均返回空问题列表）
- [ ] R-CS05 video 作品链路后置
  - 区域: Data
  - 域: `content-supply`（video 形态）
  - 原因: 用户主动 defer，计划 §14 Out of Scope；video research lane / producer / 作品判定 / 权利安全门未实现。
  - 影响: 当前仅支持 entity / article / image 三形态，video 作品不可生产。
  - 涉及文件: 计划 §14、produce video lane（未建）
  - 状态: 待办（后置，需用户明确启动）
- [ ] R-CS08 视频商用全矩阵外部依赖未齐备
  - 区域: App / Service / Data / Ops
  - 域: `runtime-media` / `content`
  - 原因: 本轮只收口“视频封面发布展示工程闭环”，但 runtime-media 商用全矩阵仍依赖真实 beta/gamma 网关、self-hosted Android/iOS runner、ECS/pre 环境、对象存储与视频转码/封面生成链路的非 dry-run 通过报告；这些外部运行条件尚未齐备。
  - 影响: 即使 App/Service/Data 的视频 `videoUrl + thumbnailUrl/coverUrl + coverStrategy + coverFrameTimeMs + duration/size` 合同已在 local_contract/scoped tests 闭合，也不能宣称“一流成熟商用视频能力”或“视频商用端到端全矩阵完成”；相关 GWT 的 gamma api_integration/user_acceptance 证据必须保持 pending 或 GATE_BLOCK。
  - 涉及文件: `specs/feature-tree/runtime/runtime-media/video-end-to-end-commercial-matrix.md`、`specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/acceptance.yaml`、`specs/feature-tree/discovery-content/content-display-journey-consistency/video-display-journey/acceptance.yaml`、`quwoquan_ops/cli/stackctl.py`
  - 状态: 待办（2026-06-22 用户确认登记；需四环境非 dry-run passed 报告、真实移动 runner、ECS/pre 与对象存储/转码链路证据齐备后方可关闭）
- [ ] R-CS09 普通网页/UGC 底稿轻改商用的版权风险（full light-edit 裁定）
  - 区域: Data
  - 域: `content-supply`（produce author / 来源权利分层）
  - 原因: 用户裁定 `factual_reference_only`（去哪儿游记、百科、普通攻略等他人 UGC）与 `licensed_adaptation` 同等以底稿为骨架轻改，可保留优质原句/自然段，`baseDraftFidelity` 对两类来源统一生效。此前代码刻意把 `factual_reference_only` 限制为纯事实证据池（不保留长句/结构）正是为规避他人 UGC 商用复刻的版权风险；本次按用户选择移除了该法律安全策略（`base_draft.py` 贴合度门、`content_review.unauthorized_expression_reuse_issues`、`release_integrity` factual-as-adaptation 门、`writing_pack`/`run.py` author 合同均已统一为底稿轻改）。
  - 影响: 商用发布时，对未获授权的他人 UGC 进行骨架+原句级保留的轻改改写存在著作权侵权风险；去平台名/作者署名/水印只降低来源痕迹，不构成版权许可。需在商用放量前补充来源授权/版权合规策略（如限定为公版/CC/自有授权来源，或获取 UGC 平台改编授权），否则规模化发布放大法律敞口。
  - 涉及文件: `quwoquan_data/scripts/_common/base_draft.py`、`quwoquan_data/scripts/_common/writing_pack.py`、`quwoquan_data/scripts/_common/content_review.py`、`quwoquan_data/scripts/_common/release_integrity.py`、`quwoquan_data/scripts/task/run.py`、`.cursor/skills/quwoquan-data-content/SKILL.md`「来源权利分层」
  - 状态: 待办（2026-06-23 用户确认接受版权风险并裁定 full light-edit；商用放量前需落地来源授权/版权合规策略）
- [ ] R-CS10 文章图文不同源 → 退化为 text_only（图文混排丢失，P0）
  - 区域: Data
  - 域: `content-supply`（download 内联图提取 / produce 配图同源）
  - 原因: 去哪儿 youji 等 UGC 底稿以「图文混排、图为主导」表达，但本批 27 个 `source.md` 仅 1 个含内联图（`![`）。RC3 已修内联 `<img>`/lazy `data-*` 真实图就地同源下载 + `sourceAssetRef` 段落锚定并有契约测试（`test_inline_source_images`，gate 绿），但 P5 批次 `p5_sichuan_20260630` 的 download 是 RC3 修复前的陈旧源（图被剥离）；RC4 红线又要求文章配图必须同源（同一底稿授权图集），同源图缺失时文章只能 `publishMediaMode=text_only`、`assets=[]`。
  - 影响: 文章正文虽高度忠实底稿（如都江堰 fidelity 90.8%），但**完全丢失原底稿的图文混排表达**，与用户「图多文少混合编排」诉求相悖；放量后大量 UGC 来源文章会退化为纯文本，削弱内容质量与消费体验。这是用户头号投诉（去哪儿 youji/7870084 数十图缺失/对不上）的根因延续。
  - 涉及文件: `quwoquan_data/scripts/download/**`（内联图 lazy-load 提取）、`quwoquan_data/scripts/produce/route_assets.py`（同源选图）、`quwoquan_data/scripts/download/research/source_quality.py`（RC4 同源红线）
  - 证据口径: 旧 scale_fix_stage artifact 已清理；RC3 提取器契约测试 `test_inline_source_images`（gate 绿，证明提取逻辑对 fixture 生效）；真实 qunar lazy-load 重下载端到端验证待补。
  - 复核（2026-06-30 P2 载体重构 + 真实下载实证）: P2 已把抽取器从「每图独立占位」改为「相邻连续图合并为单 `figureGroup` 占位（内部 N 张 assetId）+ AI 原样带回 + CLI 在占位内回填同源连续图」，`page.html` 保结构 HTML 图文混排进入内容区，并补抽取器/回填契约测试（`_common/figure_groups.py:figure_group_integrity_issues/expand_figure_groups`，接入 `verify_quwoquan_data.sh`）。**真实数据实证**：四川真实小批 batch（都江堰/青城山，`.qwq_sandbox` 沙箱）真实下载的 `sources/*/source.clean.md` 出现 `:::figuregroup id="grp-096" count="3"` 连续图合并占位，证明提取器在真实来源（非 fixture）上生效；entity 主页 finalize 的 `figure_group_integrity_issues` 在采纳前校验占位按原 id/张数带回。**仍待**：article lane 端到端「图文混排进文章正文 + 配图同源（非 text_only）」需完成真实 qunar youji（lazy-load `data-*`）重下载 + produce_author 真实创作，本窗因 managed 自动化需 local runtime（本沙箱不可用，见 R-CS03 复核）未跑到 article release；旧 scale_fix_stage artifact 已清理，复验以 `.qwq_output` 新运行输出为准。
  - 复核（2026-07-06 真实 Qunar 重下载 + 全沙箱同源图复核）: 以正式批次 `弹性百级复跑0704a/scale100_elastic_overfetch_2x_0704a` 的真实实体 `柳江古镇` 为样本，重新执行 `data research-plan --lane article --force` 与 `data download --lane article`。结果表明**抽取器已不是主阻塞**：当前 `download.fetch.extract_page_text_with_inline_images()` 离线对同一 `page.html` 可识别 `inline_images=23`，并生成 `:::figuregroup`/`asset://source-inline-*` 占位；但 fresh source unit `su_c45ad106569566d88835`（`柳江古镇2日游`）写回时，`_common/source_unit.bind_inline_source_placeholders()` 会按照合同把**未绑定到真实 `sourceAssetId` 的占位整块剥离**。该 source unit 同时已满足 `entityFocusVerdict="strong"`，却仍然 `assetCount=0`、`assetFunnel.candidateCount=23`、23/23 全因 `rights: imageRights: missing required field license` 被丢弃，导致最终 `source.md/source.clean.md` 不含任何 `:::figure/figuregroup`，文章车道只能继续退化为 `text_only`。进一步对整个 `.qwq_sandbox/data/runtime/batches/**/sources/*/meta.json` 复扫，当前 `platform="去哪儿攻略"` source unit 共 2762 个，其中 `assetCount>0` 为 0、`entityFocusVerdict in {strong, exact} && assetCount>0` 也为 0。结论：**Qunar UGC 同源图的系统性 blocker 已从“lazy-load 抽取”收敛为“逐图权利证明缺失”**；在不放松真实权利合同的前提下，本轮无法产出 non-`text_only` 的真实 article release。再叠加 R-CS03 当前 `cursor_sdk+composer` 执行面阻断（local 500 / cloud `plan_required`），本窗不能拿到新的 article managed release 作为 mixed-layout 闭环证据。
  - 状态: 待办（2026-07-06：P2 抽取器在真实 Qunar `page.html` 上已验证可识别 inline images，但正式重下载证明 source-unit 写回会在无 rights 绑定时剥掉全部占位；全沙箱 2762 个 `去哪儿攻略` source unit 均 `assetCount=0`。因此 mixed-layout 当前真实阻塞收敛为同源图逐图权利证明缺失，且 authoritative article release 还受 R-CS03 执行面阻断）

## 创作发布流体验（Create/Publish Flow）

- [x] R-CR01 「附近地点访问失败」整页断点：CreateLocationService 在 mock 环境仍强发 gateway + 系统定位
  - 区域: App
  - 域: `content/entry`、`integration`
  - 原因: `CreateLocationService` 原为直接 `new` 的具体类，alpha/mock 也走真实 gateway 请求 + 系统定位；无网关/密钥/定位权限时必现「附近地点访问失败」。
  - 影响: 发布流「选位置」首屏断点，alpha/开发态不可用。
  - 方案: 三层化（abstract `CreateLocationService` / `RemoteCreateLocationService` / `MockCreateLocationService` 本地 canonical POI，不发 HTTP、不依赖系统定位）；`createLocationServiceProvider` 按 `appDataSourceModeProvider` 切换；`create_page` 去除裸 `new`。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/publish_settings_services.dart`、`quwoquan_app/lib/core/providers/app_providers.dart`、`quwoquan_app/lib/ui/content/entry/pages/create_page.dart`
  - 证据: `test/core/providers/create_location_service_provider_test.dart`（mock→Mock / remote→Remote / mock nearby 永不为空）+ `test/ui/content/entry/contract/location_circle_services_contract_test.dart`（Remote+Mock 契约）+ 既有 `location_selector_page_widget_test.dart` / `entry_location_error_journey_test.dart` 合计 17 测试绿；`verify_ui_mock_isolation`、`verify_ui_app_data_source_mode_ratchet` 均 OK。
  - 状态: 已解决（2026-06-24）

- [x] R-CR02 错误展示载体（全屏 vs 弹窗 vs 卡片/footer/toast）边界未文档化、无回归门
  - 区域: App
  - 域: `runtime-client-foundation`（错误语义）
  - 原因: presentation 选择只存在于 `_presentationFor` 代码内，规格文档缺权威决策矩阵；术语沿用项目并不存在的 `SnackBar`。
  - 影响: 错误 UI 边界口径易漂移，无法检测后续误改。
  - 方案: `specs/ux/error-and-permission-semantics.md` 新增 §1.13「错误展示载体决策矩阵（全屏 vs 弹窗 权威边界）」，冻结 `UiErrorPresentation`→组件映射、`category×scope`→presentation 决策树与互斥边界；术语统一为「弹窗 actionDialog / 轻提示 AppToast」。
  - 涉及文件: `specs/ux/error-and-permission-semantics.md`、`quwoquan_app/test/local_contract/core/errors/ui_error_semantics__local_contract_test.dart`
  - 证据: `ui_error_semantics_test.dart` 新增「错误展示载体决策矩阵」7 条用例，逐条断言 `(category, scope)→presentation`，改坏 `_presentationFor` 即红。
  - 状态: 已解决（2026-06-24）

- [x] R-CR03 图片选择器相册下拉贴底弹出 +「最近项目」命名 + PC/桌面选择器缺失（图一）
  - 区域: App
  - 域: `content/entry`（媒体选择）
  - 原因: 相册下拉用 `showCupertinoModalPopup` 贴底从下往上长，选项多时可用性差；相册显示名未统一（应「全部照片」并置顶）；桌面无 `file_picker` 选目录 + 记忆上次目录 + 递归扫描含图子目录聚合为相册。
  - 影响: 移动端相册下拉体验差；PC/桌面无法选图（能力缺口）。
  - 方案（规划）: 抽 `AppTopAnchoredDropdown` 顶部锚定下滑浮层（自适应高度 + 封顶内容区 + scrim 关闭）；`hasAll` 相册置顶 + 显示名「全部照片」；桌面经 `PlatformCapabilities` 能力位路由到 file_picker 选目录（`FileStorageGateway` 持久化上次目录）+ 递归扫描，多选/拖拽复用 `MediaReorderableView`；缺失即结构化降级。
  - 涉及文件: `quwoquan_app/lib/components/media/picker/create_media_picker_page.dart`、`quwoquan_app/lib/components/media/picker/create_media_picker_presentation.dart`、`quwoquan_app/lib/components/media/picker/image_pick_gateway.dart`
  - 状态: 已解决（2026-06-24）。
    - 相册下拉：新增 `quwoquan_app/lib/core/widgets/app_top_anchored_dropdown.dart`（`showAppTopAnchoredDropdown` 顶部锚定下滑 + 自适应高度封顶 + scrim 关闭），`create_media_picker_page.dart` 与桌面页统一复用；移动端 `isAll` 相册置顶并显示「全部照片」（`UITextConstants.mediaPickerAlbumAllPhotos`）。证据：`test/core/widgets/app_top_anchored_dropdown_test.dart`、`test/local_contract/ui/content/create/photo_media_picker_commercial_flow__local_contract_test.dart`（含 `isAll` 置顶用例）。
    - 桌面选择器：`FileStorageGateway` 新增 `listDirectory`（io/web 实现 + 5 个测试 fake stub）；新增 `DesktopImageAlbumScanner`（递归扫描含图子目录聚合相册、跨目录「全部照片」置顶、深度/目录数/单册封顶）、`desktop_picker_services.dart`（`DesktopDirectoryPicker`/`DesktopPickerDirectoryMemory` 记忆上次目录 + `shouldUseDesktopImagePicker` 能力位路由判据）、`DesktopImagePickerPage`（多选编号 + 已选条复用 `MediaReorderableView` 拖拽重排 + 相册下拉复用 `AppTopAnchoredDropdown` + 缩略图走 `gateway.readAsBytes`/`Image.memory` 不新增 `dart:io` + 缺能力位/空目录结构化降级）；`create_page._openMediaPicker` 按 `shouldUseDesktopImagePicker` 路由。证据：`test/components/media/desktop_image_album_scanner_test.dart`、`test/components/media/desktop_picker_services_test.dart`、`test/components/media/desktop_image_picker_page_widget_test.dart`；页面矩阵已登记 `desktop_image_picker_page.dart`（T5）+ `metadata_driven_ui_gap_inventory` exempt。
    - 注：「最近项目」命名项随相册显示名统一收口（移动端聚合册显示「全部照片」），不再单列「最近项目」命名债。

- [ ] R-CR04 CreateLocationService 与 CreateLocationOption 模型分层债（lib/ui → lib/cloud/services/integration）
  - 区域: App
  - 域: `content/entry`、`integration`
  - 原因: R-CR01 三层化时，服务 + Mock + `CreateLocationOption` 模型仍位于 `lib/ui/content/entry/{services,models}`，理想应在 `lib/cloud/services/integration`（对齐 `01-arch-constraints` §2.1）。受 `verify_ui_app_data_source_mode_ratchet`（禁止 lib/ui 引用 `appDataSourceModeProvider`）约束，provider 已集中在 core，但服务实现仍在 ui。
  - 影响: 偏离端云目录约束；不违反现有门禁（mock 隔离 / 数据源棘轮均绿）。迁移需连带搬 `CreateLocationOption` 模型并改多处 import。
  - 涉及文件: `quwoquan_app/lib/ui/content/entry/services/publish_settings_services.dart`、`quwoquan_app/lib/ui/content/entry/models/publish_settings_models.dart`、`quwoquan_app/lib/core/providers/app_providers.dart`
  - 状态: 待办（2026-06-24 用户「系统性梳理遗留事项」确认登记；建议待 create-flow 并发编辑收束后随 R-CR03 一并迁移）

## 产品遥测 SLS 单轨验证（2026-07-18 用户确认登记）

- [ ] R-TELEMETRY-001 产品遥测的真实 SLS 资源、跨环境验收与真机证据未闭合
  - 区域: App / Service / Ops / Portal
  - 域: `product-ops-growth/event-ingestion-and-analytics`
  - 原因:
    1. 本机未注入 `PRODUCT_OPS_SLS_*`、`TEST_SLS_*` 或部署 Secret；阿里云 SLS Project、VPC endpoint、RAM、三个 Logstore、Scheduled SQL 与告警尚无受控环境中的实际证据。
    2. SLS 资源清单仅声明 `beta/gamma/prod`，但 product-ops 的 `alpha` 配置同样要求 SLS 运行参数。alpha 应只承担 fake-SLS 协议的 `local_contract`，不得把真实云凭据或 Mongo/ES fallback 混入；需要把“alpha 不启动真实 SLS 写入”的运行边界固化到 stackctl/config 验证。
    3. 2026-07-18 实跑 alpha T3 与最近 beta T3 均在 `contract_seeded_mock_repository` 的空 `avatarBaseUrl` 种子前置失败；gamma T3 仍受 entity 种子 403、comment 种子 404 与旧内容分页用例影响。定向 product-ops API 和 behavior 契约已通过，但不能替代完整环境门。
    4. 尚无可用真机，`user_acceptance` 的断网补传、生命周期 session 切换、脱敏异常与 Portal 可见性未取得 T4 证据。
  - 影响: 不能签署真实 SLS 的幂等写、索引/保留期、RAM 最小权限、Scheduled SQL freshness、Portal 性能和 App 端到端体验；gamma/prod acceptance 必须保持 `partial / GATE_BLOCK`。
  - 涉及文件: `quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml`、`quwoquan_ops/runbooks/product_telemetry_sls_cutover.md`、`quwoquan_service/services/product-ops-service/configs/{alpha,beta,gamma,prod}/config.yaml`、`quwoquan_service/services/product-ops-service/cmd/api/runtime_config.go`
  - 收口方案:
    1. alpha：只跑 metadata/codegen、App/Go/Portal `local_contract` 与 fake-SLS 协议；显式验证真实 SLS 未被启动或要求。测试替身仅限测试注入，绝不是运行时存储 fallback。
    2. beta：在 VPC 可达的受控 runner 部署独立 beta SLS Project/RAM/Secret，创建 3/3/90 天 Logstore 和 Scheduled SQL；先清除 `avatarBaseUrl` 种子阻断，再执行 `stackctl verify --env beta --kind all --tier t3` 及 `TEST_SLS_*` 实测：重放不重复、字段/保留期/聚合无敏感字段、Portal 查询 SLO。
    3. gamma：在同一 VPC 或获批私网连通的 runner 注入 gamma Secret；先修复 entity/comment/content 种子门，再执行 `stackctl verify --env gamma --kind all --tier t3`。开发机的 `gamma_local` 不可直连 VPC endpoint 时只能跑协议替身，不能伪称真实 SLS 验收。
    4. T4：准备至少一台 Android 或 iOS 真机，执行启动、页面访问、后台恢复、断网补传、可控异常、推荐反馈与 Portal 观测旅程；随后才进入 prod 5% rollout。
  - 已有证据: 严格 metadata/codegen、App Reporter local_contract、Go SLS fake 协议、Portal 单测/build 已通过；`product-ops` gamma API 契约及 `/content/behaviors` 定向链路已通过。以上均不等同于真实 SLS 或真机验收。
  - 状态: 进行中（2026-07-18 用户确认登记）

## 测试治理与目录迁移（Three-layer Test Migration）

- [x] R-TST01 三层测试目录的物理迁移尚未全仓完成
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 旧风险来自“三层目录只在 App 先落地，Service/Data/Ops 仍停留在 legacy 目录”的半迁移状态。2026-06-22 已通过 canonical bridge + inventory version 2 把全仓 legacy suite 全部纳入唯一三层执行根：App 377、Service 183、Data 101、quwoquan_ops 9，`pending=0`。
  - 影响: canonical 三层目录现已成为 App / Service / Data / Ops 的唯一执行入口与 acceptance 主证据口径；legacy 文件即使暂留原处，也只能通过 canonical bridge 被发现与引用，不再形成第二真相源。本项关闭表示“治理执行面已收口”，不表示 legacy 测试文件已全部物理搬迁或从磁盘移除。
  - 涉及文件: `specs/gates/test_directory_inventory.yaml`、`quwoquan_ops/gate/scaffold/{test_directory_inventory_lib.py,generate_canonical_test_bridges.py,generate_test_directory_inventory.py,verify_test_directory_inventory.py,normalize_acceptance_recorded_paths.py}`、`Makefile`、`quwoquan_ops/gate/gate_repo.sh`、`specs/03_TESTING_STRATEGY.md`
  - 证据:
    - `python3 quwoquan_ops/gate/scaffold/generate_canonical_test_bridges.py`
    - `python3 quwoquan_ops/gate/scaffold/generate_test_directory_inventory.py`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_specs.py`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_directory_inventory.py`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py`
    - `cd quwoquan_service && go test ./services/.../tests/local_contract -count=1`
    - `cd quwoquan_service/services/{assistant-service,entity-service,search-service} && go test ./tests/api_integration -count=1`
  - 状态: 已解决（2026-06-22；canonical 三层根、bridge、inventory 与 gate 全部落地，legacy 路径已退出主证据口径；2026-06-22 晚复核补充：关闭口径限定为治理执行面，不等于物理迁移完成）

- [x] R-TST02 Service/Data/Ops 的三层归类仍有启发式基线，需逐套件语义复核
  - 区域: Service / Data / Ops
  - 域: `runtime-test-pyramid`
  - 原因: 旧风险来自“层归类只停留在口头约定，无法追溯每个 suite 为什么落到某个 canonical 层”。2026-06-22 起，inventory version 2 为每个 Service/Data/Ops suite 固化 `current_path -> target_path -> classification_basis -> migration_status`，不再存在“默认都算某一层”的隐式归类。
  - 影响: 三层覆盖口径现在以 canonical target path 与 `classification_basis` 为准；后续若需要调整某个 suite 的层级，必须修改真相源并重新生成 bridge，而不是在 acceptance 或脚本里临时放宽。本项关闭表示“suite 归类已显式可追溯”，不表示分类逻辑已完全脱离路径/命名规则推导。
  - 涉及文件: `quwoquan_ops/gate/scaffold/test_directory_inventory_lib.py`、`specs/gates/test_directory_inventory.yaml`
  - 证据:
    - `specs/gates/test_directory_inventory.yaml` 中 Service/Data/Ops 全量条目均含 `classification_basis` 与 `migration_status: bridged`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_directory_inventory.py`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py`
    - `quwoquan_ops/gate/scaffold/verify_test_coverage_map.py` 已阻断“有 case id 无 canonical 文件”“有 recorded 但无 canonical 归属”“有 Journey 无 page case”
  - 状态: 已解决（2026-06-22；suite 归类已收敛为显式 inventory 真相源，不再是不可追溯的隐式基线；2026-06-22 晚复核补充：分类结果已显式化，但生成逻辑仍需后续门禁继续收紧）

- [x] R-TST03 canonical `make test-local-contract` 仍被 9 个既有 App 红测阻断
  - 区域: App
  - 域: `runtime-test-pyramid`
  - 原因: 本轮已把 `make test-local-contract` 切到 `test/local_contract/` canonical 入口并成功执行 2500+ 测试，但最终仍被 9 个既有 App 用例阻断。通过直接回放原 legacy 文件确认，失败在迁移前已存在：`chat_message_bubble_widget_test.dart` 3 条（图片/视频预览断言）、`chat_receipt_ui_widget_test.dart` 1 条（图片消息回执缺 `ProviderScope`）、`homepage_detail_page_widget_test.dart` 1 条（缺“主页暂不可用”文案）、`location_selector_page_widget_test.dart` 1 条（缺超时文案）、`work_browser_entry_page_test.dart` 1 条（缺“这个作品不可用了”文案）、`home_circles_hub_page_test.dart` 2 条（缺图片/视频卡片 key）。
  - 影响: 三层目录迁移本身已成立，但 `make test-local-contract` 不能作为全绿证据；若不单独登记，后续很容易把这 9 个存量红灯误判成 canonical wrapper 或目录门引入的回归。
  - 涉及文件: `quwoquan_app/test/{local_contract,ui}/chat/widgets/{chat_message_bubble_widget_test.dart,chat_receipt_ui_widget_test.dart}`、`quwoquan_app/test/{local_contract,ui}/entity/pages/homepage_detail_page_widget_test.dart`、`quwoquan_app/test/{local_contract,ui}/content/entry/widgets/location_selector_page_widget_test.dart`、`quwoquan_app/test/{local_contract,ui}/content/pages/work_browser_entry_page_test.dart`、`quwoquan_app/test/{local_contract,ui}/circle/pages/home_circles_hub_page_test.dart`
  - 证据:
    - 根因：产品已切 `AppPageErrorState`+`runtimeErrorSemantic`（标题/说明与旧 `UITextConstants.*Unavailable*` 不同）、聊天图片改 `AppCachedNetworkImage`（非 `Image`）、圈子 hub feed 改契约 seed（grid key 与 category 过滤不对齐）、摄影 tab inline carousel 禁用外层 onTap。
    - 修复：9 个 legacy 测试对齐当前产品契约（非 shim）；圈子 grid 测试用 `_LegacyHubCircleFeedRepository` 稳定样本 + 视频帖覆盖 work-browser 导航。
    - `flutter test` 上述 6 legacy 文件 47 用例 + 6 canonical wrapper 47 用例全绿（2026-06-21）。
  - 状态: 已解决（2026-06-21；9 个存量红测已修，`make test-local-contract` 阻断项消除；全量 2500+ 套件仍建议 CI 定期跑）

- [ ] R-TST04 canonical 治理完成与物理迁移完成仍可能被混读
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 本轮已把 `pending_count`、bridge 语义和 backlog/acceptance 文案校准为“治理执行面完成”，但仓库中仍保留 670 个 grandfathered legacy 源测试，且 `specs/gates/test_legacy_source_allowlist.yaml` 会长期存在，说明“canonical 已接管执行”与“legacy 已物理清零”仍是两件事。
  - 影响: 若后续只看 `pending_count=0` 或已关闭的 `R-TST01/R-TST02`，仍可能误判为“磁盘已无 legacy”“允许删除 allowlist / bridge 机制”，从而造成迁移完成度漂移。
  - 涉及文件: `specs/03_TESTING_STRATEGY.md`、`specs/gates/test_directory_inventory.yaml`、`specs/gates/test_legacy_source_allowlist.yaml`、`specs/feature-tree/runtime/runtime-test-{pyramid,infra}/**`
  - 证据:
    - `specs/gates/test_directory_inventory.yaml` 已为 `pending_count: 0`
    - `specs/gates/test_legacy_source_allowlist.yaml` 当前 `grandfathered_current_paths: 670`
    - 2026-06-22 已同步收紧 `specs/03_TESTING_STRATEGY.md`、`runtime-test-pyramid/spec.md`、`runtime-testinfra/spec.md` 的完成口径
  - 状态: 待办（2026-06-22 用户确认登记；后续若启动物理迁移 burn-down，需单列计划逐步减少 allowlist）

- [ ] R-TST05 `api_integration` / `user_acceptance` 统一执行入口仍依赖外部环境与凭证注入
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid`
  - 原因: 本轮已把 `Makefile` / `gate-full` 与 `prod + rollout_stage: gray_initial`、`target: gamma-local` 语义对齐，但远端层仍必须依赖 `BETA/GAMMA/PROD_*_BASE_URL` 与测试 token；仓库本身不能在裸 shell 中自举出可运行的 `api_integration` / hosted `user_acceptance`。
  - 影响: 三层执行入口虽已同源，但无法在任意开发机上直接得到“远端层为绿”的完整证据；一旦 CI/本地环境变量或拓扑准备缺失，验证会停在前置检查而不是业务断言。
  - 涉及文件: `Makefile`、`quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py`、`.cursor/skills/environment-ops/SKILL.md`
  - 证据:
    - `make verify-test-remote-env MODE=api_integration ENV=gamma` 会在入口即阻断缺失的 `GAMMA_BASE_URL`、`GAMMA_PRODUCT_OPS_BASE_URL` 与 token（2026-06-22 晚补）
    - `make verify-test-remote-env MODE=user_acceptance TARGET=gamma-local` 可在无远端前置时直接通过
    - `PROD_BASE_URL=https://example.invalid PROD_PRODUCT_OPS_BASE_URL=https://example.invalid TEST_AUTH_TOKEN=dryrun USER_ACCEPTANCE_DRY_RUN=1 make verify-test-remote-env MODE=user_acceptance TARGET=prod-hosted` wiring 通过（2026-06-22 晚补）
    - `ENV=gamma make test-api-integration` 当前直接被 `GAMMA_BASE_URL` 缺失阻断（2026-06-22）
    - `PROD_BASE_URL=https://example.invalid PROD_PRODUCT_OPS_BASE_URL=https://example.invalid TEST_AUTH_TOKEN=dryrun USER_ACCEPTANCE_DRY_RUN=1 make test-user-acceptance TARGET=prod-hosted` wiring 通过（2026-06-22）
  - 状态: 待办（2026-06-22 用户确认登记；当晚已补 `verify-test-remote-env` preflight，但远端层仍需 stackctl / CI secret / 拓扑准备才能真正实跑）

- [x] R-TST06 acceptance case 到 canonical file / report 的严格 traceability 尚未全仓铺满
  - 区域: App / Service / Data / Ops
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 旧风险来自 strict traceability 只覆盖局部治理节点，full strict 诊断一度仍有 `23` 份 acceptance 文件、`55` 个 layer 级缺口。2026-06-22 夜间继续补齐 `exposure-observability-capacity` 的 direct canonical `local_contract` 与 `config-and-reliability-governance` 的 canonical `api_integration` 后，最后两条真实缺桥/缺测试路径也已收口。
  - 影响: 当前全仓 acceptance case 均能追溯到 canonical file 或 `report.json.case_results[]`，新增 recorded 漂移会被 `verify_test_coverage_map.py` strict hard gate 即时阻断。本项关闭表示“strict traceability 治理面已全仓收口”，不表示后续可以跳过 recorded / report 回填；任何新增节点若掉出 canonical 追溯链，都会立即重新触发门禁。
  - 涉及文件: `quwoquan_ops/gate/scaffold/verify_test_coverage_map.py`、`specs/feature-tree/**/acceptance.yaml`、`quwoquan_service/services/content-service/tests/local_contract/internal/application/exposure_observability_capacity__local_contract_test.go`、`quwoquan_service/services/platform-ops-service/tests/api_integration/config_and_reliability_governance__api_integration_test.go`
  - 证据:
    - 2026-06-22 初版 full strict 诊断为 `23` 份 acceptance 文件、`55` 个 layer 级缺口
    - 2026-06-22 晚间首轮扩围后已把 full strict 缺口压到 `20` 份 acceptance 文件、`26` 个 layer 级缺口
    - 2026-06-22 深夜第二轮扩围后，`verify_test_coverage_map.py` hard gate 已覆盖 runtime 节点、17 个业务/能力节点与 `comment-thread` 的 13 个 item 级 GWT
    - 2026-06-22 收尾补上 `comment-thread.GWT12` 的真实 canonical `api_integration` 后，`comment-thread` item-level strict 扩到 `14` 个 GWT
    - 2026-06-22 夜间继续补上 `xiaoqu-entry-handoff` 的真实 canonical `api_integration` 后，hard gate 覆盖扩到 `18` 个业务/能力节点
    - 2026-06-22 夜间继续把 `page-horizontal-quality` 与 `realtime-push-and-offline-sync` 纳入 strict hard gate 后，hard gate 覆盖扩到 `20` 个业务/能力节点
    - 2026-06-22 夜间补上 `exposure-observability-capacity` 的 direct canonical `local_contract` 并纳入 strict hard gate 后，full strict 诊断收敛到 `1` 份 acceptance 文件、`1` 个 layer 级缺口
    - 2026-06-22 夜间补上 `config-and-reliability-governance` 的 canonical `api_integration` 并纳入 strict hard gate 后，full strict 诊断归零：`0` 份 acceptance 文件、`0` 个 layer 级缺口
    - `make verify-test-coverage-map`
    - `make verify-test-specs`
    - `make verify-test-directory-layout`
    - `make verify-test-no-fake`
    - `python3 quwoquan_ops/gate/scaffold/verify_test_coverage_map.py`
  - 状态: 已解决（2026-06-22；当晚已把 full strict 缺口从 `55` 压到 `0`，strict traceability hard gate 现已全仓闭环）

- [ ] R-TST07 旧 `T1-T4/L1-L4` 口径与 grandfathered legacy 例外仍散落仓库
  - 区域: App / Service / Data / Ops / Docs
  - 域: `runtime-test-pyramid` / `runtime-testinfra`
  - 原因: 本轮已清理核心 testing 规则、脚本、模板、README 与 Patrol 用例中的人类可读旧口径，并继续收掉四批真正可去掉的 grandfathered skip：一批是 deterministic 场景（assistant/user），一批是 `chat-service` / `content-service` / `rtc-service` 里由 `TestMain` 已兜底却仍留在文件内的冗余依赖双保险，一批是 `content-service/cmd/import` 与 `http_model_client` 这类可直接自举/去 loopback 的独立测试，最新一批是 `user-service/tests` 在混合 `pg/redis always-on + mongo optional` 运行时上补了按需 Mongo runtime 升级与 handler 重建，不再把文件级 `t.Skip` 当作环境契约。
  - 影响: 新增 debt 已能被 ratchet 阻断，deterministic 场景、已由 `TestMain` 承诺初始化的 legacy skip、独立可自举测试、`user-service` 这批“显式依赖 Mongo 但不该把 skip 散落在文件里”的历史例外，以及 `chat-service` 里真实缺失的 `AssistantRemoved` 事件链路都已继续收缩；但存量运行时旧命名与剩余 grandfathered 例外仍会维持历史心智负担，也意味着 `legacy-source-no-fake` 还不是零债基线。
  - 涉及文件: `specs/gates/test_legacy_source_allowlist.yaml`、`quwoquan_ops/gate/scaffold/{verify_test_specs.py,verify_test_no_fake.py}`、`quwoquan_app/test/user_acceptance/patrol/**`、`quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
  - 证据:
    - `specs/gates/test_legacy_source_allowlist.yaml` 当前 `bench_only_allowed_sources: 1`、`skip_grandfathered_sources: 2`
    - 2026-06-22 晚补后，`T4 Patrol E2E` / `L4 Patrol` / `T4 tests must run` / `T1-T4 测试` 等人类可读旧口径在非产物文件中已清零；剩余命中主要是运行时接口名与历史 tier 语义
    - 2026-06-22 深夜继续去掉 `assistant-service/internal/{adapters/http/handler_test.go,application/m11_local_scenario_test.go}` 与 `user-service/tests/error_contract_test.go` 的 skip grandfathered 后，`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-22 深夜继续去掉 `chat-service/tests/{direct_conversation_relationship_gate_test.go,send_message_relationship_gate_test.go}`、`content-service/tests/{comment_keyset_explain_bench_test.go,intersection_watermark_store_contract_test.go,post_cache_contract_test.go,viewer_object_intersection_store_contract_test.go,redis_router_contract_test.go}` 与 `rtc-service/tests/one_to_one_relationship_gate_test.go` 的冗余 skip 双保险后，`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-23 凌晨继续给 `content-service/cmd/import` 补 `TestMain` 自举 Mongo，并把 `http_model_client_test.go` 改成内存 `RoundTripper` 后，`cmd/import` canonical wrapper、`make verify-test-no-fake`、`make verify-test-directory-layout`、`make verify-test-specs` 继续全绿
    - 2026-06-23 凌晨继续把 `user-service/tests/{block_cascade_contract,follow_contract,greeting_request_state_machine,persona_contract,sub_account_view_contract}.go` 的文件级 skip 改为按需 `requireMongoBackedRuntime`，并在 `TEST_MONGO_URI=mongodb://127.0.0.1:37019` 下实跑 `go test ./tests -count=1`；`make verify-test-no-fake` / `make verify-test-directory-layout` / `make verify-test-specs` 继续全绿
    - 2026-06-23 清晨继续给 `chat-service` 补 `AssistantRemoved` metadata/codegen/handler 事件链路，并把 `event_publish_contract_test.go` 从 skeleton skip 改成真实断言；在 `TEST_MONGO_URI=mongodb://127.0.0.1:37020` 下实跑 `go test ./tests -run 'TestRemoveAssistant|TestEventPublish_AssistantRemoved|TestEventPublish_SupportedEventTypesComplete' -count=1` 通过。`event_publish_contract__api_integration` canonical wrapper 仍被同文件内既有 `createConversation` 基线红测阻塞，不属于本轮新增回归。
  - 状态: 待办（2026-06-22 用户确认登记；截至 2026-06-23 清晨已清掉 README / 注释 / Patrol 文案旧口径，并把 `skip_grandfathered_sources` 从 21 压到 2；后续需继续 burn-down 运行时接口旧命名、app 侧最后 2 条 legacy skip，以及 chat-service 事件发布套件里与本轮无关的 `createConversation` 基线红测）

## 旅游垂类商业化接入（Commerce / Affiliate Booking）

- [ ] R-COMMERCE-001 旅游垂类"购票/预订"行动建议缺失，需经联盟/导购 CPS 接入第三方票务
  - 区域: App / Service / Ops
  - 域: `entity` / `integration/affiliate_booking` / `recommendation`
  - 原因: 旅游垂类已具备实体主页、文章/图片/视频内容与创作者，但交集行动建议闭集（`intersection_action_hint.yaml` + `intersection_kind_registry.yaml` 的 `actionHintLegend` / `actionLabelByKey` / `actionHintsByKind`，端侧 `IntersectionActionKeys`）当前全部为社交/内容/对象导航类（`follow_person` / `join_circle` / `open_route` / `start_companion` / `join_trip` / `join_meetup` 等），**没有任何 commerce/购票类 actionKey**。`coWishlistedEntity: [start_companion, open_route, follow_object]` 这类 kind 已能识别"想去某实体"，但动作阶梯无购票承载位，导致"想去迪士尼 → 购票"这条商业转化在当前体系里断裂。参考携程、美团等 OTA 接迪士尼官方代购页（图一/图二）系由官方分销协议 + Distributor OpenAPI 直连或供应链聚合实现，含实时库存/价格/出票/退改；去我圈定位为内容+社区+交集推荐，不自建票务交易后台（资质、资金、出票、退改均不碰），正确路径是经联盟/导购 CPS/CPA 跳转（携程联盟、美团分销、飞猪客等）或 H5 内嵌接入第三方票务，只做归因与佣金。
  - 影响: 旅游垂类商业化与"内容 → 行动"闭环缺失；实体主页 D 面无法下发购票 CTA；推荐归因链在转化末端断点（无 commerce actionKey 承载 `referralSource` / `feedRequestId` / `intersectionId` 到第三方订单的透传）；运营漏斗无购票转化观测；与 OTA 垂类对标存在体验缺口。
  - 方案:
    - metadata-first 新增 commerce actionKey 闭集：`book_ticket` / `book_hotel` / `book_transport` / `view_official_deals`，同步登记到 `intersection_action_hint.yaml` 与 `intersection_kind_registry.yaml` 的 `actionHintLegend` / `actionLabelByKey` / `actionHintsByKind`，端侧 `IntersectionActionKeys` 补常量；走 `/qwq-extend`，禁止硬编码。
    - 新增 `integration/affiliate_booking` domain：云侧建票务链接网关，对接携程联盟 / 美团分销 / 飞猪客 CPS 转链 API（选品、转链、订单 T+1 对账），按 `01-arch-constraints` 走 metadata → codegen → Repository 三层模式，端侧经 Provider 取数，不直连联盟 API。
    - Homepage 实体扩展 commerce 接入元数据字段：`officialBookingProvider` / `bookingAffiliateUrl` / `realtimePricingFeed` / 退改策略标签等，走 `fields.yaml` → codegen；"实体 → 可订商品"映射表为多渠道选品唯一真相源，端侧不做选品（守 R24）。
    - 归因打通：联盟 `PID/SID` 对应入口 surface，自定义透传参数承载 `intersectionId` + `feedRequestId`，T+1 对账回传解析回 quwoquan 归因链，回流推荐与运营分析（对齐 R20/R21/R23）。
    - 实时性边界：CPS 模式下展示价非真相，UI 标"价格以购买页为准"；进取态可调联盟选品 API 缓存 5–15 分钟；禁止用 mock 冒充实时价（违 R04/R30，生产包纯净性）。
    - 错误与降级：联盟 API 超时/限流/商品下架走 `RuntimeFailure` + 结构化错误码（`errors.yaml` 登记 affiliate 类），UI 降级为"查看官方渠道"次级动作，deeplink 拉起失败回退 H5。
    - 合规：UI 披露"推广/合作"，不做价格欺诈与虚假划线价；资金不二清（用户钱直付第三方）；退改以购买页为准；CPS 导购一般无需旅行社资质但部分渠道需内容平台备案。
    - 落地顺序：MVP 接携程联盟一家 + 手工选品 5–10 热门景区验证闭环与佣金到账 → V1 接美团分销 + 云侧 affiliate gateway + API 取链 + 多渠道选品 → V2 飞猪补度假线路 + deeplink 优化 + T+1 对账回流推荐 → V3 助手推荐场景按 intersection kind 下发 `book_ticket`。
  - 涉及文件:
    - `quwoquan_service/contracts/metadata/recommendation/model_release/projections/intersection_action_hint.yaml`
    - `quwoquan_service/contracts/metadata/recommendation/rec_model/intersection_kind_registry.yaml`
    - `quwoquan_app/lib/cloud/runtime/recommendation/intersection_action_keys.dart`
    - `quwoquan_service/contracts/metadata/entity/homepage/fields.yaml`（待扩展 commerce 字段）
    - `quwoquan_service/contracts/metadata/integration/affiliate_booking/`（待新建 domain：service.yaml / fields.yaml / errors.yaml）
    - `quwoquan_app/lib/cloud/services/integration/affiliate_booking/`（待新建 Repository 三层）
    - `quwoquan_app/lib/core/providers/app_providers.dart`（待注册 Provider）
    - `quwoquan_app/lib/ui/entity/widgets/homepage_detail_shell*.dart`（D 面行动建议渲染 commerce hint）
  - 关联: 与 `R-LEGAL-001`（商业化能力上线前必须补充专项条款）强相关——购票/联盟导购属商业化能力，上线前必须先完成 legal-static 专项条款与法务审核；本项不得先于 `R-LEGAL-001` 关闭而上线。
  - 验收: commerce actionKey 闭集经 metadata 登记且 `make verify` + `make codegen-app` 通过；affiliate gateway Repository 三层 + Provider 注册 + `make verify-app-mock-isolation` + `make verify-app-seed-manifest` 绿；错误码端云链路 `verify_error_code_semantic.py` 绿；local_contract 覆盖 actionKey 渲染/分发/降级 + Mock 行为，api_integration 覆盖 Remote 转链与错误映射，user_acceptance 覆盖"实体主页 → 购票跳转 → 归因回流"旅程；legal-static 专项条款发布通过（前置依赖 `R-LEGAL-001`）。
  - 状态: 待办（2026-06-28 用户确认登记；暂不实现，作为旅游垂类商业化长期能力保留，待 `R-LEGAL-001` 前置与立项 `/prd` 后启动）

## 内容阅读器翻页组件架构（Content Pageflip Architecture）

- [x] R-PAGEFLIP-001 翻页诊断 harness 移出 lib/components 收口架构倒置（历史专项，已被 R-PAGEFLIP-002 续收口）
  - 区域: App
  - 域: `discovery-content` / `runtime-client-foundation/article-editor-refactor`
  - 原因: 专项启动时 content 阅读器翻页能力分散在三层——①旧生产引擎 `quwoquan_app/lib/ui/content/pageflip/**`（StPageFlip 几何/calculation，平台无关核心）；②宿主 `quwoquan_app/lib/ui/content/article_reader/pageflip/**`（render frame → deck layers → Widget paint 的宿主装配）；③旧 `quwoquan_app/lib/components/pageflip/**` 诊断 harness（16 文件，自带 engine/scene/widget/geometry 包装）。存在**架构倒置**：当时位于 `lib/components/**` 的 harness 反向依赖 UI 专属的 `lib/ui/content/pageflip`（违反 01-arch-constraints 分层方向与 R01）。
  - 证伪与定性: 专项执行时（1.2）经真相源核查证伪了初版「删除重复引擎」前提——当时的 `components/pageflip` **并非**第二套生产引擎，而是一层**仅被 test + `tool/` 诊断入口消费的诊断 harness**：其 geometry/render/widget 包装薄委托给旧生产引擎 `ui/content/pageflip`（如 `PageflipForwardCalculation` 包 `StPageFlipCalculation`），且被门禁 `verify_pageflip_backward_mainline.py`（rule-12 禁用符号扫描 + diagnostics overlay 标记）、架构测试 `article_reader_architecture_test.dart`（allowedDirectDeckEntrypoints 白名单）、合约测试 `pageflip_contract_test.dart`（诊断源码字符串断言）硬性钉位。因此当轮不可删除，正确收口是先把该 harness 移出 `lib/` 消除倒置、同时保留 harness 完整与全部门禁钉位。
  - 解决（2026-06-29，relocate_test_support）:
    - `git mv quwoquan_app/lib/components/pageflip` → `quwoquan_app/test/support/pageflip`（16 文件全部保留 git 历史），harness 内部 `package:` 自引用改相对 import；`lib/components/**` 不再出现倒置依赖。
    - 4 消费者改相对引用：`test/local_contract/ui/components/pageflip/pageflip_widget__local_contract_test.dart`、`pageflip_contract_test.dart`（→ `../../support/pageflip/pageflip.dart`），`tool/pageflip_diagnostics_main.dart`、`tool/pageflip_widget_diagnostics_main.dart`（→ `../test/support/pageflip/pageflip_diagnostics.dart`，harness 无 `flutter_test` 依赖，`flutter run -t tool/...` 仍可用）。
    - 4 处门禁/测试钉位改写：静态门禁 `verify_pageflip_backward_mainline.py`（`UI_PAGEFLIP_DIRS` 与 `diagnostics_path` 重指 `test/support/pageflip`，rule-12 禁用符号扫描继续覆盖 harness）；边界门禁 `verify_content_ui_directory_boundaries.py` 删除已死的 `components/pageflip` 倒置豁免；架构测试 `article_reader_architecture_test.dart` 删除已死的 harness 白名单（lib-only 扫描自然收紧为仅两个生产 host 可直连 deck）；合约测试 `pageflip_contract_test.dart` 两处 `_readAppSource` 路径串重指 `test/support/...`。
    - 清理 `specs/gates/file_line_budget_allowlist.yaml` 中 `lib/components/pageflip/src/widget/pageflip_widget.dart` 死条目（迁入 `test/` 后已不计入行数预算）。
    - 同步收口残留债：`article_presentation_models.dart` 已迁入 `lib/ui/content/models/`（43 处 import 全更新），content/ 根不再有散落 Dart 文件，边界门禁 `PROTECTED_CONTENT_ROOT_FILES` 清空。
  - 验证证据: `verify_pageflip_backward_mainline.py` OK；`verify_content_ui_directory_boundaries.py` passed；`make verify-app-pageflip-back-mainline` 66 过 / 3 跳（含 BACK fold band 像素、语义 back 快照、mesh 覆盖等视觉/像素不变量）；广义 pageflip 套（当轮旧路径测试 + `article_reader_architecture_test.dart`）129 过 / 3 跳；3 跳为 baseline 既有跳过（partition mesh widen UV parity pending）；`flutter analyze`（moved tree + 4 消费者 + 架构测试目录）零 error，仅余预存在 info/warning——**逐帧同构已证**。
  - 涉及文件:
    - `quwoquan_app/lib/ui/content/pageflip/**`（当轮旧生产引擎，未动；后续 R-PAGEFLIP-002 已迁入 components）
    - `quwoquan_app/lib/ui/content/article_reader/pageflip/**`（宿主，未动；后续仍保留为 UI adapter）
    - `quwoquan_app/test/support/pageflip/**`（诊断/测试 harness，自 `lib/components/pageflip` 迁入）
    - `quwoquan_app/tool/pageflip_diagnostics_main.dart` / `pageflip_widget_diagnostics_main.dart`（诊断入口，改相对引用）
    - `quwoquan_app/lib/ui/content/models/article_presentation_models.dart`（自 content/ 根迁入）
    - `quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py` / `verify_content_ui_directory_boundaries.py`、`quwoquan_app/test/local_contract/ui/content/article_reader/article_reader_architecture__local_contract_test.dart`、`quwoquan_app/test/local_contract/ui/components/pageflip/pageflip_contract__local_contract_test.dart`、`specs/gates/file_line_budget_allowlist.yaml`（钉位/预算同步）
  - 状态: 已解决（2026-06-29；relocate_test_support 落地，逐帧同构经像素/视觉回归证毕，门禁/测试钉位同步迁移；后续生产引擎单根化见 `R-PAGEFLIP-002` / [CR-20260629-080](specs/changelog/CR-20260629-080-pageflip-engine-component-standardization.yaml)）

- [x] R-PAGEFLIP-002 翻页通用引擎沉淀 components 并删除 `ui/content/pageflip` 旧根
  - 区域: App
  - 域: `runtime-client-foundation/article-editor-refactor` / `discovery-content`
  - 原因: 旧生产引擎 `quwoquan_app/lib/ui/content/pageflip/**` 是平台无关的通用翻页 engine（geometry、render frame、curl mesh、release policy、surface snapshot），长期放在 content UI 域会迫使 test harness、诊断工具和未来非 content 场景反向依赖 `ui/content`。文章 reader 的 `quwoquan_app/lib/ui/content/article_reader/pageflip/**` 则绑定文章分页、texture capture、reader diagnostics，应保留为 UI adapter。
  - 方案: 采用“通用引擎进 `lib/components/pageflip`，文章阅读宿主留 `lib/ui/content/article_reader/pageflip`”。`git mv quwoquan_app/lib/ui/content/pageflip` → `quwoquan_app/lib/components/pageflip`；旧生产根删除且不保留 facade；所有生产、test、tool import 一次性切到 `package:quwoquan_app/components/pageflip/...`；旧 `test/ui/content/pageflip` 与 `test/local_contract/ui/content/pageflip` 迁到 `test/components/pageflip` 与 `test/local_contract/components/pageflip`。
  - 保护边界: 不改 geometry、BACK 主线、release policy、gesture 状态机和 texture 语义；`components/pageflip/**` 零 `ui/**` import；`article_reader/pageflip/**` 只作为 reader adapter 消费公共引擎；`test/support/pageflip/**` 继续作为诊断 harness，不进入生产 `lib/`。
  - 验证证据:
    - 基线与迁移后均通过 `python3 quwoquan_app/scripts/content/verify_pageflip_backward_mainline.py`（OK）。
    - `make verify-app-pageflip-back-mainline` 66 过 / 3 跳（baseline 既有跳过，BACK fold band/semantic back snapshot/mesh 视觉像素主线未漂移）。
    - `flutter test --no-pub test/components/pageflip test/common/pageflip test/local_contract/components/pageflip test/ui/content/article_reader test/ui/discovery/widgets/works_immersive_viewer_widget_test.dart` 300 过 / 6 跳。
    - `flutter analyze --no-fatal-warnings --no-fatal-infos lib/components/pageflip lib/ui/content/article_reader/pageflip test/support/pageflip test/components/pageflip test/common/pageflip tool/pageflip_diagnostics_main.dart tool/pageflip_widget_diagnostics_main.dart` 0 error（仅既有 warning/info）。
    - `python3 quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py` passed，固化旧根禁回归与 `components/pageflip` 禁 `ui/**` import。
    - 四环境 packaging 低层验证：`python3 quwoquan_ops/cli/stackctl.py verify --env alpha|beta|gamma|prod --kind packaging --tier t1 --report-dir /tmp/qwq-pageflip-stackctl-<env>-t1` 全部 PASS。
  - 涉及文件:
    - `quwoquan_app/lib/components/pageflip/**`（生产通用引擎，新唯一根）
    - `quwoquan_app/lib/ui/content/article_reader/pageflip/**`（文章 reader adapter，保留）
    - `quwoquan_app/test/components/pageflip/**`、`quwoquan_app/test/local_contract/components/pageflip/**`、`quwoquan_app/test/support/pageflip/**`
    - `quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py`、`verify_pageflip_backward_mainline.py`
    - `.cursor/rules/11-pageflip-geometry-guardrails.mdc`、`.cursor/rules/12-pageflip-backward-mainline.mdc`、`.cursor/commands/pageflip-guard.md`、`quwoquan_app/AGENTS.md`
    - `specs/gates/test_directory_inventory.yaml`、`test_legacy_source_allowlist.yaml`、`file_line_budget_allowlist.yaml`
  - 状态: 已解决（2026-06-29；生产 engine 单根为 `lib/components/pageflip`，旧 `lib/ui/content/pageflip` 删除，无 facade；CR 见 [CR-20260629-080](specs/changelog/CR-20260629-080-pageflip-engine-component-standardization.yaml)）

## 长文 Markdown 渲染（Markdown Article Rendering）

- [x] R-MDARTICLE-001 冷启动创作者文章未按 Markdown 内核重生成，致 markdown 文章门禁红
  - 区域: App / Data
  - 域: `discovery-content/content-type-framework/markdown-article-kernel`
  - 原因: [markdown-article-kernel](specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md) 冻结「长文唯一持久化真相源为 Markdown（`articleMarkdown` + `articleAssetManifest` + `articleRenderProfile`），旧 `articleDocument` 预制数据全部重生成」。但冷启动创作者文章 `content_scenarios.json` 的 `seedSets.creator_authored_core.posts[0]`（`fixture_creator_content_article_001`，batch-100 E2E）仍是仅含 `body` 的薄文章，缺 `articleMarkdown` 与 `articleRenderProfile`，未走 Markdown 重生成。门禁 `make verify-markdown-article-no-article-document`（[verify_markdown_article_no_article_document.py](quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py)）因此红（该失败为预存在，非 review 清除/目录标准化引入）。
  - 影响: `make gate` 在该门禁持续红；端云长文契约存数据漂移（contentType=article 但无 Markdown 真相源），冷启动创作者文章无法经现有 markdown reader（codec → `QwqMarkdownAst` → `MarkdownPaginationEngine` → `ImmersiveMarkdownReader` → pageflip）正确渲染长文版式，退化为薄 body。
  - 涉及文件:
    - `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json`（`creator_authored_core.posts[0]`）
    - `quwoquan_app/lib/ui/content/reader/markdown/article_markdown_codec.dart` / `immersive_markdown_reader.dart` / `qwq_markdown_pagination.dart`（消费链路，已实现）
    - `quwoquan_data` 冷启动 publish 产物（`publish/{batch}/posts/{post}/article.md` + `manifest.json`，重生成来源）
  - 方案: 使该冷启动文章符合 Markdown 内核——补 `articleMarkdown`（QWQ Rich Markdown v1，含 front matter，asset 经 manifest 引用）+ `articleRenderProfile`（dict），无 `articleDocument`；优先经 `quwoquan_data` 冷启动管线产出 `article.md` + `manifest.json`（契约正确），管线未就绪则补最小合规 fixture 作 seed 占位并留管线重生成为后续数据工程项。再端云验证 `GetPost`/详情投影返回 markdown/manifest/renderProfile 且端侧 reader/pageflip 渲染正确。
  - 次序: **显式排在 `R-PAGEFLIP-001` 之后**（用户口径「完成 pageflip 后再回头落实 markdown 文章渲染」）。markdown reader 渲染末端经 pageflip 层（`article_read_only_book_deck.dart` + `lib/ui/content/models/article_presentation_models.dart`），故待 pageflip 专项稳定后再验证长文渲染，避免在不稳定的 pageflip 层上重复验证。`R-PAGEFLIP-001` 已于 2026-06-29 收口（pageflip 层逐帧同构稳定），本项前置已满足，可启动。
  - 验收: `make verify-markdown-article-no-article-document` + `make verify-article-contract-purity` 绿；content 域 markdown 契约/widget 测试覆盖「冷启动文章经 codec→AST→分页→reader 渲染」；`make gate` app 关键项绿（仅余 `R-PLAZA-001` 等无关项）；按数据/契约改动面补 CR。
  - 验证证据:
    - 单一真相修法（非手改 JSON）：生成器 `quwoquan_data/scripts/governance/creator_pool/content_bind.py::_content_document` 为 `article` 载体补 `articleMarkdown`（QWQ Rich Markdown v1，含 front matter 桌面）+ `articleRenderProfile`（dict，`contentVertical=travel`），且不再产出 `articleDocument`；经 `qwq-data` materialize 重生 `content_scenarios.json`（仅 `creator_authored_core.posts[0]` article 文档 +13/-1，image/video seed 不变）。
    - 门禁绿：`python3 quwoquan_app/scripts/content/verify_markdown_article_no_article_document.py` → `OK`；`python3 quwoquan_app/scripts/content/verify_article_contract_purity.py` → `OK`。
    - 端云验证：cloud `services/content-service/tests/post_markdown_contract_test.go` 全过（`GetPost` 投影 markdown 内核、拒绝仅 `articleDocument`）；端侧 `test/cloud/content/contract/article_get_post_hydration_contract_test.dart` + `test/ui/content/reader/markdown/**` + `test/ui/content/post/contract/post_view_projection_contract_test.dart` 全过（codec→`QwqMarkdownAst`→`MarkdownPaginationEngine`→`ImmersiveMarkdownReader`→pageflip hydration）；content 契约套 124 过。
    - 防回退：新增 `quwoquan_data/tests/local_contract/creator_pool/test_creator_content_bind__local_contract_test.py::test_article_projection_carries_markdown_kernel_not_article_document`（8 过），断言生成器 article 投影携带 markdown 内核且无 `articleDocument`。
  - 涉及文件（实际改动）:
    - `quwoquan_data/scripts/governance/creator_pool/content_bind.py`（生成器单一真相修法）
    - `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.json`（经 materialize 重生）
    - `quwoquan_data/tests/local_contract/creator_pool/test_creator_content_bind__local_contract_test.py`（防回退合约）
  - 状态: 已解决（2026-06-29；生成器单一真相修法 + materialize 重生 + 端云渲染契约全过 + markdown/纯洁度门禁绿 + 新增防回退合约；CR 见 [CR-20260629-078](specs/changelog/CR-20260629-078-coldstart-article-markdown-kernel-regeneration.yaml)）

## 内容 UI 目录标准化（Content UI Directory Standardization）

- [x] R-CONTENTDIR-001 content 客户端 UI 目录未完全标准化归一（3 个 models 目录 + reader/article_reader 命名混淆 + 双 pageflip 分层未门禁固化）
  - 区域: App
  - 域: `runtime/runtime-client-foundation`（目录标准化）/ `discovery-content`
  - 原因: [01-arch-constraints](.cursor/rules/01-arch-constraints.mdc) §2.4 要求 `lib/ui/{domain}/pages|providers|widgets|models`。但 content 域内存在三类不归一：①三个 models 目录——`lib/ui/content/models/`（域级公共）、`lib/ui/content/entry/models/`（创作私有 7 文件）、`lib/ui/content/reader/models/`（仅 `article_detail_view.dart` 1 文件，却被 `discovery/works_immersive_viewer`、`content/widgets/article_content_block_renderer`、`content/services/post_view_projection`、`content/models/content_surface_view` **跨子域消费**，本质是公共富渲染模型却窝在子域，且造成 `content/models/` 反向依赖 `content/reader/models/` 的层内倒置）；②`lib/ui/content/reader/`（实为 markdown 渲染/分页引擎：codec/ast/pagination/parser + flow/pagination services）与 `lib/ui/content/article_reader/`（翻页书本阅读宿主，消费 reader）命名混淆，未表达分层；③`lib/components/pageflip/`（StPageFlip 引擎，lib 中仅被 article_reader 消费）与 `lib/ui/content/article_reader/pageflip/`（宿主适配）host→engine 分层未被门禁固化。现有边界门禁 [verify_content_ui_directory_boundaries.py](quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py) 仅防"根散落文件 + 跨域 import discovery"，对上述均为盲区。
  - 影响: 目录认知成本高、新增文件易放错位置（已发生：公共模型 `article_detail_view` 误置 reader/models）、域级 models 反向依赖子域 models、阅读链路 reader/article_reader 命名混淆增加误改风险。
  - 方案: 第一阶段采用折中档 + 冻结 pageflip 物理布局——①models 单一化：`reader/models/article_detail_view.dart` + `entry/models/*`（7 文件）全部上提 `lib/ui/content/models/`，删除空子目录；②`reader/` → `article_render/` 重命名澄清（`article_reader/` 因内含 `article_reader/pageflip/` 宿主子树、受"冻结 pageflip 物理布局"红线约束**当轮不重命名**，仅靠门禁/文档澄清职责）；③扩展边界门禁固化三不变量：唯一 models 根（禁 `content/**/models/` 除 `content/models/`）/ pageflip 引擎仅可被 `article_reader/` 与 `test/` 消费 / `article_render/`（引擎）不得依赖 `article_reader/`（宿主）。第二阶段已由 `R-PAGEFLIP-002` 收口：生产通用引擎沉淀到 `lib/components/pageflip/`，旧 `lib/ui/content/pageflip/` 删除，article reader 宿主保留在 UI adapter。
  - 涉及文件:
    - `quwoquan_app/lib/ui/content/models/`（唯一 models 根，接收上提文件）
    - `quwoquan_app/lib/ui/content/entry/models/`、`quwoquan_app/lib/ui/content/reader/models/`（删除）
    - `quwoquan_app/lib/ui/content/reader/` → `article_render/`（重命名）及其 ~26 lib+test 消费者 import
    - `quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py`（扩展三不变量）、`verify_article_contract_purity.py`（路径）、`specs/gates/test_directory_inventory.yaml` 等清单
  - 次序: `R-PAGEFLIP-001`（pageflip 逐帧同构稳定）已收口，本项以冻结 pageflip 物理布局为红线，安全开展。
  - 验收: 边界门禁三不变量绿；`flutter analyze` 无新增 error；content 契约 + pageflip（`make verify-app-pageflip-back-mainline` 逐帧同构）+ markdown 全套测试绿，pageflip 物理布局零改动；按改动面补 CR。
  - 验证证据:
    - models 单一化：`lib/ui/content/models/` 为唯一 models 根（16 文件，含上提的 `article_detail_view` + 原 entry/models 7 文件）；`entry/models/`、`reader/models/` 已删除；对应测试迁至 `test/ui/content/models/` 与 `test/local_contract/ui/content/models/`。
    - reader→article_render：`git mv lib/ui/content/reader/ → article_render/`（markdown/ + services/）；~26 lib+test import 全更新；测试目录 `test/ui/content/article_render/`、`test/local_contract/ui/content/article_render/` 同步。
    - 边界门禁三不变量绿：`verify_content_ui_directory_boundaries.py` passed（唯一 models 根 / pageflip 引擎仅 article_reader+test 消费 / article_render 不依赖 article_reader）；新增退役路径 `package:quwoquan_app/ui/content/reader/` 扫描。
    - 契约/渲染：`verify_article_contract_purity.py` OK；`verify_markdown_article_no_article_document.py` OK；article_render + content 契约套 158 过。
    - 第一阶段 pageflip 零改动：`verify_pageflip_backward_mainline.py` OK；`make verify-app-pageflip-back-mainline` 66 过 / 3 跳（baseline 既有跳过）；当轮 pageflip 物理布局未动。
    - 第二阶段单根化：`R-PAGEFLIP-002` 已将旧 `ui/content/pageflip` 生产引擎迁入 `lib/components/pageflip`，`verify_content_ui_directory_boundaries.py` 固化旧根禁回归与 `components/pageflip` 禁 `ui/**` import。
    - `dart analyze lib/ui/content` 无新增 error，仅余预存在 warning/info。
  - 涉及文件（实际改动）:
    - `quwoquan_app/lib/ui/content/models/`（唯一 models 根）
    - `quwoquan_app/lib/ui/content/article_render/`（自 reader/ 重命名）
    - `quwoquan_app/scripts/content/verify_content_ui_directory_boundaries.py`（三不变量 + 退役路径）
    - `specs/gates/test_directory_inventory.yaml`、`test_legacy_source_allowlist.yaml`、`file_line_budget_allowlist.yaml`（路径同步）
  - 状态: 已解决（2026-06-29；models 单一化 + reader→article_render 重命名 + 分层门禁固化 + 全量回归绿；后续 pageflip 生产引擎单根化已由 `R-PAGEFLIP-002` 收口；CR 见 [CR-20260629-079](specs/changelog/CR-20260629-079-content-directory-unification.yaml) 与 [CR-20260629-080](specs/changelog/CR-20260629-080-pageflip-engine-component-standardization.yaml)）

## 主页稳定性与四环境打通（Homepage Stability & Env Integration，2026-07-07 用户确认登记）

- [x] R-HSE01 prod 真实 ECS 主页实导与灰度发布（54 实体 homepage）
  - 区域: Ops / Data / Service
  - 域: `deliver-deploy-prod-pipeline` / `content-supply`
  - 原因: WP4-WP6 已完成 gamma-local 全链实导、prod gray 演练栈（本地 rootless compose）ship dry-run→实导→introduction API 验证→rollback 幂等重放，但真实 prod ECS（prod-hosted, 118.31.239.122）此前尚未承载 homepage 通路：远端服务面栈为 2026-06-17 渲染版本，Caddyfile 无 `/v1/homepages*` 路由、无 entity-service 镜像与容器。
  - 影响: prod 用户面无法访问 54 实体主页 introduction 投影；四环境商用闭环缺 prod 实导审计证据。
  - 涉及文件: `quwoquan_ops/cli/prod/render_prod_plane_stack.py`、`quwoquan_ops/cli/prod/deploy_to_prod.sh`、`quwoquan_data/scripts/ship/handler.py`、`.qwq_output/env/prod/runs/data-release/`
  - 验收: `stackctl deploy --target prod-hosted` gray-initial→SLO gate→full；ship `--confirm-prod-apply` 实导 54 实体；prod environment run 归档 release/import/rollout/SLO；prod edge `/v1/homepages/{id}/introduction` 抽检（武侯祠/黄龙）返回真实投影。
  - 状态: 已解决（2026-07-07 完成 prod 实导全流程：ship `--confirm-prod-apply` 实导 projected=55/created=53/updated=2；媒体 304 objects（977MB）tar-over-ssh 同步；gray-initial stage=5 SLO gate decision=continue（30 样本 errorRate=0、P95=136ms）；期间编排 post-deploy health 因 topology IP publicBases 与 SNI-matched Caddy 的既有形态缺口 0/4 触发自动回滚，已按真相源修复——`render_prod_plane_stack.py` 从 `environment_topology_manifest.yaml` 解析公网 IP 注入 Caddy api 站点别名 + `default_sni`，修复后 `stackctl health prod-hosted` 4/4；full stage=100 decision=continue 无回滚；prod edge 武侯祠 homepage_30 / 黄龙 homepage_52 introduction IP+域名双口径 200、coverUrl 200；gray 栈按共享集群语义退场。历史证据已迁移到 `.qwq_output/env/prod/runs/data-release/prod_homepage54_20260707-7a0db44d1487/runs/legacy-migration-encyclopedia-autonomous-publish-v3-20260711-01d5d7178e1f/legacy_evidence/`，原 applied/rollback refs 保留。）

- [ ] R-HSE02 entity-service homepage_state 导入后需重启才对读路径可见
  - 区域: Service / Ops
  - 域: `entity`（homepage introduction 读路径）
  - 原因: entity-service 将 homepage_state 作为启动时一次性加载的聚合，importer 写入 Mongo 后运行中进程不重读；prod gray 演练与 gamma-local 实导均复现（重启容器后 introduction API 立即可见）。
  - 影响: 每次 homepage 数据发布必须人工/编排追加 rolling restart，遗忘即持续返回旧数据，形成发布断点。
  - 涉及文件: `quwoquan_service/services/entity-service/`、`quwoquan_data/scripts/ship/handler.py`
  - 验收: entity-service 支持 homepage_state 热重载（变更流/按 releaseId 触发重读），或 ship→import 编排自动追加受控 rolling restart 并把动作写入 import report/runbook。
  - 状态: 待办（2026-07-07 登记；过渡操作=导入后手动重启，动作已记入 prod_gray_drill 与 prod 实导证据 `prod_homepage54_20260707/release_rollout.json`——本次 prod 实导中 gray/full 两阶段均通过容器 recreate 满足重启语义并留痕）

- [ ] R-HSE03 process_domain_mapping.yaml 与 prod-hosted 实际运行面口径差异
  - 区域: Ops
  - 域: `platform-ops-governance`（部署拓扑真相源）
  - 原因: `quwoquan_ops/environments/process_domain_mapping.yaml` 声明 prod 环境 entity 域归属 `quwoquan_service` 聚合进程，但 prod-hosted rootless compose 实际按 onebox split-services 运行独立 `entity-service`（`quwoquan_ops/environments/prod_plane_access_isolation.yaml` 已按现实登记 governed compose services）。两份真相源口径不一致。
  - 影响: 「同一环境 domain 唯一归属 + integration/prod 映射一致」军规存在漂移风险；后续扩服务/迁移域时易按错口径配置路由与告警。
  - 涉及文件: `quwoquan_ops/environments/process_domain_mapping.yaml`、`quwoquan_ops/environments/prod_plane_access_isolation.yaml`、`quwoquan_ops/environments/workload_topology_inventory.yaml`
  - 验收: 对齐两份清单口径（以实际运行面为准修 mapping，或写明 split-services 过渡语义），并补跨清单一致性校验进 gate。
  - 状态: 待办（2026-07-07 登记）

- [ ] R-HSE04 共享部署拓扑 YAML 多会话并发写损坏事故
  - 区域: Ops
  - 域: `platform-ops-governance`（拓扑清单完整性）
  - 原因: 本轮执行期间 `quwoquan_ops/environments/` 拓扑清单曾被并发会话/工具写坏（无写锁、无原子写），已恢复；2026-07-07 复核四份拓扑 YAML（environment_topology_manifest / process_domain_mapping / workload_topology_inventory / prod_plane_access_isolation）均可正常解析。
  - 影响: 拓扑清单是环境渲染、部署与门禁的唯一真相源，损坏会放大为 stackctl render/deploy 全链失败或错误发布。
  - 涉及文件: `quwoquan_ops/environments/*.yaml`、`quwoquan_ops/cli/lib/environment_topology.py`
  - 验收: 拓扑 YAML 写路径统一临时文件+原子 rename，加载处保留 schema 校验硬失败；gate 增加拓扑清单可解析性快检。
  - 状态: 待办（2026-07-07 登记）

- [x] R-HSE05 单机 Cursor bridge 实测安全并发上限为 2 worker
  - 区域: Data
  - 域: `content-supply`（managed 编排吞吐）
  - 原因: WP7 多 worker 小样本实测（mw2/mw3 探针）：2 worker 稳定（0 基础设施失败，总吞吐 +12%）；3 worker 出现 2 次 `Bridge ConnectError: [Errno 61] Connection refused` 且总吞吐反降 6%，错峰冷启（cooldown 10s）下仍复现，瓶颈在本地 bridge 会话承载。
  - 影响: 放量模型的单机并发假设从「经验值 3」修正为实测 2；日产 10 万等效单机数按 2 并发上调至 ~253 台（含其它假设，见报告）。
  - 涉及文件: `quwoquan_data/control_plane/_shared/cursor_local_calibrated.runtime.yaml`、`quwoquan_data/verticals/travel/coverage/two_province_homepage_rollout.yaml`
  - 验收: per-worker 独立 bridge/错峰冷启强化或远端 author 池（cloud runtime）实测把安全并发提到 ≥3，并复测退化曲线。
  - 状态: 已解决（2026-07-17；3 个隔离 Cursor bridge 的 30-job soak 为 30/30 成功、effectiveConcurrency=3、bridgeDisconnectCount=0、probeJobsPerHour=488.039、startupLatencyP95=31.6641s，满足 rollout capacity 合同。证据：`.qwq_output/env/repo/runs/20260717T041601Z-data-capacity-soak/report.json`。该报告是可删除的运行证据，重建规则仍只来自仓内 runtime profile 与 rollout contract。）

- [ ] R-HSE06 浙江/四川省级覆盖 NO-GO：真实金丝雀与来源饱和尚未准出
  - 区域: Data
  - 域: `content-supply`（homepage lane 源供给）
  - 原因: 两省 coverage 的来源饱和、逐图权利、2899 approved homepage、60 个冷启动 posts、aggregate launch release、四环境 promotion 和动态 App UAT 尚未形成同一验收闭包。
  - 影响: 双省金丝雀未绿前不得启动 M1/M2/M3，也不得把 creator fixture、历史批次或静态 API fixture 当成目标主页 release 证据。
  - 涉及文件: `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/zhejiang-sichuan-province-coverage/acceptance.yaml`、`quwoquan_data/verticals/travel/coverage/中国/浙江省/`、`quwoquan_data/verticals/travel/coverage/中国/四川省/`。
  - 验收: 浙江普陀山、东钱湖与四川海螺沟金丝雀 execution 顺序通过来源、逐图权利、Agent 正文、独立 review、object transaction、aggregate release、Beta/Gamma 导入、API 与动态 App UAT；随后按同一 CLI 推进 M1/M2/M3，并生成 60 个冷启动 posts 与四环境 promotion evidence。
  - 状态: 进行中（2026-07-18 当前复验：仓外 Cursor key file 权限与启动探针通过；Data `verify all`、门禁范围内 1354 项 local_contract 与 20 项 user_acceptance 全绿，全仓 `make gate` 真实退出 0。发布链已收口为 release-first：entity/post/creator/tag 使用 immutable object snapshots，精确 CAS 媒体闭包冻结到 `payload/media/objects/**`，环境 importer/media sync 不再回读 mutable canonical publish；article/image/video 均有同一 object transaction，video 使用独立 poster CAS 与 `posterAssetId` 强闭包。已通过 active-runtime preflight 破坏性删除旧三实体 canonical、旧 tasks/releases 及 Beta/Gamma data-release 证据，不迁移旧金丝雀；新建 `20260718--travel-homepage-coverage--cn-zhejiang-sichuan--baseline-003`，其 empty desired-state、release lifecycle 与 payload integrity 全绿，canonical publish 当前为 0 entities / 0 posts。最新 Data api_integration 为 31 passed / 1 GATE_BLOCK，唯一阻塞是 Gamma S3 endpoint TLS connection reset；Alpha health 11/11，Beta health 15/17，Gamma health 0/23，prod-sim health 0/12。`stackctl doctor` 已把 Beta/Gamma 的根因结构化为仓外 `~/.config/quwoquan/product_telemetry_sls/<env>.env` 缺失，并在前置条件失败时禁止建议盲目重启；Gamma 因此不能形成真实环境闭环。尚未生成 2899 entities、60 posts、M3/launch release、四环境 promotion 或动态 App UAT，因此不得启动 M1/M2/M3，也不得关闭本项。）

- [ ] R-HSE07 gamma T3 交集语义环境闭环尚未复验
  - 区域: Data / Service / App
  - 域: `intersection-definition-and-application` / 测试治理
  - 原因: 上次 gamma-local T3 strict probe 有 5 项 intersection 语义断言失败；本轮目录与数据契约收口没有真实启动 gamma-local，因此不能沿用旧失败，也不能宣称已通过。
  - 影响: 双省 release 即使生成，也必须等 Gamma 导入、API 与动态 App 用户旅程重新执行后才能准出。
  - 涉及文件: `quwoquan_app/scripts/gamma/run_local_gamma_t3.py`、`quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json`
  - 验收: 双省 canary release 导入 Gamma 后，T3 intersection 语义、实体主页 API 与动态 App UAT 在同一 run 证据中全绿。
  - 状态: 进行中（2026-07-11：Data 测试隔离债已关闭，`verify_quwoquan_data.sh` 在全仓 gate 中通过，末段 141 tests 全绿；当前只保留尚未具备 release 输入的 gamma T3 环境复验。）

## App Cloud 商用接入与服务目录治理（2026-07-13 用户确认登记）

- [ ] R-CLOUD01 Realtime / RTC 缺少可信实时鉴权
  - 区域: App / Service
  - 域: `realtime` / `rtc`
  - 原因: WebSocket、LongPoll 与 RTC signaling 仍可由客户端 URL 参数提供 `userId/topics`，未证明短期 ticket、Bearer 与服务端 auth ack 同源。
  - 影响: 严格服务端下链路不可用；若服务端信任客户端身份，则存在跨用户订阅和数据泄露风险。
  - 涉及文件: `quwoquan_app/lib/cloud/services/realtime/**`、`quwoquan_app/lib/cloud/rtc/rtc_signaling_client.dart`、realtime/rtc metadata 与服务端入口。
  - 验收: metadata 生成 ticket operation/auth policy；客户端只提交 ticket，服务端从可信身份派生 actor/topics 并返回 ack；越权负例、过期、重放、断线恢复和三层测试全绿。
  - 状态: 进行中（2026-07-15 复核；App realtime 已删除 production Mock delegate/catalog 与运行时 mode 切换，固定为 Remote-only composition，但这只消除错误装配，不等于可信实时鉴权。`rtc-service` 与 `realtime-gateway` 仍不接入三朵云 prod root，尚不存在短期 ticket、participant/BOLA、ticket 过期/重放负测或 Gamma 新证据，不能关闭）

- [ ] R-CLOUD02 Assistant consent 失败开放且未按 actor 隔离
  - 区域: App / Service
  - 域: `assistant`
  - 原因: 端侧可把 `granted=false` 且 `revokedAt` 为空解释为已授权，远端 grant/revoke 失败时还能本地合成成功；本地状态未按 account/persona 分区。
  - 影响: 网络故障、账号切换或撤权后可能错误继续使用敏感能力，审计事实与用户选择不一致。
  - 涉及文件: `quwoquan_app/lib/cloud/services/assistant/assistant_repository.dart`、Assistant consent metadata、服务端 consent store。
  - 验收: consent 由服务端版本化事实唯一决定；端侧按 actor 隔离、失败关闭且不伪成功；grant/revoke/read、切号、离线、过期与审计测试全绿。
  - 状态: 进行中（2026-07-15 复核；Assistant consent HTTP 入口继续要求经 JWT 验签写入的 account principal，伪造 `X-Client-User-Id` local contract 返回 401；尚未补齐端侧 actor 分区、版本化 consent 唯一真相、撤权即时拒绝和 Gamma 负测，不能关闭）

- [x] R-CLOUD03 Behavior / Ops 离线队列可跨 actor 重放
  - 区域: App / Service / Ops
  - 域: `behavior` / `ops`
  - 原因: 当前 Hive queue 使用全局分区；账号或 Persona 切换后，旧事件可能使用新 token 重放。
  - 影响: 污染推荐、运营指标和审计，同时造成跨主体隐私串写。
  - 涉及文件: `quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart`、`quwoquan_app/lib/cloud/services/ops/ops_event_repository.dart`、operation context 与本地安全存储。
  - 验收: 队列按 environment/account/persona/device 加密分区，登出清理，poison DLQ/drop 指标完备；切号与重放负例通过。
  - 状态: 已解决（2026-07-14；App 离线队列统一通过 `ActorQueueStorage` 按 environment/account/persona/device 哈希分区，使用 secure storage 中的随机 256-bit key 加密 Hive queue 与 DLQ；Behavior、Ops 与异常遥测拒绝跨 actor envelope，poison/overflow 进入 DLQ 并记录 `app_actor_queue_transition_total`，退出及 actor/session 切换原子清理 queue、DLQ 与密钥。`flutter analyze`、actor 分区/密文/DLQ/切号/退出 36 项 local contract、`make verify-test-coverage-map`、`make verify-app-cloud-security-cutovers`、`make verify-app-cloud-runtime-single-path`、`make verify-app-cloud-package-boundaries` 全绿。）

- [ ] R-CLOUD04 ContractGraph Dart 生成链不可全量重生且合同包循环依赖
  - 区域: App / Service
  - 域: `runtime-codegen` / `runtime-client-foundation`
  - 原因: App emitter 仍有直接读取业务 YAML、手写 generated 与 orphan 产物；`quwoquan_cloud_contracts` 反向依赖 `quwoquan_app`。
  - 影响: metadata-first、供应链 provenance、breaking change 和 clean checkout 构建均不可证明。
  - 涉及文件: `quwoquan_service/internal/metadata/**`、App codegen、`quwoquan_app/lib/cloud/runtime/generated/**`、`quwoquan_app/packages/quwoquan_cloud_contracts/**`。
  - 验收: App emitter 只消费固定 ContractGraph hash；output manifest 完整；删除 generated 后可 byte-for-byte 重建；合同包为 pure Dart 且包图无环。
  - 状态: 进行中（2026-07-16 复核；Registry/ContractGraph 已完成单轨破坏性切换：14 个 Registry、唯一 `_schemas/`、唯一 compiler/Graph/handoff/readiness 口径，Registry、readiness、Graph、lock、breaking report 与 generated manifest 均不再携带 `version/schemaVersion/registryRevision`，旧字段和版本目录由反向门禁直接拒绝。当前唯一 Graph `635a57032f8a0923914f505c4bdc6fd6faa6cbd6de6f20a32a881cf8a0d1c470` 从同一输入重生 91 个对象、177 条字段绑定关系、343 个 canonical operation、163 个 projection 与 341 个 OpenAPI transport；340→343 的三条净增已审计为 ProfileUpdateProposal 冻结对象的真实 command/query packet，不是兼容版本或重复 owner，因此最终数量继续由 Graph 派生。App handoff 覆盖 156 个 exposure，manifest 228 个输出 clean rebuild；metadata commercial、handoff 与 manifest 定向门已复验通过。readiness 当前仍为 54 modeled、36 contract-ready、1 implemented、0 derived commercial-ready，Gamma、行为型 user_acceptance、其余对象 packet 和 55 个手写 ready assertion 仍未闭合。L2/L3、CR-088、14 个 business object registry、Graph/descriptor 和 App handoff 已由外部并行任务纳入当前 `dev1.0` 提交 `4c60e95c`；但本轮又修正了 strict DTO generator 与派生产物，这些精确路径尚未获授权 stage/checkpoint，clean checkout 仍无法重现最新静态门结果，故保持进行中。2026-07-17 附注：CR-110/CR-111 已将单轨信封/aliases 与门禁盲区 residual（wire 双读、正向 alias 测试、assets 版本身份、verify_single_track_contracts 加严）单独立项收口；本项仍仅覆盖 Graph 全量重生/包环/readiness，不因单轨 residual 打勾关闭。2026-07-17 续：CR-112 已清零非常规变量名 wire 双读盲区、specs/军规短期双读教学与 wirepoc schemaVersion，并加严门禁扫描 generated/specs/.mdc；本项仍不关闭。2026-07-17 续：CR-113 已完成客户端 wire 去 `_id`（storage/bson `_id` 仍保留）与 orphan wirepoc 删除、门禁 T3_wire_id_key；不因本 CR 关闭 Graph/包环/readiness。）

- [ ] R-CLOUD05 Mock / fixture / 空 Remote 仍进入商业依赖图
  - 区域: App
  - 域: `runtime-client-foundation`
  - 原因: 24 个 production `Mock*` 类、fixture runtime loader、Prototype 数据与 Remote 仍同处 App production package；部分对象仍经聚合 Repository、恒空 Remote 或失败回退空集合。
  - 影响: alpha 与 beta/gamma/prod 行为分叉，商店包包含测试数据/实现，并把不可用伪装为业务空态。
  - 涉及文件: `quwoquan_app/lib/cloud/**`、`quwoquan_app/packages/quwoquan_cloud_contracts/**`、App composition roots。
  - 验收: pure contracts、独立 mock package/alpha runner 和 production Remote root 物理隔离；prod kernel/AOT/SBOM 无 Mock/fixture/Noop 可达；空 Remote/fallback 为零。
  - 状态: 进行中（2026-07-16 复核；Realtime 已从 production 删除 `MockRealtimeConnectionDelegate`/`MockRealtimeEventCatalog` 和 mode 热切换，production provider 固定 Remote-only，alpha runner 从生成的 immutable bundle 注入 fixture，测试替身只在 `test/support`。本轮确认 Invite 旧 Repository/Mock/Remote/provider 无任何业务消费者后整条删除，不保留 alias，Mock 单调门从 25 收紧到 24。Report、Location、ProfileUpdateProposal 与部分 Content typed packet 仍保持已完成，但 App production 尚有 24 个 `Mock*`、48 个 abstract Repository、56 个 repository 命名文件、93 个 `lib/cloud/services/**` Dart 文件及 fixture runtime loader，prod kernel/AOT/SBOM 零可达尚未证明，不能关闭）

- [ ] R-CLOUD06 存在性 UAT 与 Remote adapter 覆盖不足
  - 区域: App / Service / Ops
  - 域: `runtime-test-pyramid`
  - 原因: 多个 UAT 只检查证据路径存在，API integration 以裸 HTTP 或服务测试替代 Dart Remote adapter，且存在动态 skip/自 seed。
  - 影响: 当前测试通过不能证明真实页面、generated client、错误恢复和四环境端到端可用。
  - 涉及文件: `quwoquan_app/test/{api_integration,user_acceptance}/**`、`specs/03_TESTING_STRATEGY.md`、coverage/no-fake gate。
  - 验收: 逐 operation 的 local contract + Dart Remote gamma API integration + 行为型页面 UAT 闭合；路径存在、动态 skip、自 seed 和 Memory adapter 不计通过。
  - 状态: 进行中（2026-07-16 复核；ChatConversationPage 已用真实 widget/Provider 行为验证发送、权限拒绝与 realtime fixture，并删除文件存在性 UAT、Mock realtime 假 UAT及 `ChatDetailPage` 兼容别名；coverage/acceptance/no-fake 门通过。Chat 的 5 项真实 Mongo/Redis API integration 通过。最新 `python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all` 报告 `.qwq_output/env/gamma/runs/20260716T030836Z-verify-gamma-local/report.json`：Gamma package、拓扑、T2 media、T4 page smoke/media surface 通过，但 T3 `.qwq_output/env/gamma/runs/20260716T030856Z-local-gamma-t3-gamma-local/t3_report.json` 失败。固定 Comment Idempotency-Key 已改为同一 run 稳定、跨 run 隔离，runtime parent/reply/reaction/media bind setup 均通过；剩余 endpoint 仅 7 passed，另有 4 contract_blocked、5 个 metadata blocked operation 被旧 Gamma 服务 200 错误接受，以及 Assistant/creator-pool/Location/Notification/RTC 共 7 个 `not_ready`。Entity 源码已接 generated default-deny，本地三条 blocked route 403、未知 route 404；但 `.qwq_output/env/gamma/runs/20260716T031439Z-up-gamma-local/report.json` 因缺真实 `WECHAT_OAUTH_APP_ID` fail-closed，当前 User/Entity 新镜像未装入 Gamma，不能用旧容器证明修复。这证明真实 Dart Remote Gamma、设备与十 Journey 仍未闭合，不能关闭）

- [x] R-CLOUD07 服务目录跟踪本机构建二进制
  - 区域: Service / Supply Chain
  - 域: `platform-ops-governance`
  - 原因: 多个源码服务根目录存在被 Git 跟踪的 Mach-O `api` 可执行文件，未由发布构建和 provenance 管理。
  - 影响: 仓库体积、跨平台构建、依赖漏洞扫描、可重现性和代码评审均失真。
  - 涉及文件: `quwoquan_service/services/*-service/api`、`.gitignore`、service layout/build gate。
  - 验收: 跟踪二进制清零；构建只输出到 `.qwq_output`；Mach-O/ELF/`*.test`/coverage/cache 回归门禁接入 `make gate`。
  - 状态: 已解决（2026-07-13；`verify_service_layout.py` 已将 tracked Mach-O/ELF、`*.test`、coverage、服务根构建输出纳入阻断并验证全仓清零；构建输出统一归入 `.qwq_output`）

- [x] R-CLOUD08 seed-box 声明与镜像/入口组成漂移
  - 区域: Service / Ops
  - 域: `platform-ops-governance`
  - 原因: process/module 声明、Docker build 列表和 `SERVICE_SPECS` 未保持完全一致。
  - 影响: 路由、发布、健康检查和故障隔离可能针对不存在或未声明的子进程，形成幽灵服务。
  - 涉及文件: `quwoquan_ops/environments/{process_domain_mapping,module_package_mapping}.yaml`、`quwoquan_service/services/seed-box/deploy/**`。
  - 验收: 四向集合严格相等且由同一 module mapping 生成/验证；package contract 与 gamma/prod 路由探针通过。
  - 状态: 已解决（2026-07-13；类型化 service asset profile 与 `verify_service_layout.py` 已验证 process/module/build/service specs 四向闭包；服务资产布局与脚手架 local contract 4/4 通过）

- [ ] R-CLOUD09 realtime-gateway 缺少源码与构建 provenance
  - 区域: Service / Ops
  - 域: `gateway-orchestrator-foundation/realtime-gateway`
  - 原因: workload 已登记并使用镜像，但仓内未证明源码根、Docker build context、固定 digest 或外部来源。
  - 影响: 无法审计、复现、修复或回滚 realtime 生产工作负载。
  - 涉及文件: `quwoquan_service/services/realtime-gateway/**`、`quwoquan_ops/environments/workload_topology_inventory.yaml`。
  - 验收: 补齐第一方源码/build/contract tests/镜像流水线，或登记受控外部 source/digest/SBOM/provenance；禁止 `latest`。
  - 状态: 进行中（2026-07-15 复核；端侧 Remote-only 改造未产生服务端 provenance；仍无可关闭本项的第一方源码、固定 digest、SBOM 或 provenance 新证据，`realtime-gateway` 继续不接入 prod root）

- [x] R-CLOUD10 topology 将业务 domain 与外部 capability 混用
  - 区域: Service / Ops
  - 域: `platform-ops-governance`
  - 原因: domain、source service、runtime module、deployment package、OS process、workload 与 SFU/TURN capability 尚无机器可校验的类型边界。
  - 影响: ownership、扩缩容、路由、告警和 ContractGraph coverage 会把外部基础设施误判为业务域。
  - 涉及文件: `quwoquan_ops/environments/**`、ContractGraph source/build 引用、service layout verifier。
  - 验收: 引入类型化 asset profile 和 source-build-workload 闭包；LiveKit/TURN 使用 capability 字段，legal-static 使用 static-artifact profile。
  - 状态: 已解决（2026-07-13；`service_asset_profiles.json` 区分 source/package/external/static profile，source-build-workload 双向闭包门已通过；LiveKit/TURN 与 legal-static 不再冒充业务 domain）

# 趣我圈商用准出总控主清单（Commercial Maturity Master Plan）

> 状态：主清单已冻结（CM-001～CM-067，批次 B01～B06）
> 证据截点：2026-07-20 15:00（本文所有"当前证据"均以该时点磁盘与门禁实测为准）
> 定位：从现状审计到整体商用准出的**唯一功能与能力执行主清单**。审计底料在
> [`docs/functional_module_commercial_maturity_matrix.md`](functional_module_commercial_maturity_matrix.md)（M1～M18 + H1/H2 + §28），
> 域级专项底料在 `docs/*-commercial-maturity-plan.md` 六份专项规划；本文不复制底料，只做收敛、编排与准出勾稽。
> 风险唯一账本仍是 [`docs/outstanding_risks_backlog.md`](outstanding_risks_backlog.md)；本文只引用 R-* 编号，不建立第二套风险清单。

## 0. 推导口径与使用规则

### 0.1 审查主线与四个输入源

全部 CM 项沿唯一主线证明：
`业务目标 → 核心业务对象 → 关联对象 → 对象关系/基数 → 聚合边界 → 生命周期/状态机 → command/query/event/error → 存储/缓存/索引 → 页面投影 → 用户旅程 → 交集差异化 → 运营指标 → 测试与环境证据`。

CM 项由四个来源合并去重推导，来源在每张卡"底料"字段可反查：

1. 成熟度矩阵 M1～M18/H1/H2 的任务清单与 GATE_BLOCK 候选（覆盖索引，不照抄为 18 个任务）。
2. 六份专项规划已冻结的工作包：搜索 WP-H/I/J/K/L/E/G、交集 WP-IX-0～5、发文字批次 A～F（G1～G8/N1～N12）、发图批次 A～F（GATE-P1～）、发视频批次 V-A～V-F（GATE-V1～V10）、推荐 W1～W13 状态附记。
3. 开放 R-*（当前 75 项）中属产品/能力收口者；纯平台侧 R-OPS-* 归并行运维轨道，只登记依赖。
4. **验证准出型**：现状看似完整但无当前版本商用准出证据的能力，各建一个验证型 CM（无代码改动的能力不得从规划消失）。

### 0.2 CM 项类型、优先级与状态枚举

- 类型：`产品功能 / 业务对象 / UX 重构 / 平台横切 / 外部集成 / 测试准出`；验证准出型在名称后标 `[验证型]`。
- 优先级：`GATE_BLOCK`（不关闭不得商用放量）、`COMMERCIAL_MUST`（商用必备）、`DIFFERENTIATOR`（交集差异化主战场）。
- D1～D6 状态：`PASS / PARTIAL / BLOCKED / UNVERIFIED`；`BLOCKED` 必须写明外部阻断（凭据/设备/法务/第三方），`UNVERIFIED` 表示无当前版本证据。
- 追踪状态（§7）：`PLANNED / IN_PROGRESS / GATE_BLOCKED / VERIFIED / DONE / DEFERRED_APPROVED`。
- **一个 CM = 一个独立会话 = 一个批次内工作包**；仅当多个 CM 共享同一对象生命周期与同一真相源且无法分别准出时允许合批，且每个 CM 仍须独立给出 Exit 结论。

### 0.3 拆分红线（违反即拆项）

- 一个条目跨越多个无共同 owner 的聚合。
- 同时包含平台建设与产品页面大重构。
- 外部 provider 接入与上层业务旅程可独立验证。
- 页面数量或状态机过大导致一个会话无法完整实施。
- 共享 metadata 需先冻结后才能消费。

### 0.4 共享真相源 owner 与串行合流

以下共享面在每个批次内**只允许一个 owner 会话**写入；非 owner 会话只提交变更请求与 patch 摘要，由 owner 统一 `metadata → verify → codegen` 后合流。拓扑/registry 类 YAML 必须原子写并先解析（防 R-HSE04 重演）。

| 共享面 | 路径 | owner 归属 |
|---|---|---|
| 页面对象合同 | `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml` | 当批含页面新增/绑定变更的首个 UX 类 CM 会话 |
| route/surface/event catalog | `_shared/ui_surfaces.yaml`、`_shared/app_routes.yaml`、`ops/event_record/event_catalog.yaml` | CM-003（B01 冻结后按域申请） |
| Journey/Scenario 与跨域 acceptance | `specs/feature-tree/journey_scenario_registry.yaml`、跨域 `acceptance.yaml` | CM-002 |
| ContractGraph/codegen manifest | `quwoquan_service/contracts/metadata/**` + generated manifest | 各域 CM 按对象 owner 串行；跨域冲突升级总控 |
| 风险账本 | `docs/outstanding_risks_backlog.md` | 总控会话（新增须用户确认） |
| 环境拓扑 | `quwoquan_ops/environments/*.yaml` | 运维轨道（本清单只读） |
| Prometheus/Alertmanager | `quwoquan_ops/observability/monitoring/**` | CM-003 定义目录规则；实例告警随域 CM 提交给运维轨 owner |
| generated 文件 | 全部 `DO NOT EDIT` 产物 | 禁止手改；只经 codegen |

### 0.5 与并行轨道去重

| 轨道 | 该轨道负责 | 本清单负责 | 禁止 |
|---|---|---|---|
| 运维运营平台（R-OPS-* 15 项残余） | SLS/Prometheus/Alertmanager 部署、发布 SLO readback、CI/CD 供应链、配置面 | 各能力的采集接线、指标定义、四环境证据消费 | 不另建日志/发布平台 |
| 推荐平台长期轨（R-IX01～04） | 深排模型、per-candidate 物化、精品池召回 | App 消费面、解释、行为回流对账（CM-064） | 不复制模型/分桶真相源 |
| 数据生产轨（R-CS01/02/03/09、R-HSE06 源侧） | 内容生产、版权、省级覆盖发布 | 导入后的服务/App/测试消费证据 | 不在 CM 内重做数据生产 |
| 业务对象 12 批（B0～B11 已收口部分） | 已完成对象 Facet/metric/告警 | 未闭合残余以 R-OBJ-* 映射进 CM | 不重建已收口 Facet |

## 1. 当前整体结论（任务 §6.1）

**结论：`NOT_READY`。**

判定依据不是静态矩阵（页面横向矩阵 87 行、`verify_test_specs` 冻结时实测绿；`verify_test_coverage_map` 与页面对象合同门在冻结校验窗口因并行会话未提交改动暂红，见 §8 门禁快照），而是以下**可定位证据**的商用阻断。任一类未关闭前不得宣称商用准出：

| # | 阻断类别 | 关键证据 | 承接 CM |
|---|---|---|---|
| 1 | 商用登录凭据与第三方登录 | R-AUTH-001 未注入；`ext.auth.wechat` 域直连 violation、Apple 无验签、one-tap 未接线（external registry §7.2/7.5） | CM-007 |
| 2 | 法务合规 | R-LEGAL-001：legal-static 主体/地址/客服/ICP 占位，`legal-review-required` | CM-018 |
| 3 | 内容安全缺失 | 发布即 approved，无机审/频控/审核闭环（text G5，`post_publication.go:102-103`） | CM-025 |
| 4 | UGC 视频链路物理断裂 | GATE-V1：转码 worker 不存在，`RecordMediaProcessingResult` 零生产调用方；R-CS08 四环境 0 通过 | CM-027/028/029 |
| 5 | 搜索可用性与容量 | WP-I：beta/gamma 无可检索种子；R-S06-S-1/2 真集群容量与写时长稳未准出 | CM-030/032 |
| 6 | 入站深链能力缺失 | 无 DeepLinkResolver/PendingInboundTarget；Android manifest 无 VIEW/BROWSABLE；`external-inbound-deeplink-return` acceptance 全 pending | CM-011 |
| 7 | 交集差异化未闭环 | R-IX09：27 active kind 中 18 个无源；R-IX10 北极星观测缺位；约伴 C0 无候选/请求状态机与安全门（R-PLAZA-001）；首次兴趣先验无承载且 Story 规格自相矛盾 | CM-057～062 |
| 8 | 通知触达断链 | R-OBJ-003：push provider 全 planned/mock（`ext.push.*`），notification `NoopDeliveryAdapter` | CM-047/048 |
| 9 | RTC 离线来电与环境证据 | R-RTC01 离线 Push 全链未实现；R-CLOUD01 剩 Gamma/prod 运行制品；R-CLOUD09 无固定 digest/SBOM | CM-043～046 |
| 10 | 真实遥测与发布门 | R-TELEMETRY-001 真实 SLS 零证据；R-OPS-SLO-READBACK/OBS-STACK 生产演练未闭合（运维轨） | CM-067（消费依赖） |
| 11 | 精确坐标隐私 | `integration/location/fields.yaml` 精确经纬 PUBLIC+log allow、`log_kv_policy.yaml` plain、`location_service.go` trace 明文；与 `content/post/privacy.yaml` city-level 冲突 | CM-051 |
| 12 | 测试与环境证据缺口 | App `api_integration` 全仓仅 9 文件；四环境发布证据未兑现（text G4）；R-CLOUD06 存在性 UAT 残余；acceptance 幽灵路径已由 CM-002 关闭 | CM-005/029/065/066 |
| 13 | 助手运行时假实现 | R-ASSIST-001～004：会话端云断链、工具假实现/硬编码 grounding、日志泄敏、非 token 级流式 | CM-053 |
| 14 | 数据主体权利缺失 | R-UPROF-002：无注销/封禁跨域级联；导出/撤回同意无对象与页面 | CM-015 |

## 2. 覆盖对账表（任务 §6.2）

> 口径：`覆盖`= 有 CM 承接（整改或验证）；`待核验`= 归属验证型 CM、尚无当前版本证据；`阻断`= 承接 CM 依赖外部凭据/设备/法务/轨道。规划自身无遗漏由 2.1～2.9 反查列保证。

### 2.1 Journey（11 条，全覆盖）

| Journey | 状态 | 承接 CM（反查） |
|---|---|---|
| identity-entry-and-continuation | 阻断（凭据） | CM-007/008/009/010/013/018 |
| cold-start-safe-handoff | 待核验 | CM-010/012（+CM-003 ANR/TTI 口径） |
| content-discovery-to-consumption | 覆盖 | CM-019/020/021/022/064 |
| cross-domain-search | 阻断（种子/容量） | CM-030/031/032/033 |
| app-root-navigation-safety | 待核验（既有证据复归） | CM-066（回归）；边缘手势现有 local/UAT 维持 |
| message-social-connection | 覆盖 | CM-034/035/036（+CM-045/046 实时行动、CM-048 通知维度） |
| circle-entity-group-collaboration | 覆盖 | CM-037/038/039/040 |
| assistant-omnipresent-private-assistant | 覆盖 | CM-053/054/055 |
| external-acquisition-and-deeplink | 阻断（能力缺失） | CM-011/049/050 |
| intersection-action-to-companionship | 阻断（差异化主战场） | CM-041/057/058/059/060/061/062/063（+CM-014 联系人标签） |
| profile-private-activity-history | 覆盖 | CM-013/014（互动历史验证并入 CM-014） |

### 2.2 Scenario（24 条，全覆盖）

| Scenario | 承接 CM | Scenario | 承接 CM |
|---|---|---|---|
| identity-entry-persona-continuation | CM-007/009/010 | assistant-context-grounded-answering | CM-053/055 |
| cold-start-safe-handoff-and-telemetry | CM-012 | assistant-chat-topic-understanding | CM-053 |
| global-route-edge-pop-contract | CM-066 | assistant-search-handoff-and-grounding | CM-031/053 |
| content-feed-open-detail | CM-019/021 | assistant-proactive-subscription-delivery | CM-047/053 |
| content-comment-interaction（2026-07-20 新增） | CM-022 | immersive-media-edge-swipe-back | CM-066 |
| content-detail-profile-handoff | CM-019 | home-edge-swipe-exit-guard | CM-066 |
| profile-share-interaction-history | CM-014 | outbound-object-share-distribution | CM-049 |
| global-search-query-and-filter | CM-030/031 | external-inbound-deeplink-return | CM-011 |
| message-direct-and-greeting-upgrade | CM-014/034/035 | public-web-seo-install-conversion | CM-050 |
| message-group-entry-matrix | CM-036/037 | intersection-action-deepening-on-object | CM-057/058 |
| circle-entity-group-handoff | CM-037/040 | companionship-and-nearby-connection | CM-059（附近/LBS 维持 deferred） |
| message-assistant-in-conversation | CM-053 | contact-label-driven-connection | CM-014 |

**registry 缺口（本轮确认仍在）**：内容创作/发布无 Journey/Scenario（text G3、photo GATE-P1）→ CM-023 承接登记；RTC 实时通话无独立 Scenario → CM-046 承接裁决（补绑定或显式并入 message Scenario）。

### 2.3 业务对象域（14 canonical + platform 控制面）

| 域 | 承接 CM | 域 | 承接 CM |
|---|---|---|---|
| user | CM-007/008/009/013/014/015/016 | ops | CM-003/012/024 |
| content | CM-019～029/041 | realtime | CM-043/044/045 |
| entity | CM-040/041/042 | recommendation | CM-057/060/064 |
| messages(chat) | CM-034/035/036 | rtc | CM-043/045/046 |
| social(circle) | CM-037/038/039 | search | CM-030/031/032/033 |
| assistant | CM-053/054/055 | tag | CM-062/063 |
| integration | CM-051/052（+CM-007/047 provider） | platform 控制面 | 运维轨道（CM-067 消费） |
| notification | CM-047/048 | — | — |

`metadata/chat`、`metadata/circle` 两个 generated/历史出口目录治理分别并入 CM-034、CM-039。

### 2.4 Go 服务（14）与运行依赖

| 服务 | 承接 CM | 服务 | 承接 CM |
|---|---|---|---|
| user-service | CM-007/013/014/015 | notification-service | CM-047/048（内层测试 CM-005） |
| chat-service | CM-034/035/036 | platform-ops-service | 运维轨道 |
| circle-service | CM-037/038/039 | product-ops-service | CM-003/012/024/049 |
| content-service | CM-019～029/041 | realtime-gateway | CM-044（api_integration 目录 CM-005） |
| entity-service | CM-040/041/042 | rtc-service | CM-043/046（local_contract 目录 CM-005） |
| integration-service | CM-051/052 | search-service | CM-030/031/032 |
| assistant-service | CM-053/054/055 | tag-service | CM-062/063（local_contract 目录 CM-005） |

运行依赖：recommendation-service/rec-model-service → CM-064 + 推荐轨；LiveKit/coturn → CM-043/044/046；legal-static → CM-018；seed-box → CM-066（环境证据）。

### 2.5 页面与挂靠面（横向矩阵 87 行 + 非占行承载面）

| 页面组（行数） | 承接 CM | 页面组（行数） | 承接 CM |
|---|---|---|---|
| app/shell（7） | CM-011/012/050 | rtc（5） | CM-045/046 |
| welcome（1） | CM-010 | search（3） | CM-030/031/033 |
| discovery/content 消费（3） | CM-019/020/021 | settings（10） | CM-015/016/017 |
| assistant（4） | CM-053/054 | interest_match（1） | CM-058 |
| chat（9） | CM-034/035/036 | user（18） | CM-008/009/013/014/022(评论页) |
| circle（6） | CM-037/038/039 | components 媒体/模板（6） | CM-027/028（媒体）/CM-016（模板消费） |
| content/entry（6） | CM-023～028 | entity（7） | CM-040/041/042 |
| intersection（1） | CM-058 | — | — |

非占行挂靠面（必须随父 CM 验收，不得漏审）：创作入口 sheet/动作面板→CM-023；发布确认 sheet 与 `PublishLocationSearchPage`→CM-023/026；评论 viewer modal/分屏/detail surface/input overlay→CM-022；主页口碑 sheet→CM-040；资料提案 review sheet→CM-013；assistant half sheet/history/feedback→CM-053/054；群成员 sheet→CM-036；分享/转发面板→CM-049；相机/预览壳→CM-027/028。

### 2.6 外部依赖（external registry 分组，全登记）

| 依赖组 | registry 状态 | 承接 CM |
|---|---|---|
| 地图 POI（baidu/amap） | production/compliant | CM-051（隐私）/CM-052（审计） |
| SMS OTP（mock/aliyun/tencent） | mock/planned | CM-007（登录链）+ 运维轨凭据 |
| Push（apns/fcm/vendor/mock） | planned/mock | CM-047 |
| 运营商 one-tap | planned（双端 isAvailable=false） | CM-007 |
| 社交 OAuth（wechat 直连/alipay/qq/apple） | violation/none | CM-007 |
| webhook 投递 | planned | CM-052 |
| LLM/搜索/天气/金融（assistant 直连） | production/violation | CM-055 |
| Embedding | planned/violation | CM-055（登记）+ 推荐轨 |
| 对象存储 S3/OSS | production/waived | CM-027（VOD/转码消费） |
| LiveKit/coturn | production/waived | CM-043/044/046 |
| ES/Mongo/PG/Redis/MinIO | production/waived | 各域 CM 集成测试消费 |
| 数据管线公开源 | production/waived | 数据轨道 |
| 客户端平台能力（geolocator/callkit/one-tap channel） | production/planned/waived | CM-045/046（callkit）、CM-007（one-tap）、CM-051（定位） |
| 登记表自动校验 | 缺失 | CM-056 |

### 2.7 横切 H1/H2

| 横切 | 承接 CM |
|---|---|
| H1 观测接线（ANR/TTI/恢复页/黄金指标规则/对象 metric 覆盖门 R-OBJ-001） | CM-003（冻结）+ 各域 CM D5 消费 + CM-024（发布漏斗实例） |
| H2 测试治理（acceptance 诚信/统一 runner/目录缺失/旧口径） | CM-001/002/005/006 + CM-065/066（执行面） |

### 2.8 专项规划工作包 → CM 吸收对照（无遗漏）

| 专项 | 工作包 | 吸收 CM |
|---|---|---|
| 搜索 | WP-H / WP-I / WP-J / WP-K / WP-L / WP-E+G | CM-030 / CM-030 / CM-031 / CM-031 / CM-032 / CM-032 |
| 交集 | WP-IX-0 / IX-1 / IX-2 / IX-3 / IX-4 / IX-5 | CM-057 / CM-057 / CM-058 / CM-059 / CM-060 / CM-061 |
| 发文字 | 批次 A / B / C / D / E / F | CM-023 / CM-023+002 / CM-024 / CM-025 / CM-026 / CM-029 |
| 发图 | 批次 A / B / C / D / E / F（共享底座随文字） | CM-023 / CM-029 / CM-024 / CM-025 / CM-026 / CM-029 |
| 发视频 | V-A / V-B / V-C / V-D / V-E / V-F | CM-027 / CM-028 / CM-028 / CM-029 / CM-023～026 分型 / CM-057（kind 增量） |
| 推荐 | W1～W13 状态附记 + 长期轨 | CM-064（消费对账）+ 推荐轨道（R-IX01～04 依赖登记） |

### 2.9 开放 R-*（75 项）→ CM/轨道映射（全量）

| R-* | 承接 | R-* | 承接 |
|---|---|---|---|
| R-LEGAL-001 | CM-018 | R-CLOUD01 | CM-043 |
| R-AUTH-001 | CM-007 | R-RTC01 | CM-045 |
| R-PLAZA-001 | CM-059 | R-RTC02 | CM-046 |
| R-S06-S-1 / S-2 | CM-032 | R-CLOUD02 | CM-054 |
| R-IX01/02/03/04 | 推荐轨（CM-064 登记依赖） | R-CLOUD04 | codegen 轨（CM-004 登记依赖） |
| R-IX05 | CM-042 | R-CLOUD05 | CM-067 前置（各域 CM 分摊 Mock 清理） |
| R-IX08 | CM-057/061 | R-CLOUD06 | CM-065/066 |
| R-IX09 | CM-057 | R-CLOUD09 | CM-044 |
| R-IX10 | CM-060 | R-OPS-ACCEPTANCE-PHANTOM | CM-002 |
| R-ID02 | CM-057 | R-OPS-STARTUP-IDEMPOTENCY | CM-012 |
| R-ID09 | CM-057（D4） | 其余 R-OPS-*（15 项） | 运维轨道（CM-067 消费其证据） |
| R-ID10 | CM-058 | R-OBJ-001 | CM-003 + 各域 D5 |
| R-CS01/02/03/09 | 数据轨道 | R-OBJ-002 | CM-024 + 各域 D5 |
| R-CS05 | CM-027 | R-OBJ-003 | CM-047/048 |
| R-CS08 | CM-027/029 | R-OBJ-004 | CM-064 |
| R-CS10 | CM-026 | R-OBJ-006 | CM-013 |
| R-CS11 | CM-029 | R-OBJ-007 | CM-020 |
| R-CR04 | CM-026 | R-ASSIST-001～004 | CM-053 |
| R-TELEMETRY-001 | CM-067 依赖（运维轨主责） | R-UPROF-001 | CM-014 |
| R-TST04 | CM-006 | R-UPROF-002 | CM-015 |
| R-TST05 | CM-005 | R-UPROF-003 | CM-013 |
| R-TST07 | CM-006 | R-UPROF-004 | CM-066 |
| R-COMMERCE-001 | DEFERRED_APPROVED（依 backlog 待 R-LEGAL-001 与立项，不入当前商用范围） | R-WELCOME-001 | CM-010 |
| R-HSE02 | CM-042 | R-CIRCLE-001 | CM-039 |
| R-HSE03/04 | 运维轨道 | R-CIRCLE-002 | CM-037 |
| R-HSE06/07 | CM-042/066 + 数据轨 | R-CIRCLE-003 | CM-039/064 |

## 3. 功能与能力主清单摘要（任务 §6.3）

> 字段口径：`成熟度`=D1～D6 逐维状态（P=PASS、A=PARTIAL、B=BLOCKED、U=UNVERIFIED，按 D1→D6 顺序）+ 关键页面 P 级；`决策`为该项主页面决策；详情、依据与完整验收见 §4 对应卡。所有"当前证据"均可反查矩阵/专项文档/backlog。

### 3.1 B01 横切契约冻结

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-001 RTC 分层 Story 边界与证据收敛复核 [验证型] | 测试准出 | 横切；验收诚信 | feature-tree realtime-call 节点 | 无页面 | 四个产品 Story 与四个 `parent--contract` Story 分工明确；`--` 是全仓扁平化命名而非旧副本；三项特性树门禁实测绿 | D2:P D6:P 其余— | 八个 L3 Story 各有独立价值/GWT、引用与 tree_index 单轨 | 保留 | 逐对核验边界、GWT 与引用；禁止误删合同 Story | verify_test_specs/feature_tree_refactor/acceptance_standard 绿 | RTC 功能缺口归 CM-043～046 | COMMERCIAL_MUST / B01 | VERIFIED |
| CM-002 acceptance planned/recorded 全量对账 | 测试准出 | 横切；验收诚信 | 全部 acceptance.yaml | 无页面 | 76 条不存在的 planned 文件引用已摘除；hard gate、合同红测与 coverage map 全绿 | D6:P | planned 文件真实存在、recorded canonical 且可定位 | 精修 | 已完成结构化扫描、硬门与风险账本回写 | verify_test_specs+coverage map+合同测试绿 | 后续真实测试随各域 CM 登记 | GATE_BLOCK / B01 | VERIFIED |
| CM-003 H1 观测事件与指标目录冻结 | 平台横切 | 横切；D5 底座 | ops event/runtime catalog | 无页面 | ANR 无采集、通用 TTI 无合同、恢复页无 outcome、黄金指标无登记规则 | D5:A | ANR/TTI/恢复页事件 metadata-first；≤3 黄金指标登记规则；对象 metric 覆盖门 | 新增 | catalog 扩展→codegen→App 采集接线→覆盖门脚本 | local_contract 事件契约+门禁脚本绿 | 与运维轨 SLS 轨去重 | GATE_BLOCK / B01 | PLANNED / R-OBJ-001 |
| CM-004 共享真相源 owner 与合流机制 | 平台横切 | 横切；多会话并行安全 | §0.4 八共享面 | 无页面 | R-HSE04 曾发生并发写坏；无显式 owner 表 | D2:A | 每批次 owner 唯一、原子写、变更请求流程 | 新增 | owner 表落地+拓扑 YAML 原子写检查 | 并行批次零真相源冲突 | 全部批次 | COMMERCIAL_MUST / B01 | PLANNED / R-CLOUD04 依赖登记 |
| CM-005 api_integration 统一入口与缺失目录 | 测试准出 | 横切；D6 底座 | 测试执行入口/服务测试目录 | 无页面 | R-TST05 凭据注入缺口；circle/rtc/tag 缺 local_contract、gateway 缺 api_integration、notification 内层零测试 | D6:A | 缺凭据 fail-fast；目录以真实测试补齐 | 新增 | preflight 收口+按对象补真实测试 | make test-api-integration 可复验+新目录测试绿 | stackctl/CI secret（运维轨） | COMMERCIAL_MUST / B01 | PLANNED / R-TST05 |
| CM-006 测试旧口径校准与 legacy burn-down | 测试准出 | 横切；口径单轨 | 测试规范/命名 | 无页面 | R-TST04/07：旧 T/L 命名、已删 allowlist 的陈旧叙述 | D6:A | backlog/spec 与磁盘一致；旧命名棘轮递减 | 精修 | 重扫→修文档→棘轮门 | 扫描零新增+backlog 回写 | CM-002 | COMMERCIAL_MUST / B01 | PLANNED / R-TST04/07 |

### 3.2 B02 身份、壳与对象基座

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-007 商用登录凭据与第三方 provider 收口 | 外部集成 | identity-entry | AuthenticationChallenge/AccountSession/CredentialBinding；user-service+integration | login_page 及授权 sheet | R-AUTH-001 凭据未注入；wechat 直连 violation、apple 无验签、one-tap 双端不可用、SMS 仅 mock | D1:B D2:A D4:U D6:B | 真实 provider 经统一治理出口；四环境登录准出 | 精修 | 凭据注入→provider adapter 归置→真机矩阵 | 真机四 provider UAT+越权负例 | 凭据/SDK 授权（外部） | GATE_BLOCK / B02 | GATE_BLOCKED / R-AUTH-001 |
| CM-008 账号安全与凭证管理准出 [验证型] | 测试准出 | identity-entry | CredentialBinding/AccountSession | settings_account_security_page | 页面已实现（矩阵 settings 组绿）；最后凭证保护/多设备撤销无当前证据 | D1:U D6:U | 绑定/解绑/会话撤销全状态可恢复 | 保留 | 真机 UAT+并发负例 | user_acceptance+api_integration | CM-007 | COMMERCIAL_MUST / B02 | PLANNED |
| CM-009 Persona 对象绑定与生命周期收口 | 业务对象 | identity-entry | Persona（user.persona 聚合） | persona_management_page | page contract 错绑 user_account；退役/并发/回流未证 | D2:A D1:A | 绑定 Persona+摘要 Slice；全生命周期承载 | 适度重构 | 修 contract→拆 961 行页→补终态 | page-object gate+journey UAT | CM-004（contract owner） | COMMERCIAL_MUST / B02 | PLANNED |
| CM-010 Welcome 身份四态规格裁决 | 产品功能 | cold-start+identity | StartupAttempt/onboarding 规格 | welcome_screen | onboarding 规格要求四态入口 vs 实现为 objectless 品牌页；R-WELCOME-001 字体降级 | D1:A D3:A | 规格与实现二选一统一；字体授权落定 | 精修 | 规格裁决→registry/acceptance 同步 | 启动 UAT+规格一致性 | M1/M2 所有权 | COMMERCIAL_MUST / B02 | PLANNED / R-WELCOME-001 |
| CM-011 入站深链能力落地 | 产品功能 | external-acquisition | LinkTemplate/PendingInboundTarget | 原生注册+Resolver+恢复面 | 无 Resolver/原生 VIEW 注册；acceptance 全 pending | D1:B D6:B（能力 P0） | 冷/热/延迟深链→canonical route→安全 fallback | 新增 | Resolver+Android/iOS 注册+pending replay+TTL | 三端深链 UAT+失效降级 | link_templates 真相源；CM-050 协同 | GATE_BLOCK / B02 | PLANNED |
| CM-012 启动幂等修复与启动遥测准出 [验证型] | 平台横切 | cold-start | EventRecord(startup)/StartupAttempt | shell/welcome/恢复面 | R-OPS-STARTUP-IDEMPOTENCY 同 proof 异批丢事实；11 阶段遥测无真实 SLS 证据 | D1:A D5:A D6:U | 批次 digest 幂等；3s/6s 真机证据 | 精修 | 幂等键修复→真机 20 次矩阵 | api_integration 重放+设备报告 | R-TELEMETRY-001（SLS 侧） | COMMERCIAL_MUST / B02 | PLANNED |
| CM-013 身份/资料聚合 Facet 对象化收口 | 业务对象 | identity+profile-history | UserAccount/Persona/Profile 投影；user-service | 资料编辑/proposal sheet | R-OBJ-006：Auth 18 方法、~79 处 forPage、78 条手写路由；R-UPROF-003 计数对账 | D2:A | ≤10 方法 Facet、generated dispatch、forPage 清零 | 适度重构 | 拆 Facet→切 dispatch→计数对账策略 | ContractGraph+PG/Mongo 集成 | CM-004；user-service owner | COMMERCIAL_MUST / B02 | PLANNED / R-OBJ-006 |
| CM-014 关系四层与联系人旅程收口 | 产品功能 | message-social+contact-label | PersonaRelationship/SubjectFollow/GreetingRequest/ContactDiscovery | profile_stats/blocked/add_contact 五页/greeting | R-UPROF-001 拉黑服务端强制缺失；互动历史 mine-only 已实现未准出 | D1:A D2:A D6:U | 拉黑服务端过滤；四层单轨；多入口合并回流 | 精修 | 服务端 enforcement→联系人旅程 UAT | 越权负例+journey UAT | CM-013 | GATE_BLOCK / B02 | PLANNED / R-UPROF-001 |
| CM-015 数据主体权利对象与页面 | 产品功能 | identity/settings | 注销/导出/撤回 Consent 新对象；user-service | settings 新增权利入口 | R-UPROF-002 无跨域级联；无对象/页面/终态 | D1:B D2:B（P0） | 注销冷静期/导出/撤回全状态机+跨域级联 | 新增 | metadata 对象→级联 saga→页面 | 三层+级联 api_integration | 法务口径（CM-018） | GATE_BLOCK / B02 | PLANNED / R-UPROF-002 |
| CM-016 设置对象页准出 [验证型] | 测试准出 | settings | UserSettings 及 View 投影 | notifications/privacy/calls/dark_mode/blocked_keywords/my_reports 六页 | 页面+typed Facet 已实现（矩阵绿）；真机/CAS 冲突/乐观回滚无当前证据 | D1:U D6:U | 六页全状态真机准出 | 保留 | UAT+CAS 并发负例 | user_acceptance+api_integration | — | COMMERCIAL_MUST / B02 | PLANNED |
| CM-017 权限预留页裁决 | UX 重构 | settings | 平台权限 profile | settings_permissions_page | 只读"预留"空壳（矩阵 P2/P3 为 —） | D1:B D3:B（P1） | 真实权限状态+跳系统设置，或删除入口 | 完全重构或删除 | 裁决→实现或下线 | 页面 UAT 或删除后矩阵同步 | AppPermissionCoordinator | COMMERCIAL_MUST / B02 | PLANNED |
| CM-018 法务条款与 legal-static 商用发布 | 外部集成 | identity/settings | LegalStaticRelease | about/legal_document_page | R-LEGAL-001：主体/地址/客服/ICP 占位、legal-review-required | D1:B（外部） | 审签条款+版本一致+prod 发布门绿 | 精修 | 法务输入→manifest→发布验证 | legal-static 发布门+consent 一致 UAT | 法务（外部） | GATE_BLOCK / B02 | GATE_BLOCKED / R-LEGAL-001 |

### 3.3 B03 核心旅程

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-019 消费面路由/surface/SLO 修正 | UX 重构 | content-discovery | Post/Feed 投影；content-service | home/unified_viewer/work_browser | viewer 硬编码 `/user/$userId`；homeFeed surface 缺 GetFeed；Feed SLO 200/500 双口径 | D2:A D4:A | 路由/surface 单轨；SLO 冻结一个数 | 精修 | 修路由→surface 登记→SLO 冻结 | page-object gate+metadata verify | CM-004 | COMMERCIAL_MUST / B03 | PLANNED |
| CM-020 内容主链超千行结构治理 | UX 重构 | content-discovery | 阅读器/创作 provider | book_deck/works_viewer/editor provider | R-OBJ-007：4885/2361 行等 12 文件超红线 | D3:A（技术债） | <1000 行/职责拆分；pageflip 单几何真相源 | 适度重构 | 按 BACK 主线拆分+visual 证据 | pageflip visual+行数棘轮 | pageflip 军规 | COMMERCIAL_MUST / B03 | PLANNED / R-OBJ-007 |
| CM-021 内容删除/封禁传播全链验证 | 业务对象 | content-discovery | Post tombstone/投影 | feed/viewer/search 消费面 | 删除/私密/封禁跨 feed/search/通知传播无 E2E 证据 | D1:U D6:U | 失效对象全消费面确定性终态 | 保留 | 传播矩阵测试 | api_integration 传播断言+UAT | CM-030（search 侧） | GATE_BLOCK / B03 | PLANNED |
| CM-022 评论治理与互动收口 | 产品功能 | content-comment-interaction | Comment/ContentReaction/Report | 评论 sheet 族+profile_comments_page | 服务端 V3 成熟；举报/审核入口缺、L2 规格旧叙述、页面 P2 | D1:A D2:A D3:A | 举报/审核反馈闭环；评论主流程≥P4 | 适度重构 | Report 入口→moderation 反馈→页面重构→规格单轨 | 三层+moderator UAT | CM-025（审核方向） | COMMERCIAL_MUST / B03 | PLANNED |
| CM-023 创作 Journey 登记与发布回流 | 产品功能 | 创作（新增 registry） | Post/PublishIntent/LocalDraft | create/编辑器/确认 sheet | text G1 成功仅 Toast、G3 无 Journey、G7 分型不可见、N10-12 | D1:A D3:A（P2） | 写→发→见回流闭环；registry 登记 | 适度重构 | text 批次 A+B 全量 | roundtrip UAT×3 类型+registry 绿 | CM-002/004 | GATE_BLOCK / B03 | PLANNED |
| CM-024 发布漏斗观测接线 | 平台横切 | 创作 | 发布漏斗事件/黄金指标 | 创作链埋点 | text G2：漏斗零采集（云侧 400 拒） | D5:B | 三黄金指标+referralSource 贯通 | 精修 | text/photo 批次 C（依赖 CM-003 目录） | 采集→SLS/Prom→大盘回放 | CM-003 | COMMERCIAL_MUST / B03 | PLANNED / R-OBJ-002 |
| CM-025 内容安全方向裁定与实装 | 产品功能 | 创作/治理 | PostModerationCase/频控 | 发布链+作者通知 | text G5：发布即 approved；`content_too_long`/`rate_limited` 闲置 | D1:B（合规） | 先审后发或机审+拦截（用户裁定）+作者闭环 | 新增 | 裁定→状态机激活→频控→通知 | 审核链三层+合规检查 | **用户裁定方向**；CM-047 | GATE_BLOCK / B03 | PLANNED |
| CM-026 发布契约与结构治理 | 业务对象 | 创作 | PostStatus/media 上限/location 分层 | 发布链 | text G6 枚举漂移、G8 tag 断链、R-CS10 图文退化、R-CR04 | D2:A | 枚举=可达状态；tag 创作入口；location 迁 cloud 层 | 精修 | text/photo 批次 E | metadata verify+死分支清零 | CM-063（tag） | COMMERCIAL_MUST / B03 | PLANNED / R-CS10、R-CR04 |
| CM-027 视频转码管线落地 | 外部集成 | 创作（视频） | MediaAsset/ProcessingResult/media outbox | 云侧 worker（无页面） | GATE-V1 worker 不存在；GATE-V6 特性树空壳；GATE-V9 adaptive 死声明 | D1:B D2:B | 上传→转码→ready→发布全链真实 | 新增 | V-A：worker+relay+指标+特性树回填 | testcontainers+ffmpeg E2E | 对象存储/VOD（R-CS05） | GATE_BLOCK / B03 | PLANNED / R-CS08 |
| CM-028 视频上传硬化与 Android 能力位 | 产品功能 | 创作（视频） | MediaUploadSession | create video flow/video_editor | GATE-V2 Android 导出缺失、V3 内存/无分片、V7 处理中态缺失 | D1:A D4:B | 流式/分片/续传/进度+能力位降级+处理中语义 | 适度重构 | V-B+V-C | 大文件弱网 UAT+能力位测试 | CM-027 | GATE_BLOCK / B03 | PLANNED |
| CM-029 发布四环境证据兑现 | 测试准出 | 创作 | 发布链全对象 | — | text G4/GATE-V4/V5/V8：`CONTENT_MEDIA_GAMMA_UAT` blocked、gamma 无发布旅程、幽灵路径 | D6:B | 三类型发布 alpha→gamma patrol→prod 探针 | 保留 | photo F+V-D | 四环境运行制品+翻牌 | CM-023/027/028；R-CS11 | GATE_BLOCK / B03 | PLANNED / R-CS08/11 |
| CM-030 搜索可用性与环境种子 | 产品功能 | cross-domain-search | SearchQuery/Index/seed | global_search/network_results | WP-H 残余（EnsureIndex 语义、recent 指标、手写路由、10 静默 catch）；WP-I beta/gamma 零种子 | D1:B D6:A | 搜什么都有；工程债清零 | 精修 | WP-H+WP-I | gamma 非空断言+beta 人工 | 数据轨种子；R-S09 候选登记 | GATE_BLOCK / B03 | PLANNED |
| CM-031 搜索交集 attach 与对象完备 | 产品功能 | cross-domain-search | 交集 attach/user 承载/失效反馈 | network_results/landing | WP-J 死字段（connectionState 恒空）；WP-K user/tag 承载缺 | D1:A D3:A | 交集 Tab 真数据；对象完备；≥P4 | 适度重构 | WP-J+WP-K | 双态交集 UAT+对象召回断言 | CM-057（交集读模型）；R-S08 候选 | DIFFERENTIATOR / B03 | PLANNED |
| CM-032 搜索观测与发布准出 | 测试准出 | cross-domain-search | search 专有事件/容量 | — | WP-L 无事件目录；R-S06-S-1/2 真集群未准出；App api_integration=0 | D5:A D6:B | 黄金三指标+真集群 measured+App Remote 证据 | 保留 | WP-L+WP-E/G | 容量报告+api_integration 绿 | CM-003；真集群资源 | GATE_BLOCK / B03 | GATE_BLOCKED / R-S06-S-1/2 |
| CM-033 location.place 对象裁决与落地页重构 | 业务对象 | cross-domain-search | location.place（待裁决） | location_place_landing_page | 仅 route-extra 承载，无 canonical 对象/resolve；页面 P1 | D2:B D1:A | 正式对象+详情 resolve，或合并 Homepage | 完全重构 | 裁决→对象/合并→页面 | resolve API+失效态 UAT | CM-042（Homepage 提升） | COMMERCIAL_MUST / B03 | PLANNED |
| CM-034 消息对象契约与页面绑定补齐 | 业务对象 | message-social | Membership/Message/UserState errors+绑定 | chat 9 页 | 3 对象无 errors.yaml；page contract 只绑 Conversation；`metadata/chat` 出口治理 | D2:A | 对象错误单轨+绑定完整 | 精修 | errors→codegen→contract 补绑 | metadata verify+page-object gate | CM-004 | COMMERCIAL_MUST / B03 | PLANNED |
| CM-035 消息 readiness 翻牌与 Remote 扩面 | 测试准出 | message-social | chat operations readiness | — | operations 默认 blocked；App api_integration 仅 roster parity | D6:A | 发送/回执/成员/打招呼 Remote 证据+翻牌 | 保留 | api_integration 扩面→readiness 回填 | beta Mongo/Redis+gamma realtime | CM-005 | COMMERCIAL_MUST / B03 | PLANNED |
| CM-036 会话/群治理真机与离线准出 [验证型] | 测试准出 | message-social | outbox/gap sync/群命令 | chat_conversation/群治理 4 页 | 实现成熟（B5/B12 收口）；断网/杀进程/并发角色无当前真机证据 | D1:U D4:U | 离线恢复+治理终态真机准出 | 保留 | 设备矩阵 UAT | journey UAT+弱网报告 | CM-043（realtime 环境） | COMMERCIAL_MUST / B03 | PLANNED |
| CM-037 CircleGroup 群单元生命周期承载 | 产品功能 | circle-collaboration | CircleGroup/CircleGroupMembership | circle_detail 群单元 tab+审批面 | 8 个 op 无 UI 消费；R-CIRCLE-002 审批命令缺失 | D1:B（P0 面） | 申请/审批/拒绝/归档全承载 | 新增 | 命令补全→页面承载→chat 绑定 | 状态机三层+群旅程 UAT | CM-034/036 | GATE_BLOCK / B03 | PLANNED / R-CIRCLE-002 |
| CM-038 CircleFile 与 PostPlacement 管理裁决 | 产品功能 | circle-collaboration | CircleFile/CirclePostPlacement | detail storage 区+管理动作 | File 更新/删除/权限旅程未证；pin/feature 无管理员 UI | D1:A | 完整文件旅程+管理动作可达，或显式 deferred | 精修 | 裁决→补 UI→权限负例 | owner/member UAT | CM-037 | COMMERCIAL_MUST / B03 | PLANNED |
| CM-039 圈子契约、性能与推荐闭环 | 业务对象 | circle-collaboration | social 6 对象 errors/hub 聚合/circle 事件 | circles/hub/stats | 6 对象缺 errors；R-CIRCLE-001 hub N+1；R-CIRCLE-003 推荐零消费 | D2:A D4:A | errors 单轨；服务端聚合；circle 事件进推荐 | 精修 | errors→hub 聚合 API→事件消费 | metadata verify+性能预算+推荐对账 | CM-064 | COMMERCIAL_MUST / B03 | PLANNED / R-CIRCLE-001/003 |
| CM-040 主页认领/上报结果回流 | 产品功能 | circle-entity-handoff | HomepageClaimRequest/StatusReport | claim/status_report 页+状态查询面 | 只有提交页；无状态查询/补材料/撤回/结果反馈 | D1:A（P2） | 提交→审核→结果全生命周期承载 | 适度重构 | 查询 op→状态页→通知回流 | 状态机三层+申请人 UAT | CM-048（通知） | COMMERCIAL_MUST / B03 | PLANNED |
| CM-041 想去 wishlist 用户写入口 | 产品功能 | intersection-action | Wishlist intent（对象化裁决） | homepage_detail 想去控件 | `trackWishlistAdd/Remove` 全仓 UI 零调用；seed 冒充用户意图 | D1:B（C0 前置） | 实体页可逆想去+privacyScope 裁决 | 新增 | 对象裁决→UI→行为链→隐私 | 双用户真实意图 E2E | CM-057 消费；隐私裁决 | DIFFERENTIATOR+GATE_BLOCK / B03 | PLANNED |
| CM-042 实体主页真实数据与热重载准出 | 测试准出 | circle-entity-handoff | Homepage 导入/投影 | entity 7 页 | R-HSE02 导入需重启；R-IX05 四主页 populated 未闭；R-HSE06/07 双省/gamma T3 | D1:A D6:B | 热可见+四主页真实数据+双省动态 UAT | 保留 | 热重载→populated 对账→T3 复验 | gamma T3+prod 抽检 | 数据轨 release | GATE_BLOCK / B03 | GATE_BLOCKED / R-HSE02/06/07 |

### 3.4 B04 外部与复合能力

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-043 RTC 可信鉴权环境认证与 ticket 边界 | 外部集成 | message-social（实时） | Connection ticket/auth_ack | websocket transport | R-CLOUD01 剩环境证据；App ticket 裸 http.Client+静默 null | D2:A D6:B | ticket 经 generated client+RuntimeFailure；gamma/prod 运行制品 | 精修 | ticket 改造→gamma cold-start→负例 | 伪造/重放/过期负例+环境报告 | SLS secret（运维轨）；R-AUTH-001 | GATE_BLOCK / B04 | GATE_BLOCKED / R-CLOUD01 |
| CM-044 realtime-gateway provenance 与观测实证 | 外部集成 | 横切实时 | gateway 制品/scrape | — | R-CLOUD09 无固定 digest/SBOM；prometheus.yml 排除 gateway | D5:B | 固定 digest+SBOM+scrape+告警演练 | 精修 | 制品流水线→target 登记→演练 | 供应链证据+告警实证 | 运维轨 Prometheus owner | GATE_BLOCK / B04 | PLANNED / R-CLOUD09 |
| CM-045 三端离线来电矩阵 | 外部集成 | message-social（实时） | CallRinging push policy/DeviceRegistration | incoming_call+系统唤醒 | R-RTC01 全链未实现（PushKit/FCM/Web Push） | D1:B | 后台/锁屏/被杀唤醒或明确降级 | 新增 | provider→注册→平台回调→去重 | 真机三端唤醒 UAT | CM-047（provider 共用） | GATE_BLOCK / B04 | GATE_BLOCKED / R-RTC01 |
| CM-046 RTC 入口矩阵、QoE 与真机媒体准出 | 产品功能 | message-social（实时） | CallSession/Participant | rtc 5 页+入口矩阵 | 入口仅会话页；R-RTC02 QoE 指标/告警缺；Scenario 未绑定 | D1:A D5:B | 入口矩阵+32 人+弱网重连+QoE 黄金指标 | 精修 | 入口→Scenario 裁决→真机矩阵→QoE | 设备双端 UAT+QoE 大盘 | CM-043/044/045 | COMMERCIAL_MUST / B04 | PLANNED / R-RTC02 |
| CM-047 Push 外送 provider 决策与实装 | 外部集成 | 通知触达 | push_delivery/ExternalInteraction | — | R-OBJ-003 deferred：`ext.push.*` 全 planned、Noop adapter | D1:B | APNs/FCM 真实装或经批准延期+站内单轨声明 | 新增 | 凭据→adapter→token 注册→回执 | 真机推送到达+回执审计 | Apple/Google 凭据（外部） | GATE_BLOCK / B04 | GATE_BLOCKED / R-OBJ-003 |
| CM-048 站内信七源闭环准出 [验证型] | 测试准出 | 通知 | Notification/DeliveryJob | chat 通知维度 | 七源→inbox 已收口（B11）；delivery_job 无 errors；失效目标/幂等无当前证据 | D1:U D2:A | 七源幂等+失效解释+errors 补齐 | 保留 | errors→重放负例→UAT | 逐源三层矩阵 | CM-034 | COMMERCIAL_MUST / B04 | PLANNED |
| CM-049 出站分享 MVP | 产品功能 | external-acquisition | OutboundShareFact/share token | 分享面板（挂靠面） | scenario draft；面板/卡片/归因未成体系 | D1:A（P2） | 四对象分享卡+口令/链接+归因事实 | 适度重构 | 渠道 MVP→卡片→token→事实 | 分享→回流归因 E2E | CM-011（回流）；CM-050 | COMMERCIAL_MUST / B04 | PLANNED |
| CM-050 Web 安装转化与公开对象页 | 产品功能 | external-acquisition | public projection/install handoff | web shell/install banner | scenario draft；安装后还原未闭环 | D1:A | SEO 公开页+安装后目标还原 | 适度重构 | 公开投影→banner→还原链 | 未装/已装双态 UAT | CM-011/049 | COMMERCIAL_MUST / B04 | PLANNED |
| CM-051 精确坐标隐私修复 | 平台横切（安全隐私） | 全位置场景 | Location 字段策略/log_kv/trace | 位置选择/搜索/发布链 | fields PUBLIC+log allow、log_kv plain、trace 明文、Post fields/privacy 矛盾 | D2:B（GATE） | 精确输入粗输出；日志/trace/metric 零明文 | 精修 | classification→log_kv→trace 脱敏→扫描门 | 隐私泄漏扫描=0+契约单轨 | **风险登记待用户确认**；CM-004 | GATE_BLOCK / B04 | PLANNED / 新风险候选 |
| CM-052 ExternalInteraction 状态机与死信面 | 业务对象 | 横切集成 | ExternalInteraction/Attempt/DLQ | operator 消费面（Portal/CLI） | aggregate 与 fields 枚举漂移；死信 op 无消费者；webhook planned | D2:A D1:A | 状态机单轨+死信可恢复+webhook 裁决 | 精修 | 枚举对齐→operator 面→恢复演练 | DLQ 恢复 api_integration | 运维轨 Portal | COMMERCIAL_MUST / B04 | PLANNED |
| CM-053 助手运行时可信化 | 产品功能 | assistant-omnipresent | AssistantConversation/Run/工具面 | assistant 4 页+half sheet | R-ASSIST-001 端云断链/无取消；002 工具假实现；003 日志泄敏；004 非 token 流式 | D1:A D2:A D5:B | 会话查询面+真实工具+脱敏+token 级流式 | 适度重构 | 四项分解修复 | 流式/取消/脱敏三层 | LLM 依赖（CM-055） | GATE_BLOCK / B04 | PLANNED / R-ASSIST-001~004 |
| CM-054 助手 consent 负测与页面准出 | 测试准出 | assistant | SkillConsent | management/inline gate | R-CLOUD02 剩 gamma 负测；页面 UAT 已真实化 | D6:A | gamma 撤权/失败关闭负例闭环 | 保留 | gamma 负测→回写 | gamma api_integration | CM-043（gamma 栈） | COMMERCIAL_MUST / B04 | PLANNED / R-CLOUD02 |
| CM-055 助手外部依赖统一治理 | 外部集成 | assistant | MiMo/搜索/天气/金融 provider | — | registry §7.2：五组 violation 直连 | D2:A | 统一治理出口/attempt 审计或显式豁免 | 精修 | Port 归置→审计→registry 回写 | attempt ledger+registry 合规 | CM-052/056 | COMMERCIAL_MUST / B04 | PLANNED |
| CM-056 外部依赖登记自动校验门禁 | 平台横切 | 横切 | external_service_registry.yaml | — | 新厂商域名/SDK 无自动扫描 | D2:A | 未登记依赖 gate 阻断 | 新增 | 扫描脚本→gate 接入 | 门禁负例演示 | CM-004 | COMMERCIAL_MUST / B04 | PLANNED |

### 3.5 B05 交集差异化

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-057 交集真实数据先决与契约名实收口 | 业务对象 | intersection-action | 交集投影/kind registry/凭证链 | 七触点（消费） | R-IX09 18 kind 无源；R-IX08 凭证/smoke；R-ID02 schema；Explain/inbox 三缺陷；R-ID09 读放大 | D2:A D1:B | kind 名实一致（产出/deferred 二选一）；seed 档案+凭证单轨 | 精修 | WP-IX-0+WP-IX-1 | 数据密度对账+契约测试 | CM-041（wishlist 源）；推荐轨 | DIFFERENTIATOR+GATE_BLOCK / B05 | PLANNED / R-IX08/09 |
| CM-058 交集配对主入口完全重构 | UX 重构 | intersection-action | 机会读模型 | interest_match launcher（P1→P5） | 纯导流 launcher；无机会卡/真实信号 | D1:B D3:B | P5 主入口：真实机会+行动 | 完全重构 | WP-IX-2 | 双态 UAT+零伪候选断言 | CM-057 | DIFFERENTIATOR / B05 | PLANNED / R-ID10 |
| CM-059 约伴行动闭环与安全门 | 产品功能 | intersection→companionship | Companion candidate/request（新对象） | 约伴承接+impact 列表页（新增） | 仅 route extra 进普通建群；安全门（login/realName/minor/blocked/rateLimit）不执行 | D1:B（P0） | 候选→请求→接受/拒绝→关系形成+安全门 | 新增 | WP-IX-3 | 双用户 E2E+青少年/拉黑负例 | CM-057；R-PLAZA-001 风控 | DIFFERENTIATOR+GATE_BLOCK / B05 | PLANNED / R-PLAZA-001 |
| CM-060 交集北极星观测与灰度 | 平台横切 | intersection | connection-formed 事件/大盘/kill-switch | — | R-IX10：关系形成不可归因、无大盘、无 kill-switch | D5:B | 北极星+漏斗后两级+kill-switch | 新增 | WP-IX-4 | recording rule+大盘回放+灰度演练 | CM-003/057 | DIFFERENTIATOR / B05 | PLANNED / R-IX10 |
| CM-061 交集三层测试与四环境收口 | 测试准出 | intersection | 交集全链测试 | — | smoke 401 失效；Mock↔Remote 一致性缺口 | D6:A | 事实真实性/隐私/双用户三层齐备 | 保留 | WP-IX-5 | alpha fixture+gamma Remote+设备 | CM-057~059 | DIFFERENTIATOR / B05 | PLANNED |
| CM-062 首次兴趣先验承载 | 产品功能 | 冷启动×交集供给 | 兴趣先验（user profile 先验字段） | 首次进入选择/跳过面（P0 新增） | Story 规格自相矛盾（GWT 要求 vs out-of-scope）；无承载 | D1:B（P0） | 可跳过采集+游客合并+首刷保底 | 新增 | 规格修正→页面→画像写入→首刷对账 | 新用户 UAT+非空率 SLO | CM-063；推荐轨消费 | GATE_BLOCK / B05 | PLANNED |
| CM-063 TagFeedback 消费链与 taxonomy 收口 | 业务对象 | 交集供给 | TagFeedback/TaxonomyRelease | 兴趣编辑（嵌入承载） | feedback 无 publisher/消费者；release 切换/失效 refs 语义未冻结；tag-service 测试缺 | D2:A D6:A | 反馈进推荐；release 生命周期单轨 | 精修 | publisher→消费→失效迁移→测试 | 事件回放+release 切换测试 | CM-005（目录）；CM-026（创作 tag） | COMMERCIAL_MUST / B05 | PLANNED |

### 3.6 B06 全局回归与准出

| Plan ID / 名称 | 类型 | 用户目标 / Journey | 对象与 owner | 页面与入口 | 当前证据与缺口 | 当前成熟度 | 目标规格 | 重构决策 | 工作包 | 验收证据 | 依赖与冲突 | 优先级/批次 | 状态/风险 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-064 推荐消费侧对账与 AB 单轨 | 测试准出 | content-discovery | 推荐消费/行为回流/AB 分桶 | feed/viewer 消费面 | W1-W13 服务端为主；R-OBJ-004 分桶双轨；circle 事件零消费 | D5:A D6:U | 曝光/反馈/归因端云对账；分桶单轨裁决 | 保留 | 消费对账→AB 裁决登记 | Behavior/SLS/Prom 三轨对账 | 推荐轨；CM-039 | COMMERCIAL_MUST / B06 | PLANNED / R-OBJ-004 |
| CM-065 App api_integration 全域扩面 | 测试准出 | 横切 | 各版块 Remote 契约 | — | 全仓 9 文件，集中 assistant；多数版块为零 | D6:B | 每版块≥读/写/结构化失败三断言+Mock parity | 保留 | 按版块补齐（依赖各域 CM 合流） | api_integration 套件绿 | CM-005；各域 CM | GATE_BLOCK / B06 | PLANNED |
| CM-066 gamma-local 全量旅程回归 | 测试准出 | 全部 Journey | — | — | R-UPROF-004 无主页旅程；R-HSE07 T3 未复验；R-CLOUD06 存在性 UAT 残余 | D6:B | 11 Journey patrol+T3 语义+设备矩阵全绿 | 保留 | 补旅程→全量执行→报告归档 | gamma run 报告+acceptance 回填 | B01~B05 完成度 | GATE_BLOCK / B06 | PLANNED |
| CM-067 prod gray canary 与 READY 复评 | 测试准出 | 全部 | — | — | R-TELEMETRY-001 真实 SLS、R-OPS-SLO-READBACK/GRAY-ROLLBACK 未闭合（运维轨） | D5:B D6:B | gray-initial 真实 SLO/告警/回滚+READY 复评 | 保留 | canary→readback→本文 §1 复评回写 | prod runs 证据+复评记录 | 运维轨全部前置 | GATE_BLOCK / B06 | GATE_BLOCKED / R-TELEMETRY-001 |

## 4. 清单项详细卡（任务 §6.4）

> 卡片固定十要素。底料引用矩阵（`matrix §N`= [`functional_module_commercial_maturity_matrix.md`](functional_module_commercial_maturity_matrix.md) 章节）与专项文档章节，不复制大表；"当前证据"均为 2026-07-20 磁盘/门禁实测，推测一律写为"待核验"。黄金指标每项 ≤3 个一级指标。

### 4.1 B01 横切契约冻结

#### CM-001 RTC 分层 Story 边界与证据收敛复核 [验证型]（测试准出 | B01 | COMMERCIAL_MUST）

1. 定位：验收诚信横切；证明 realtime-call 的产品 Story 与合同 Story 是有界拆分而非重复真相源。
2. 当前证据：`one-to-one-call/group-call/call-experience/media-infrastructure` 分别承载用户流程、页面体验与媒体能力；四个 `parent--contract` Story 分别承载生命周期原子性、owned participant、一致 UI 控制与 SFU 发布合同。`--` 命名在全仓 tree_index 中广泛用于把原子合同 Story 扁平化到 L3，不是旧节点标记；八份 acceptance 的 GWT 标题、done_when 与证据对象不同。`verify_feature_tree_refactor.sh`、`verify_acceptance_standard.sh`、`verify_test_specs.py` 实测全绿。
3. 对象：feature-tree 节点与 `tree_index.yaml`；owner=CM-002 所属 registry/acceptance 共享面。
4. 对象↔页面：不涉页面。
5. 旅程断点：无；真实 RTC 功能/环境缺口由 CM-043～046 承接，不能误归因于树结构。
6. 页面决策：不适用。
7. D1 —；D2 八个 L3 Story 边界清楚且 metadata 真相源唯一｜维持现状，禁止把产品 Story 与合同 Story机械合并｜`verify_feature_tree_refactor.sh` 绿；D3 —；D4 —；D5 —；D6 每份 acceptance 有独立 GWT 与三层证据声明，未完成场景保持 pending/partial｜由 CM-002 继续校验 planned/recorded 真实性｜`verify_test_specs`+`verify_acceptance_standard` 绿。
8. 黄金指标：不适用（治理项）。
9. 测试×环境：local=树校验脚本；api/UAT=—；环境=repo gate。
10. In=八个 Story 的边界、GWT 与引用复核；Out=RTC 实现与 planned 场景真实性（CM-002、CM-043～046）；依赖=无；Exit=三项树/验收门禁全绿且无重复职责。2026-07-20 已达到，状态 `VERIFIED`。

#### CM-002 acceptance planned/recorded 全量对账（测试准出 | B01 | GATE_BLOCK）

1. 定位：验收诚信横切；acceptance 是准出勾稽的地基。
2. 当前证据：2026-07-20 全仓扫描发现 76 条不存在的 `tests.planned.file`，已全部摘除；未完成行为仍由 pending/partial、`done_when` 与 `test_evidence.cases` 保留。`verify_test_specs.py` 已新增 planned 文件存在性、recorded canonical/存在性与缺失 acceptance fail-closed 规则；R-OPS-ACCEPTANCE-PHANTOM 已回写关闭。
3. 对象：全部 `acceptance.yaml` 的 `tests.planned/recorded`；owner=registry/acceptance 共享面（本批唯一写者）。
4. 对象↔页面：不涉页面。
5. 旅程断点：无；风险是"声明即完成"假绿。
6. 页面决策：不适用。
7. D1 —；D2 —；D3 —；D4 —；D5 —；D6 planned 文件均真实存在、recorded 仅 canonical 源/真实 report｜合同红测→全仓摘除 76 条幽灵引用→门禁 fail-closed｜`verify_test_specs`、`verify_test_coverage_map` 与 3 项 local_contract 全绿。
8. 黄金指标：不适用。
9. 测试×环境：local=扫描脚本自测；环境=repo gate 阻断。
10. In=全仓 acceptance 对账+扫描门；Out=补齐各域缺失测试本体（归各域 CM，落地后才可写入 planned/recorded）；依赖=无；Exit=零幽灵路径+门禁常绿。2026-07-20 已达到，状态 `VERIFIED`。

#### CM-003 H1 观测事件与指标目录冻结（平台横切 | B01 | GATE_BLOCK）

1. 定位：全部 CM 的 D5 底座；图一规格（ANR/错误率/页面打开时长/黄金指标）唯一入口。
2. 当前证据：matrix §8（H1-A/E）：无 ANR watchdog（仅 50/200ms frame jank）、通用页面 TTI 无合同（仅 home feed）、`AppPageErrorState` 无曝光/恢复 outcome、`runtime_exception` 非通用异常出口；R-OBJ-001 对象 metric→dashboard/alert 覆盖门未建。缺口分类：`可观测缺口`。
3. 对象：`ops/event_record/event_catalog.yaml`、runtime log catalog、告警目录规则；owner=route/surface/event catalog 共享面。
4. 对象↔页面：事件消费方为全部页面；本项只冻结契约不改业务页。
5. 旅程断点：无直接旅程；缺口导致"生产不可观测"。
6. 页面决策：不适用。
7. D1 —；D2 事件命名散落→metadata-first 单轨目录｜catalog 扩展（`app_anr_outcome`、`page_first_usable`、错误面 outcome 维度）→codegen｜`make verify-metadata`+codegen 幂等；D3 —；D4 ANR/hang 无采集→Android ApplicationExitInfo/iOS hang 事实+下次启动补报｜platform 防腐实现｜local 去重契约；D5 黄金指标无登记规则→每业务≤3 且四要素（分子/分母/窗口/下钻）登记；R-OBJ-001 通用覆盖门脚本｜规则文档+脚本接 gate｜覆盖门绿；D6 —→事件 schema/脱敏/终态结算 local_contract｜补测试｜套件绿。
8. 黄金指标：本项产出"规则"，不自设业务指标。
9. 测试×环境：local=catalog/采集契约；api=batch 幂等（beta）；UAT=真机可控卡死/慢页（gamma-local，随 CM-066）。
10. In=目录冻结+App 采集接线+覆盖门；Out=SLS/Prometheus 平台部署（运维轨）、各业务指标实例（各域 CM）；依赖=与运维轨 M0 矩阵去重；Exit=目录合入+采集三层证据+覆盖门接 gate。

#### CM-004 共享真相源 owner 与合流机制（平台横切 | B01 | COMMERCIAL_MUST）

1. 定位：多会话并行的安全底座；防第二真相源与并发写坏。
2. 当前证据：R-HSE04（拓扑 YAML 曾被并发写坏）；本轮实测 RTC acceptance 曾在验证窗口内出现"两份 YAML 拼接"瞬态。§0.4 owner 表为本项产出的初版。缺口分类：`技术债/契约双轨`。
3. 对象：§0.4 八共享面；owner=总控。
4. 对象↔页面：不涉。
5. 旅程断点：无。
6. 页面决策：不适用。
7. D1 —；D2 无显式 owner→每批 owner 唯一+变更请求流程｜owner 表写入各批启动包+拓扑原子写校验｜并行批次零冲突复盘；D3 —；D4 —；D5 —；D6 —→合流点在批次出口显式验证｜批次出口清单｜§5 出口检查通过。
8. 黄金指标：不适用。
9. 测试×环境：repo gate（YAML 可解析快检）。
10. In=机制+快检；Out=各共享面具体内容变更；依赖=—；Exit=B02 起所有批次按机制运行且无真相源事故；R-CLOUD04（codegen 全量重生）登记为依赖不由本项关闭。

#### CM-005 api_integration 统一入口与缺失测试目录（测试准出 | B01 | COMMERCIAL_MUST）

1. 定位：D6 底座；让远端层证据可复验而非动态 skip。
2. 当前证据：R-TST05（远端层依赖环境变量注入，裸 shell 不可自举）；磁盘缺口：`circle/rtc/tag-service` 无 `tests/local_contract` 根（有包旁测试）、`realtime-gateway` 无 `tests/api_integration`、notification domain/application 内层 0 个 `_test.go`（matrix §9 H2-A）。缺口分类：`测试缺口`。
3. 对象：Makefile 远端目标、服务测试目录；owner=各服务。
4. 对象↔页面：不涉。
5. 旅程断点：无。
6. 页面决策：不适用。
7. D1 —；D2 —；D3 —；D4 —；D5 —；D6 缺凭据静默/目录缺失→preflight fail-fast+真实测试补目录（禁空 wrapper）｜`verify-test-remote-env` 收口+按对象补状态机/边界测试｜新目录测试绿+`ENV=… make test-api-integration` 可复验。
8. 黄金指标：不适用。
9. 测试×环境：local=新 local_contract；api=gateway/notification 真实存储集成（beta）；环境=gamma-local 入口演练。
10. In=入口+四个目录缺口；Out=App api_integration 扩面（CM-065）；依赖=stackctl/CI secret（运维轨）；Exit=目录齐+preflight 可解释阻断+R-TST05 回写进展。

#### CM-006 测试旧口径校准与 legacy burn-down（测试准出 | B01 | COMMERCIAL_MUST）

1. 定位：测试口径单轨；防止已删除机制的历史叙述误导执行。
2. 当前证据：R-TST04/R-TST07 开放；`test_legacy_source_allowlist.yaml`、`test_directory_inventory.yaml`、bridge generator 已不在磁盘，但 backlog/spec 仍按旧机制叙述；旧 `T1-T4/L1-L4` 命名与条件 skip 残留（matrix §9 H2.7）。缺口分类：`技术债`。
3. 对象：`specs/03_TESTING_STRATEGY.md`、runtime-testinfra spec、backlog 对应条目。
4. 对象↔页面：不涉。
5. 旅程断点：无。
6. 页面决策：不适用。
7. D6 陈旧叙述/旧命名→文档与磁盘一致+旧命名棘轮递减｜重扫→修文档→棘轮门｜扫描零新增+R-TST04/07 状态回写（不得沿用历史数字）。其余维度 —。
8. 黄金指标：不适用。
9. 测试×环境：repo gate。
10. In=口径校准+棘轮；Out=物理迁移 burn-down 的执行本体（按扫描结果另立）；依赖=CM-002；Exit=backlog 与磁盘零漂移。

### 4.2 B02 身份、壳与对象基座

#### CM-007 商用登录凭据与第三方 provider 收口（外部集成 | B02 | GATE_BLOCK）

1. 定位：identity-entry Journey 的商用前提；"用户是关系"的入口。
2. 当前证据：R-AUTH-001（正式凭据未注入密钥系统）；registry §7.2/7.5：`ext.auth.wechat` user-service 直连 violation、alipay/qq 路由存在无真实置换、apple 无 JWKS 验签、one-tap 双端 `isAvailable=false`、SMS 仅 mock provider。login_page 本体成熟（matrix §10 M1-C P3）。缺口分类：`外部集成/环境假完成`。
3. 对象：`AuthenticationChallenge`、`AccountSession`、`CredentialBinding`（user.account 聚合）；provider 治理面=integration-service；owner=user-service+integration。
4. 对象↔页面：对象→login_page 嵌入承载（合理）；页面→对象绑定已 typed；provider 状态必须由 capability 正向证明（现有契约保持）。
5. 旅程断点：无凭据时社交/运营商入口只能静默降级 OTP；OTP 生产短信厂商未接（mock）。
6. 页面决策：login_page 保留精修（P3→P4，真机后评级）；不新增页面。
7. D1 社交/一键不可用→四 provider 真实登录+关闭不循环+续接恢复｜凭据注入→provider adapter→双目标回归｜真机四 provider UAT；D2 wechat 直连 violation→统一治理出口或显式豁免登记｜adapter 归置+registry 回写｜registry 合规复核；D3 已达标基线→保持｜真机双色截图｜视觉记录；D4 SDK callback/超时预算未冻结→P95/超时/重试/取消冻结｜弱网+重复 callback 负例｜beta 报告；D5 登录漏斗已有部分→3 指标：有效登录完成率/点击到续接 P95/失败恢复成功率｜绑定 challenge/session outcome｜SLS+user metric 对账；D6 真实 SDK 证据缺→alpha fake SDK+beta Remote+gamma 真机+prod canary｜补 provider 负例｜acceptance 回填。
8. 黄金指标：①有效登录完成率 ②点击→续接完成 P95 ③登录失败恢复成功率；下钻=provider/errorCode/网络/版本。
9. 测试×环境：local=capability/错误语义契约（已有基线）；api=challenge/session PG 集成+provider sandbox（beta/gamma）；UAT=真机四 provider+关闭安全态（gamma-local、prod gray）。
10. In=凭据、provider 收口、SMS 真厂商接线；Out=注销/数据权利（CM-015）、账号安全页（CM-008）；依赖=外部凭据与 SDK 授权、CM-018 法务；共享面=integration metadata（owner 申请）；Exit=R-AUTH-001 关闭条件全部满足并回写。

#### CM-008 账号安全与凭证管理准出 [验证型]（测试准出 | B02 | COMMERCIAL_MUST）

1. 定位：identity Journey 的安全管理面；对象已有承载，缺当前版本准出证据。
2. 当前证据：`lib/ui/settings/pages/settings_account_security_page.dart` 已实现并入横向矩阵（消费 `ListCredentialsSlice`+typed CredentialBinding writer，服务端保护最后凭证——矩阵 settings 组备注）；无真机 UAT/并发负例/多设备会话撤销证据。缺口分类：`测试缺口`。
3. 对象：`CredentialBinding`、`AccountSession`、`DeviceRegistration`；owner=user-service。
4. 对象↔页面：对象→账号安全页+设置账号动作（承载成立）；页面→对象绑定已在 page contract 登记（本轮实测 87 页合同绿）。
5. 旅程断点：待核验——最后凭证解绑保护、绑定冲突、他端会话撤销回显。
6. 页面决策：保留（P3→P4 经真机核验）。
7. D1 无当前证据→绑定/解绑/撤销全状态可恢复｜UAT 矩阵｜journey 绿；D2 已 typed→保持；D3 已模板化→真机双色核验；D4 —→并发解绑/重放幂等预算｜负例｜api 断言；D5 —→复用 CM-007 指标下钻（credentialType）；D6 U→三层补齐｜写 UAT+api_integration｜acceptance 绑定。
8. 黄金指标：并入 CM-007（不另设）。
9. 测试×环境：local=widget/Facet 契约；api=最后凭证保护+会话撤销（beta）；UAT=真机绑定解绑（gamma-local）。
10. In=准出证据；Out=功能新增；依赖=CM-007（真实 provider 后复验社交凭证行）；Exit=三层证据回填+页面评级更新。

#### CM-009 Persona 对象绑定与生命周期收口（业务对象 | B02 | COMMERCIAL_MUST）

1. 定位：Persona 是"用户是关系"的行为主体；绑定错误会污染整个对象勾稽。
2. 当前证据：`page_object_contract.yaml#user.persona_management` 现绑 `object_ids: [user.user_account]` 而命令聚合是 `Persona`（本轮实测仍如此）；页面 961 行接近红线；退役/删除空 Persona/并发激活的页面终态未证。缺口分类:`对象或聚合跑偏/页面成熟度不足`。
3. 对象：`Persona`（user.persona 聚合，mutation 六命令）；关联=UserAccount（N:1）、MediaAsset 引用。
4. 对象↔页面：页面实际操作 Persona 但合同声明 UserAccount——典型"页面→对象错绑"。
5. 旅程断点：retire 后引用保留语义、激活并发冲突、配额满回流。
6. 页面决策：适度重构（P2→P4）：先修合同，再按职责拆分。
7. D1 部分终态未证→六命令全状态承载｜补终态+回流｜persona journey UAT（已有基线扩展）；D2 合同错绑→绑 `user.persona`+账号摘要 Slice｜改 contract+codegen 校验｜page-object gate；D3 961 行→拆分+模板保持｜行数棘轮；D4 CAS 冲突→并发激活负例；D5 —→操作成功且零串号率（并入身份组指标下钻 persona 状态）；D6 —→状态机三层｜补 api_integration｜acceptance。
8. 黄金指标：并入身份组（下钻维度 personaState）。
9. 测试×环境：local=状态机+widget；api=PG 聚合+CAS（beta）；UAT=管理旅程（gamma-local）。
10. In=合同修正+生命周期收口；Out=Persona 关系图（CM-014）；依赖=CM-004（contract owner）；Exit=错绑清零+全命令三层证据。

#### CM-010 Welcome 身份四态规格裁决（产品功能 | B02 | COMMERCIAL_MUST）

1. 定位：冷启动与身份入口的规格一致性；产品心智"欢迎=品牌启动"或"欢迎=身份路由"二选一。
2. 当前证据：onboarding 规格要求四态身份入口，`welcome_screen.dart` 为 objectless 品牌启动页（page contract objectless、CR-20260720-125 进一步简化为品牌信息）；R-WELCOME-001 品牌字体授权未定稿。缺口分类:`信息架构错误（规格双轨）`。
3. 对象：StartupAttempt（runtime 状态机，非云聚合）；onboarding 规格节点。
4. 对象↔页面：页面→无对象（与合同一致）；规格→页面（冲突点）。
5. 旅程断点：首启后身份路由由 shell/登录门承担，规格却写在 welcome——验收挂错节点。
6. 页面决策：welcome_screen 保留精修（P2→P3/P4）；裁决产出规格修正而非新页面。
7. D1 规格实现冲突→单一口径（推荐：welcome=纯启动，身份四态归登录门/AuthContinuation 并改写 onboarding 规格）｜裁决+regisry/acceptance 同步｜规格一致性复核；D2 —；D3 字体开发态降级→授权字体落定或显式豁免｜R-WELCOME-001 跟进；D4 3s/6s 合同已有→维持；D5 启动指标归 CM-012；D6 welcome UAT 缺→启动品牌屏断言纳入启动 UAT。
8. 黄金指标：并入 CM-012 启动组。
9. 测试×环境：local=welcome local_contract（已有）+规格校验；UAT=启动旅程。
10. In=裁决+文档同步+字体跟进；Out=启动遥测（CM-012）；依赖=M1/M2 所有权（本项即裁决者）；Exit=规格单轨+R-WELCOME-001 回写。

#### CM-011 入站深链能力落地（产品功能 | B02 | GATE_BLOCK）

1. 定位：external-acquisition Journey 的回流一半；无深链则分享增长闭环不成立。
2. 当前证据：生产代码无 `DeepLinkResolver/PendingInboundTarget`（本轮 rg 零命中）；Android manifest 无 VIEW/BROWSABLE/autoVerify（零命中）；iOS scheme 仅服务登录 SDK 回调；`external-inbound-deeplink-routing` acceptance 全 pending；`_shared/link_templates.yaml` 真相源已存在。缺口分类:`功能缺失/旅程断点`。
3. 对象：LinkTemplate（shared metadata）+ PendingInboundTarget（runtime 值对象，TTL）；目标对象归各域。
4. 对象↔页面：能力→原生注册+Resolver+安全 fallback 面（复用现有错误/首页，不新增品牌页）。
5. 旅程断点：站外点击→App 冷/热启动→目标页：当前全断。
6. 页面决策：新增能力面（P0→P4）；fallback 复用 `AppPageErrorState`/首页。
7. D1 全断→冷/热/延迟深链+未装引导+失效安全终态｜Resolver+注册+pending replay+TTL｜三端深链 UAT；D2 无第二路由表→只消费 link_templates+canonical route｜实现约束｜route 单轨扫描；D3 —→fallback 语义一致；D4 —→点击到目标 P95≤2.5s（规格既定）｜冷启动重放预算｜设备计时；D5 —→解析成功率进 CM-050 组；D6 acceptance pending→三层补齐（解析单测/端云 resolve/设备旅程）。
8. 黄金指标：入站链接目标解析成功率（一级，归 M14 组）；下钻=来源/目标类型/冷热。
9. 测试×环境：local=模板解析/TTL；api=resolve+权限失效（beta）；UAT=Android App Links+iOS Universal Links 真机（gamma-local）。
10. In=接收/解析/重放/fallback；Out=出站分享卡（CM-049）、SEO 页（CM-050）；依赖=域名 assetlinks/AASA 发布（运维轨）；Exit=acceptance 从 pending 转 recorded+三端证据。

#### CM-012 启动幂等修复与启动遥测准出 [验证型]（平台横切 | B02 | COMMERCIAL_MUST）

1. 定位：冷启动 Journey 的事实完整性与 3s/6s 承诺证据。
2. 当前证据：R-OPS-STARTUP-IDEMPOTENCY（同 proof 异批复用致第二批丢失）；启动 11 阶段遥测+四段 `app_startup` 事件实现完整（matrix §11 M2-B），但真实 SLS 与真机矩阵证据缺（R-TELEMETRY-001 牵连）。缺口分类:`可观测缺口/环境假完成`。
3. 对象：EventRecord(startup 子集)、StartupAttempt/Journal。
4. 对象↔页面：welcome/shell/恢复面（既有）。
5. 旅程断点：事实丢失导致安全终态率不可信。
6. 页面决策：不改页面。
7. D1 —；D2 proof 幂等键错误→每批 canonical digest 派生｜服务端修复+重放负例｜api_integration 同 proof 异批断言；D4 3s/6s 无真机分布→冷/暖启动 20 次矩阵｜设备执行｜报告归档；D5 启动三指标未上真实盘→安全终态率/点击到首个可用内容 P95/恢复成功率｜接 CM-003 目录+运维轨 SLS｜大盘可回放；D6 U→断网补传/杀进程恢复三层。
8. 黄金指标：①6s 安全终态率 ②点击→首个可用内容 P95 ③启动恢复成功率。
9. 测试×环境：local=状态机（已厚）；api=startup ingress 幂等（beta）；UAT=真机矩阵（gamma-local）。
10. In=幂等修复+真机证据；Out=SLS 平台（运维轨）；依赖=CM-003；Exit=R-OPS-STARTUP-IDEMPOTENCY 回写+启动组指标可读。

#### CM-013 身份/资料聚合 Facet 对象化收口（业务对象 | B02 | COMMERCIAL_MUST）

1. 定位：user 域 DDD 单轨；R-OBJ-006 的执行体。
2. 当前证据：R-OBJ-006：AuthRepository 18 方法、UserRepository 12、Homepage 11 超 R02；约 79 处 `forPage`；user-service 78 条业务路由手写未切 generated dispatch；R-UPROF-003 关系计数 increment+全量 reconcile 规模风险。资料编辑写链已切 `UpdateUserProfileCommand`（本轮复验，page contract 已同步）。缺口分类:`契约双轨/技术债`。
3. 对象：UserAccount/Persona/Profile 投影/Relationship 读写分面；owner=user-service。
4. 对象↔页面：资料编辑/proposal sheet 绑定已修正；其余 user 页面按 Facet 拆分逐一复核。
5. 旅程断点：无直接断点；漂移风险在鉴权/超时/错误映射不可独立演进。
6. 页面决策：不改 IA；仅随 Facet 收口做消费替换。
7. D1 —；D2 聚合 Repository/手写路由→≤10 方法对象 Facet+generated dispatch+forPage 清零｜拆分→切换→删除旧径（零 shim）｜ContractGraph+接口方法数棘轮门；D3 —；D4 计数对账风险→事件驱动计数+定期 reconcile 策略冻结｜R-UPROF-003 方案裁决｜大关系集压测；D5 —；D6 →切换前后 parity 三层｜api_integration 对照｜回归绿。
8. 黄金指标：不适用（结构项），回归护栏=身份组指标不劣化。
9. 测试×环境：local=Facet 契约+Mock parity；api=PG/Mongo/Redis+dispatch（beta）；UAT=登录/资料/关系主旅程回归。
10. In=user 域 Facet/路由/forPage/计数；Out=entity Homepage Facet（随 CM-040/042 域内收口）；依赖=CM-004；Exit=R-OBJ-006 验收四条全绿回写。

#### CM-014 关系四层与联系人旅程收口（产品功能 | B02 | GATE_BLOCK）

1. 定位：contact-label-driven-connection 与 profile-private-activity-history 的关系底座；"用户是关系"。
2. 当前证据：R-UPROF-001：拉黑后内容可见性缺服务端强制（feed 过滤依赖客户端 header）——越权风险；关系四层（事实边/权限门/派生称谓/私有标签）规格在册；联系人添加五页+互动历史已实现（matrix §21 M12-C），mine-only 与多入口回流无当前准出证据。缺口分类:`安全隐私/旅程断点/测试缺口`。
3. 对象：PersonaRelationship、SubjectFollow、GreetingRequest、ContactDiscoveryRecord、互动历史投影；owner=user-service+content 投影。
4. 对象↔页面：对象→profile_stats/blocked/add_contact 族/greeting_inbox（承载成立）；页面→对象 typed（已 gate 绿）。
5. 旅程断点：拉黑后对方内容仍可能经未过滤读路径可见（服务端）；搜索/扫码/手机号三入口结果回流一致性待证。
6. 页面决策：全部保留精修（P3→P4）；不新增页面。
7. D1 多入口回流待证→添加→确认→关注/打招呼→会话升级闭环｜旅程补测｜journey UAT；D2 拉黑客户端过滤→服务端强制（feed/搜索/详情读路径统一 viewer gate）｜服务端 enforcement+负例｜越权 api_integration 全绿；D3 —→真机核验；D4 —→通讯录哈希匹配规模预算；D5 —→3 指标：关注/拉黑生效率（服务端视角）、添加联系人完成率、打招呼→会话升级率；D6 →mine-only 隐私负例+四层边界三层。
8. 黄金指标：①关系动作服务端生效率 ②联系人添加完成率 ③打招呼→正式会话升级率。
9. 测试×环境：local=四层规则/Provider；api=拉黑级联+可见性负例（beta/gamma）；UAT=添加三入口+私有历史（gamma-local）。
10. In=服务端强制、三入口回流、互动历史准出；Out=交集派生称谓 UI 增强（CM-058）；依赖=CM-013；Exit=R-UPROF-001 回写+隐私负例全绿。

#### CM-015 数据主体权利对象与页面（产品功能 | B02 | GATE_BLOCK）

1. 定位：商用合规必备（注销/导出/撤回同意）；当前完全缺失的 P0 能力。
2. 当前证据：R-UPROF-002 无账号注销/封禁跨域级联；matrix §24 M15：查询/撤回/导出/注销无对象、页面与终态；ConsentRecord 寄宿 user_profile 未对象化。缺口分类:`对象缺失/功能缺失/安全隐私合规`。
3. 对象：新建（metadata-first）：AccountDeletionRequest（冷静期状态机）、DataExportRequest、ConsentRecord 对象化；owner=user-service，级联经各域 public 契约。
4. 对象↔页面：新对象→settings 权利入口+状态页；结果经通知回流（CM-048）。
5. 旅程断点：当前用户无法注销/导出/撤回——全断。
6. 页面决策：新增（P0→P4，Inset 模板族）。
7. D1 全缺→申请→冷静期→执行→结果全终态｜状态机+页面+撤回窗口｜UAT 覆盖冷静期取消；D2 无对象→三对象 S/F/E 齐+跨域级联事件单轨｜metadata→codegen→saga｜ContractGraph+级联 api_integration；D3 —→Inset 模板+危险动作确认（标杆：Apple/微信注销流）；D4 →级联幂等/部分失败恢复预算；D5 →数据主体请求完成率（一级）；D6 →级联全域断言（content/chat/circle/entity/media）三层。
8. 黄金指标：数据主体请求按期完成率；下钻=请求类型/失败域。
9. 测试×环境：local=状态机；api=跨域级联真实存储（beta/gamma）；UAT=注销冷静期旅程（gamma-local）。
10. In=三对象+页面+级联；Out=法务文案定稿（CM-018 输入）；依赖=CM-018 口径、CM-048 通知；共享面=user metadata owner；Exit=R-UPROF-002 回写+合规检查表通过。

#### CM-016 设置对象页准出 [验证型]（测试准出 | B02 | COMMERCIAL_MUST）

1. 定位：UserSettings 对象能力已成型，缺当前版本准出证据。
2. 当前证据：六页（notifications/privacy/calls/dark_mode/blocked_keywords/my_reports）已实现并入矩阵（typed `UserSettingsQueryReader/CommandWriter`、`PrivacySettingsView` 等——settings 组备注）；page contract 已绑 `user.user_settings`（本轮 87 页合同绿）；无真机/CAS 冲突/乐观回滚当前证据。缺口分类:`测试缺口`。
3. 对象：UserSettings（PG+outbox、version CAS）、ContentReportQuery（my_reports）。
4. 对象↔页面：全部成立（历史 UserAccount 错绑已修复——matrix §24 复验记录）。
5. 旅程断点：待核验——多端 CAS 冲突恢复、乐观更新回滚、免打扰时段生效。
6. 页面决策：保留（P3→P4 经真机）。
7. D1 U→六页全状态真机；D2 已单轨→保持；D3 →双色/断点核验；D4 →CAS 并发负例；D5 →设置写入成功且收敛率（一级）；D6 U→三层补齐。
8. 黄金指标：设置写入成功且跨端收敛率。
9. 测试×环境：local=已有 Facet 契约；api=CAS 409+quietHours（beta）；UAT=六页真机（gamma-local）。
10. In=准出证据；Out=数据权利（CM-015）、权限页（CM-017）；依赖=—；Exit=acceptance 回填+评级更新。

#### CM-017 权限预留页裁决（UX 重构 | B02 | COMMERCIAL_MUST）

1. 定位：消灭"视觉存在但业务无价值"的空壳页。
2. 当前证据：`settings_permissions_page.dart` 仍为三行只读"预留"（矩阵 P2/P3=—）；平台权限真实状态由 `AppPermissionCoordinator` 掌握但页面不消费。缺口分类:`页面成熟度不足/信息架构错误`。
3. 对象：平台权限 profile（client capability，非云对象）。
4. 对象↔页面：对象有真实状态、页面不消费——"页面无对象支撑"。
5. 旅程断点：用户进入后无任何可执行动作。
6. 页面决策：完全重构（真实权限状态+跳系统设置+能力位降级）或删除入口——由本项裁决并实施。
7. D1 空壳→每行真实状态/动作或页面下线；D2 —；D3 P1→P4（标杆：iOS Settings 权限组）；D4 —→返回重检语义；D5 —；D6 →权限 profile 驱动 widget 测试+UAT。
8. 黄金指标：不适用。
9. 测试×环境：local=capability profile 双态；UAT=权限跳转真机。
10. In=裁决+实施+矩阵同步；Out=各业务权限语义（归各域）；依赖=—；Exit=页面达 P4 或删除且矩阵/inventory 同步。

#### CM-018 法务条款与 legal-static 商用发布（外部集成 | B02 | GATE_BLOCK）

1. 定位：商用放量的法律前提。
2. 当前证据：R-LEGAL-001：manifest `legal-review-required`，运营主体/注册地址/客服电话/ICP 占位；About/legal_document_page 承载链路本体可用（matrix §24）。缺口分类:`安全隐私合规/外部阻断`。
3. 对象：LegalStaticRelease（immutable version 制品）；ConsentRecord 版本一致性。
4. 对象↔页面：about→WebView 链路成立；缺的是内容与审签。
5. 旅程断点：条款正文不可商用。
6. 页面决策：保留精修（离线/缓存/版本标识随 CM-016 组核验）。
7. D1 占位→审签正文+主体信息真实；D2 →manifest 版本与登录 consent 版本单轨；D3 —；D4 →legal 站点独立回滚演练；D5 →法律正文可达率与版本匹配率（一级，随设置组）；D6 →prod legal-static 发布门+consent 一致 UAT。
8. 黄金指标：法律正文可达且版本匹配率。
9. 测试×环境：local=manifest 校验；api=`/legal/*` 探针（gamma/prod)；UAT=登录协议→正文一致。
10. In=法务输入落 manifest+发布验证；Out=商业化专项条款（R-COMMERCE-001 前置，维持延期）；依赖=法务（外部）；Exit=R-LEGAL-001 关闭回写。

### 4.3 B03 核心旅程

#### CM-019 消费面路由/surface/SLO 修正（UX 重构 | B03 | COMMERCIAL_MUST）

1. 定位：content-discovery Journey 的契约洁净度；"内容是入口"的读主链。
2. 当前证据：`unified_media_viewer_page.dart:59` 仍硬编码 `context.push('/user/$userId')`；`ui_surfaces.yaml#homeFeed` 无 `GetFeed` 却含上传/分享等 20 个 operation；Feed P95 业务规格 200ms vs metadata 500ms 双口径（matrix §12 M3-D）。缺口分类:`契约双轨`。
3. 对象：Post Feed/Read 投影；surface 真相源。
4. 对象↔页面：home/viewer/work_browser 绑定成立；surface 与主任务漂移。
5. 旅程断点：无功能断点；治理性漂移。
6. 页面决策：三页保留精修。
7. D1 —；D2 硬编码路由/surface 漂移→generated route+surface 只留真实 operation｜修三处+扫描门｜route 单轨扫描绿；D3 —；D4 SLO 双口径→冻结一个数并回写规格与 metadata｜裁决+同步｜metadata verify；D5 —；D6 →修正后回归。
8. 黄金指标：并入 CM-064 消费组。
9. 测试×环境：local=路由/surface 契约；api=GetFeed SLO 断言（beta）。
10. In=三处漂移修正；Out=viewer 大重构（CM-020）；依赖=CM-004（surface owner）；Exit=扫描零硬编码+SLO 单轨。

#### CM-020 内容主链超千行结构治理（UX 重构 | B03 | COMMERCIAL_MUST）

1. 定位：阅读/沉浸/创作主链可维护性（R-OBJ-007 执行体）。
2. 当前证据：R-OBJ-007：`article_read_only_book_deck.dart` 4885 行、`create_editor_provider.dart` 2361 行等 12 文件超 R03 红线，混 26 处 `@Deprecated`。缺口分类:`技术债`。
3. 对象：无对象变更；渲染/状态职责拆分。
4. 对象↔页面：不改绑定。
5. 旅程断点：无；回归面不可控是风险本体。
6. 页面决策：适度重构（结构性，不改 IA）。
7. D1 —；D2 —；D3 12 文件超线→各<1000 行+deprecated 清零｜按 pageflip BACK 主线拆分（守 12 号军规单几何真相源）｜行数棘轮+pageflip visual 证据；D4 →拆分前后帧/内存不劣化；D5 —；D6 →创作草稿/发布恢复/沉浸/翻页回归全绿。
8. 黄金指标：不适用；护栏=pageflip visual+性能不劣化。
9. 测试×环境：local=visual/结构测试；UAT=阅读翻页旅程回归。
10. In=12 文件；Out=功能变更；依赖=pageflip 军规；Exit=R-OBJ-007 回写。

#### CM-021 内容删除/封禁传播全链验证（业务对象 | B03 | GATE_BLOCK）

1. 定位：对象生命周期"失效"态在全部消费面的确定性；商用信任底线。
2. 当前证据：DeletedPostTombstone 对象在册；删除/私密/封禁跨 feed/search/viewer/通知/分享回链的 E2E 传播断言缺失（matrix §12 M3-E D1 任务未兑现）。缺口分类:`关系或生命周期不完整/测试缺口`。
3. 对象：Post tombstone、各消费投影（feed/search index/通知 target/分享 token）。
4. 对象↔页面：失效对象→各消费面解释性终态（非 404/raw error）。
5. 旅程断点：删除后旧曝光入口点击行为未证。
6. 页面决策：不改页面；补终态语义核验。
7. D1 传播未证→删除/私密/封禁后所有入口确定性终态｜传播矩阵用例｜E2E 断言绿；D2 →tombstone 事件消费单轨核对；D3 →失效态文案语义一致；D4 →传播延迟预算（曝光剔除水位）；D5 →失效对象曝光率（护栏指标）；D6 →feed/search/深链/通知四入口 api_integration+UAT。
8. 黄金指标：护栏=已失效对象曝光率≈0。
9. 测试×环境：api=四入口传播（beta/gamma）；UAT=删除后回访旅程。
10. In=传播验证+缺口修复；Out=审核状态语义（CM-025）；依赖=CM-030（search 侧同批）；Exit=传播矩阵全绿。

#### CM-022 评论治理与互动收口（产品功能 | B03 | COMMERCIAL_MUST）

1. 定位：content-comment-interaction Scenario（2026-07-20 已入 registry）的商用收口。
2. 当前证据：服务端 V3 成熟（Mongo aggregate+outbox、pinned-first；R-CMT01~03 已闭）；缺口：评论组件无正式 Report/审核反馈入口、`publish-comment-reaction` L2 仍留"Post 成员/三档排序"旧叙述、`profile_comments_page` P2（默认头像+原始 postId 摘要）、observability 残留 polling/sort 旧词（matrix §25 M16-D）。缺口分类:`功能缺失/页面成熟度不足/契约双轨`。
3. 对象：Comment、ContentReaction、Report、Comment count projection；owner=content-service。
4. 对象↔页面：评论 sheet 族（viewer modal/分屏/detail/input）+profile_comments_page；`canReport` 契约在册无 UI。
5. 旅程断点：被举报/被隐藏评论的作者与读者反馈断；profile 评论→失效线程回跳。
6. 页面决策：sheet 族精修（P3→P4）；profile_comments_page 适度重构（P2→P4）；L2 规格单轨化。
7. D1 治理断→评论→举报→审核→反馈闭环+失效线程终态｜Report 入口+moderation 反馈+占位语义｜moderator/author/viewer UAT；D2 规格双轨→L2 与 V3 单轨｜改 spec+防回归扫描（禁 CommentDto/count-delta 复活）｜metadata/spec 一致；D3 P2 页→P4｜摘要卡真实内容+深链定位｜真机核验；D4 →热帖深分页既有 explain 证据维持；D5 →3 指标：有效评论完成率/提交到可见 P95/评论后互动率｜接 CM-003；D6 →App Remote+moderation 负例三层。
8. 黄金指标：①有效评论完成率 ②提交→可见 P95 ③评论后有效互动率。
9. 测试×环境：local=状态机/widget（厚基线）；api=真实 Mongo 线程+report（beta）；UAT=四载体评论旅程（gamma-local）。
10. In=治理入口/页面/规格；Out=审核平台（Portal，运维轨）与审核方向裁定（CM-025 输入）；依赖=CM-025；Exit=Scenario 验收绑定回填。

#### CM-023 创作 Journey 登记与发布回流（产品功能 | B03 | GATE_BLOCK）

1. 定位：创作是唯一无 registry 归属的核心旅程；发布成功断尾是最大体验断点。
2. 当前证据：text G3（registry 全文无创作条目，本轮复验仍无）、G1（发布成功仅 Toast+关页，无结果回流）、G7（micro/article 静默分型）、N10（干净 HEAD 基线红灯：mock `avatarBaseUrl` 空串致 homepage_picker 崩）、N11/N12 视觉项；photo GATE-P1 同源。缺口分类:`旅程断点/信息架构错误`。
3. 对象：Post/PublishIntent/LocalDraft；registry 新 Journey+Scenario。
4. 对象↔页面：create 链 6 页+确认 sheet+发布结果回流面（新增轻量）。
5. 旅程断点：发布成功→去向断；排队/失败任务不可见。
6. 页面决策：create_page 适度重构（P2→P4）；新增发布结果回流态与任务可见性（轻量，非新路由页）。
7. D1 断尾→写→发→见→回响闭环｜text 批次 A 全量（回流面+任务可见+分型显性化+N10 fixture 修复）｜三类型 roundtrip UAT；D2 无 registry→新增创作 Journey/Scenario+acceptance 绑定｜text 批次 B｜registry 校验绿；D3 4 处硬编码文案+分型不可见→token 化+显性化｜真机核验；D4 →发布排队/重试语义预算（复用 CR-114 可靠合同）；D5 →归 CM-024；D6 →journey UAT+api roundtrip 扩展。
8. 黄金指标：归 CM-024 组。
9. 测试×环境：local=状态机/widget；api=photo roundtrip 扩展 text/video 占位；UAT=发布回流旅程。
10. In=text 批次 A+B（含 photo 共享底座）；Out=漏斗观测（CM-024）、安全（CM-025）；依赖=CM-002/004（registry owner）；Exit=registry 登记+回流 UAT 绿。

#### CM-024 发布漏斗观测接线（平台横切 | B03 | COMMERCIAL_MUST）

1. 定位：创作组 D5；text G2 的执行体。
2. 当前证据：text G2：端侧漏斗 payload 被云侧 400 拒且端侧静默吞（`create_page_provider_bridge.dart` vs `behavior_service.go`）；无发布大盘/延迟告警；R-OBJ-002 创作域实例。缺口分类:`可观测缺口`。
3. 对象：发布漏斗事件（进 CM-003 目录，journey=creation）；黄金指标 recording rules。
4. 对象↔页面：创作链埋点接线。
5. 旅程断点：无；运营不可算是风险。
6. 页面决策：不改页面。
7. D5 零采集→事件 metadata-first→codegen→payload 改造（clientEventId/occurredAt/errorCode）→三黄金指标+告警｜text/photo 批次 C｜采集→SLS/Prom→大盘回放演练；其余维度 —（D6=事件契约 local+指标可读 api）。
8. 黄金指标：①有效发布率 ②开始→内容可见 P95 ③发布失败恢复成功率。
9. 测试×环境：local=事件契约；api=指标可读断言（beta）；UAT=漏斗对账演练。
10. In=事件+指标+告警+referralSource 贯通；Out=SLS 平台（运维轨）；依赖=CM-003；Exit=三指标真实入盘。

#### CM-025 内容安全方向裁定与实装（产品功能 | B03 | GATE_BLOCK）

1. 定位：UGC 商用合规核心；text G5 执行体。
2. 当前证据：`post_publication.go:102-103` 发布即 approved；`content_too_long`/`rate_limited` 错误码闲置；作者侧审核结果无闭环（G5b）；Portal 治理页已可复核举报（运维轨已收）。缺口分类:`安全隐私合规/功能缺失`。
3. 对象：PostModerationCase（激活死枚举）、频控策略、作者通知（经 CM-048）。
4. 对象↔页面：发布链+作者侧状态/通知反馈；Portal 审核台归运维轨。
5. 旅程断点：违规内容无拦截；被拒作者无感知。
6. 页面决策：发布链增审核中/被拒终态表达（随 CM-023 回流面）。
7. D1 无审核闭环→（方向 a/b 用户裁定后）发布→审核→结果→作者反馈全链｜状态机激活+频控+通知投影｜审核链 UAT；D2 死枚举→枚举=可达状态单轨；D3 →被拒态文案合规；D4 →频控预算（对标 75/日级配额）；D5 →审核时效/拦截率护栏；D6 →审核路径三层+灰度回滚（误杀回滚开关）。
8. 黄金指标：护栏=违规拦截率、审核时效 P95（不占业务三指标位）。
9. 测试×环境：local=状态机；api=审核流转+频控（beta）；UAT=被拒作者旅程。
10. In=裁定后的机制实装；Out=第三方内容安全厂商接入（当前未选型，如需先走 CM-056 登记）；依赖=**用户方向裁定（a 先审后发/b 后审+拦截/c 维持现状）**、CM-048；Exit=裁定记录+机制上线+G5 关闭。

#### CM-026 发布契约与结构治理（业务对象 | B03 | COMMERCIAL_MUST）

1. 定位：发布链 metadata 单轨与分层清洁；text 批次 E 执行体。
2. 当前证据：G6 PostStatus 枚举漂移（3 死状态+死分支）、ModerationCase `reviewed` 不在闭集；G8 tag 创作断链（编辑器仅 entity picker，creation-tagging-ia 全 pending）；R-CS10 文章图文不同源退化 text_only；R-CR04 CreateLocationService/Option 滞留 lib/ui。缺口分类:`契约双轨/技术债`。
3. 对象：PostStatus/semanticMentions(tag)/articleAssetManifest/location 分层。
4. 对象↔页面：编辑器 tag 入口（新增嵌入控件，消费 CM-063 目录）。
5. 旅程断点：图文混排丢失（R-CS10）；tag 表达断供给。
6. 页面决策：编辑器精修（tag 入口+图文同源）。
7. D1 图文退化→文章图文同源发布；D2 枚举漂移/断链→枚举单轨+tag 双通道+location 迁 `lib/cloud/services/integration`｜text/photo 批次 E｜metadata verify+死分支清零+目录门；D3 —；D4 →media 数量/大小上限入 metadata+`media_too_large`；D5 —；D6 →契约测试+孤儿 MediaAsset TTL 对账任务。
8. 黄金指标：不适用。
9. 测试×环境：local=契约/编辑器 widget；api=上限负例（beta）。
10. In=批次 E 全量；Out=taxonomy 本体（CM-063）；依赖=CM-063 目录可用；Exit=G6/G8、R-CS10、R-CR04 回写。

#### CM-027 视频转码管线落地（外部集成 | B03 | GATE_BLOCK）

1. 定位：UGC 视频商用第一阻断（GATE-V1）；无 worker 则视频链路物理断裂。
2. 当前证据：`RecordMediaProcessingResult` 零生产调用方、media outbox 无 relay、全仓 ffmpeg/ffprobe 零命中（video 计划 2026-07-20 复核）；GATE-V6 `media-processing-helper-read` 特性树空壳；GATE-V9 `adaptive(hls_or_dash)` 死声明；GATE-V10 转码零指标。缺口分类:`功能缺失/对象生命周期不完整`。
3. 对象：MediaAsset processing 状态机、media outbox/relay、转码 worker（新服务或 content-service worker，裁决记录 CR）。
4. 对象↔页面：云侧为主；端侧"处理中"语义归 CM-028。
5. 旅程断点：上传完成→永久 processing→发布不可达。
6. 页面决策：不涉。
7. D1 断裂→上传→转码→ready→发布真实链｜V-A：worker+relay+ffmpeg｜E2E（testcontainers+真实 ffmpeg）；D2 特性树空壳→L2/L3 acceptance 回填+adaptive 决策登记（做/不做/何时）｜规格同步｜acceptance 绿；D3 —；D4 →转码时长/并发/失败重试预算；D5 →转码时长/积压/失败率+media outbox lag 告警｜接 CM-003；D6 →真实介质 api_integration。
8. 黄金指标：①上传→ready E2E 时延 P95 ②转码失败率 ③队列积压（护栏）。
9. 测试×环境：api=ffmpeg E2E（beta）；环境=gamma 真实介质（随 CM-029）。
10. In=V-A 全量；Out=端侧硬化（CM-028）；依赖=对象存储/VOD 资源（R-CS05 数据轨协同）；Exit=GATE-V1/V6/V9/V10 关闭。

#### CM-028 视频上传硬化与 Android 能力位（产品功能 | B03 | GATE_BLOCK）

1. 定位：视频创作端侧可靠性与跨平台诚实降级。
2. 当前证据：GATE-V2 `quwoquan/video_editing` 仅 iOS（Android 抛 UnsupportedError 且入口不按能力位隐藏）；GATE-V3 全量 readAsBytes 进内存/无分片续传/失败不入离线队列；GATE-V7 media_not_ready 仅指数退避无"处理中"语义；`GetMediaUploadSession` resume 零消费。缺口分类:`性能与可靠性缺口/UX 状态不全`。
3. 对象：MediaUploadSession（resume 契约激活）。
4. 对象↔页面：create video flow/video_editor/相机壳。
5. 旅程断点：大文件 OOM、中断不可续、处理中无反馈。
6. 页面决策：video flow 适度重构（P2→P4）。
7. D1 处理中断→排队/处理中/失败/续传全状态；D2 resume 死契约→激活消费；D3 Android 假入口→能力位隐藏+结构化降级（R-XP4 口径）；D4 内存/断点→流式+分片+进度+断点续传预算；D5 →上传段 operation_result 已有+补进度/失败原因；D6 →大文件弱网 UAT+能力位双端测试。
8. 黄金指标：视频上传成功率（一级，创作组下钻）。
9. 测试×环境：local=能力位/状态机；api=分片续传（beta）；UAT=大文件弱网真机。
10. In=V-B+V-C；Out=转码云侧（CM-027）；依赖=CM-027；Exit=GATE-V2/V3/V7 关闭。

#### CM-029 发布四环境证据兑现（测试准出 | B03 | GATE_BLOCK）

1. 定位：创作组的环境假完成清算；`CONTENT_MEDIA_GAMMA_UAT` 翻牌唯一路径。
2. 当前证据：text G4（alpha failed/beta 无/gamma blocked/prod 仅 health；gamma patrol 无发布旅程）；GATE-V4（`test/api_integration/gamma/` 目录不存在、5 幽灵 planned）；GATE-V5/V8（R-CS08 四环境 0 通过、media/cover op blocked）；R-CS11 灰度三阶段非 dry-run 缺失。缺口分类:`环境假完成/测试缺口`。
3. 对象：发布链全对象的环境证据。
4. 对象↔页面：—。
5. 旅程断点：—。
6. 页面决策：—。
7. D6 假完成→alpha fixture 修复（N10）→beta 写端点 verify→gamma patrol 三类型发布旅程→`CONTENT_MEDIA_GAMMA_UAT` 翻牌→prod gray 发布探针｜photo F+V-D｜四环境运行制品落盘+acceptance recorded 回填（先经 CM-002 摘除幽灵）。其余维度随证据回写。
8. 黄金指标：不适用。
9. 测试×环境：全四环境执行本体。
10. In=证据兑现+翻牌；Out=功能修复（CM-023/027/028 前置）；依赖=CM-023/027/028、数据轨种子、R-CS11 环境轨协同；Exit=R-CS08 逐 target 转绿+翻牌记录。

#### CM-030 搜索可用性与环境种子（产品功能 | B03 | GATE_BLOCK）

1. 定位：cross-domain-search 的"搜得到"底线；WP-H/WP-I 执行体。
2. 当前证据：search 计划 §8：WP-H 残余（EnsureIndex 失败语义跨域不一致、recent 路由无指标、手写路由未切 descriptor、AppSearchRepository 10 处静默 catch、global_search 测试链复验）；WP-I：beta/gamma 无可检索种子（搜什么都空）、`e2e.yaml` 引用不存在文件、热门圈子/地点伪热度。缺口分类:`功能缺失/环境假完成`。
3. 对象：SearchQuery/SearchIndexView/RecentSearchState/seed manifest。
4. 对象↔页面：global_search/network_results（承载成立）。
5. 旅程断点：真实环境搜索结果为空。
6. 页面决策：两页精修（默认页灵感区随 WP-K 在 CM-031）。
7. D1 空结果→种子后跨对象非空；D2 工程债→路由 descriptor 化+receipts 登记+catch 结构化；D4 →ES 超时语义统一（已改 config，语义裁决收口）；D5 →recent 指标；D6 →fixture parity+gamma 非空断言+beta 人工。
8. 黄金指标：归 CM-032 组。
9. 测试×环境：local=repository/provider 契约；api=gamma `/search` 非空；UAT=默认页历史旅程复验。
10. In=WP-H 残余+WP-I；Out=交集 attach（CM-031）；依赖=数据轨种子协同；Exit=beta/gamma"搜得到"证据+R-S09 候选经用户确认登记。

#### CM-031 搜索交集 attach 与对象完备（产品功能 | B03 | DIFFERENTIATOR）

1. 定位：搜索差异化核心（"为什么与我相关"）；WP-J/WP-K 执行体。
2. 当前证据：WP-J：`connectionState/IntersectionReason` 为死字段（服务不填充、端侧假空态）；WP-K：user 结果无承载、tag 检索无产品决策、结果失效无反馈、Tab 硬编码中文、无结果视图可精修（12 张截图依据）。缺口分类:`交集差异化缺失/UX 状态不全`。
3. 对象：搜索命中×viewer 交集 attach（消费 `ObjectIntersections`，超时降级）；user_search_projection。
4. 对象↔页面：network_results 交集 Tab/分区；landing 失效反馈。
5. 旅程断点：交集 Tab 恒空；结果→已删对象 404 死路。
6. 页面决策：network_results 适度重构（P2→P4，交集区目标 P5）。
7. D1 死链→结果→对象/行动+失效回搜索页 typed 提示；D2 死字段→attach 阶段+闭集映射+降级开关；D3 →Tab token 化+无结果视图+灵感卡片化（标杆截图依据）；D4 →attach 超时不阻塞主路径预算；D5 →交集结果点击率（下钻 connectionState）；D6 →双态交集 UAT+user 召回断言。
8. 黄金指标：归 CM-032 组（交集 Tab 有效行动率为其 3 号指标下钻）。
9. 测试×环境：local=attach 降级单测；api=双服务真实交集；UAT=有/无交集双态。
10. In=WP-J+WP-K；Out=交集读模型本体（CM-057）；依赖=CM-057 数据密度、CM-021（失效传播）；Exit=connectionState 真实填充+R-S08 候选经确认登记。

#### CM-032 搜索观测与发布准出（测试准出 | B03 | GATE_BLOCK）

1. 定位：搜索组 D5/D6 与发布门；WP-L+WP-E/G 执行体。
2. 当前证据：无 search 专有事件目录；R-S06-S-1（真集群容量 measured 缺）、R-S06-S-2（写时增量长稳）；App 搜索 api_integration=0；6 个 pending GWT 待补 recorded。缺口分类:`可观测缺口/测试缺口/环境假完成`。
3. 对象：search 事件（query_submit/result_impression/result_click/refine/zero_result）+容量报告。
4. 对象↔页面：—。
5. 旅程断点：—。
6. 页面决策：—。
7. D5 无目录→事件 metadata-first+三黄金指标+发布门搜索探针｜WP-L｜大盘+对账演练；D6 容量未准出→真集群 measured+写时长稳+App Remote 证据｜WP-E/G｜报告+api 套件绿。
8. 黄金指标：①有效搜索成功率（非空且有行动）②提交→首个可操作结果 P95 ③结果→有效行动率。
9. 测试×环境：api=gamma 真栈 Remote；环境=真集群容量报告；UAT=漏斗对账。
10. In=WP-L+WP-E/G；Out=—；依赖=CM-003、真集群资源（外部）；Exit=R-S06-S-1/2 回写+6 GWT recorded。

#### CM-033 location.place 对象裁决与落地页重构（业务对象 | B03 | COMMERCIAL_MUST）

1. 定位：消灭"页面有实体语义、对象不存在"的最强断点（matrix §14/§27 双记）。
2. 当前证据：`location.place` 仅 shared search taxonomy+route；无 canonical packet/Store/事件/生命周期；`location_place_landing_page` route-extra-only（刷新/冷启动/提升后不可重取），page contract 主对象仍写 search_query。缺口分类:`对象缺失/页面无对象支撑`。
3. 对象：裁决二选一——建 `location.place` 正式投影对象（含 resolve Slice、tombstone）或收敛为 Homepage 提升前的纯搜索快照（页面降级为无正式操作）。
4. 对象↔页面：裁决后单轨。
5. 旅程断点：深链/刷新落地页空白；提升为 Homepage 后旧地点悬挂。
6. 页面决策：完全重构（P1→P4）。
7. D1 不可重取→placeId resolve 或显式快照语义；D2 无对象→裁决+metadata 落地；D3 →失效/提升态；D4 →resolve P95；D5 →promote_click 既有埋点保留；D6 →resolve/失效三层。
8. 黄金指标：地点落地→提升/行动转化率（下钻，归搜索组）。
9. 测试×环境：local=payload/快照契约；api=resolve+tombstone；UAT=深链直达落地页。
10. In=裁决+实现+页面；Out=Homepage 本体（CM-040/042）；依赖=CM-042 提升链、CM-004（metadata owner）；Exit=page contract 主对象修正+深链 UAT 绿。

#### CM-034 消息对象契约与页面绑定补齐（业务对象 | B03 | COMMERCIAL_MUST）

1. 定位：messages 域对象化洁净度。
2. 当前证据：`conversation_membership/message/conversation_user_state` 无对象级 `errors.yaml`（域级寄宿 conversation）；page contract 对 chat 页主要绑 Conversation/UserAccount，Message/Membership/UserState 未登记；`metadata/chat/openapi.yaml` generated 出口边界需机器声明（matrix §15 M6-B/D）。缺口分类:`契约双轨`。
3. 对象：六消息对象；owner=chat-service+messages metadata。
4. 对象↔页面：chat 9 页绑定补全。
5. 旅程断点：无直接断点。
6. 页面决策：不改 IA。
7. D2 错误寄宿/绑定粗→对象级 errors（或显式域级声明并加校验）+page contract 补 Message/Membership/UserState+generated 出口标注｜metadata→codegen→contract｜verify+page-object gate；其余维度 —（D6=错误码端云链路契约测试）。
8. 黄金指标：不适用。
9. 测试×环境：local=错误码链路；api=错误响应映射（beta）。
10. In=契约补齐；Out=功能（CM-035/036）；依赖=CM-004；Exit=对象错误所有权单轨+绑定完整。

#### CM-035 消息 readiness 翻牌与 Remote 扩面（测试准出 | B03 | COMMERCIAL_MUST）

1. 定位：消息"实现成熟但契约 blocked"的诚实差清算。
2. 当前证据：chat operations 普遍 commercial blocked（`SendMessage` 显式 `CHAT_MESSAGE_MEDIA_GAMMA_CLOSURE`）；readiness `environments: []`；App api_integration 仅 roster parity 一条（matrix §15）。缺口分类:`环境假完成/测试缺口`。
3. 对象：chat operations readiness。
4. 对象↔页面：—。
5. 旅程断点：—。
6. 页面决策：—。
7. D6 blocked→发送/回执/成员/打招呼升级 App Remote api_integration+gamma 环境证据→逐 op 翻牌｜扩面+readiness 回填｜beta Mongo/Redis+gamma realtime 套件绿。其余维度随证据回写。
8. 黄金指标：归 CM-036 消息组。
9. 测试×环境：api=真实存储+realtime（beta/gamma）。
10. In=扩面+翻牌；Out=功能变更；依赖=CM-005/034、CM-043（realtime 环境）；Exit=readiness 有环境证据+blocked 清零或显式理由。

#### CM-036 会话/群治理真机与离线准出 [验证型]（测试准出 | B03 | COMMERCIAL_MUST）

1. 定位：消息主旅程的设备级商用证据。
2. 当前证据：实现成熟（持久 outbox/gap sync/群命令/greeting 全状态，B5/B12 收口）；断网重发/杀进程恢复/并发角色冲突/IME 横竖屏无当前版本真机证据。缺口分类:`测试缺口`。
3. 对象：Conversation/Message/Membership/GreetingRequest 行为面。
4. 对象↔页面：chat 9 页+成员 sheet。
5. 旅程断点：待核验清单即断点假设。
6. 页面决策：保留（P3→P4 经真机）。
7. D1 U→1v1/群/greeting 升级/离线恢复全旅程真机；D4 U→弱网/重放/乱序报告；D5 →3 指标：消息有效送达率/发送到对端可见 P95/失败恢复成功率；D6 U→设备矩阵执行。
8. 黄金指标：①有效送达率 ②发送→对端可见 P95 ③失败恢复成功率。
9. 测试×环境：UAT=gamma-local 设备矩阵；api=复用 CM-035。
10. In=准出证据；Out=新功能；依赖=CM-035/043；Exit=journey 报告+评级更新。

#### CM-037 CircleGroup 群单元生命周期承载（产品功能 | B03 | GATE_BLOCK）

1. 定位：circle-entity-group-collaboration 的核心断点；组织协作差异化前提。
2. 当前证据：CircleGroup/CircleGroupMembership 共 14 个 operation 无生产 UI 消费（仅 stats 只读）；R-CIRCLE-002 圈子级入圈审批命令缺失（joinPolicy=approval 旅程断裂）（matrix §17 M8-D + backlog）。缺口分类:`功能缺失/对象无承载`。
3. 对象：CircleGroup、CircleGroupMembership、CircleMembership 审批扩展；owner=circle-service。
4. 对象↔页面：circle_detail 群单元区+申请/审批面（嵌入 sheet 优先，不新增路由页则记录裁决）。
5. 旅程断点：申请入圈/群→无人可批；组织节点群不可治理。
6. 页面决策：新增承载面（P0→P4）。
7. D1 断裂→申请→审批/拒绝→加入→退出/归档全承载｜审批命令补全（metadata-first）+UI+通知回流｜owner/applicant 双视角 UAT；D2 命令缺失→JoinCircleRequest 审批状态机单轨；D3 →与 chat 群治理 IA 区分（圈子群单元≠普通群）；D4 →审批列表分页；D5 →入圈申请→审批完成率；D6 →状态机+BOLA 三层。
8. 黄金指标：群单元申请→审批完成率（圈子组下钻）。
9. 测试×环境：local=状态机；api=审批流转（beta）；UAT=组织群旅程。
10. In=审批命令+承载面；Out=chat Conversation 本体（CM-034~036）；依赖=CM-048（通知）；Exit=R-CIRCLE-002 回写+14 op 有消费或显式 deferred。

#### CM-038 CircleFile 与 PostPlacement 管理裁决（产品功能 | B03 | COMMERCIAL_MUST）

1. 定位：圈子协作资产与内容治理的可达性。
2. 当前证据：CircleFile 5 op 中浏览/创建已接（storage 区），完整更新/删除/权限旅程未证；CirclePostPlacement pin/feature 管理员动作无 UI（matrix §17 M8-B/D）。缺口分类:`功能缺失（部分）`。
3. 对象：CircleFile、CirclePostPlacement。
4. 对象↔页面：detail storage 区+内容管理动作（嵌入菜单）。
5. 旅程断点：管理员无法置顶/精选；文件治理半途。
6. 页面决策：精修（补动作入口或登记 deferred，二选一裁决）。
7. D1 半承载→文件全旅程+pin/feature 可达或 CR 记录 deferred；D2 —；D3 →权限态菜单；D4 →配额/存储水位既有契约核验；D5 →精选内容曝光占比（护栏）；D6 →owner/member 权限负例。
8. 黄金指标：不单设。
9. 测试×环境：local=权限 widget；api=placement 命令；UAT=管理员旅程。
10. In=裁决+实施；Out=—；依赖=CM-037；Exit=op 消费勾稽清零。

#### CM-039 圈子契约、性能与推荐闭环（业务对象 | B03 | COMMERCIAL_MUST）

1. 定位：圈子域工程质量与"圈子是归属"的推荐供给。
2. 当前证据：social 6 对象缺对象级 errors；R-CIRCLE-001 hub 频道页 N+1 客户端聚合与端侧过滤；R-CIRCLE-003 recommendation-service 零 circle 事件消费（圈子推荐闭环缺失）；`metadata/circle` generated 出口治理（matrix §17 + backlog）。缺口分类:`契约双轨/性能/运营缺口`。
3. 对象：social 域对象 errors、hub 聚合读模型、circle 事件→推荐投影。
4. 对象↔页面：hub/circles/stats 三页。
5. 旅程断点：hub 慢与流量放大；圈子不进推荐。
6. 页面决策：hub 精修（服务端聚合后简化端侧）。
7. D2 errors 缺→补齐+出口标注；D4 N+1→服务端聚合 API+分页预算｜hub 聚合 Slice｜性能对比报告；D5 圈子推荐断→circle 事件消费+召回通道登记（与推荐轨分工：本项只到事件/投影，排序归推荐轨）；D6 →聚合 parity 三层。
8. 黄金指标：圈子加入后 7 日有效活跃率（圈子组一级，另两项随 CM-037/064）。
9. 测试×环境：local=聚合 parity；api=事件消费投影（beta）；UAT=hub 性能旅程。
10. In=errors+聚合+事件消费；Out=推荐排序（推荐轨）；依赖=CM-064 对账；Exit=R-CIRCLE-001/003 回写。

#### CM-040 主页认领/上报结果回流（产品功能 | B03 | COMMERCIAL_MUST）

1. 定位："主页是对象"的治理闭环；申请人可感知。
2. 当前证据：HomepageClaimRequest/StatusReport 仅有提交页；无状态查询 operation/状态页/补材料/撤回/审核结果反馈（matrix §18 M9-C/D）。缺口分类:`旅程断点/功能缺失`。
3. 对象：HomepageClaimRequest、HomepageStatusReport（查询/撤回命令补全）；owner=entity-service。
4. 对象↔页面：claim/status_report 页扩展+我的申请状态面（嵌入设置或主页管理菜单，裁决记录）。
5. 旅程断点：提交后黑箱。
6. 页面决策：两页适度重构（P2→P4）。
7. D1 黑箱→提交→审核→通过/拒绝→补材料/撤回全终态+通知回流；D2 →查询/撤回 op metadata-first；D3 →材料隐私展示（脱敏）；D4 —；D5 →认领申请完成率（实体组下钻）；D6 →状态机三层+申请人 UAT。
8. 黄金指标：实体组下钻。
9. 测试×环境：local=状态机；api=流转+权限；UAT=申请人旅程。
10. In=查询/撤回+状态承载+回流；Out=Ops 审核台（运维轨）；依赖=CM-048；Exit=全状态承载勾稽清零。

#### CM-041 想去 wishlist 用户写入口（产品功能 | B03 | DIFFERENTIATOR+GATE_BLOCK）

1. 定位：C0「共同想去→约伴」差异化闭环的事实供给源；当前只有 seed 冒充。
2. 当前证据：`ContentBehaviorTracker.trackWishlistAdd/Remove` 与服务端 `entity_wishlist_events` 投影存在，但 `lib/ui/**` 零调用（intersection 计划 §5.4 GATE 格 1）；wishlist 未登记 canonical 对象；`coWishlistedEntity.privacyScope=public` 未经用户裁决。缺口分类:`对象缺失/交集差异化缺失`。
3. 对象：Wishlist intent（对象化裁决：canonical fact 或 behavior 投影显式登记）；owner=content behaviors+entity 消费。
4. 对象↔页面：homepage_detail「想去」可逆控件（嵌入，不新增页）。
5. 旅程断点：用户无法产生"想去"事实→交集 C0 分母为零。
6. 页面决策：homepage_detail 精修（控件+状态回显）。
7. D1 无入口→点亮/取消/回显+我的想去列表（承载裁决：并入足迹或独立 tab）；D2 未对象化→登记对象/投影+privacyScope 冻结（**隐私默认建议 friends/mutual 级，公开需用户确认**）；D3 →控件语义与收藏区分；D4 →幂等/防抖；D5 →想去添加率（交集组分母指标）；D6 →双用户 coWishlisted 产出 E2E。
8. 黄金指标：交集组分母（可解释交集覆盖率的输入）。
9. 测试×环境：local=控件/行为契约；api=事件→投影（beta）；UAT=双账号想去→交集出现。
10. In=入口+对象化+隐私裁决；Out=约伴承接（CM-059）；依赖=CM-057 消费、隐私裁决（用户）；Exit=真实用户可产生 coWishlistedEntity 且 E2E 绿。

#### CM-042 实体主页真实数据与热重载准出（测试准出 | B03 | GATE_BLOCK）

1. 定位：实体域"真实可运营"准出；主档真实≠四主页 populated。
2. 当前证据：R-HSE02（导入后需重启才可见）；R-IX05（四主页云侧真实内容/impact 未全闭）；R-HSE06 双省 NO-GO（数据轨主责）；R-HSE07 gamma T3 交集语义未复验。缺口分类:`环境假完成/性能与可靠性缺口`。
3. 对象：Homepage state 热重载、四主页投影、双省 release 消费。
4. 对象↔页面：entity 7 页。
5. 旅程断点：发布后旧数据窗口；四主页 seed 派生数据风险。
6. 页面决策：不改 IA。
7. D1 —；D2 —；D4 重启窗口→releaseId 触发热重载或编排受控 restart 留痕｜实现+ship 编排｜导入→可见 TTV 断言；D6 populated 未证→四主页真实内容/impact 对账+T3 复验+prod 抽检｜执行｜gamma T3 全绿。
8. 黄金指标：已发布主页有效 bundle 可用率（实体组一级）。
9. 测试×环境：api=导入→读路径（beta/gamma）；UAT=双省动态旅程；prod 抽检。
10. In=热重载+对账+T3；Out=双省内容生产（数据轨）；依赖=数据轨 release、CM-066；Exit=R-HSE02 回写+R-IX05 实体段收口。

### 4.4 B04 外部与复合能力

#### CM-043 RTC 可信鉴权环境认证与 ticket 边界（外部集成 | B04 | GATE_BLOCK）

1. 定位：实时链路可信化的环境收尾；R-CLOUD01 残余执行体。
2. 当前证据：R-CLOUD01 更新记录：本地/门禁全绿，剩 Gamma/prod 运行制品（SLS secret 后 cold-start 报告）；App `realtime_connection_ticket` 获取仍用裸 `http.Client`+失败静默 null（matrix §16 M7-B）。缺口分类:`环境假完成/技术债`。
3. 对象：Connection ticket/auth_ack；owner=realtime-gateway+chat-service。
4. 对象↔页面：websocket transport（无页面）。
5. 旅程断点：无 ticket 链路时实时通道降级语义待证。
6. 页面决策：不涉。
7. D2 裸 client→generated client+RuntimeFailure 结构化（R09/R17 口径）｜改造+负例｜dart analyze+契约测试；D6 环境证据缺→gamma cold-start 认证报告+伪造/重放/过期负例｜执行落盘｜R-CLOUD01 关闭。其余 —。
8. 黄金指标：ws 鉴权成功率（实时组下钻）。
9. 测试×环境：api=负例套件（gamma）；环境=运行制品归档。
10. In=ticket 改造+环境证据；Out=媒体面（CM-046）；依赖=SLS secret（运维轨）；Exit=R-CLOUD01 回写关闭。

#### CM-044 realtime-gateway provenance 与观测实证（外部集成 | B04 | GATE_BLOCK）

1. 定位：实时网关供应链与可观测拼图（R-CLOUD09 执行体）。
2. 当前证据：R-CLOUD09：无固定 digest/SBOM/来源验证；`prometheus.yml` 无 gateway scrape target；断连告警未演练（matrix §16 M7-E）。缺口分类:`可观测缺口/供应链`。
3. 对象：gateway 构建制品、scrape/告警配置。
4~6. 不涉页面/旅程。
7. D5 观测缺→scrape target+断连/失败率告警+演练记录｜配置经运维轨 owner 提交｜告警实证；D2 供应链→固定 digest+SBOM+provenance｜流水线改造｜制品核验。其余 —。
8. 黄金指标：gateway 可用性（实时组护栏）。
9. 测试×环境：环境=beta/gamma scrape 可见+prod 演练。
10. In=制品+观测；Out=Prometheus 平台部署（运维轨）；依赖=CM-004（Prometheus owner 机制）；Exit=R-CLOUD09 回写。

#### CM-045 三端离线来电矩阵（外部集成 | B04 | GATE_BLOCK）

1. 定位：通话商用可用性的决定性缺口（R-RTC01 执行体）。
2. 当前证据：R-RTC01：iOS PushKit/Android FCM/Web Push 全链未实现；callkit UI 仅前台在线可达（registry `cap.os.callkit_incoming` 备注一致）。缺口分类:`功能缺失/外部集成`。
3. 对象：CallRinging push policy、DeviceRegistration（push token）、平台唤醒回调。
4. 对象↔页面：incoming_call_page+系统级来电 UI。
5. 旅程断点：后台/锁屏/被杀来电全丢。
6. 页面决策：不新增页面；系统面接线。
7. D1 全丢→三端唤醒或按平台显式降级声明｜policy+token 注册+VoIP 通道+去重防重响｜真机三态矩阵；D2 →ringing push 契约 metadata-first；D4 →唤醒时延预算；D5 →来电唤醒成功率；D6 →离线接听/拒接/超时三层。
8. 黄金指标：离线来电唤醒成功率（实时组一级之一）。
9. 测试×环境：UAT=真机后台/锁屏/杀进程（gamma-local+prod gray）。
10. In=三端唤醒链；Out=push provider 本体（CM-047 共用凭据）；依赖=CM-047、Apple VoIP 凭据（外部）；Exit=R-RTC01 回写。

#### CM-046 RTC 入口矩阵、QoE 与真机媒体准出（产品功能 | B04 | COMMERCIAL_MUST）

1. 定位：通话体验商用化（入口可达+质量可观测）。
2. 当前证据：入口仅会话页 AppBar（主页/圈子/通话记录无）；R-RTC02 QoE 黄金指标与告警缺失；32 人上限/弱网重连无真机证据；realtime-call 无 Scenario 绑定（matrix §16 M7-C/E）。缺口分类:`旅程断点/可观测缺口`。
3. 对象：CallSession/CallParticipant/CallInvitation。
4. 对象↔页面：rtc 5 页+入口矩阵。
5. 旅程断点：非会话场景发起通话不可达；通话质量黑盒。
6. 页面决策：5 页保留精修（P2/P3→P4）；入口按裁决补。
7. D1 入口窄→入口矩阵裁决+实现（含通话记录回拨）｜矩阵+UAT；D2 Scenario 缺→registry 补绑定或显式并入 message Scenario（经 CM-002 owner）；D3 →双端通话页真机核验；D4 32 人未证→压测+弱网重连报告；D5 QoE 缺→接通率/首帧时延/MOS 或丢包代理+告警｜R-RTC02 执行；D6 →双设备媒体互通 UAT。
8. 黄金指标：①通话接通率 ②接通→首帧 P95 ③通话中断率。
9. 测试×环境：api=LiveKit 集成（beta）；UAT=双真机互通+弱网（gamma-local）。
10. In=入口+QoE+真机证据；Out=离线唤醒（CM-045）；依赖=CM-043/044/045；Exit=R-RTC02 回写+Scenario 勾稽闭合。

#### CM-047 Push 外送 provider 决策与实装（外部集成 | B04 | GATE_BLOCK）

1. 定位：触达能力的商用决定项（R-OBJ-003 deferred 清算）。
2. 当前证据：registry：`ext.push.apns/fcm/vendor` 全 planned、`ext.push.mock` 仅 mock；notification-service `NoopDeliveryAdapter`；App 无 firebase_messaging/APNs token 注册。缺口分类:`外部集成/功能缺失`。
3. 对象：push_delivery 契约（已有 metadata）、DeviceRegistration token、DeliveryJob。
4. 对象↔页面：系统推送面+settings 通知偏好联动。
5. 旅程断点：App 未打开时全部触达断（消息/审核/交集/来电共享此底座）。
6. 页面决策：不新增页面。
7. D1 无外送→APNs/FCM 真实投递或**经批准的显式延期**（当前站内闭环单轨已声明，商用放量前必须重决策）｜凭据→adapter→token 生命周期→回执｜真机到达率；D2 →provider attempt 审计单轨（对齐 external_interaction）；D4 →频控/合并策略；D5 →推送到达率+点击率；D6 →投递回执 api_integration+真机 UAT。
8. 黄金指标：推送有效到达率（通知组一级）。
9. 测试×环境：api=investigation provider sandbox（beta）；UAT=真机锁屏到达（gamma/prod gray）。
10. In=决策+实装（或批准延期记录）；Out=站内 inbox（CM-048）；依赖=Apple/Google 凭据（外部）、CM-052；Exit=R-OBJ-003 push 段回写。

#### CM-048 站内信七源闭环准出 [验证型]（测试准出 | B04 | COMMERCIAL_MUST）

1. 定位：站内触达（对象事件→通知→已读→跳转）当前版本准出。
2. 当前证据：七源（评论/点赞/关注/greeting/群邀/审核/交集）→inbox 已实现（B11 收口记录）；`delivery_job` 无 errors.yaml；失效目标跳转/重复事件幂等/多端已读同步无当前证据（matrix §22 M13）。缺口分类:`测试缺口/契约小缺`。
3. 对象：Notification、NotificationDeliveryJob、UserSettings 偏好联动。
4. 对象↔页面：通知中心（chat 承载）+红点。
5. 旅程断点：待核验——失效目标解释性终态。
6. 页面决策：保留。
7. D1 U→七源逐源到达/跳转/失效终态；D2 errors 缺→补 delivery_job errors；D4 →重复投递幂等负例；D5 →通知点击率（下钻 source）；D6 U→逐源三层矩阵。
8. 黄金指标：站内通知点击转化率。
9. 测试×环境：local=investigation 映射；api=七源事件重放（beta）；UAT=红点→已读→跳转。
10. In=准出+errors；Out=push 外送（CM-047）；依赖=CM-034；Exit=七源矩阵全绿。

#### CM-049 出站分享 MVP（产品功能 | B04 | COMMERCIAL_MUST）

1. 定位：增长闭环的出站一半；`outbound-object-share-distribution` scenario（draft）落地。
2. 当前证据：scenario 处 draft；分享面板/分享卡/归因 token 未成体系（matrix §23 M14）；OutboundShareFact 对象未落 metadata。缺口分类:`功能缺失/对象缺失`。
3. 对象：OutboundShareFact（新）、share token（归因）；消费 link_templates。
4. 对象↔页面：四对象（post/homepage/circle/profile）分享面板挂靠面。
5. 旅程断点：站内→站外表达断。
6. 页面决策：分享面板系统化（挂靠面，随宿主页验收）。
7. D1 断→分享面板→渠道（系统分享/复制链接/口令）→落地一致；D2 →fact+token metadata-first；D3 →分享卡模板（标杆：小红书口令/微信卡片）；D4 →卡片生成时延；D5 →分享率+回流率（与 CM-011 共组）；D6 →分享→深链回流 E2E。
8. 黄金指标：①对象分享率 ②分享→回流转化率（M14 组，与 CM-011 共享第 3 指标解析成功率）。
9. 测试×环境：local=token/模板；api=归因事实；UAT=真机分享→another 设备回流。
10. In=MVP 渠道+归因；Out=Web 落地承接（CM-050）；依赖=CM-011（回流侧）、scenario 从 draft 转 specified（CM-002 owner）；Exit=E2E 归因链绿。

#### CM-050 Web 安装转化与公开对象页（产品功能 | B04 | COMMERCIAL_MUST）

1. 定位：站外承接与 SEO 获客（`public-web-seo-install-conversion` draft 落地）。
2. 当前证据：web shell 目标保留（R-XP 断点体系就绪）；公开对象投影/install banner/安装后还原未实现（matrix §23）。缺口分类:`功能缺失`。
3. 对象：公开只读投影（脱敏 Slice）、install handoff（延迟深链）。
4. 对象↔页面：web 公开页+banner；App 安装后还原链（CM-011 pending replay 复用）。
5. 旅程断点：站外链接→未装用户→装后还原全断。
6. 页面决策：新增 web 公开对象页（P0→P3 首版）。
7. D1 断→未装引导+装后还原；D2 →公开投影脱敏契约（隐私门槛：仅 public scope 字段）；D3 →SEO meta/OG 卡；D4 →公开页 TTFB 预算；D5 →安装转化率；D6 →双态（已装/未装）UAT。
8. 黄金指标：分享落地→安装转化率（M14 组下钻）。
9. 测试×环境：api=公开投影脱敏断言；UAT=真机未装→装→还原。
10. In=公开页+banner+还原；Out=全量 Web 版（跨平台轨长期）；依赖=CM-011/049；Exit=scenario 验收绑定回填。

#### CM-051 精确坐标隐私修复（平台横切·安全隐私 | B04 | GATE_BLOCK）

1. 定位：位置隐私商用底线；当前为全链明文。
2. 当前证据（本轮逐文件复核）：`integration/location/fields.yaml` 精确 `latitude/longitude` classification=PUBLIC 且 `logging.allow`；`contracts/metadata/log_kv_policy.yaml` `lat/lng: plain`；`location_service.go` reverse-geocode 把精确坐标写 trace attribute；`content/post/fields.yaml` location 含精确坐标 vs `privacy.yaml` 声明 city-level 矛盾。缺口分类:`安全隐私`。**风险登记：候选新 R-*，待用户确认后由总控写入 backlog（16 号军规）。**
3. 对象：Location 值对象字段策略、log_kv policy、trace 属性、Post.location 契约。
4. 对象↔页面：位置选择/附近/发布链（行为不变，数据面收紧）。
5. 旅程断点：无功能断点；合规断点。
6. 页面决策：不改页面。
7. D2 契约矛盾→精确输入/粗化输出单轨（Post 存储精确、wire 输出 city/geohash 分级）｜metadata 修正→codegen→读路径分级｜契约测试；D5 日志明文→lat/lng drop 或 geohash 粗化+trace 脱敏+扫描门｜log_kv+代码修复+`verify` 扫描｜零明文取证；D6 →隐私负例（未授权 viewer 拿不到精确坐标）。其余 —。
8. 黄金指标：护栏=日志/trace 精确坐标出现次数=0。
9. 测试×环境：local=字段策略契约；api=读路径分级断言（beta）；环境=日志抽样取证（gamma/prod）。
10. In=四处修复+扫描门；Out=LBS 新功能（保持 deferred）；依赖=用户确认风险登记、CM-004（metadata owner）；Exit=扫描零命中+矛盾契约单轨+backlog 登记完成。

#### CM-052 ExternalInteraction 状态机与死信面（业务对象 | B04 | COMMERCIAL_MUST）

1. 定位：外发交互（SMS/push/webhook）审计底座的名实一致。
2. 当前证据：aggregate 状态机与 fields.yaml 枚举漂移（`delivered/compensated` vs `succeeded/failed/dead_letter`）；`RequeueExternalInteractionDeadLetter` 无消费者（死信只能改库）；webhook provider planned（matrix §27 M18-B/C）。缺口分类:`契约双轨/运维缺口`。
3. 对象：ExternalInteraction、ExternalInteractionAttempt、DLQ 恢复命令。
4. 对象↔页面：operator 消费面（Portal/CLI，经运维轨 owner）。
5. 旅程断点：死信恢复无面。
6. 页面决策：不新增 App 页面。
7. D2 枚举漂移→单轨闭集｜metadata 对齐+codegen｜verify；D1 死信断→operator 可恢复（CLI 优先）｜恢复命令消费面｜恢复演练；D5 →attempt ledger 指标；D6 →DLQ 重放 api_integration。其余 —。
8. 黄金指标：外发交互终态率（护栏）。
9. 测试×环境：api=DLQ 恢复演练（beta）。
10. In=对齐+恢复面；Out=webhook 真实投递（依赖业务需求，先登记）；依赖=运维轨 Portal；Exit=枚举单轨+演练记录。

#### CM-053 助手运行时可信化（产品功能 | B04 | GATE_BLOCK）

1. 定位：助手作为差异化入口的可信运行时（R-ASSIST-001~004 执行体）。
2. 当前证据：R-ASSIST-001 会话生命周期端云断链（无查询面/本地双模型/无取消）；002 工具假实现与硬编码 grounding；003 模型日志泄敏+业务告警缺口；004 非 token 级流式+SSE 断线整条重发。缺口分类:`功能缺失/技术债/安全隐私/可观测缺口`。
3. 对象：AssistantConversation/Run/工具调用面；owner=assistant-service。
4. 对象↔页面：assistant 4 页+half sheet。
5. 旅程断点：历史会话不可回放；长回答不可取消；断线重耗。
6. 页面决策：页面保留精修；修复集中在运行时。
7. D1 断链→会话查询面+取消+断线续传；D2 假工具→真实实现或能力位摘除（诚实降级）；D3 —；D4 →token 级流式+重连预算；D5 泄敏→日志脱敏+助手 SLI 告警；D6 →流式/取消/脱敏三层+gamma 真栈。
8. 黄金指标：①助手回答完成率（无中断）②首 token P95 ③工具调用成功率。
9. 测试×环境：local=运行时契约；api=SSE 断线续传（beta）；UAT=长会话真机。
10. In=四项修复；Out=外部依赖迁移（CM-055）；依赖=CM-055 可并行；Exit=R-ASSIST-001~004 逐项回写。

#### CM-054 助手 consent 负测与页面准出（测试准出 | B04 | COMMERCIAL_MUST）

1. 定位：R-CLOUD02 残余（gamma 负测）收口。
2. 当前证据：R-CLOUD02 更新记录：契约/实现/页面 UAT 已闭，剩 gamma 环境撤权→拒绝→失败关闭负例。缺口分类:`环境证据`。
3~6. 对象=SkillConsent；页面=management/inline gate（保留）。
7. D6 gamma 负测缺→gamma api_integration 撤权链路负例落盘+backlog 回写。其余已闭维持。
8. 黄金指标：consent 越权阻断率=100%（护栏）。
9. 测试×环境：api=gamma 负测。
10. In=负测执行；Out=—；依赖=gamma 栈（CM-043 同窗）；Exit=R-CLOUD02 关闭。

#### CM-055 助手外部依赖统一治理（外部集成 | B04 | COMMERCIAL_MUST）

1. 定位：registry §7.2 五组 violation 的清算（LLM/搜索/天气/金融/embedding）。
2. 当前证据：`ext.llm.xiaomi_mimo`、`ext.search.duckduckgo_html/bing_rss`、`ext.weather.*`、`ext.finance.yahoo_chart` 均 domain-direct violation；DuckDuckGo HTML 抓取稳定性/审计性不足。缺口分类:`外部集成治理`。
3. 对象：assistant 外部 Port+attempt ledger。
4~6. 不涉页面。
7. D2 直连→统一治理出口（integration-service 扩展或同等 Port+审计）或逐条显式豁免登记｜Port 归置+registry 回写｜registry 合规复核零 violation 或全豁免；D4 →厂商超时/降级预算；D5 →外部调用审计指标；D6 →降级链 local+真实调用 api（beta）。
8. 黄金指标：助手外部依赖降级命中率（护栏）。
9. 测试×环境：api=provider 降级链。
10. In=五组治理；Out=向量/embedding 启用（推荐轨）；依赖=CM-052/056；Exit=registry 状态回写。

#### CM-056 外部依赖登记自动校验门禁（平台横切 | B04 | COMMERCIAL_MUST）

1. 定位：external registry 的防腐门（registry §10-P1-3）。
2. 当前证据：新增厂商域名/SDK/配置无自动扫描；registry 靠人工维护。缺口分类:`门禁缺口`。
3. 对象：`docs/external_service_registry.yaml`+扫描脚本。
4~6. 不涉。
7. D2 人工维护→扫描 lib/services/data 新增外部 endpoint/SDK，未登记 gate 阻断｜脚本+gate 接入（归 `quwoquan_ops/gate/`）｜负例演示（注入未登记域名被阻断）。
8~9. repo gate。
10. In=脚本+接线；Out=逐条依赖整改（CM-007/047/055）；依赖=—；Exit=gate 常绿+误报率可控。

### 4.5 B05 交集差异化

#### CM-057 交集真实数据先决与契约名实收口（业务对象 | B05 | DIFFERENTIATOR+GATE_BLOCK）

1. 定位：交集体系的分母与契约底座（WP-IX-0+WP-IX-1）；一切交集页面/指标的前置。
2. 当前证据：R-IX09（27 active kind 中 18 个无数据源产出）；R-IX08（构造级 dart-define 凭证回退+smoke 与带鉴权栈不兼容）；2026-07-20 端云验证暴露 Explain 回退链/inbox spans/seed 档案三缺陷（intersection 计划 §11.3）；R-ID02 分层 schema、R-ID09 读放大预算。缺口分类:`对象或聚合跑偏/交集差异化缺失`。
3. 对象：ObjectIntersections 读模型、kind registry、交集事实投影族；owner=recommendation/user 交集面。
4. 对象↔页面：七触点消费（inbox/主页卡/首页 chip/搜索 Tab/视频书句/launcher/impact）。
5. 旅程断点：可展示交集覆盖率过低→所有触点空态。
6. 页面决策：不动页面（页面归 CM-058）。
7. D1 密度不足→seed 档案+真实事实源梳理；D2 名实不符→18 kind 逐一裁决（接源/显式 deferred 摘牌）+Explain/inbox/Mock host 同步修复+凭证单轨｜WP-IX-0/1 全量｜kind 对账表+契约测试；D4 →读放大预算冻结（R-ID09）；D5 →可解释交集覆盖率（分母指标）；D6 →Mock↔Remote 一致性契约（缺陷 3 防回归）。
8. 黄金指标：可解释交集覆盖率（活跃 viewer 中 ≥1 可展示 fact 的占比）。
9. 测试×环境：local=kind/Explain 契约；api=gamma 真栈 fact 断言；环境=seed 档案对账。
10. In=WP-IX-0/1；Out=页面重构（CM-058）、行动（CM-059）；依赖=CM-041（wishlist 源）、推荐轨；Exit=R-IX08/09 回写+三缺陷修复。

#### CM-058 交集配对主入口完全重构（UX 重构 | B05 | DIFFERENTIATOR）

1. 定位：交集差异化的旗舰页面（launcher P1→P5，WP-IX-2）。
2. 当前证据：`interest_match` launcher 为纯导流三入口（无真实机会/信号）；R-ID10 impact 证据列表页缺失（P0 新增，归 CM-059 附属）。缺口分类:`页面成熟度不足/差异化缺失`。
3. 对象：交集机会读模型（消费 CM-057）。
4. 对象↔页面：launcher 完全重构+机会卡；空态诚实。
5. 旅程断点：入口无价值→差异化不可感知。
6. 页面决策：完全重构（P1→P5）。
7. D1 导流壳→真实机会卡→行动承接（约伴/打招呼/进圈）；D2 →只消费 CM-057 读模型（禁伪造候选）；D3 →P5 视觉（真机双色核验，intersection 计划 §11.1 探针基线复用）；D4 →首屏机会卡 TTI 预算；D5 →launcher→行动转化率；D6 →登录/未登录+有/无信号双态 UAT+零伪候选断言保留。
8. 黄金指标：交集入口→有效行动转化率。
9. 测试×环境：local=widget 双态；api=机会数据真实断言；UAT=真机双态。
10. In=WP-IX-2；Out=约伴状态机（CM-059）；依赖=CM-057；Exit=页面 P5 评级+双态证据。

#### CM-059 约伴行动闭环与安全门（产品功能 | B05 | DIFFERENTIATOR+GATE_BLOCK）

1. 定位：C0「共同想去→约伴」的行动闭环（WP-IX-3）；R-PLAZA-001 安全门执行体。
2. 当前证据：约伴仅 route extra 进普通建群（无候选/请求/同意状态机）；安全门（login/realName/minorMode/blocked/rateLimit）声明存在但不执行；impact 证据列表页缺失（P0）。缺口分类:`功能缺失/安全隐私`。
3. 对象：CompanionCandidate/CompanionRequest（新对象 metadata-first）+安全门 policy。
4. 对象↔页面：约伴承接面（最薄）+impact 证据列表页（新增 P0→P4）。
5. 旅程断点：共同想去→无法约伴成行。
6. 页面决策：新增两面（承接+impact 列表）。
7. D1 断→候选→请求→双向同意→会话/群创建+交集归因事件；D2 →状态机 metadata-first 单轨；D3 →承接面轻量（不打断宿主）；D4 →候选计算预算；D5 →约伴请求→成行率；D6 →双用户 E2E+青少年模式/拉黑/频控负例全绿。
8. 黄金指标：约伴发起→双向同意成行率。
9. 测试×环境：local=状态机+安全门；api=双账号流转（beta/gamma）；UAT=双真机成行+负例。
10. In=WP-IX-3+安全门执行；Out=LBS 附近（保持 deferred）；依赖=CM-041/057/058、CM-014（拉黑语义）；Exit=R-PLAZA-001 回写+C0 E2E 绿。

#### CM-060 交集北极星观测与灰度（平台横切 | B05 | DIFFERENTIATOR）

1. 定位：差异化是否成立的度量体系（WP-IX-4；R-IX10 执行体）。
2. 当前证据：R-IX10：connection-formed 不可归因、漏斗后两级（行动→关系形成）无观测、无大盘、无 kill-switch。缺口分类:`可观测缺口`。
3. 对象：`connection-formed-via-intersection` 事件→投影→recording rule→大盘；灰度开关。
4~6. 不涉页面。
7. D5 缺位→北极星+按动作类型拆分+护栏反指标（骚扰举报率）+kill-switch｜WP-IX-4｜recording rule 在线可算+灰度演练记录。其余 —（D6=事件契约+对账测试）。
8. 黄金指标：北极星=经由交集形成的连接数（connection-formed-via-intersection）。
9. 测试×环境：api=指标可读；环境=大盘回放+kill-switch 演练。
10. In=WP-IX-4；Out=推荐排序实验（推荐轨）；依赖=CM-003/057/059；Exit=R-IX10 回写。

#### CM-061 交集三层测试与四环境收口（测试准出 | B05 | DIFFERENTIATOR）

1. 定位：交集全链证据化（WP-IX-5）。
2. 当前证据：`intersection_remote_smoke__api_integration_test.dart` 在带鉴权栈恒 401（证据通道失效）；Mock↔Remote 一致性缺口（displayBinding 收紧未同步四配套面）。缺口分类:`测试缺口`。
3~6. 对象=交集全链测试资产；不涉页面。
7. D6 通道失效→smoke 改 canonical 鉴权+事实真实性/隐私（fact 可见性）/双用户三层矩阵+beta 执行证据｜WP-IX-5｜alpha fixture+gamma Remote+设备全绿。
8. 黄金指标：不适用。
9. 测试×环境：三层×四环境执行本体。
10. In=WP-IX-5；Out=—；依赖=CM-057~059；Exit=交集组 acceptance recorded 回填。

#### CM-062 首次兴趣先验承载（产品功能 | B05 | GATE_BLOCK）

1. 定位：冷启动推荐质量与交集供给的入口（M17-C P0）。
2. 当前证据：`interest-onboarding-prior` Story 规格自相矛盾（GWT 要求先验联动 vs Out-of-scope 排除采集 UI）；无任何承载页面；游客兴趣合并语义未定义（matrix §26）。缺口分类:`功能缺失/规格双轨`。
3. 对象：兴趣先验（user profile 先验字段+TagCatalog 消费）。
4. 对象↔页面：首次进入选择/跳过面（新增，welcome 后或首页首刷前，位置裁决记录）。
5. 旅程断点：新用户首刷靠默认兜底；交集"共同兴趣"维度供给弱。
6. 页面决策：新增（P0→P4，可跳过）。
7. D1 缺→选择/跳过+游客合并+首刷生效；D2 规格矛盾→先修 Story 规格单轨；D3 →选择面轻量（标杆：小红书兴趣选择）；D4 →首刷生效时延；D5 →先验非空率+首刷点击率提升；D6 →新用户/游客合并双态 UAT。
8. 黄金指标：新用户先验非空率（交集/推荐组下钻）。
9. 测试×环境：local=选择面 widget；api=画像写入→首刷（beta）；UAT=新装机旅程。
10. In=规格修正+页面+写入链；Out=推荐排序消费（推荐轨）；依赖=CM-063（目录）；Exit=规格单轨+新用户旅程绿。

#### CM-063 TagFeedback 消费链与 taxonomy 收口（业务对象 | B05 | COMMERCIAL_MUST）

1. 定位：兴趣/标签域的闭环与生命周期洁净（M17-B/D）。
2. 当前证据：TagFeedback 有 REST 无 publisher/checkpoint（推荐管线消费不到）；TaxonomyRelease 切换原子性/失效 tag refs 迁移语义未冻结；tag-service 无 `tests/local_contract` 根（matrix §26）。缺口分类:`关系或生命周期不完整/测试缺口`。
3. 对象：TagFeedback、TagCatalog/TaxonomyRelease；owner=tag-service。
4. 对象↔页面：兴趣编辑嵌入承载（既有）。
5. 旅程断点：负反馈不改变推荐——用户感知"说了不算"。
6. 页面决策：不新增页面。
7. D1 反馈死链→feedback→推荐画像生效（可感知）；D2 release 语义→切换原子性+失效 refs 迁移单轨；D4 →目录缓存失效预算；D5 →负反馈生效率；D6 →目录测试补根+release 切换/回滚测试。
8. 黄金指标：负反馈 24h 生效率（推荐组护栏）。
9. 测试×环境：local=tag-service 契约补齐（随 CM-005 目录）；api=feedback→投影→feed 对账。
10. In=publisher+消费+release 语义+测试；Out=创作 tag 入口（CM-026）；依赖=CM-005；Exit=反馈闭环对账绿。

### 4.6 B06 全局回归与准出

#### CM-064 推荐消费侧对账与 AB 单轨（测试准出 | B06 | COMMERCIAL_MUST）

1. 定位：推荐"端到端可归因"的消费侧清算；与推荐平台轨（W1-W13、R-IX01~04）明确分工。
2. 当前证据：推荐计划 §0：服务端 13 项多数完成；消费侧残余：R-OBJ-004 AB 分桶双轨（`ExperimentAssignment` vs 行为管线 hash 分桶）、circle 事件零消费（R-CIRCLE-003，事件侧归 CM-039）、行为信号端云字段差（feedRequestId 归因链）。缺口分类:`契约双轨/运营缺口`。
3. 对象：曝光/行为事件、AB assignment、推荐解释面。
4. 对象↔页面：feed/viewer 消费面（不改 IA）。
5. 旅程断点：无；归因链断是运营断点。
6. 页面决策：不改。
7. D2 分桶双轨→单轨裁决+登记（推荐轨执行，本项验收）；D5 归因断→曝光→点击→行为→回流 SLS/Prom/Behavior 三轨对账演练｜对账脚本+演练｜对账报告；D6 →端云字段 parity 契约。
8. 黄金指标：行为回流对账一致率（护栏）。
9. 测试×环境：api=对账断言（beta/gamma）。
10. In=消费侧对账+裁决登记；Out=模型/召回（推荐轨）；依赖=CM-024（事件底座）、推荐轨；Exit=R-OBJ-004 回写+对账演练归档。

#### CM-065 App api_integration 全域扩面（测试准出 | B06 | GATE_BLOCK）

1. 定位：端云契约真实性的最终防线。
2. 当前证据：App `test/api_integration` 全仓 9 文件（assistant 5/content 2/intersection 1/user 1——matrix §9 复核）；消息/圈子/搜索/设置/通知/RTC 版块为零。缺口分类:`测试缺口`。
3~6. 对象=各版块 Remote 契约；不涉页面。
7. D6 覆盖极薄→每版块 ≥读/写/结构化失败三断言+与 local Mock parity 勾稽（R12 一体性）｜依赖各域 CM 合流后统一补面｜`ENV=gamma-local make test-api-integration-app` 全绿。
8. 黄金指标：不适用。
9. 测试×环境：api=gamma-local 真栈。
10. In=扩面+parity 勾稽；Out=各域功能（前置 CM）；依赖=CM-005 入口、B02~B05 完成度；Exit=版块覆盖表全绿。

#### CM-066 gamma-local 全量旅程回归（测试准出 | B06 | GATE_BLOCK）

1. 定位：11 Journey 的镜像环境总回归。
2. 当前证据：R-UPROF-004（gamma 设备矩阵无用户主页旅程）；R-HSE07（T3 交集语义未复验）；R-CLOUD06（rtc/assistant/discovery UAT 存在性断言残余）；gamma patrol 无发布/深链旅程。缺口分类:`环境假完成`。
3~6. 对象=patrol 套件+设备矩阵；不涉页面。
7. D6 缺旅程→patrol 补齐（发布/深链/主页/交集 T3）+存在性 UAT 升级语义断言+11 Journey 全量执行落盘｜执行+报告归档+acceptance 回填｜全绿或如实 GATE_BLOCKED。
8. 黄金指标：不适用。
9. 测试×环境：gamma-local 全量+真机矩阵。
10. In=补旅程+全量执行；Out=功能修复（回各 CM）；依赖=B01~B05 出口、CM-042；Exit=R-UPROF-004/R-HSE07/R-CLOUD06 回写。

#### CM-067 prod gray canary 与 READY 复评（测试准出 | B06 | GATE_BLOCK）

1. 定位：商用准出的最后一门与本文 §1 结论的复评点。
2. 当前证据：R-TELEMETRY-001（真实 SLS 遥测零证据）；R-OPS-SLO-READBACK/GRAY-ROLLBACK-EXEC/OBS-STACK 等运维轨未闭合；prod 仅 health 探针级证据。缺口分类:`环境假完成（生产）`。
3~6. 对象=prod gray rollout 证据链；不涉页面。
7. D5/D6 生产黑盒→gray-initial canary（真实设备+真实遥测）→SLO readback→回滚演练→READY/NOT_READY 复评回写本文 §1｜依赖运维轨平台就绪后执行｜prod runs 制品+复评记录。
8. 黄金指标：消费全局 SLO（启动安全终态率/核心旅程成功率/崩溃率）。
9. 测试×环境：prod gray。
10. In=canary+复评；Out=平台部署（运维轨）；依赖=运维轨 R-OPS 系列、R-TELEMETRY-001、B06 前置项；Exit=本文 §1 结论更新并注明日期与证据。

## 5. 批次执行表（任务 §6.5）

> 并行规则：同批次内 CM 可并行，但共享面写入按 §0.4 owner 串行；跨批次依赖必须在前置批次出口检查通过后启动（个别显式标注"可提前并行"的除外）。外部阻断项（凭据/法务/设备/第三方）在批次内先行启动其非阻断部分，阻断部分如实标 GATE_BLOCKED 不得伪造完成。

| 批次 | 主题 | CM 项 | 进入条件 | 出口检查 |
|---|---|---|---|---|
| B01 | 横切契约冻结 | CM-001～006 | 本文冻结 | test-specs/coverage-map/页面门常绿；CM-003 目录合入；owner 表生效；幽灵 planned 清零 |
| B02 | 身份、壳与对象基座 | CM-007～018 | B01 出口（CM-003/004 必须；002/005/006 可并行收尾） | 登录/账号安全/Persona/设置组三层证据回填；深链 acceptance 转 recorded；R-OBJ-006/R-UPROF-001/002 回写；外部阻断项(R-AUTH-001/R-LEGAL-001)状态如实 |
| B03 | 核心旅程 | CM-019～042 | B02 出口（身份可用）；CM-019/020/021/034 可与 B02 后半并行 | 创作 registry 登记+回流 UAT；视频 GATE-V1 关闭；搜索"搜得到"；消息 readiness 翻牌；圈子审批承载；实体 R-HSE02 回写；发布四环境证据 |
| B04 | 外部与复合能力 | CM-043～056 | B01 出口；CM-047/051/052/056 可与 B03 并行；CM-045 依赖 CM-047 | RTC R-CLOUD01/09 回写；push 决策落地；分享/Web 双向闭环；坐标隐私扫描零命中；助手 R-ASSIST 回写 |
| B05 | 交集差异化 | CM-057～063 | CM-041（B03）+CM-003；CM-062/063 可与 B03 并行 | 北极星在线可算；C0 双用户成行 E2E；launcher P5；R-IX08/09/10、R-PLAZA-001 回写 |
| B06 | 全局回归与准出 | CM-064～067 | B02～B05 出口+运维轨平台就绪 | gamma 全量旅程绿；App api_integration 版块全覆盖；prod gray canary 证据；§1 结论复评回写 |

## 6. 启动提示词包（任务 §6.6）

### 6.0 共享执行契约（每个 CM 会话提示词的固定前缀）

```text
你在 quwoquan 仓库执行商用准出清单项 {CM-ID}。唯一执行合同是
docs/commercial_maturity_master_plan.md §4 中 {CM-ID} 的十要素卡（先完整读卡再动手），
本提示词只补充变量，不覆盖卡内容。

强制约束：
1. metadata-first：字段/错误码/path/operation/surface/route 先改 quwoquan_service/contracts/metadata/**，
   经 make verify 后 codegen，再写业务逻辑；禁止手改 generated。
2. 共享面 owner：按总控 §0.4 执行；你不是 owner 的共享文件只产出变更请求（patch 摘要贴入 Exit Report），
   不直接提交写入。
3. 风险账本：解决 R-* 必须回写 docs/outstanding_risks_backlog.md（勾选+日期+证据）；
   发现新长期风险先向用户复述 事项/原因/影响，确认后才登记。
4. 证据诚实：三层测试（local_contract/api_integration/user_acceptance）×四环境证据按卡内矩阵执行并落盘
   .qwq_output/env/**/runs；无法执行的层级如实标 GATE_BLOCKED 及原因，禁止动态 skip、存在性断言或伪造。
5. 完成定义：卡片要素 10 的 Exit 条件全部满足 + 对应 acceptance.yaml recorded 回填 +
   与触达范围匹配的 make gate 子集绿。
6. 收尾必做：更新总控 §7 追踪表中 {CM-ID} 行（状态/最后验证日期/commit/Exit Report 路径/未关闭 gate），
   并按 AGENTS.md Exit Review 七项汇报。
```

### 6.1 B01 变量块

```text
CM-001：RTC 分层 Story 边界与证据收敛复核。底料=matrix §16、specs/feature-tree/chat-conversation/realtime-call/**。
范围内=四个产品 Story 与四个 parent--contract Story 的边界/GWT/引用复核；范围外=RTC 功能实现。
结论基线=八节点是合法 L3 扁平化，不得机械删除合同 Story。owner=CM-002（registry/acceptance 面）。
```

```text
CM-002：acceptance planned/recorded 全量对账。底料=matrix §9(H2-4)、backlog R-OPS-ACCEPTANCE-PHANTOM、
video 计划 GATE-V4。范围内=全仓 acceptance 扫描门+幽灵清理；范围外=补写各域测试本体（登记给对应 CM）。
完成基线=planned 文件必须存在、recorded 必须 canonical/可定位、缺失 acceptance fail-closed；不得登记未来占位文件。
依赖=无。owner=你（Journey/Scenario+跨域 acceptance 面）。
```

```text
CM-003：H1 观测事件与指标目录冻结。底料=matrix §8 全文（图一规格）、ops/event_record/event_catalog.yaml、
backlog R-OBJ-001。范围内=ANR/TTI/恢复页事件契约+App 采集+黄金指标登记规则+覆盖门脚本；
范围外=SLS/Prometheus 平台部署（运维轨）、各业务指标实例。依赖=与运维轨 M0 去重（先读
docs/ops_capability_environment_consumer_matrix.md）。owner=你（event catalog 面）。
```

```text
CM-004：共享真相源 owner 与合流机制。底料=总控 §0.4、backlog R-HSE04/R-CLOUD04。
范围内=owner 表落地到各批启动包+拓扑 YAML 原子写快检+批次出口清单模板；范围外=各共享面内容变更。
依赖=无。owner=总控。
```

```text
CM-005：api_integration 统一入口与缺失测试目录。底料=matrix §9(H2-A/1)、backlog R-TST05。
范围内=远端 preflight fail-fast+circle/rtc/tag local_contract 根+realtime-gateway api_integration+
notification 内层测试（真实测试，禁空 wrapper）；范围外=App api_integration 扩面（CM-065）。
依赖=stackctl/CI secret 现状如实记录。owner=各服务目录归属服务。
```

```text
CM-006：测试旧口径校准与 legacy burn-down。底料=matrix §9(H2.7)、backlog R-TST04/R-TST07。
范围内=文档与磁盘一致化+旧命名棘轮门；范围外=物理迁移执行（按扫描结果另立）。
依赖=CM-002 同窗协调。owner=specs/03_TESTING_STRATEGY.md 及 testinfra spec。
```

### 6.2 B02 变量块

```text
CM-007：商用登录凭据与第三方 provider 收口。底料=matrix §10(M1)、backlog R-AUTH-001、
docs/external_service_dependency_registry.md §7.2/7.5。范围内=凭据注入+wechat/apple/one-tap/SMS
provider 收口+四环境登录准出；范围外=注销/数据权利(CM-015)、账号安全页准出(CM-008)。
依赖=外部凭据（无凭据部分如实 GATE_BLOCKED，先做 adapter 归置与负例）。owner=user+integration metadata。
```

```text
CM-008：账号安全与凭证管理准出[验证型]。底料=matrix §24 settings 组、
lib/ui/settings/pages/settings_account_security_page.dart。范围内=真机 UAT+最后凭证/会话撤销/并发负例
证据补齐；范围外=新功能。依赖=CM-007（社交凭证行复验在其后）。
```

```text
CM-009：Persona 对象绑定与生命周期收口。底料=matrix §10(M1-B/C)、
_shared/page_object_contract.yaml#user.persona_management。范围内=合同绑定修正+961 行页拆分+
退役/并发终态；范围外=Persona 关系图（CM-014）。依赖=CM-004（contract owner 申请）。
```

```text
CM-010：Welcome 身份四态规格裁决。底料=matrix §10/§11、backlog R-WELCOME-001、
specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/**。
范围内=规格与实现单轨裁决+registry/acceptance 同步+字体授权跟进；范围外=启动遥测（CM-012）。
依赖=CM-002 owner 报备。
```

```text
CM-011：入站深链能力落地。底料=matrix §11(M2-C)、§23(M14)、_shared/link_templates.yaml、
specs/feature-tree/**/external-inbound-deeplink-routing/**。范围内=DeepLinkResolver+双端原生注册+
pending replay+安全 fallback+三端 UAT；范围外=出站分享(CM-049)、Web 页(CM-050)。
依赖=assetlinks/AASA 域名发布（运维轨，先本地校验产物）。
```

```text
CM-012：启动幂等修复与启动遥测准出[验证型]。底料=matrix §11(M2-B/E)、backlog
R-OPS-STARTUP-IDEMPOTENCY。范围内=proof 幂等修复+真机 20 次冷/暖启动矩阵+启动三指标接目录；
范围外=SLS 平台。依赖=CM-003。
```

```text
CM-013：身份/资料聚合 Facet 对象化收口。底料=backlog R-OBJ-006/R-UPROF-003、matrix §21(M12)。
范围内=user 域 Facet 拆分+generated dispatch 切换+forPage 清零+计数对账策略；范围外=entity Facet。
依赖=CM-004。验收含切换前后 parity 回归。
```

```text
CM-014：关系四层与联系人旅程收口。底料=matrix §21(M12-C/D)、backlog R-UPROF-001。
范围内=拉黑服务端强制+三入口添加回流+互动历史 mine-only 准出+越权负例；范围外=交集称谓 UI(CM-058)。
依赖=CM-013。
```

```text
CM-015：数据主体权利对象与页面。底料=matrix §24(M15-C)、backlog R-UPROF-002。
范围内=AccountDeletionRequest/DataExportRequest/ConsentRecord 对象化+跨域级联 saga+settings 承载页+
冷静期旅程；范围外=法务文案定稿（CM-018 输入）。依赖=CM-018 口径、CM-048 通知回流。
```

```text
CM-016：设置对象页准出[验证型]。底料=matrix §24 settings 组六页。范围内=六页真机 UAT+CAS 并发+
乐观回滚证据；范围外=权限页（CM-017）。依赖=无。
```

```text
CM-017：权限预留页裁决。底料=matrix §24(M15-B)、lib/ui/settings/pages/settings_permissions_page.dart、
AppPermissionCoordinator。范围内=重构为真实权限面或删除入口（裁决记录 CR）+矩阵/inventory 同步；
范围外=各业务权限语义。依赖=无。
```

```text
CM-018：法务条款与 legal-static 商用发布。底料=backlog R-LEGAL-001、matrix §24(M15-D)。
范围内=法务输入落 manifest+版本一致+发布验证；范围外=商业化条款（R-COMMERCE-001 维持延期）。
依赖=法务外部输入（无输入时完成技术侧就绪并如实 GATE_BLOCKED）。
```

### 6.3 B03 变量块

```text
CM-019：消费面路由/surface/SLO 修正。底料=matrix §12(M3-B/D)。范围内=viewer 硬编码路由清零+
homeFeed surface 修正+Feed SLO 单轨；范围外=结构治理(CM-020)。依赖=CM-004（surface owner）。
```

```text
CM-020：内容主链超千行结构治理。底料=backlog R-OBJ-007、.cursor/rules/11+12（pageflip 军规）。
范围内=12 文件拆分+deprecated 清零+visual 证据；范围外=功能变更。依赖=无（守单几何真相源红线）。
```

```text
CM-021：内容删除/封禁传播全链验证。底料=matrix §12(M3-E)。范围内=tombstone 四入口传播矩阵
（feed/search/深链/通知）+终态语义；范围外=审核语义(CM-025)。依赖=CM-030 search 侧同窗。
```

```text
CM-022：评论治理与互动收口。底料=matrix §25(M16)、registry#content-comment-interaction。
范围内=Report/审核反馈入口+profile_comments_page 重构+L2 规格单轨+三黄金指标；范围外=审核后台。
依赖=CM-025 方向裁定（治理反馈文案）。
```

```text
CM-023：创作 Journey 登记与发布回流。底料=docs/text-post-commercial-maturity-plan.md 批次 A/B
（G1/G3/G7/N10~N12）、photo 计划共享底座。范围内=registry 登记+回流面+任务可见+分型显性化+
fixture 修复；范围外=漏斗观测(CM-024)、安全(CM-025)。依赖=CM-002（registry owner）。
```

```text
CM-024：发布漏斗观测接线。底料=text 计划批次 C（G2）、matrix §13(M4-E)。范围内=漏斗事件
metadata-first+payload 修复+三黄金指标+告警；范围外=SLS 平台。依赖=CM-003。
```

```text
CM-025：内容安全方向裁定与实装。底料=text 计划批次 D+§10.2 裁定项（G5）。
范围内=先向用户提交 a/b/c 方向裁定，裁定后状态机激活+频控+作者反馈闭环；范围外=第三方审核厂商
（如需先走 CM-056 登记）。依赖=用户裁定（未裁定前只做方案与红线准备）、CM-048。
```

```text
CM-026：发布契约与结构治理。底料=text 计划批次 E（G6/G8）、backlog R-CS10/R-CR04。
范围内=PostStatus 单轨+tag 创作入口+图文同源+media 上限 metadata+location 迁移；范围外=taxonomy
本体(CM-063)。依赖=CM-063 目录可用。
```

```text
CM-027：视频转码管线落地。底料=docs/video-post-commercial-maturity-plan.md 批次 V-A
（GATE-V1/V6/V9/V10）。范围内=worker+outbox relay+真实 ffmpeg E2E+特性树回填+转码指标；
范围外=端侧(CM-028)。依赖=对象存储资源（R-CS05 协同）。
```

```text
CM-028：视频上传硬化与 Android 能力位。底料=video 计划 V-B/V-C（GATE-V2/V3/V7）。
范围内=流式/分片/续传/进度+能力位降级+处理中语义+resume 契约激活；范围外=转码云侧。依赖=CM-027。
```

```text
CM-029：发布四环境证据兑现。底料=text G4、video V-D（GATE-V4/V5/V8）、backlog R-CS08/R-CS11。
范围内=alpha fixture 修复→beta 写端点→gamma patrol 发布旅程→CONTENT_MEDIA_GAMMA_UAT 翻牌→
prod 探针；范围外=功能修复本体。依赖=CM-023/027/028、CM-002（幽灵摘除先行）。
```

```text
CM-030：搜索可用性与环境种子。底料=docs/search-commercial-maturity-plan.md §8 WP-H/WP-I。
范围内=WP-H 残余工程债+beta/gamma 可检索种子+伪热度诚实化；范围外=交集 attach(CM-031)。
依赖=数据轨种子协同；R-S09 候选经用户确认登记。
```

```text
CM-031：搜索交集 attach 与对象完备。底料=search 计划 WP-J/WP-K（12 张截图依据）。
范围内=attach 阶段+connectionState 闭集+user 承载+tag 裁决+失效反馈+视觉精修；范围外=交集读模型
本体(CM-057)。依赖=CM-057 数据密度、CM-021。R-S08 候选经用户确认登记。
```

```text
CM-032：搜索观测与发布准出。底料=search 计划 WP-L/WP-E/G、backlog R-S06-S-1/2。
范围内=search 事件目录+三黄金指标+真集群容量 measured+App 搜索 api_integration+6 GWT recorded；
范围外=—。依赖=CM-003、真集群资源（无资源如实 GATE_BLOCKED）。
```

```text
CM-033：location.place 对象裁决与落地页重构。底料=matrix §14(M5-B)/§27(M18-D)。
范围内=对象裁决（正式投影 or Homepage 快照）+resolve/失效语义+页面 P1→P4+page contract 修正；
范围外=Homepage 本体。依赖=CM-042 提升链、CM-004。
```

```text
CM-034：消息对象契约与页面绑定补齐。底料=matrix §15(M6-B/D)。范围内=三对象 errors 所有权裁决+
page contract 补绑+metadata/chat generated 出口标注；范围外=功能。依赖=CM-004。
```

```text
CM-035：消息 readiness 翻牌与 Remote 扩面。底料=matrix §15(M6-F)。范围内=发送/回执/成员/greeting
App api_integration+gamma 证据+readiness 回填翻牌；范围外=—。依赖=CM-005/034、CM-043 环境。
```

```text
CM-036：会话/群治理真机与离线准出[验证型]。底料=matrix §15(M6-C/E)。范围内=离线恢复/杀进程/
并发角色/IME 真机矩阵+消息三黄金指标接线；范围外=新功能。依赖=CM-035。
```

```text
CM-037：CircleGroup 群单元生命周期承载。底料=matrix §17(M8-B/D)、backlog R-CIRCLE-002。
范围内=入圈/群审批命令 metadata-first+承载面+通知回流+BOLA 负例；范围外=普通群治理（已有）。
依赖=CM-048。
```

```text
CM-038：CircleFile 与 PostPlacement 管理裁决。底料=matrix §17(M8-B)。范围内=文件全旅程+
pin/feature 动作补齐或 CR 记录 deferred；范围外=—。依赖=CM-037 同窗。
```

```text
CM-039：圈子契约、性能与推荐闭环。底料=matrix §17、backlog R-CIRCLE-001/003。范围内=social errors+
hub 服务端聚合+circle 事件→推荐投影（到事件/投影为止）；范围外=推荐排序（推荐轨）。依赖=CM-064 对账。
```

```text
CM-040：主页认领/上报结果回流。底料=matrix §18(M9-C/D)。范围内=查询/撤回 op+状态承载+通知回流+
申请人旅程；范围外=Ops 审核台。依赖=CM-048。
```

```text
CM-041：想去 wishlist 用户写入口。底料=matrix §18/§19、intersection 计划 §5.4。
范围内=homepage_detail 想去控件+对象化登记+privacyScope 冻结（隐私默认向用户确认）+双账号 E2E；
范围外=约伴(CM-059)。依赖=CM-057 消费侧同窗。
```

```text
CM-042：实体主页真实数据与热重载准出。底料=backlog R-HSE02/R-IX05/R-HSE06/07、matrix §18。
范围内=releaseId 热重载（或受控 restart 留痕）+四主页 populated 对账+gamma T3 复验；
范围外=双省内容生产（数据轨）。依赖=数据轨 release、CM-066 同窗。
```

### 6.4 B04 变量块

```text
CM-043：RTC 可信鉴权环境认证与 ticket 边界。底料=backlog R-CLOUD01（更新记录）、matrix §16(M7-B)。
范围内=App ticket 改 generated client+RuntimeFailure+gamma cold-start 认证报告+伪造/重放/过期负例；
范围外=媒体面(CM-046)。依赖=SLS secret（运维轨；缺则完成代码侧并如实 GATE_BLOCKED）。
```

```text
CM-044：realtime-gateway provenance 与观测实证。底料=backlog R-CLOUD09、matrix §16(M7-E)。
范围内=固定 digest+SBOM+scrape target+断连告警演练；范围外=Prometheus 平台部署。
依赖=运维轨 Prometheus owner（配置以变更请求提交）。
```

```text
CM-045：三端离线来电矩阵。底料=backlog R-RTC01、registry cap.os.callkit_incoming。
范围内=CallRinging push policy+token 注册+PushKit/FCM/Web 唤醒+去重防重响+真机三态；
范围外=push provider 凭据本体(CM-047)。依赖=CM-047（无凭据先做契约与本地链路）。
```

```text
CM-046：RTC 入口矩阵、QoE 与真机媒体准出。底料=backlog R-RTC02、matrix §16(M7-C/E)。
范围内=入口矩阵裁决+Scenario 绑定（经 CM-002 owner）+32 人压测+弱网重连+QoE 指标告警+双机 UAT；
范围外=离线唤醒。依赖=CM-043/044/045。
```

```text
CM-047：Push 外送 provider 决策与实装。底料=backlog R-OBJ-003、registry §7.1 push 组、
metadata/integration/push_delivery/**。范围内=provider 决策（实装或经批准延期记录）+APNs/FCM adapter+
token 生命周期+回执审计+真机到达；范围外=站内 inbox(CM-048)。依赖=Apple/Google 凭据（外部）。
```

```text
CM-048：站内信七源闭环准出[验证型]。底料=matrix §22(M13)。范围内=七源逐源三层矩阵+delivery_job
errors 补齐+失效目标终态+幂等负例；范围外=push 外送。依赖=CM-034。
```

```text
CM-049：出站分享 MVP。底料=matrix §23(M14-C)、registry#outbound-object-share-distribution。
范围内=OutboundShareFact+token 归因+四对象分享面板+渠道 MVP+E2E；范围外=Web 落地页(CM-050)。
依赖=CM-011 回流侧、CM-002（scenario draft→specified）。
```

```text
CM-050：Web 安装转化与公开对象页。底料=matrix §23(M14-D)、registry#public-web-seo-install-conversion。
范围内=公开脱敏投影+SEO 页+install banner+装后还原；范围外=全量 Web 版。依赖=CM-011/049。
```

```text
CM-051：精确坐标隐私修复。底料=matrix §27(M18-B/E)、integration/location/fields.yaml、
contracts/metadata/log_kv_policy.yaml、content/post/{fields,privacy}.yaml、location_service.go。
范围内=classification 修正+log_kv drop/粗化+trace 脱敏+Post 契约单轨+扫描门；范围外=LBS 新功能。
依赖=先向用户复述并确认风险登记（16 号军规），CM-004（metadata owner）。
```

```text
CM-052：ExternalInteraction 状态机与死信面。底料=matrix §27(M18-B/C)。范围内=aggregate/fields 枚举
单轨+RequeueDeadLetter operator 消费面（CLI 优先）+恢复演练；范围外=webhook 真实投递。
依赖=运维轨 Portal（CLI 不依赖）。
```

```text
CM-053：助手运行时可信化。底料=backlog R-ASSIST-001~004。范围内=会话查询面+取消+断线续传+
工具真实化或能力位摘除+日志脱敏+token 级流式；范围外=外部依赖迁移(CM-055)。依赖=可与 CM-055 并行。
```

```text
CM-054：助手 consent 负测与页面准出。底料=backlog R-CLOUD02（更新记录）。范围内=gamma 撤权→拒绝→
失败关闭负例落盘+回写；范围外=—。依赖=gamma 栈可用。
```

```text
CM-055：助手外部依赖统一治理。底料=registry §7.2（ext.llm/search/weather/finance/embed）。
范围内=统一治理出口或逐条豁免登记+attempt 审计+降级链测试；范围外=向量启用（推荐轨）。
依赖=CM-052/056。
```

```text
CM-056：外部依赖登记自动校验门禁。底料=registry §10-P1-3。范围内=扫描脚本（新增外部 endpoint/SDK
未登记即阻断）+gate 接入+负例演示；范围外=逐条依赖整改。依赖=无。脚本归 quwoquan_ops/gate/。
```

### 6.5 B05 变量块

```text
CM-057：交集真实数据先决与契约名实收口。底料=docs/intersection-commercial-maturity-plan.md
WP-IX-0/IX-1+§11.3 三缺陷、backlog R-IX08/09、R-ID02/09。范围内=seed 档案+18 kind 裁决+
Explain/inbox/Mock host 修复+凭证单轨+读放大预算；范围外=页面(CM-058)、行动(CM-059)。
依赖=CM-041 同窗（wishlist 源）、推荐轨。
```

```text
CM-058：交集配对主入口完全重构。底料=intersection 计划 §10.1/WP-IX-2、backlog R-ID10。
范围内=launcher P1→P5+机会卡+双态诚实空态+真机视觉核验；范围外=约伴状态机。依赖=CM-057。
```

```text
CM-059：约伴行动闭环与安全门。底料=intersection 计划 §10.3/WP-IX-3、backlog R-PLAZA-001。
范围内=CompanionCandidate/Request 状态机+承接面+impact 证据列表页+五道安全门执行+双用户 E2E+
青少年/拉黑/频控负例；范围外=LBS 附近（deferred）。依赖=CM-041/057/058、CM-014。
```

```text
CM-060：交集北极星观测与灰度。底料=intersection 计划 WP-IX-4、backlog R-IX10。
范围内=connection-formed-via-intersection 全链+漏斗后两级+护栏反指标+kill-switch+大盘；
范围外=推荐排序实验。依赖=CM-003/057/059。
```

```text
CM-061：交集三层测试与四环境收口。底料=intersection 计划 WP-IX-5+§11.2（smoke 401）。
范围内=smoke canonical 鉴权改造+事实真实性/隐私/双用户三层矩阵+beta 执行证据；范围外=—。
依赖=CM-057~059。
```

```text
CM-062：首次兴趣先验承载。底料=matrix §26(M17-C)、specs/**/interest-onboarding-prior/**。
范围内=Story 规格矛盾修正（先行）+选择/跳过面+游客合并+首刷生效+新装机 UAT；范围外=推荐排序消费。
依赖=CM-063 目录；页面位置（welcome 后/首刷前）裁决记录 CR。
```

```text
CM-063：TagFeedback 消费链与 taxonomy 收口。底料=matrix §26(M17-B/D/F)。范围内=feedback
publisher/checkpoint+推荐画像生效+TaxonomyRelease 切换/失效 refs 语义+tag-service 测试根；
范围外=创作 tag 入口(CM-026)。依赖=CM-005。
```

### 6.6 B06 变量块

```text
CM-064：推荐消费侧对账与 AB 单轨。底料=docs/recommendation-commercial-maturity-plan.md §0、
backlog R-OBJ-004。范围内=曝光→行为→回流三轨对账演练+分桶单轨裁决登记+端云字段 parity；
范围外=模型/召回（推荐轨）。依赖=CM-024、推荐轨。
```

```text
CM-065：App api_integration 全域扩面。底料=matrix §9(H2-3)。范围内=消息/圈子/搜索/设置/通知/RTC
等版块 Remote 三断言+Mock parity 勾稽；范围外=功能修复。依赖=CM-005、各域 CM 合流后执行。
```

```text
CM-066：gamma-local 全量旅程回归。底料=backlog R-UPROF-004/R-HSE07/R-CLOUD06。
范围内=patrol 补旅程（发布/深链/主页/交集 T3）+存在性 UAT 语义化+11 Journey 全量执行落盘+
acceptance 回填；范围外=功能修复（回各 CM）。依赖=B01~B05 出口。
```

```text
CM-067：prod gray canary 与 READY 复评。底料=backlog R-TELEMETRY-001+R-OPS 系列、总控 §1。
范围内=gray-initial canary+SLO readback 消费+回滚演练消费+总控 §1 结论复评回写；
范围外=平台部署（运维轨）。依赖=运维轨就绪+B06 前置；未就绪如实 GATE_BLOCKED。
```

## 7. 总控追踪表（任务 §6.7）

> 每个 CM 会话收尾必须更新本表自己那一行；总控定期复核"总控复核"列。初始状态：整改型=PLANNED，验证型=UNVERIFIED，外部阻断=GATE_BLOCKED。Exit Report 统一落 `.qwq_output/env/repo/runs/cm-exit-reports/{CM-ID}.md`（运行产物，不入库；关键结论回写本表与 acceptance）。

| CM | 批次 | 状态 | 最后验证 | commit | Exit Report | 未关闭 gate/风险 | 回流影响 | 总控复核 |
|---|---|---|---|---|---|---|---|---|
| CM-001 | B01 | VERIFIED | 2026-07-20 | — | `.qwq_output/env/repo/runs/cm-exit-reports/CM-001.md` | 无结构性 gate；RTC 功能缺口归 CM-043～046 | 纠正误删合同 Story 的错误路线 | 总控复核通过 |
| CM-002 | B01 | VERIFIED | 2026-07-20 | — | `.qwq_output/env/repo/runs/cm-exit-reports/CM-002.md` | 无；R-OPS-ACCEPTANCE-PHANTOM 已关闭 | 后续 CM 只能登记已落盘测试文件 | 总控复核通过 |
| CM-003 | B01 | PLANNED | — | — | — | R-OBJ-001 | — | 未复核 |
| CM-004 | B01 | PLANNED | — | — | — | R-HSE04 机制化 | — | 未复核 |
| CM-005 | B01 | PLANNED | — | — | — | R-TST05 | — | 未复核 |
| CM-006 | B01 | PLANNED | — | — | — | R-TST04/07 | — | 未复核 |
| CM-007 | B02 | GATE_BLOCKED | — | — | — | R-AUTH-001（外部凭据） | — | 未复核 |
| CM-008 | B02 | UNVERIFIED | — | — | — | — | — | 未复核 |
| CM-009 | B02 | PLANNED | — | — | — | 合同错绑 | — | 未复核 |
| CM-010 | B02 | PLANNED | — | — | — | R-WELCOME-001 | — | 未复核 |
| CM-011 | B02 | PLANNED | — | — | — | 深链 P0 | — | 未复核 |
| CM-012 | B02 | PLANNED | — | — | — | R-OPS-STARTUP-IDEMPOTENCY | — | 未复核 |
| CM-013 | B02 | PLANNED | — | — | — | R-OBJ-006/R-UPROF-003 | — | 未复核 |
| CM-014 | B02 | PLANNED | — | — | — | R-UPROF-001 | — | 未复核 |
| CM-015 | B02 | PLANNED | — | — | — | R-UPROF-002 | — | 未复核 |
| CM-016 | B02 | UNVERIFIED | — | — | — | — | — | 未复核 |
| CM-017 | B02 | PLANNED | — | — | — | 空壳页 | — | 未复核 |
| CM-018 | B02 | GATE_BLOCKED | — | — | — | R-LEGAL-001（法务） | — | 未复核 |
| CM-019 | B03 | PLANNED | — | — | — | 路由/surface/SLO 漂移 | — | 未复核 |
| CM-020 | B03 | PLANNED | — | — | — | R-OBJ-007 | — | 未复核 |
| CM-021 | B03 | PLANNED | — | — | — | 传播矩阵未证 | — | 未复核 |
| CM-022 | B03 | PLANNED | — | — | — | 治理入口缺 | — | 未复核 |
| CM-023 | B03 | PLANNED | — | — | — | G1/G3/G7/N10 | — | 未复核 |
| CM-024 | B03 | PLANNED | — | — | — | G2/R-OBJ-002 | — | 未复核 |
| CM-025 | B03 | PLANNED | — | — | — | G5；**待用户方向裁定** | — | 未复核 |
| CM-026 | B03 | PLANNED | — | — | — | G6/G8/R-CS10/R-CR04 | — | 未复核 |
| CM-027 | B03 | PLANNED | — | — | — | GATE-V1/V6/V9/V10 | — | 未复核 |
| CM-028 | B03 | PLANNED | — | — | — | GATE-V2/V3/V7 | — | 未复核 |
| CM-029 | B03 | GATE_BLOCKED | — | — | — | R-CS08/R-CS11（依赖前置+环境轨） | — | 未复核 |
| CM-030 | B03 | PLANNED | — | — | — | 种子缺失（R-S09 候选） | — | 未复核 |
| CM-031 | B03 | PLANNED | — | — | — | 死字段（R-S08 候选） | — | 未复核 |
| CM-032 | B03 | GATE_BLOCKED | — | — | — | R-S06-S-1/2（真集群资源） | — | 未复核 |
| CM-033 | B03 | PLANNED | — | — | — | 对象缺失 | — | 未复核 |
| CM-034 | B03 | PLANNED | — | — | — | errors/绑定缺 | — | 未复核 |
| CM-035 | B03 | PLANNED | — | — | — | readiness blocked | — | 未复核 |
| CM-036 | B03 | UNVERIFIED | — | — | — | — | — | 未复核 |
| CM-037 | B03 | PLANNED | — | — | — | R-CIRCLE-002 | — | 未复核 |
| CM-038 | B03 | PLANNED | — | — | — | op 消费缺口 | — | 未复核 |
| CM-039 | B03 | PLANNED | — | — | — | R-CIRCLE-001/003 | — | 未复核 |
| CM-040 | B03 | PLANNED | — | — | — | 回流断 | — | 未复核 |
| CM-041 | B03 | PLANNED | — | — | — | wishlist 零入口；隐私裁决 | — | 未复核 |
| CM-042 | B03 | GATE_BLOCKED | — | — | — | R-HSE02/06/07（数据轨协同） | — | 未复核 |
| CM-043 | B04 | GATE_BLOCKED | — | — | — | R-CLOUD01（SLS secret） | — | 未复核 |
| CM-044 | B04 | PLANNED | — | — | — | R-CLOUD09 | — | 未复核 |
| CM-045 | B04 | GATE_BLOCKED | — | — | — | R-RTC01（依赖 CM-047 凭据） | — | 未复核 |
| CM-046 | B04 | PLANNED | — | — | — | R-RTC02 | — | 未复核 |
| CM-047 | B04 | GATE_BLOCKED | — | — | — | R-OBJ-003（外部凭据） | — | 未复核 |
| CM-048 | B04 | UNVERIFIED | — | — | — | delivery_job errors | — | 未复核 |
| CM-049 | B04 | PLANNED | — | — | — | scenario draft | — | 未复核 |
| CM-050 | B04 | PLANNED | — | — | — | scenario draft | — | 未复核 |
| CM-051 | B04 | PLANNED | — | — | — | **坐标隐私（登记待确认）** | — | 未复核 |
| CM-052 | B04 | PLANNED | — | — | — | 枚举漂移/死信无面 | — | 未复核 |
| CM-053 | B04 | PLANNED | — | — | — | R-ASSIST-001~004 | — | 未复核 |
| CM-054 | B04 | PLANNED | — | — | — | R-CLOUD02 残余 | — | 未复核 |
| CM-055 | B04 | PLANNED | — | — | — | registry violation ×5 组 | — | 未复核 |
| CM-056 | B04 | PLANNED | — | — | — | 门禁缺失 | — | 未复核 |
| CM-057 | B05 | PLANNED | — | — | — | R-IX08/09、三缺陷 | — | 未复核 |
| CM-058 | B05 | PLANNED | — | — | — | launcher P1 | — | 未复核 |
| CM-059 | B05 | PLANNED | — | — | — | R-PLAZA-001 | — | 未复核 |
| CM-060 | B05 | PLANNED | — | — | — | R-IX10 | — | 未复核 |
| CM-061 | B05 | PLANNED | — | — | — | smoke 通道失效 | — | 未复核 |
| CM-062 | B05 | PLANNED | — | — | — | 规格矛盾+P0 页 | — | 未复核 |
| CM-063 | B05 | PLANNED | — | — | — | feedback 死链 | — | 未复核 |
| CM-064 | B06 | PLANNED | — | — | — | R-OBJ-004 | — | 未复核 |
| CM-065 | B06 | PLANNED | — | — | — | api_integration=9 文件 | — | 未复核 |
| CM-066 | B06 | GATE_BLOCKED | — | — | — | 依赖 B01~B05 出口 | — | 未复核 |
| CM-067 | B06 | GATE_BLOCKED | — | — | — | R-TELEMETRY-001+运维轨 | — | 未复核 |

## 8. 规划冻结自检（任务 §7 完成定义）

- [x] **无遗漏反查**：§2.1～2.9 覆盖 11 Journey/24 Scenario/14+1 域/14 服务/87 页面组+挂靠面/外部依赖全组/H1/H2/6 专项工作包/75 开放 R-*，每行均有 CM ID 或显式轨道归属；模板占位 `R-XXX` 不计。
- [x] **验证型不消失**：CM-001/008/012/016/036/048 等验证准出型独立建项，未因"已实现"而免于准出。
- [x] **可验收表述**：67 张卡的 D 维任务均绑定门禁/测试/报告证据；无"提升/优化/增强"类不可验收词充当验收标准。
- [x] **依赖/owner/合流**：§0.4 owner 表+§5 进入/出口条件+每卡要素 10 依赖字段齐备。
- [x] **分析与商用分离**：六份专项规划的"分析完成"未被当作能力完成；其工作包全部映射为待执行 CM（§2.8）。
- [x] **风险单轨**：未新建风险账本；新风险候选（精确坐标、R-S08/R-S09）均标注"待用户确认后登记"。
- [x] **外部阻断诚实**：R-AUTH-001/R-LEGAL-001/R-CS08/R-S06/R-TELEMETRY-001 等 10 项初始即标 GATE_BLOCKED，不伪装可执行。
- [ ] **执行期滚动项**：§7 状态列随会话推进更新；§1 结论仅由 CM-067 复评回写（当前保持 NOT_READY）。

冻结时刻门禁快照（2026-07-20 15:00 实测，本文为纯文档交付、不影响任何门）：

| 门禁 | 结果 | 说明 |
|---|---|---|
| `verify_test_specs.py` | 绿 | RTC 八个 L3 Story 均为合法扁平化节点，产品 Story 与合同 Story 边界独立；CM-001 已复核通过 |
| `verify_agent_context_contract.py` | 绿 | — |
| CM 编号勾稽（本文自检脚本） | 绿 | 67 项在 §3/§4/§6/§7 四节完整一致、无重复 |
| 引用路径存在性 | 绿 | 唯一错误引用（log_kv_policy 路径）已在冻结前修正 |
| `verify_test_coverage_map.py` | 红（外部） | 并行未提交改动：platform-ops-governance recorded 非 canonical ×2、`chatAnnouncement` surface 未入页面清单；非本文引入，归对应并行会话（CM-002 对账时复核） |
| `make verify-app-page-horizontal-quality` | 红（外部） | 并行会话正在拆分 persona 页，新文件 `persona_management_form_page.dart` 未登记质量矩阵；归该并行会话（与 CM-009 同域，合流时勾稽） |
| `git diff --check`（本文两文件） | 绿 | 无空白/冲突标记 |

变更记录：

| 日期 | 变更 | 说明 |
|---|---|---|
| 2026-07-20 | v1 冻结 | CM-001~067、B01~B06、覆盖对账、启动提示词、追踪表初始化 |
| 2026-07-20 | v1.1 执行纠偏 | CM-001 复核确认八节点为合法分层 Story，撤销“重复节点”误判并标记 VERIFIED |
| 2026-07-20 | v1.2 测试诚信硬门 | CM-002 摘除 76 条 planned 幽灵路径、补 fail-closed 门禁并关闭 R-OPS-ACCEPTANCE-PHANTOM |

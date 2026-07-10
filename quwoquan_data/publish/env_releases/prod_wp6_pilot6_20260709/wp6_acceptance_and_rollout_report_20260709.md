# WP6 验收与放量报告 —— 全国景点主页放量计划收口

- 日期：2026-07-09（rev2：prod 增量导入完成后更新；初版当日被外部清理，已重建）
- 计划：`~/.cursor/plans/全国景点主页放量_552eb106.plan.md` §五 WP6 / §六
- 前序：WP1-WP4（主清单/打标/coverage 账本/路由绑定）、WP5（全链首跑，报告 `~/.qwq_wp5_notes/wp5_final_report.md`）
- 姊妹文档：[试点省覆盖率报告](pilot_province_coverage_report_20260709.md)、[新一轮规划输入](next_round_planning_inputs_20260709.md)

## 一、试点省覆盖率（WP6-1，摘要）

| 省 | 主清单 | 已发布(主清单内) | ready | ready 触达率 |
|---|---|---|---|---|
| 四川省 | 678 | 12 | 239 | 5.0% |
| 浙江省 | 415 | 6 | 253 | 2.4% |
| 合计 | 1093 | 18 | 492 | 3.7% |

覆盖集中「地点/景区」（16/18），乐山市 6/27 最高。缺口：ready 未发布 474、pending 599、no_primary_source 2、WP5 尾部 3 分区。详见覆盖率报告。

## 二、环境导入 + 标签链接可用性实测（WP6-2）

### 2.1 gamma 导入（releaseId `gamma_wp6_pilot6_20260709`）

- `qwq-data ship` 新增 `--force-entity-refs`（对称 `--force-post-refs`，含 publish index 缺失阻断断言 + 2 合同测试）；upsert 6 实体、homepage-import v2 created homepage_99~104、media sync 311 objects、consistency preflight 通过。
- 发现并固化 **R-HSE02 停服序列**：entity-service 启动时装载 homepage_state 入内存，运行中直写 DB 会被覆盖；必须「停容器 → homepage-import → 启容器」。

### 2.2 prod 增量导入（releaseId `prod_wp6_pilot6_20260709`，用户批准后执行）

按 gamma 固化序列执行，全程 stackctl + 四平面 SSH 账号：

1. **dry-run 演练**（`prod_wp6_pilot6_dryrun_20260709`）：projected=6 issues=0，preflight passed。
2. **媒体增量**：本地库 311 对象 vs 远端 304，差集 7 对象（18.3MB）tar-over-ssh 补齐至 311。注意：远端媒体目录属主 `prod-edge-svc`，service 平面账号 mkdir 被拒，改用 edge 平面密钥完成（已记 knownGaps）。
3. **R-HSE02 停服**：`podman stop quwoquan-service-prod_entity-service_1`。
4. **正式导入**：`ship --confirm-prod-apply --mode upsert --delete-policy none`（Mongo host 19410 直连）：content import entities=6；homepage-import **created=6（homepage_54~59）updated=0 issues=0**；存量 66 主页无损（导入后共 72）。
5. **object_tag_index**：60 实体全量 manifest 经 tag-service `import-objects` upsert 进 prod `quwoquan_tag`。
6. **重启 + 健康**：entity-service 起，`stackctl health prod-hosted` **4/4 healthy**。
7. **SLO 采样**：30 请求 errorRate=0，p50=132.7ms，p95=217.7ms（p95 高于上轮 142ms 基线系小样本冷 TLS 握手，err=0 判定 continue；本次为纯数据发布，无镜像/配置变更，不走 deploy stage）。

契约与证据归档 `publish/env_releases/prod_wp6_pilot6_20260709/`（prod.json / import-prod.json / import-homepage-prod.json / media-sync.json / consistency-preflight-prod.json / slo-full.json / release_rollout.json）。

### 2.3 双环境验证矩阵

| 环节 | gamma | prod |
|---|---|---|
| introduction URL（6 实体） | 6/6 200 + 正文/categoryTags | **6/6 200**（sections 正文 300~2500 字符 + 关键词 + coverUrl 全过） |
| categoryTags API 面（shell + object-page-bundle） | 4/4 | **6/6**（含定海古城=历史古镇、郭沫若故居=博物馆、嵊山岛=自然景观） |
| `/v1/tag/inverted`（区县地理+类型标签） | 10/10 | **6/6**（定海区/嵊泗县/犍为县/马边彝族自治县/历史古镇/博物馆均含新实体） |
| coverUrl 媒体面 | 通过 | **3/3 200**（验证媒体增量传输生效） |
| 存量不破坏 | — | homepage_30/52 仍 200；entities 55→61、homepages 66→72、posts 66 不变 |
| link_targets 绑定 | 5/5 | 共用同一 publish 索引：homepage 绑定 58 条，区县→新实体 3/3（历史古镇类型标签绑定为 search targetKind，属账本既有语义非回归） |
| coverage 账本回写 | envImports.gamma=true | **envImports.prod=true**，introductionUrl 携带 per-env homepageId |

**homepageId per-env 映射**：定海古城 gamma=99/prod=54、郭沫若故居 100/55、峨边黑竹沟 101/56、犍为文庙 102/57、马边大风顶 103/58、嵊山岛 104/59。跨环境不可移植，链接必须按环境从账本取。

alpha/beta：alpha 未拉起、beta 导入同样需停服窗口，按计划以 gamma+prod 为证据并如实说明。

## 三、分层测试证据矩阵（WP6-3）

| 层 | 证据 | 验收意图 | 状态 |
|---|---|---|---|
| local_contract | ship/sampling 合同测试 19 例（含 `--force-entity-refs` 2 例） | contract | PASS |
| local_contract | data release consistency 9 例 | contract | PASS |
| local_contract | `verify_quwoquan_data.sh` 全量门禁（fanout 28 + pytest 167 + template lint + cli-first） | contract/GWT | PASS（实跑 exit 0） |
| local_contract | WP5 产线修复测试 8 例 | GWT | PASS |
| api_integration | gamma 链路实测（introduction 6/6、categoryTags 4/4、inverted 10/10、link_targets 5/5） | SIT | PASS |
| api_integration | **prod 链路实测（introduction 6/6、categoryTags 6/6、inverted 6/6、coverUrl 3/3、存量无损、SLO err=0）** | SIT | PASS |
| api_integration | gamma/prod import 契约 + preflight + rollout 时间线 | SIT/contract | PASS（归档 env_releases） |
| user_acceptance | App 端标签页→主页 UI 旅程 | UAT | **未执行**（App 消费页未接入，列规划输入 #9） |

## 四、全国放量 roadmap（WP6-4）

产能基线：1-1.5 主页/h/worker、首过率 89%（非放弃口径）、ready 按 75% 折扣。推进顺序：P0 补漏（尾部 3 分区+黄龙/西湖收编）→ P1 两省 ready 收口（~355，16w 云并发 ≈4 工作日/省）→ P2 扩源（pending 599，四川优先）→ P3 全国按 ready 率排省。日产 10 万依赖 ~200 机等效云端并发（download/author 分离、弹性 worker 池、导入免停服）。

**backlog 处置（用户已决策）**：不登记 `docs/outstanding_risks_backlog.md`；全部 10 项整理为[新一轮规划输入](next_round_planning_inputs_20260709.md)（P0：停服窗口/云端并发/多代理治理冲突；P1：ready 精度/祖先标签/链接契约/v2 重放；P2：尾部分区/App UAT/两省排产），每项含根因/影响/建议动作/工作量/验收意图与证据层。

## 五、Exit Review（WP6-5）

| 维度 | 结论 |
|---|---|
| 规格达成 | WP6 五条目 + prod 增量导入（用户批准）全部完成；alpha/beta 豁免已说明 |
| 测试证据 | local_contract 全绿（195+ 例）；api_integration gamma+prod 双环境全绿；user_acceptance 缺口列规划输入 |
| E2E | Data→Service 双环境闭环：publish 主线 → ship 契约 → gamma/prod Mongo → entity/tag-service API → 账本回写 envImports=true |
| 产品/UX | introduction+categoryTags 双环境可消费；link_targets 58 条绑定就绪；契约限制列规划输入 #5/#6 |
| 运营观测 | 账本可持续出数；env_releases 双环境审计链完整；prod SLO 采样 err=0；新增观察：prod 容器 healthcheck 长期 unhealthy（既有）、磁盘 90%（列规划输入附录） |
| 自动化/门禁 | 数据工程全量门禁 PASS；未绕 gate；codegen 未手改；prod 写入走 `--confirm-prod-apply` 显式确认 |
| 剩余风险 | 规划输入 10 项 + 附录 3 观察；另：本轮两份报告初版曾因临时落点被外部清理而重建，已随本 release 审计包归档——印证规划输入 #3 多代理治理冲突的现实影响 |

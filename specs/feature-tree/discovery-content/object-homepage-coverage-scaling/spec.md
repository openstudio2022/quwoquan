# L2 特性：object-homepage-coverage-scaling（实体主页省级覆盖放量）

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `object-homepage-coverage-scaling`

> 命名裁决：本能力的任务口径原为「L2 object-homepage-network」，但 `object-homepage-network`
> 已是独立 L1（三类对象页体验收口层）。为遵守 single-source（不得维护第二套树 / tree_index id
> 唯一），本 L2 命名为 `object-homepage-coverage-scaling`，聚焦**实体主页内容供给的省级覆盖放量**；
> 对象页消费体验仍归 `object-homepage-network` 与 `shared-homepage-network`。

## 背景与动机

WP5 省级批量跑已验证 `decompose → fanout by-partition → leaf` 全链正确性（舟山/乐山试点，
净增 6 实体主页），但暴露四类放量阻断：

1. **吞吐缺口**：实测 1-1.5 主页/h/worker，距日产 10 万有 50-100x 缺口；download 与 author
   同 worker 串行互相稀释。
2. **静态资格漂移**：历史静态 ready 标记曾与实际抓取、版权和页面身份脱节，导致排产计划
   失真且失败归因滞后。
3. **候选与发布资格必须分开**：当前两省主清单只有 2899 项（浙江 922 / 四川 1977），
   不能支撑 H10K。发现层必须先形成不少于 20,000 条原始候选，经 canonical identity
   去重和旅行对象语义准入后保留不少于 12,000 个唯一候选；每省至少 6,000 个对象还要在
   execution 内以对象本地来源目录和证据重新确认 `encyclopedia-primary` 资格。
4. **放量硬前置未落**：entity-service 导入停服窗口（R-HSE02）、tag inverted 无祖先展开
  （省/市级聚合断链）、prod 磁盘 90% 未决策。

本能力把「省级全覆盖」从试点口径升级为可复制的省级放量产线：主清单扩容 → execution 内
来源资格核验 → 两段流水线并发 → 省级参数化 recipe → 单任务执行与环境导入 → App 消费 UAT。

## 「省级全覆盖」冻结定义

一个省达到「全覆盖」当且仅当同时满足：

1. **市州文件齐全**：`quwoquan_data/verticals/travel/coverage/中国/{省}/` 下每个地级行政区
   恰有一个主清单文件（浙江 11 市、四川 21 市州），schema `quwoquan_data.discovery_seed`。
2. **区县分组无缺口**：每个市州文件的 `districts` 覆盖行政区树
   `Topic/地理/行政区/中国/{省}/{市州}/` 下全部叶子区县，且每区县 `leaves` 非空。
3. **10 类旅行地点类型覆盖**：省级汇总维度上，`地点/景区、自然景观、打卡地、遗址、古镇、
   宗教场所、博物馆、公园、温泉、主题乐园` 十类 entityType 均有候选（个别区县确无某类
   属诚实事实，不凑数）。
4. **跨省地点单主归属**：跨省/跨市地点只在主归属省登记一次（`geoTagRef` 单主），次归属经
   `geoTagRefs` 数组表达（泸沽湖模式）。
5. **来源发现饱和**：`wiki_category`、`wikidata_geo`、`osm_poi`、
   `baidu_baike_search`、`toutiao_baike_search` 五路只发现名称和身份线索；主页正文、底稿、
   writing pack 与 `primaryEvidenceRef` 只允许 Wikipedia、百度百科、今日头条百科三源
   `encyclopedia-primary` 闭集。Wikivoyage、官方文旅、OTA、地图和其他 discovery
   provider 均不得投影正文或主证据。矩阵每个 cell 都必须到 exhausted、saturated 或
   typed blocked 终态，资源 limit 不得冒充饱和。
6. **数值目标（证据约束）**：2899 项是 M3 历史基线，不是最终目标。H10K 准出要求
   20,000 条以上原始发现候选、12,000 个以上去重且 source-ready 的唯一对象，以及浙江、
   四川各自冻结 5,000 个不可替换目标；10,000 个目标必须全部 accepted、canonical、
   immutable-release-bound 且 Gamma 可查询。

## 里程碑准入门（Canary / H200 / H1000 / M3 / H10K）

- **Canary**：浙江固定普陀山、东钱湖，四川固定海螺沟；累计 3 个主页。
- **H200（执行里程碑 `m1`）**：两省各新增 100，累计 203。真实 Cursor SDK author/reviewer、
  Mongo+Redis ReliableTask、对象事务、首过率、权威成本和 accepted throughput 必须出数。
- **H1000（执行里程碑 `m2`）**：两省各新增 500，累计 1203；冻结目标失败不得替换。
- **M3**：执行现有 2899 项历史主清单，累计浙江 922、四川 1977；它是 H10K 的前序
  immutable closure，不再是最终全覆盖口径。
- **H10K**：在 M3 之后新增浙江 4078、四川 3023，累计每省 5000、总计 10,000；必须在
  24 小时内达到至少 416.67 accepted homepage/h 并完成 canonical、immutable release、
  Gamma import/API/App UAT、回滚与重放。

下一档创建前必须复验上一档 `rollout_milestone_closure`。并发/队列、成本 kill switch、
来源/权利闭包和环境回滚任一未通过时保持 `GATE_BLOCK`；Prod 未获显式审批前只导 Gamma。

## 功能范围

1. **主清单扩容管线**（`qwq-data governance coverage discover|merge`）：五路发现候选 →
   canonical identity 去重 → 类型/地理/来源资格预筛 → 写回市州 YAML，自闭环、无总控 index。
2. **execution 来源资格核验**：`sources/qualification/request.json` 只冻结选中目标身份；
   下载后由对象本地 `evidence/source_catalog.json` 和证据包产出
   `sources/qualification/result.json`，任何 blocked 对象不得进入 publish。
3. **统一多载体框架**：homepage/article/image/video 四载体共享 target selection、
   source unit、asset index、review ledger、publish、ship、coverage/env import 共同层，
   载体差异收敛进 lane adapter。
4. **单 execution 流水线**：来源、下载、质量、compose、draft、review 由同一个
   `.qwq_output/data/tasks/<executionId>/` 工作包编排；并发只是 recipe/runtime profile，
   不创建 worker、batch 或阶段运行根。
5. **省级参数化 recipe**：`--province`、discovery、limit、milestone 与 executionId
   仅作为运行参数；recipe 只保留可复用规模、runtime 与质量参数。
6. **执行与导入**：每个 execution 附 task preflight、execution-readiness、release、
   ship/import、API 与 App UAT 证据；环境回执写对应 env run。
7. **App 消费 UAT**：标签页/搜索入口到实体主页消费路径（metadata route/surface +
   RemoteRepository）用户验收。
8. **真实 worker 与成本治理**：对象作业经 Mongo+Redis ReliableTask 分发到 typed
   Python worker；author/reviewer 的 Cursor SDK usage、真实 billed cost、重试成本和
   `unitPassedCost` 进入权威账本，超 daily/batch/object cap 立即停止新派发。

## Out of Scope

- 对象页视觉/交集体验升级（归 `object-homepage-network`）。
- 主页认领、维护、下线治理（归 `shared-homepage-network`）。
- 100,000/日实际生产；该档只允许依据真实 H10K 的 p50/p95、首过率、source-ready
  capacity、队列滞后和权威成本 evaluate-only。
- 浙江/四川以外省份的实跑（本能力交付可复制策略，下一省执行另开 Story）。
- 未经审批的 Prod 写入。

## 约束

- 正文生成一律经 Cursor SDK，provider/model 读取受版本控制的 runtime profile，禁止
  会话模型、脚本拼接或 fixture 代写实体主页正文。
- data CLI-first：新能力一律 `qwq-data` 子命令化，禁止新增可直跑 `__main__` 业务脚本。
- 每个 execution 只能发布动态资格核验 confirmed 的对象；无权威主源等失败必须以稳定
  `DataIssue` 归因落账，不能回写静态主清单。
- 来源、阶段结果、失败隔离与 review 证据只归当前 execution 工作包；approved
  对象经摘要校验后原子写入 canonical publish，release 独立写
  `QWQ_OUTPUT_ROOT/data/releases/<releaseId>/`。不维护隔离目录、永久 freeze、
  retired ready、迁移索引或 rollback 副本。
- review 未批准的对象不得写入 canonical；批准对象只经 object transaction 原子写入，
  不维护第二套 promote 路径或新旧稿兼容裁决。
- 任何 dry-run、候选数、控制面 task throughput、文件存在或 assembled release 都不等于
  accepted content；只有通过 review、对象事务、immutable release 和 Gamma 消费闭包的
  对象才计入 H200/H1000/M3/H10K。

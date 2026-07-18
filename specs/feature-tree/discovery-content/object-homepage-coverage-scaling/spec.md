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
3. **来源资格必须运行期确认**：两省主清单已扩展到 2899 项（浙江 922 / 四川 1977）；主清单
   只保存稳定身份与分类，每个 execution 必须以对象本地来源目录和证据重新确认
   `encyclopedia-primary` 资格。
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
5. **来源发现饱和**：官方文旅、政府名录、OTA 公共索引、地图 POI、Wikidata/OSM 与百科
   搜索可用于发现名称线索；主页正文、底稿、writing pack 与 `primaryEvidenceRef` 只允许
   `encyclopedia-primary` 四百科闭集。Wikivoyage、360 与上述 discovery provider 均不得
   投影正文或主证据。新一轮发现增量 < 5% 视为饱和。
6. **数值目标（证据约束）**：当前唯一主清单为浙江 922、四川 1977、合计 2899 个叶子；
   全覆盖准出按该主清单动态计算，不维护硬编码副本。后续扩容会自动提高准出目标。

## 里程碑准入门（M1/M2/M3）

- **M1 校准批**：WP5 尾部 3 分区（乐山沙湾区/市中区、舟山岱山县）补跑收口 + 两省各 100
  地点校准批跑通，证明并发与平稳性改造（download/author 分段、Agent 池化并发 ≥4、
  no-progress watchdog、跑批保护协议）生效；产出改造后吞吐基线（目标单机 ≥4-6 主页/h）。
- **M2 扩量批**：M1 达标后，两省各 500 地点批；首过率（非放弃口径）≥85%。
- **M3 全量批**：M2 达标后，两省全部主清单地点都执行动态来源资格核验；确认对象跑完成稿，
  其余对象以 typed `GATE_BLOCK` 与归因留在该 execution，不得计入覆盖成功。

准入约束：M1 未达标不得启动 M2；并发与平稳性改造未完成不得启动省级大批（>100）；
放量硬前置（entity-service reload/import、tag 祖先展开、prod 存储决策）未完成前，
省级大批只导 gamma，prod 只做受控小批窗口。

## 功能范围

1. **主清单扩容管线**（`qwq-data vertical coverage-*`）：发现候选 → 去重 → 类型/地理
   打标 → 写回市州 YAML，自闭环、无总控 index。
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

## Out of Scope

- 对象页视觉/交集体验升级（归 `object-homepage-network`）。
- 主页认领、维护、下线治理（归 `shared-homepage-network`）。
- 日产 10 万的云端弹性 worker 池专项（本能力交付单机流水线与并发改造，云端横向扩展
  另列专项）。
- 浙江/四川以外省份的实跑（本能力交付可复制策略，下一省执行另开 Story）。

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

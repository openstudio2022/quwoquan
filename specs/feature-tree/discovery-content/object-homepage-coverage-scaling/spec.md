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
2. **ready 虚高**：sourceReadiness=ready 存在 20-30% 乐观偏差（放弃主因 7/9 为
   sourceScreen 无权威主源），排产计划失真。
3. **主清单规模不足**：两省主清单共 1093 项（浙江 415 / 四川 678），距「省级全覆盖」的
   来源发现饱和口径有约 2-3x 缺口。
4. **放量硬前置未落**：entity-service 导入停服窗口（R-HSE02）、tag inverted 无祖先展开
  （省/市级聚合断链）、prod 磁盘 90% 未决策。

本能力把「省级全覆盖」从试点口径升级为可复制的省级放量产线：主清单扩容 → 前置源核验 →
两段流水线并发 → 省级参数化 recipe → 批次执行与环境导入 → App 消费 UAT。

## 「省级全覆盖」冻结定义

一个省达到「全覆盖」当且仅当同时满足：

1. **市州文件齐全**：`quwoquan_data/verticals/travel/coverage/中国/{省}/` 下每个地级行政区
   恰有一个主清单文件（浙江 11 市、四川 21 市州），schema `quwoquan_data.discovery_seed/2`。
2. **区县分组无缺口**：每个市州文件的 `districts` 覆盖行政区树
   `Topic/地理/行政区/中国/{省}/{市州}/` 下全部叶子区县，且每区县 `leaves` 非空。
3. **10 类旅行地点类型覆盖**：省级汇总维度上，`地点/景区、自然景观、打卡地、遗址、古镇、
   宗教场所、博物馆、公园、温泉、主题乐园` 十类 entityType 均有候选（个别区县确无某类
   属诚实事实，不凑数）。
4. **跨省地点单主归属**：跨省/跨市地点只在主归属省登记一次（`geoTagRef` 单主），次归属经
   `geoTagRefs` 数组表达（泸沽湖模式）。
5. **来源发现饱和**：百科（wikipedia/wikivoyage/百度百科）、官方文旅、政府名录（A 级景区
   /文保单位/历史文化名镇名村）、OTA 公共索引、地图 POI 名称线索五路来源均完成发现扫描，
   新一轮发现增量 < 5% 视为饱和。
6. **数值目标（证据约束）**：两省合计 3000+ 候选。这是来源饱和后的预期规模，不是凑数
   指标——若五路来源饱和后仍不足 3000，以「来源饱和报告 + 缺口清单」作为达成证据。

## 里程碑准入门（M1/M2/M3）

- **M1 校准批**：WP5 尾部 3 分区（乐山沙湾区/市中区、舟山岱山县）补跑收口 + 两省各 100
  地点校准批跑通，证明并发与平稳性改造（download/author 分段、bridge 池化并发 ≥4、
  no-progress watchdog、跑批保护协议）生效；产出改造后吞吐基线（目标单机 ≥4-6 主页/h）。
- **M2 扩量批**：M1 达标后，两省各 500 地点批；首过率（非放弃口径）≥85%。
- **M3 全量批**：M2 达标后，两省全部真 ready（前置 sourceScreen 核验后的 ready）地点
  跑完成稿或诚实放弃归因。

准入约束：M1 未达标不得启动 M2；并发与平稳性改造未完成不得启动省级大批（>100）；
放量硬前置（entity-service reload/import、tag 祖先展开、prod 存储决策）未完成前，
省级大批只导 gamma，prod 只做受控小批窗口。

## 功能范围

1. **主清单扩容管线**（`qwq-data vertical coverage-*`）：发现候选 → 去重 → 类型/地理
   打标 → 写回市州 YAML，自闭环、无总控 index。
2. **前置 sourceScreen**（`qwq-data vertical source-screen`）：排产前批量深核验，回写
   `sourceReadiness` 三态 + 核验时间戳，产出 ready 折扣率与扩源缺口报告。
3. **统一多载体框架**：homepage/article/image/video 四载体共享 target selection、
   source unit、asset index、review ledger、publish、ship、coverage/env import 共同层，
   载体差异收敛进 lane adapter。
4. **两段流水线**：download stage（源抓取+图片+sourceScreen，8-16 并发离线预跑）与
   author stage（只消费就绪对象）独立编排；bridge 池化提 author 并发至 4-8。
5. **省级参数化 recipe**：`--province` + 市州/区县 fanout + sourceReadiness 分层 +
   分批上限 + 断点续跑 + 失败归因，100/500/all-ready 三档。
6. **批次执行与导入**：每批附 env ready、run-recipe、scale-readiness、verify、ship/import
   报告、coverage 账本回写全证据链。
7. **App 消费 UAT**：标签页/搜索入口到实体主页消费路径（metadata route/surface +
   RemoteRepository）用户验收。

## Out of Scope

- 对象页视觉/交集体验升级（归 `object-homepage-network`）。
- 主页认领、维护、下线治理（归 `shared-homepage-network`）。
- 日产 10 万的云端弹性 worker 池专项（本能力交付单机流水线与并发改造，云端横向扩展
  另列专项）。
- 浙江/四川以外省份的实跑（本能力交付可复制策略，下一省执行另开 Story）。

## 约束

- 正文生成一律经本地 Cursor SDK managed-local bridge（`--model composer`），禁止会话
  模型代写实体主页正文。
- data CLI-first：新能力一律 `qwq-data` 子命令化，禁止新增可直跑 `__main__` 业务脚本。
- 只跑前置核验后的 `sourceReadiness=ready`；放弃必须 reasoned（无权威主源等归因落账）。
- 批次证据归 `QWQ_OUTPUT_ROOT/data/local/runtime/**`，发布审计归
  `quwoquan_data/publish/env_releases/**`。
- promote 质量对比门保留：新稿劣于老稿 SKIP 属正常裁决，不算失败。

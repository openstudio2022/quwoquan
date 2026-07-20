# L2 设计：object-homepage-coverage-scaling

## 架构总览

```text
[候选扩容]                                 [execution 资格核验]                    [ReliableTask 流水线]
coverage matrix/discover/merge     → object-local source catalog + evidence → download worker (IO 池)
(区县×10类×五来源 cell            (三百科闭集+逐图权利+qualification)       └→ author/reviewer (Cursor SDK 池)
 →20K raw→12K source-ready         →冻结每省 5K，不替换失败对象)                   └→ object transaction
 →checkpoint→canonical identity)                                                     └→ immutable release
                                                                    └→ Gamma import/API/App UAT/rollback/replay
```

## 职责边界

| 组件 | 职责 | 真相源 |
|---|---|---|
| `qwq-data governance coverage` | 市州分片 cell、分页/checkpoint、身份聚合、语义准入、写回 | runtime matrix/checkpoint + 市州 YAML |
| execution qualification | 对象本地三百科身份、证据与权利准入 | `sources/qualification/*.json` + `evidence/source_catalog.json` |
| `qwq-data task geo-homepages` | 省级单任务编排 | recipe YAML + execution manifest |
| download stage | 源抓取、图片、sourceScreen 复核 | source unit + asset index |
| author stage | composer 成稿（只消费就绪对象） | writing_pack + page.md |
| ReliableTask fleet | Mongo 持久任务、Redis ready index、lease/retry、typed Python worker | task store + AgentResultEnvelope + fleet report |
| object transaction | review 后的单对象 canonical 原子写、幂等、回滚 | apply/verify/rollback audit |
| entity-service importer | homepage_state 灌库 + reload | import report v2 |

## 关键设计决策

1. **矩阵与主清单分责**：runtime matrix/checkpoint 证明发现进度与饱和，市州 YAML 只保存
   通过身份/语义准入的 canonical 候选；limit 不得冒充 exhausted/saturated。
2. **身份优先、OSM 后置**：QID/pageid/OSM type+id 优先；名称+坐标+区县只作 fallback。
   OSM/Wikidata/百科搜索均是 discovery-only，OSM-only 与普通设施不得直接进入主清单。
3. **运行期资格核验**：主清单不保存来源就绪状态；每个 execution 只在对象本地证据
   满足无版本分支的 `encyclopedia-primary` 当前合同后确认发布资格。
4. **分段并发**：download 与 author/reviewer 以独立 execution stage 编排；download
   使用 IO worker 池，author 只消费 source-ready 对象。任务经 Mongo+Redis ReliableTask
   获取 lease、重试与幂等；完成的 source unit 不重下，同一 execution 只允许 resume。
5. **Agent 池化与成本保留**：受控并发由 H200 校准，不拍脑袋；每次 author/reviewer turn
   的 provider/model/modelFamily/runId、usage、真实 billed cost 和重试成本增量写入
   `TokenLedger`。daily/batch/object cap 任一越界立即停止新派发。
6. **跑批保护协议**：runtime 保护清单 + 活跃 lease 标记（复用 ops_governance lease
   概念），保护 frozen plan、`.qwq_output/release`、workflow state；key 生命周期
   （403/limit 自动暂停、恢复自动续跑）为 CLI 内置能力。
7. **载体统一**：四载体（homepage/article/image/video）共享共同层契约，lane adapter
   只表达输出物差异（homepage: page.md/_entity.json/manifest.json；article:
   writing_pack + draft.article.md；image: 单源权利资产；video: 真实源媒体包）。
8. **里程碑只认 accepted closure**：Canary/H200/H1000/M3/H10K 的计数只来自 review
   approved + object transaction + immutable release + Gamma 查询闭包；候选数、dry-run、
   文件存在和控制面吞吐不计完成。

## 依赖与交互

- 上游：`quwoquan_data/verticals/travel/coverage/**`（主清单）、
  `quwoquan_data/control_plane/families/content/travel/homepage/**`（recipe）。
- 下游：`quwoquan_data/publish/**`（发布主线与 coverage 账本）、entity-service
  homepage importer（gamma/prod 导入）、App 实体主页消费页。
- 横向：`object-homepage-network`（消费体验）、`shared-homepage-network`（主页治理）、
  tag-service（祖先展开查询）。

## 可观测与演进

- 每批分段吞吐出数：sourceScreen / download / author / review / ship 五段速率。
- coverage 静态验证随 immutable release 生成；import/rollout/SLO 等环境证据只落
  `.qwq_output/env/**`，不得回写 canonical publish。
- H10K 在 24 小时内实测至少 416.67 accepted homepage/h；H100K 只依据 H10K p50/p95、
  首过率、`unitPassedCost`、source-ready capacity、queue lag 与 24h soak evaluate-only，
  并保留至少 20% 容量余量。

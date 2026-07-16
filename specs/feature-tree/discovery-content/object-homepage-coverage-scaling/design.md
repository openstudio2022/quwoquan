# L2 设计：object-homepage-coverage-scaling

## 架构总览

```text
[主清单扩容]                            [execution 资格核验]             [两段流水线]
coverage matrix/discover/merge  →  object-local source catalog + evidence  →  download stage (8-16 并发)
(区县×10类×六来源 cell          (四百科闭集+qualification result)         └→ author stage (Agent 池化 4-8)
 →checkpoint→身份/语义准入)                                                   └→ review → publish → ship
                                                              └→ coverage 账本 + env import
```

## 职责边界

| 组件 | 职责 | 真相源 |
|---|---|---|
| `qwq-data vertical coverage-*` | 市州分片 cell、分页/checkpoint、身份聚合、语义准入、写回 | runtime matrix/checkpoint + 市州 YAML |
| execution qualification | 对象本地四百科 v2 身份、证据与权利准入 | `sources/qualification/*.json` + `evidence/source_catalog.json` |
| `qwq-data task geo-homepages` | 省级单任务编排 | recipe YAML + execution manifest |
| download stage | 源抓取、图片、sourceScreen 复核 | source unit + asset index |
| author stage | composer 成稿（只消费就绪对象） | writing_pack + page.md |
| 来源策略迁移 | ready v2 重筛、published quarantine、closure rebuild queue | runtime/runs；canonical publish freeze + Merkle 不变 |
| entity-service importer | homepage_state 灌库 + reload | import report v2 |

## 关键设计决策

1. **矩阵与主清单分责**：runtime matrix/checkpoint 证明发现进度与饱和，市州 YAML 只保存
   通过身份/语义准入的 canonical 候选；limit 不得冒充 exhausted/saturated。
2. **身份优先、OSM 后置**：QID/pageid/OSM type+id 优先；名称+坐标+区县只作 fallback。
   OSM/Wikidata/百科搜索均是 discovery-only，OSM-only 与普通设施不得直接进入主清单。
3. **运行期资格核验**：主清单不保存来源就绪状态；每个 execution 只在对象本地证据
   满足 `encyclopedia-primary-v2` 后确认发布资格。
4. **两段流水线**：download 与 author 以独立 execution stage 编排；download 可离线预跑
   （IO 密集，8-16 并发），author 只消费 download 就绪对象（Agent 密集，池化 4-8）；
   断点基线：完成的 source unit 不重下，同一 execution 只允许 resume。
5. **Agent 池化**：受控并发提升单机 author 吞吐；安全上限由 M1 校准批实测
   写入 runtime profile，不拍脑袋。
6. **跑批保护协议**：runtime 保护清单 + 活跃 lease 标记（复用 ops_governance lease
   概念），保护 frozen plan、`.qwq_output/release`、workflow state；key 生命周期
   （403/limit 自动暂停、恢复自动续跑）为 CLI 内置能力。
7. **载体统一**：四载体（homepage/article/image/video）共享共同层契约，lane adapter
   只表达输出物差异（homepage: page.md/_entity.json/manifest.json；article:
   writing_pack + draft.article.md；image: 单源图片作品；video: schema + smoke）。

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
- 放量后演进：云端弹性 worker 池（`--runtime cloud`）横向扩展，本设计的两段流水线与
  frozen plan 分发协议是其前置。

# L2 设计：object-homepage-coverage-scaling

## 架构总览

```text
[主清单扩容]                    [前置核验]                [两段流水线]
coverage discover/merge  →  source-screen 批量深核验  →  download stage (8-16 并发)
(五路来源发现→去重→打标      (回写 sourceReadiness       └→ author stage (bridge 池化 4-8)
 →写回市州 YAML)              三态+时间戳)                    └→ review → publish → ship
                                                              └→ coverage 账本 + env import
```

## 职责边界

| 组件 | 职责 | 真相源 |
|---|---|---|
| `qwq-data vertical coverage-*` | 候选发现、去重、打标、写回 | 市州 YAML（discovery_seed/2） |
| `qwq-data vertical source-screen` | 排产前深核验、三态回写 | 市州 YAML `sourceReadiness` + `sourceScreenedAt` |
| `qwq-data task run-recipe` | 省级批次编排（decompose/fanout/leaf） | recipe YAML + frozen plan |
| download stage | 源抓取、图片、sourceScreen 复核 | source unit + asset index |
| author stage | composer 成稿（只消费就绪对象） | writing_pack + page.md |
| `qwq-data ship` | promote 质量门、lookup 重建、coverage 回写 | publish 主线 + coverage ndjson |
| entity-service importer | homepage_state 灌库 + reload | import report v2 |

## 关键设计决策

1. **主清单自闭环**：目录即行政层级，无总控 index；扩容管线逐市州文件写回，
   `verify coverage-master-list` 门禁校验 schema 与全局唯一 canonicalName。
2. **sourceScreen 前置**：把运行时深核验（WP5 放弃主因）前移为排产前批量阶段，
   排产只消费核验后 ready；核验结论带时间戳，支持陈旧重验。
3. **两段流水线**：download 与 author 以独立 recipe stage 编排；download 可离线预跑
   （IO 密集，8-16 并发），author 只消费 download 就绪对象（bridge 密集，池化 4-8）；
   断点基线：完成的 source unit 不重下，author 用同 `--batch` resume 续跑。
4. **bridge 池化**：多 bridge 端口隔离提升单机 author 并发；安全上限由 M1 校准批实测
   写入 runtime profile，不拍脑袋。
5. **跑批保护协议**：runtime 保护清单 + 活跃 lease 标记（复用 ops_governance lease
   概念），保护 frozen plan、`.qwq_output/release`、workflow state；key 生命周期
   （403/limit 自动暂停、恢复自动续跑）为 CLI 内置能力。
6. **载体统一**：四载体（homepage/article/image/video）共享共同层契约，lane adapter
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
- coverage 账本（`publish/index/coverage/{省}.ndjson`）承载 hasHomepage 与 envImports
  审计口径。
- 放量后演进：云端弹性 worker 池（`--runtime cloud`）横向扩展，本设计的两段流水线与
  frozen plan 分发协议是其前置。

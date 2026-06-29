# workflow 目录与资产证据链规格（对象优先 · 来源内聚 · 阶段编号 · 公共上提 · 路径单一真相源）

本规格冻结 `runtime/tasks/{task}/` 工程过程目录的组织方式，使其**与 `publish/` 发布主线同构**，
并保证「单个对象（实体/内容）可集中查证」「来源与图片内聚」「`asset://` 可直查物理文件」「内部引用全为相对路径」。

`task_workflow` 是任务级编排根，`task_download` 是任务级下载规划工作区；两者只承载编排和中间态，不承载对象最终成品。

> 与 [`content_pipeline_spec.md`](content_pipeline_spec.md) 不冲突：该文是端到端管线主线，本文只补「目录与资产证据链」这一层契约。冲突以本文为准。
>
> **本规格是目录与路径的唯一真相源**。不得在别处维护第二套目录定义、命名约定或路径生成规则；
> 历史实现偏差已并入 `quwoquan_data/tasks/旅行/地域/四川省/景区/景区精选/notes.md`，本文只保留最新目录契约与验收门。

---

## 0. 关键裁定（消除 v1 的冲突与命名漂移，动手前生效）

历史实现存在 2 类问题：实体主页位置内部冲突、来源单元/阶段命名漂移。本节给出**唯一裁定**，后续所有目录树、处理要求、门禁、代码以此为准。

| 裁定项 | v1 的问题 | v2 裁定（唯一标准） | 实现需对齐 |
|---|---|---|---|
| **实体主页 scope** | §1.3 说 batch 内；`content_pipeline_spec` + 代码说 task 根 | **成品 task-scoped（跨批次唯一）落 task 根 `entities/`；过程 batch-scoped 落 batch 内 `entities/`** | `build/homepage.py`（已 task 根，保留）；batch 内补过程阶段 |
| **来源单元目录名** | 文本 `1.overview_baike` vs 代码 `001_overview_baike` | **`{seq:02d}.{sourceKind}`**（如 `01.overview_baike`） | 改 `paths.source_unit_dir` |
| **来源元数据文件** | 文本 `meta.json` vs 代码 `manifest.json` | **`meta.json`**（与对象成品 `manifest.json` 区分语义） | 改 `_common/source_unit.py` |
| **来源图索引** | 文本 `assets/index.json` vs 代码 `assets.index.json` | **`assets/index.json`**（assets 目录的清单内聚在 assets 内） | 改 `_common/source_unit.py` |
| **过程阶段枚举** | 代码 `3.compose/6.materialize`，文本 `3.brief/3.build/5.review` | **统一枚举见 §1.5；成品落对象根，无 `6.materialize` 阶段目录** | 改 `paths.STAGE_*` |
| **批次顶层目录** | 实际仍写 `download/build/produce/` | **batch 顶层只允许 `entities/ posts/ _shared/ batch_manifest.json`**，工作区改为 `task_workflow/ task_download/ task_build/ task_produce/ task_publish/ task_reconcile/` | 改各 handler 写入端 |
| **task_manifest 命名冲突** | `task_root/task_manifest.json` 已被 `_common/dedup.py` 占用为「去重账本」(completedEntities/...) | **`task_manifest.json` = 任务定义快照（§2.1/§14.1）；去重账本改名 `dedup_ledger.json`** | M4：改 `_common/dedup.py` + 拆 `paths.task_manifest` |
| **post 目录 angle 层** | `test_post_dir_layout.py` 断言 `posts/{type}/{title}/{seq}`（无 angle），与 `test_batch_object_paths` 的 angle 层冲突 | **统一为 `posts/{type}/{angle}/{title}/{seq}`（§2.5）；materialize 写入与两处测试同步** | M4：改 `materialize.py` + 两处测试 |

---

## 1. 五条原则 + 第六条（路径真相源）

1. **对象优先**：批次内一切过程产物都挂在「最终对象」目录下，不再按阶段平铺所有对象。对象 = 实体 / 内容（文章、图片、视频）。
2. **同构 publish**：对象目录结构与 `publish/`（`DataRoot`）一致——实体 `entities/{domain}/{type}/{name}/`，内容 `posts/{contentType}/{angle}/{title}/{seq}/`。**不使用** `objects/{objectKey}/` 写死目录，也不下划线压平标签树。
3. **阶段编号**：对象目录下每个过程阶段加序号前缀（§1.5）；最终成品落对象根（无序号），与 publish 对齐。
4. **公共上提**：任务级公共信息在 task 根，批次级公共信息在 batch 根 `batch_manifest.json` 与 `_shared/`；对象目录只放该对象自身的过程与成品，**不重复**任务/批次级信息。
5. **相对引用**：`citedSourceRefs / sourcePaths / sourceAssetRef` 等一律为相对 batch 根（或相对 task 根，见 §5）的 POSIX 相对路径，禁止绝对路径。
6. **路径单一真相源**：所有 runtime 目录路径**必须**由 `_common/paths.py` 的对象优先函数生成（§9）；handler / 脚本 / 测试**禁止**手拼路径，**禁止**用 stage-first 写函数（`batch_command_root/batch_inputs_dir/batch_results_dir`）产出新批次产物。

### 1.5 过程阶段枚举（唯一标准）

| 序号阶段 | 适用对象 | 含义 | 该阶段产物 |
|---|---|---|---|
| `1.download/` | 实体 / 内容 | 来源拉取与来源单元落盘 | `source_plan.json`、`sources/{NN}.{kind}/`（内容若引用实体来源则为 `source_refs.json`） |
| `2.quality/` | 实体 / 内容 | 来源质量分析 | `quality_analysis.json` |
| `3.compose/` | 内容 / 实体 | 内容创作契约 / 实体主页输入证据 | `writing_pack.json` / `entity_page_input.json` |
| `4.draft/` | 内容 / 实体 | 会话模型草稿 | `prompt.md`、`draft.article.md`、`page.md`、`draft_meta.json` |
| `5.review/` | 内容 / 实体 | human-in-loop 审校 + 追责快照 | `ledger.json`、`review.json`、`review_gate.json`、`repair_report.json`、`provenance.json` |
| （对象根，无序号） | 实体 / 内容 | **成品**（= promote 直拷 publish） | 见 §1.3 / §1.4 |

> 不存在 `6.materialize` 阶段目录：materialize 的产出就是「成品落对象根」，不另设阶段目录。

---

## 2. 完整目录树（逐文件，不遗漏）

### 2.1 任务根（公共，跨批次唯一）

```
runtime/tasks/{task}/                  # {task} = taskId 斜杠路径（committed 分类树同构，受版本控制的规格在 tasks/{task}/）
  task_manifest.json          # [处理] task 定义快照：intentLabel/垂类/organizeBy/scope/目标对象口径（由 task run 写，来源 committed task.yaml）
  notes.md                    # [处理] 人写任务说明（可选）
  catalog.ndjson              # [处理] 任务级对象台账（可选，assemble 消费）
  entities/{domain}/{type}/{name}/   # [处理] 实体【成品】，跨批次唯一，见 2.3-成品；promote_task_entities 直拷 publish
  posts/                      # [处理] 任务级聚合产物（assemble 用，可选）
  _shared/                    # [处理] 任务级共享（dedup_ledger.json / catalog.ndjson / entities.ndjson …）
```

> **批次工作区不再挂在任务根下**（消除「批次埋在 `旅行/地域/四川省/景区/…` 分类树深处、无法在顶层找到批次」的问题）。批次统一上提到顶层 `runtime/batches/{intentLabel}-{taskHash}__{batch}/`（见 2.2），通过 `batch_manifest.json.taskId` 反指所属任务。任务根只保留跨批次唯一的实体成品、任务定义快照与任务级共享账本。

### 2.2 批次根（顶层 `runtime/batches/`，批次级公共）

```
runtime/batches/{intentLabel}-{taskHash}__{batch}/   # intentLabel = 任务意图标签（≤16 字，源自 task.yaml.intentLabel）；taskHash = 归一 taskId 短哈希（8 hex），消歧同名任务
  batch_manifest.json         # [处理] 批次公共：taskId（反指任务，反查唯一依据）、目标对象、参数快照、env、salt、命令链、globalBatchSeq、时间戳、schemaVersion（新布局标识）
  _shared/                    # [处理] 批次级跨对象共享产物（不属于任一对象）
    source_catalog.json       #   受控来源类目白名单（限定 sourceKind，挡散文来源）
    content_object_index.json #   内容对象路由：ref → {contentType,angle,title,seq}（批次内 ref→对象唯一路由真相）
    compose_brief.json        #   批次共享叙事契约（可选）
    task_workflow_state.json  #   workflow 编排状态（批次工作区，不进对象/publish）
    assistant_tasks/          #   会话任务投递（可清理，可清空重投）
  entities/{domain}/{type}/{name}/   # 实体【过程】对象，见 2.3-过程
  posts/{contentType}/{angle}/{title}/{seq}/   # 内容对象（过程+成品），见 2.4
```

> - 批次目录名 = `{intentLabel}-{taskHash}__{batch}`：`intentLabel` 是 ≤16 字人类可读任务意图标签（由用户指令/对话在 `task new` / `select-targets` 时给定，落 `task.yaml.intentLabel`，缺省回退 taskId 末段清洗截断）；`taskHash` 是归一 taskId 的稳定短哈希（`sha1(normalizedTaskId)[:8]`）；`batch` 是批次号（含日期+序号）。首个 `__` 之前为「任务唯一前缀 `{intentLabel}-{taskHash}`」，之后为 `batch`。`batch_root()` 由 taskId 确定性拼装，不引入第二索引文件、不嵌全局 seq。
> - **为何要 `taskHash`**：fanout 各分区叶任务**同名**（如 `四川省/…/全国景点主页` 与 `云南省/…/全国景点主页`）且**共享同一 `batch`（`fanout_<plan>`）**，旧布局 `tasks/{taskId}/batches/{batch}/` 由 taskId 路径天然区分；上提到顶层后必须由 `taskHash` 重新提供任务唯一性，否则两任务会塌缩到同一目录、内容对象互相串扰。`intentLabel` 仅作人读标签（可被多任务复用）。
> - **batch→task 反查唯一依据仍是 `batch_manifest.json.taskId`**；`{intentLabel}-{taskHash}__` 前缀任务唯一，用于顶层候选目录的精确过滤与 `batch` 还原。
> - batch 顶层**只允许** `entities/ posts/ _shared/ batch_manifest.json` 四项；出现 `download/ build/ produce/ pipeline/` 即 BLOCK（§10 顶层结构门）。

### 2.3 实体对象目录（成品 task 根 / 过程 batch 内）

**成品（task 根 `entities/{domain}/{type}/{name}/`，跨批次唯一）：**

```
entities/{domain}/{type}/{name}/
  _entity.json                # [处理] 实体事实（label/domain/type/tagRefs/sourceRefs，回指 source 相对路径）
  page.md                     # [处理] 实体主页正文（>= MIN_PAGE_CHARS，reader-facing，无机械标题/平台词）
  manifest.json               # [处理] 实体资产/出处清单（assets[].sourceAssetRef 相对引用）
  assets/{assetId}.{ext}      # [处理] 主页配图，文件名 = assetId
```

**过程（batch 内 `batches/{batch}/entities/{domain}/{type}/{name}/`）：**

```
entities/{domain}/{type}/{name}/
  _object.json                # [处理] 对象索引：publish 目标相对路径 + 各阶段状态 + 成品 task 根相对路径
  1.download/
    source_plan.json          #   该实体来源计划（离线复跑入口）
    sources/{NN}.{sourceKind}/  #   来源单元，见 §3
  2.quality/
    quality_analysis.json     #   该实体来源质量分析（最小契约）
  3.compose/
    entity_page_input.json    #   compose 阶段送入会话模型的输入证据
  4.draft/
    page.md                   #   实体主页草稿
  5.review/
    review.json               #   实体审校结果
    provenance.json           #   追责快照
```

### 2.4 内容对象目录（batch 内 `posts/{contentType}/{angle}/{title}/{seq}/`，过程+成品同处）

```
posts/{contentType}/{angle}/{title}/{seq}/
  # ── 成品（落对象根，= promote 直拷 publish）──
  article.md                  # [处理] 最终正文（gallery carrier 可另行产出 gallery.md；article 载体不得写入）
  manifest.json               # [处理] post 最小发布契约（entityRefs/tagRefs/sourceTaskId/assets[].sourceAssetRef…）
  assets/{assetId}.{ext}      # [处理] 成品配图，文件名 = assetId
  _object.json                # [处理] 对象索引：publish 目标相对路径 + 各阶段状态
  # ── 过程（编号阶段，证据链）──
  1.download/
    source_refs.json          #   引用的来源单元相对路径（一般指向实体对象来源）
    sources/{NN}.{sourceKind}/  #   仅内容自身补充来源时才有，见 §3
  2.quality/
    quality_analysis.json     #   内容角度来源质量分析（最小契约）
  3.compose/
    writing_pack.json         #   创作契约（content_pipeline_spec §2 最小字段；assets[] 用 assetId 接真实图）
  4.draft/
    prompt.md                 #   模型输入
    draft.article.md          #   会话模型写回的草稿正文
    draft_meta.json           #   生成出处（generator/model/styleFamily/openingStrategy/citedSourcePaths/coveredFacts）
  5.review/
    ledger.json               #   human-in-loop 账本（裁决真相源）
    review.json               #   最小 envelope：decision/issues/check pass
    review_gate.json          #   完整诊断
    repair_report.json        #   修复建议 + evidence_summary
    provenance.json           #   最终追责快照
  gallery.md                  # [处理] 仅 gallery carrier 可选；article carrier 不得写入
```

---

## 2.5 内容对象 angle 与命名（消除 produce 面缺 angle 的偏差）

- `angle` = 内容角度标签最后一段（与 tag / `content_pipeline_spec` 角度体系一致），如 `攻略`；它是 `posts/{contentType}/{angle}/{title}/{seq}/` 的**必选层级**，与 publish `DataRoot.post_dir` 一致，**不得省略**。
- 编排器默认每实体取 `task.content.angles[0]` 产 1 篇代表作；多角度扩产由独立 batch 串跑（显式扩展 refs），不在单次 run 内放大成 N×M。
- `title` = `{实体名}·{angle}`（= 现 publishTitle）；`seq` 同标题多篇按 ref 稳定递增，默认 `1`。
- 落盘 angle 取自 `3.compose/writing_pack.json` 或 `4.draft/draft_meta.json` 的 `angle`（= compose intent），materialize 据此定位对象根，不再写 `produce/posts/...`。

---

## 3. 来源单元内聚契约（source unit）

每个来源是一个**稳定 sourceUnitId** 的批次级自包含单元，实体/内容对象只保留 `1.download/source_refs.json` 软引用索引，替代旧「实体目录承载来源 + 图片与来源分离」布局：

```
sources/{sourceUnitId}/
  source.md            # 原文
  source.clean.md      # 清洗后正文
  source.quality.json  # 来源质量评分（score / retained / 信号命中）
  meta.json            # 来源说明：{url, title, sourceKind, relevance, credit, license, fetchedAt}
  assets/{assetId}.{ext}        # 该来源自带图片，文件名 = assetId
  assets/{assetId}.variants/{profile}.webp   # 多变体（thumbnail/display/cover/full）
  assets/index.json    # 每图：{assetId, fileName, url, sha256, bytes, width, height, license, credit, relevance, sourceUnitRef, variants[]}
```

约束：
- `sourceUnitId` 由 canonical URL、source snapshot hash 与原始 source key 稳定派生；同一底稿内容跨对象只物理存一份。
- 对象级 `1.download/source_refs.json` 记录 `sourceRef`、`metaRef`、`sourceId`、`ordinal`、`researchLane`、`sourceUseMode`、`publishMediaMode` 与 `targetRefs`。
- `sourceKind` 取自 `_shared/source_catalog.json` 白名单（§7）。
- **禁止对象级散落 `images/`**：任何图片必须归属某来源单元 `assets/`，并在 `assets/index.json` 标注 `relevance`（与对象相关性，便于人审）。
- `meta.json.relevance` 解释「这条来源为何与该对象相关」，杜绝孤立无法判断相关性的来源。

---

## 4. 资产可追溯契约（asset closure，相对路径）

目标：从 `article.md`/`page.md` 的 `asset://{assetId}` 能**不查 manifest**直接定位物理文件，并反查来源原图。

1. **文件名即 assetId**：成品与来源单元的物理资产文件名 = `{assetId}.{ext}`；`article.md` 写 `asset://{assetId}`，目录下同名文件即是。
2. **manifest 资产闭环**：`manifest.assets[]` 每项含 `{assetId, fileName, caption, imageLayout, sourceAssetRef}`，`sourceAssetRef` 指向来源单元原图的**相对路径**。
3. **出处相对化**：`manifest.citedSourceRefs` / `provenance.sourcePaths|citedSourcePaths` 全部相对 batch 根（实体成品在 task 根时相对 task 根），禁止绝对路径。
4. 相对路径统一由 `paths.relative_batch_ref(...)`（或 task 根等价函数）生成，禁止手拼。

### 4.1 成品资产命名与批次稳定性（新增）

- 成品 `assetId` 统一采用 `实体_角色_全局批次号_hash`，其中 `globalBatchSeq` 为十进制原样输出，不补零；解析时从右锚定 `digest8`、`globalBatchSeq` 与 `role`。
- `globalBatchSeq` 的唯一真相源是 `batches/{batch}/batch_manifest.json`，每个批次工作区首次创建时分配一次，同 `batch_id` resume/重跑沿用原号。
- 批内唯一性只在本批内用 `asset_id_registry.json` 约束；冲突时通过 `nonce` 重算 hash，不做全局 asset 注册表或全仓扫描。
- 双批真实联网 E2E 稳定性验证见 [`asset_id_zero_collision_spec.md`](asset_id_zero_collision_spec.md) 与 [`batch_stability_e2e_spec.md`](batch_stability_e2e_spec.md)。

---

## 5. 公共上提边界（避免重复）

| 信息 | 唯一位置 | 禁止 |
|---|---|---|
| 任务定义/口径/intentLabel | `runtime/tasks/{task}/task_manifest.json`、committed `tasks/{task}/task.yaml` | 在对象目录重复 |
| 批次归属任务（反查唯一依据） | `runtime/batches/{intentLabel}-{taskHash}__{batch}/batch_manifest.json.taskId` | 用目录名 intentLabel 当反查真相 |
| 批次参数/env/salt/命令链/globalBatchSeq/时间/schemaVersion | `runtime/batches/{intentLabel}-{taskHash}__{batch}/batch_manifest.json` | 在对象目录重复 |
| 受控来源类目 | `runtime/batches/{intentLabel}-{taskHash}__{batch}/_shared/source_catalog.json` | 每对象各存一份 |
| 批次级共享 brief | `…/_shared/compose_brief.json` | 复制进每个内容对象 |
| workflow 状态 | `…/_shared/task_workflow_state.json` | 上提到对象根 |
| 实体成品（事实/主页/资产） | `runtime/tasks/{task}/entities/{d}/{t}/{name}/`（跨批次唯一，不随批次上提） | 在每个 batch 重复生产 |
| 对象自身来源/质量/草稿/审校/内容成品 | 对象目录 `N.xxx/` 与对象根 | 上提到批次根 |

---

## 6. 受控来源类目（挡 weather_* 散文）

- `_shared/source_catalog.json` 登记本批次允许的 `sourceKind` 白名单及含义。
- `weather_*` 不作为独立普通来源；天气信息应作为百科/攻略来源（如 `overview_baike`）中的**事实段落**自然包含。
- 门禁：来源单元 `sourceKind` 必须命中 catalog；未登记类目（含裸 `weather_*`）BLOCK。

---

## 7. 文风（去机械化结尾）

- 删除模板化标题 `## 它到底适合谁`，并禁止其等价机械句式作为独立小节标题。
- 「适合谁」的判断融入体验/建议段，以自然语气表达，不再每篇一个固定小节。
- 门禁：标题级机械句式（精确匹配清单）BLOCK。

---

## 8. 与 publish 同构映射（对象根 ⇄ 发布主线）

| 对象 | batch/task 内对象根 | publish 目标 | 一致点 |
|---|---|---|---|
| 实体 | task 根 `entities/{domain}/{type}/{name}/` | `publish/entities/{domain}/{type}/{name}/` | `_entity.json/page.md/manifest.json/assets/` |
| 内容 | batch 内 `posts/{contentType}/{angle}/{title}/{seq}/` | `publish/posts/{contentType}/{angle}/{title}/{seq}/` | `article.md/manifest.json/provenance.json/assets/` |

promote/ship 时对象根成品**直接拷贝**到 publish 同名路径；过程阶段（`N.xxx/`）不进入 publish。
内容对象 produce 面带 `angle` 层后与 publish `DataRoot.post_dir` 完全同构，promote 退化为同名直拷。

---

## 9. 路径真相源与禁止事项（原则 6 的强制落地）

唯一路径生成器：`_common/paths.py`。新批次写入只允许以下对象优先函数：

| 用途 | 必须使用 | 禁止 |
|---|---|---|
| 批次公共 | `batch_manifest_path` / `batch_shared_dir` | 在对象目录写公共信息 |
| 实体过程对象根 | `batch_entity_object_dir` | `batch_command_root(..,'build'/'download')` |
| 实体过程阶段 | `batch_entity_stage_dir(.., STAGE_*)` | 手拼 `/results/` `/inputs/` |
| 内容对象根 | `batch_post_object_dir(.., angle, ..)` | `batch_command_root(..,'produce')/'posts'` |
| 内容过程阶段 | `batch_post_stage_dir(.., STAGE_*)` | 手拼 produce 子目录 |
| 来源单元 | `batch_source_unit_dir(task_id, batch_id, sourceUnitId)` + 对象 `1.download/source_refs.json` | 对象级 `images/`、自拼 sources 路径 |
| 相对引用 | `relative_batch_ref` / task 根等价 | 绝对路径、`os.path.join` 手拼 |

禁止：
- handler/脚本/测试调用 `batch_command_root / batch_inputs_dir / batch_results_dir` **写新批次产物**（仅历史档案读取例外，且必须经 `schemaVersion` 判定）。
- 样例脚本 `rebuild_directory_layout_sample.py` 与产线使用不同路径函数（必须共用同一套，杜绝「样例符合、产线不符合」再次发生）。

---

## 10. 防偏差门禁矩阵（保障不再漂移）

> 上一轮偏差的根因之一是「门禁声明性豁免 stage-first，绿 ≠ 达标」。v2 用以下门禁把规格变成可机检契约，并接入 `verify_quwoquan_data.sh` 与 `make gate`。

| 门 | 校验内容（对照本规格章节） | 处置 | 状态 |
|---|---|---|---|
| **批次顶层归属门**（`verify_directory_evidence_chain.py`） | 批次工作区只能落顶层 `runtime/batches/{intentLabel}-{taskHash}__{batch}/`，**不得**再出现在 `runtime/tasks/{task}/batches/`；`batch_manifest.json.taskId` 必填且与 intentLabel 自洽 | BLOCK | ◑ 本版落地 |
| **顶层结构门**（新增 `verify_directory_layout_structure.py`） | §2.2 batch 顶层只允许 4 项；出现 `download/build/produce/pipeline/` BLOCK；内容对象路径 = `posts/{type}/{angle}/{title}/{seq}`；阶段名 ∈ §1.5 枚举且带序号 | BLOCK | ❌ 待建 |
| **去 stage-first 豁免**（改 `verify_directory_evidence_chain.py`） | 删除「stage-first 不在扫描范围」，新布局批次全量纳入（scan 遍历顶层 `runtime/batches/`，taskId 取自 `batch_manifest.taskId`）；按 `batch_manifest.schemaVersion` 区分新旧 | BLOCK | ◑ 本版落地 |
| **批次号/资产零碰撞门**（新增 `verify_asset_id_zero_collision.py`） | §4.1/§14.2 `globalBatchSeq` 单调；批内 registry + `parse_post_asset_id` 零碰撞 | BLOCK | ❌ 待建 |
| **命名一致门** | §0/§3：来源单元 `{NN}.{kind}`、`meta.json`、`assets/index.json`、阶段枚举 | BLOCK | ❌ 待建 |
| **散落 images 门** | §3 无对象级 `images/` | BLOCK | ✅ 已有 |
| **相对路径门** | §4/§5 manifest/provenance 无绝对路径 | BLOCK | ✅ 已有 |
| **资产闭环门** | §4 `sourceAssetRef` 源图存在 | BLOCK | ✅ 已有 |
| **来源类目门** | §6 sourceKind 命中 catalog、挡 weather_* | BLOCK | ✅ 已有 |
| **来源图门** | §3 relevance 必填、像素尺寸、去重、变体 | BLOCK | ✅ 已有 |
| **机械标题门** | §7 | BLOCK | ✅ 已有 |
| **路径真相源门**（新增） | §9 扫 handler 是否调用禁用的 stage-first 写函数 | BLOCK | ❌ 待建 |
| **规格↔实现同步门**（新增） | §1.5/§3 枚举与 `paths.py` 常量一致；样例脚本与产线共用 paths | BLOCK | ❌ 待建 |
| **双批稳定性比对门**（新增 `verify_batch_stability_compare.py`） | §4.1/§11/§12 baseline snapshot + candidate compare；目录同构 + 质量非回归 | BLOCK | ❌ 待建 |

---

## 11. 落地状态与未完成清单（历史，只读）

> e2e_1 实测对照本规格的逐项状态。该段仅作历史回溯，不作为本版最新规范输入。✅ 已达标 / ◑ 部分 / ❌ 未落地。本规划的「完成」定义 = 下表全部 ✅ 且 §10 门全绿。

| # | 维度 | 规格章节 | e2e_1 现状 | 目标 | 待办归属 |
|---|---|---|---|---|---|
| D1 | 批次顶层对象优先 | §2.2 | ❌ `download/build/produce/` 平铺 | batch 顶层仅 4 项 | P1 写入端 |
| D2 | 内容对象路径含 angle | §2.4/§8 | ❌ `produce/posts/{type}/{title}/{seq}`（缺 angle） | `posts/{type}/{angle}/{title}/{seq}` | P1 `materialize.py` |
| D3 | 实体成品/过程分层 | §2.3 | ◑ 成品 task 根（符合裁定），batch 内缺过程阶段 2/3 | 补 batch 内 `2.quality/3.build/_object.json` | P1 `homepage.py` |
| D4 | 过程阶段编号 | §1.5/§2.4 | ◑ 草稿已落对象 `3.brief/4.draft`（M3b 绿）；brief 输入/stage 报告待迁 | 对象内 `1..5` 编号阶段 | M3c/M3d produce/* |
| D5 | 批次公共上提 | §2.2/§5 | ✅ download/task run 产出 `_shared/source_catalog.json` + `batch_manifest.json`（M2 落地，测试绿） | 维持 | M2 ✓ |
| D6 | 对象索引 `_object.json` | §2.3/§2.4 | ❌ 无 | 每对象产出 | P1 各 handler |
| D7 | task 根 `task_manifest.json` | §2.1 | ⚠️ 未产出 | task run 写 | P1 task run |
| D8 | 来源单元命名 | §0/§3 | ✅ `{NN}.{kind}`/`meta.json`/`assets/index.json`/`sourceKind`（M1 已落地，配套测试绿） | 维持 | M1 ✓ |
| D9 | 图片归属/变体 | §3 | ✅ | 维持 | — |
| D10 | 相对路径 | §4/§5 | ✅ | 维持 | — |
| D11 | 文风去机械标题 | §7 | ✅ | 维持 | — |
| D12 | 来源类目挡 weather | §6 | ✅ | 维持 | — |

### 执行分步（里程碑 M1–M7，每步以「该步测试绿 + §10 对应门绿」收口；M7 收口端到端重跑）

- **M1 地基（✅ 已完成）**：`paths.py` 阶段常量/枚举对齐（去 `3.compose`/`6.materialize`，引入 `3.brief`/`3.build`）+ `relative_task_ref/object_index_path/batch_source_catalog_path/batch_pipeline_state_path/batch_assistant_tasks_dir` 新增；`source_unit.py` 命名 `{NN}.{kind}`/`meta.json`/`assets/index.json`/`sourceKind`；`verify_directory_evidence_chain.py` 同步；`test_batch_object_paths`/`test_source_unit_evidence_chain`/`test_directory_evidence_gate`/`test_image_download_gates`/`test_download_images` 全绿。
- **M2 download 对象化（✅ 已完成）**：`prepare.py`/`source_inputs.py`(curated_sources/images, 含旧布局历史读取)/`run.py`(download_plan checkpoint + 启动写 batch_manifest/source_catalog)/`evidence_contract.py` 把 `source_plan` 从 `download/inputs/source_plan/{eid}.json` 切到 `entities/{d}/{t}/{name}/1.download/source_plan.json`；新增 `_common/batch_manifest.py` 产出 `_shared/source_catalog.json`（投影 committed catalog）与 `batch_manifest.json`（对象优先定义快照，幂等）；assistant_tasks 投递落 `_shared/assistant_tasks`；`prepare` 迁移安全（对象/旧计划任一存在即不覆盖）；新增 `test_batch_shared_artifacts`，并更新 `test_download_source_plan`/`test_download_images`/`test_task_run_pipeline` 到对象优先；`verify_quwoquan_data.sh` 全绿。注：download gate/stage report（`download/results/*`）仍 stage-first，连同 produce 一并在 M6 迁 `_shared/` 后启用顶层结构门。
- **M3 produce 过程对象化（✅ 已完成）**：`entity_workflow.py`/`route_workflow.py`/`draft_io.py`/`produce/handler.py`/`stage_reports.py` 把 compose/draft/review 从 `produce/{inputs,drafts,results}/{ref}` 扁平面切到内容对象 `3.brief/4.draft/5.review`（M3a 路由 + M3b 草稿 + M3c brief 输入 + M3d 阶段报告/账本对象化，读取端经 `read_stage_envelope`/`iter_stage_envelopes` + `iter_ledgers` 对象优先 + legacy 回退去重）。
- **M4 materialize 对象根+angle（✅ 已完成）**：`materialize.py` 成品（article/manifest/provenance/gallery/assets）落内容对象根 `posts/{type}/{angle}/{title}/{seq}/`，angle/title/seq 以 `content_object_index.json` 路由为唯一坐标真相（删 `_build_title_seq_index` 自算序号），并写 `_object.json`（§14.3）；过程阶段证据保留同处对象根（只清成品 assets/，不再 `rmtree` 整 posts）。`run.py` 启动写 `task_manifest.json`（任务定义快照 §14.1，去重账本改名 `dedup_ledger.json`）+ `task_workflow_state.json` 落 `_shared/`。`promote_to_publish.py` 改为成品白名单拷贝（过程阶段目录 `1.download/2.quality/3.brief/3.build/4.draft/5.review` 不进发布包）+ 读 `batch/posts`；`publish_filter.py` 账本/实体边车读 `5.review/`。`post_verify.resolve_posts_roots` 对象优先。
- **M5 读取端 + 历史读取（✅ 已完成）**：新增 `paths.batch_posts_root`/`batch_post_roots`（对象优先 + 旧 `produce/posts` 历史读取）；produce/posts 读取端（`produce/gate.py` 重写为四层叶子发现 + 阶段报告对象优先、`media/handler.py` 回退经路由定位、`verify_content_semantics.py`/`verify_content_quality.py` 默认根、`quality/dirty_data.py` 脏数据扫描、`reconcile/diff.py` 漂移扫描、`publish/assemble.py` release 拼装成品白名单、`task/ops.py latest_post_outputs`）全部切到 `batch/posts` 对象根；`_common/evidence_contract.py` materialize 输出串改对象根；`_common/content_evidence.py` 仅涉 download 来源（已 M2 落地，无需改）。
- **M6 门禁（✅ 已完成）**：`verify_directory_evidence_chain.py` 在原有 5 项（散落 images/绝对路径/机械标题/无类别 weather/资产闭环）之上新增 4 门——**命名门**（posts=type/angle/title/seq、entities=domain/type/name、阶段子目录 ⊆ 编号阶段∪assets、来源单元 NN.kind）、**顶层结构门**（批次根条目 ⊆ {entities,posts,_shared,batch_manifest.json} ∪ 受控 workspace 命令目录）、**回退门**（produce 已迁对象根的 posts/inputs/drafts/results/review 扁平面被重写即 BLOCK）、**同步门**（盘上成品对象 ⊆ `content_object_index` 路由，防漂移）。已经 `verify/gate.py(gate_verify→scan_batch)` 接入 `qwq-data verify`，并由 `test_directory_evidence_gate`（红/绿全覆盖）随 `verify_quwoquan_data.sh` 执行。路径真相源门(A8)以「回退门(runtime) + 样例与产线共用 `_common.paths`/`content_object` 路由」落实（`rebuild_directory_layout_sample.py` 已改为经路由解析 post 目录，不再自构路径）。
- **M7 清理 + 重跑 + 自检（✅ 已完成）**：清理 runtime 旧 stage-first 产物（gitignored 的 `runtime/tasks` 旧 `e2e_1`：含 `produce/posts`、`produce/drafts`、`pipeline/` 等扁平面）；确定性重建 `layout_sample`（无网络，`rebuild_directory_layout_sample.py` 经路由登记内容对象 + 写 `_object.json` + 修正纹理尺寸至像素门 960×640）；`scan_all` 全 runtime 绿；48 项数据测试全绿（含真实管线 e2e：`test_task_run_pipeline`/`test_entity_composer`/`test_verify_pilot_gwt`/`test_hitl_pipeline` 走 produce→materialize→verify 对象优先链路）。逐条对照 §2/§12：A1–A7、A9 由样例 + 门 + 对应测试覆盖；A8 见 M6；A10（App/Web 渲染）属端侧合约测试，不在本数据工程门内。注：真实网络内容重跑需在 download_plan/produce_author 等 checkpoint 由会话 agent 介入检索与成文，非确定性、需人参与，单列后续动作。

---

## 12. 验收（GWT，可机检；映射 §10 门 + T1–T4）

| # | Given | When | Then（验收） | 门/测试 | 层 |
|---|---|---|---|---|---|
| A1 | 新批次跑 download | 写入来源 | 来源落 `sources/{sourceUnitId}/`，对象只写 `1.download/source_refs.json`，图片在来源单元 `assets/`，无对象级散 `images/` | `test_batch_object_paths` + download 门 | T1 |
| A2 | 来源单元含图 | 写 `assets/index.json` | 每图有 `assetId/fileName/sha256/width/height/relevance/sourceUnitRef/variants` | 来源图门 | T1 |
| A3 | 内容 materialize | 写成品 | 成品落 `posts/{type}/{angle}/{title}/{seq}/` 对象根，`asset://` 可直查文件 | `test_post_dir_layout`（扩展） | T2 |
| A4 | manifest/provenance | 写出处 | 引用字段相对路径，无绝对路径 | 相对路径门 | T2 |
| A5 | 批次目录 | 列目录 | 顶层仅 `entities/posts/_shared/batch_manifest.json`；过程阶段带序号；公共信息不在对象重复 | **顶层结构门** | T2 |
| A6 | 来源类目 | 写来源 | `sourceKind` 命中 catalog；裸 `weather_*` BLOCK | 来源类目门 | T2 |
| A7 | 文章正文 | review | 无机械收尾标题 | 机械标题门 | T2 |
| A8 | handler 写入 | 静态扫描 | 无 stage-first 写函数用于新批次；样例与产线共用 paths | **路径真相源门 + 同步门** | T1 |
| A9 | 同构 publish | promote | 对象根成品与 publish 同名，直拷 | `test_ship_sampling` | T3 |
| A10 | App/Web 渲染 | 加载成品 | `asset://` → 物理/CDN 可解析渲染 | `markdown_seo_html_renderer_test.dart` | T4 |

---

## 13. 旧布局迁移说明（历史，只读）

- 旧 stage-first 目录（`download/ produce/ build/`）不再作为新批次规范输出；仅作为历史运行痕迹保留在旧批次中。
- 新批次只写本规格结构，不再接受任何旧路径映射。
- 迁移代表样例和历史 runtime 批次的清理结果，记录在任务 notes 与运行记录，不回写进规范正文。

---

## 14. 关键产物 schema 附录（最小字段，实施据此产出/校验）

> 仅列最小必填；可加字段但不得少。所有路径字段为相对引用（§4/§5）。

### 14.1 `runtime/tasks/{task}/task_manifest.json`
`{ schemaVersion:"quwoquan.task.manifest", taskId, intentLabel, vertical, organizeBy, scope{region?, entityTypes[], coverageTargets[]}, content{angles[]}, createdAt }`
（`intentLabel` = ≤16 字人类可读任务意图标签，来源 committed `task.yaml.intentLabel`；它是顶层批次目录前缀 `runtime/batches/{intentLabel}-{taskHash}__{batch}/` 的唯一标签真相源。）

### 14.2 `runtime/batches/{intentLabel}-{taskHash}__{batch}/batch_manifest.json`
`{ schemaVersion:"quwoquan_data.batch_manifest", taskId, batchId, layout:"object-first", env, salt, params{}, coverageTargets[], commandChain[], globalBatchSeq, createdAt, updatedAt }`
（`taskId` 是 **batch→task 反查的唯一依据**（目录名 intentLabel 仅用于人读定位与候选过滤，可被多任务复用）；`layout` 与 `schemaVersion` 是新旧布局判定依据；§10 去豁免门与 §13 旧布局历史说明据此区分新旧批次。）

### 14.3 对象 `_object.json`（实体过程根 / 内容对象根各一份）
`{ schemaVersion:"quwoquan.object.index", objectKind:"entity"|"content", objectRef, publishTargetRef(相对 publish 根), finalRef(成品相对路径), stages{ "1.download":"done"|"pending"|... }, updatedAt }`

### 14.4 `_shared/source_catalog.json`
`{ schemaVersion:"quwoquan.source_catalog", sourceKinds:[ {kind, label, allowsImages:bool, note} ] }`

### 14.4b `_shared/content_object_index.json`
`{ schemaVersion:"quwoquan_data.content_object_index/1", refs:{ "<ref>": {contentType, angle, title, seq} } }`
（批次内 `ref → 内容对象坐标` 的**唯一路由真相**。坐标在 compose-brief 时由 brief 确定性算出：`angle=_publish_angle(brief)`、`title=titleHint={实体}·{angle}`、`contentType=produce --type`、`seq` 默认 1，同组多 ref 按 ref 稳定排序。draft_io / produce stage 写入 / materialize / 读取端统一经此路由解析对象目录，杜绝 ref 在阶段目录间漂移。）

### 14.5 来源单元 `assets/index.json`
`{ assets:[ {assetId, fileName, url, sha256, bytes, width, height, license, credit, relevance, sourceUnitRef, variants:[{profile, fileName, width, height, format, quality, byteSize, sha256}]} ] }`

---

## 15. task run 编排落盘约定（对象优先，`task/run.py` 据此切换）

> 编排器是薄壳，stage 间流转改为「写对象阶段目录」；`task_workflow_state.json` 与 `assistant_tasks/` 属批次工作区，落 `_shared/`（不进对象目录、不进 publish）。
>
> 批次工作区根 = 顶层 `runtime/batches/{intentLabel}-{taskHash}__{batch}/`（不再挂任务根）；`build_homepage` 仍把实体**成品**落任务根 `runtime/tasks/{task}/entities/{d}/{t}/{name}/`（跨批次唯一），批次内只放实体过程对象。

| stage | 类型 | 对象 | 写入位置（对象优先） |
|---|---|---|---|
| download_plan | checkpoint | 实体 | `entities/{d}/{t}/{name}/1.download/source_plan.json` |
| download_fetch | auto | 实体 | `sources/{sourceUnitId}/` + `entities/{d}/{t}/{name}/1.download/source_refs.json` |
| build_prepare | auto | 实体 | `entities/{d}/{t}/{name}/3.build/entity_page_input.json` |
| build_homepage | checkpoint | 实体 | 成品落 task 根 `entities/{d}/{t}/{name}/`（page.md/_entity.json/manifest.json/assets/） |
| build_validate | auto | 实体 | 采纳门读 task 根成品 + batch 内 `2.quality/` |
| produce_plan | auto | 内容 | `posts/{type}/{angle}/{title}/{seq}/3.brief/`（brief 输入） |
| produce_compose | auto | 内容 | `3.brief/writing_pack.json` + `4.draft/prompt.md` |
| produce_author | checkpoint | 内容 | `4.draft/draft.article.md` + `draft_meta.json` |
| produce_annotate | auto | 内容 | 原地标注 `4.draft/draft.article.md` |
| produce_review | auto | 内容 | `5.review/{ledger,review,review_gate,repair_report}.json`；通过则成品落对象根 |
| ship | auto | 实体+内容 | promote 对象根成品 → publish 同名 |

批次工作区（非对象、非 publish）：`_shared/assistant_tasks/`、`_shared/task_workflow_state.json`、`_shared/repair_report/`。

### 15.1 produce ref → 内容对象 路由与落盘细则（M3 实施据此，杜绝阶段目录漂移）

唯一路由：`_common/content_object.py`（§14.4b 索引）。compose-brief 阶段（`build_*_writing_pack`）先 `register_from_brief(task,batch,ref,brief)` 登记 `ref→coords`，之后所有 produce 路径都经路由解析；未登记 ref 只读回退旧 `produce/drafts|inputs|results`（迁移回溯）。

| 现状（stage-first 扁平面） | 目标（对象优先，经路由） | 改造点 |
|---|---|---|
| `produce/inputs/compose/{ref}.json`（brief 输入） | `posts/{type}/{angle}/{title}/{seq}/3.brief/brief.json` | `run.py _run_produce_plan` / `plan.write_brief` / `iter_*_briefs` |
| `produce/drafts/{ref}/writing_pack.json` | `…/3.brief/writing_pack.json` | `draft_io.writing_pack_path` |
| `produce/drafts/{ref}/{prompt.md,article.md,draft_meta.json}` | `…/4.draft/{prompt.md,draft.article.md,draft_meta.json}` | `draft_io.*` + agent prompt 提示 + `batch_orchestration` |
| `produce/results/{compose_brief,compose,review,quality_analysis}/{ref}.json` + `*_gate`/`repair_report` | `…/2.quality/quality_analysis.json`、`…/5.review/{review,review_gate,repair_report}.json`；compose 快照并入 `5.review/compose.json` | 新增 `_common/object_stage_reports.py`（produce 专用对象写入），entity/route_workflow 切换；download 仍用 `stage_reports`（M6 再迁 `_shared`） |
| `produce/review/{ledger,entities}/{ref}.json` | `…/5.review/{ledger,entities}.json` | `review_ledger.py` |
| `produce/posts/{type}/{title}/{seq}/`（缺 angle） | `posts/{type}/{angle}/{title}/{seq}/`（对象根成品）+ `_object.json` | `materialize.py`（M4） |

- 草稿正文文件名统一为 `draft.article.md`（区别于成品 `article.md`，避免 posts 扫描误判）；agent 写回提示、`batch_orchestration.articleOut` 与对应测试同步改名。
- materialize（M4）从对象 `4.draft/draft.article.md` + `3.brief/writing_pack.json` + `5.review/*` 读，成品写对象根 `article.md/manifest.json/provenance.json/assets/` + `_object.json`，不再写 `produce/posts`。
- `_drafts_authored`（task run author checkpoint）改为遍历路由索引 ref 判定草稿就绪，替代 `drafts/*/article.md` 扫描。

### 15.2 M3 实施子步（每步保持 produce 测试 + verify 门全绿）

- **M3a（✅ 已完成）**：`_common/content_object.py` 路由 + `_shared/content_object_index.json` + `test_content_object_router`，接入 verify。
- **M3b（✅ 已完成）**：草稿三件套（writing_pack→`3.brief`，prompt/draft.article/draft_meta→`4.draft`）经路由落对象；`build_*_writing_pack` 登记路由；`draft_io` 路径解析 + 旧布局只读回退；草稿正文改名 `draft.article.md`；`batch_orchestration` 写回路径经路由相对化；`_drafts_authored`/跨篇相似度扫描切 `iter_draft_articles`；测试同步全绿。
- **M3c（✅ 已完成）**：compose brief 输入落对象 `3.brief/brief.json`（`content_object.write_brief_object/read_brief_object/iter_briefs/has_briefs`）；`run.py _run_produce_plan` 写对象 brief；`iter_route_briefs/iter_entity_briefs`、`load_compose_brief`、produce handler 入口守卫、`content_review`、`verify_content_semantics` 全部经路由读 brief + 旧扁平面只读回退；测试全绿。
- **M3d（✅ 已完成）**：produce 阶段报告对象化——`stage_reports` 新增 produce step→对象阶段映射（quality_analysis(+gate)→`2.quality`、compose_brief(+gate)→`3.brief`、compose/review/media_check(+gate)/repair_report→`5.review`），对象目录内文件名为 `{step}.json`；统一读取端 `read_stage_envelope`/`iter_stage_envelopes`（对象优先 + legacy 去重回退）；`review_ledger` 账本/实体边车落 `5.review/{review_ledger.json,review_entities.json}`（`load_ledger`/`iter_ledgers` 双源去重）；读取端 `media/handler`、`media/gate`、`produce/validate`、`verify/gate`、`task/run` review_gate 聚合、`materialize`（review+compose 读取与序号索引）全部切换；`evidence_contract` 路径串同步对象树；48/48 数据测试全绿（含全链路 e2e）。顺带修复历史遗漏：`build_writing_pack` 现输出 `publishLayout`。
- **M3c**：brief 输入落 `3.brief/brief.json`；`iter_*_briefs` 经路由枚举；`run.py _run_produce_plan` / `plan.write_brief` 切换；`content_review`/handler 的 compose-inputs 读取同步。
- **M3d**：produce stage 报告（quality_analysis/compose/review/gate/repair/ledger）经 `object_stage_reports` 落 `2.quality`/`5.review`；同步 `gate`/`validate`/`media`/`review_ledger`/`materialize` 读取端；`evidence_contract` produce 段更新。

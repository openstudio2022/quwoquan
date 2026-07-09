# workflow 内容生产规格（Agent 生产 · Human-in-loop · 一键发布到运行库）

本规格描述从「人定义任务」到「内容灌入各环境运行库」的端到端主线。所有命令统一经 `qwq-data` CLI 暴露。
`workflow run` 是任务级编排入口；`task_download` 是任务级检索规划工作区；对象级 `1.download..5.review` 是唯一成品前过程树。

## 0. 单一主线与去版本化

- `publish/` 是**唯一发布主线**，目录为 `publish/{posts,entities,tags,index,sample_bundles}/`，无 `v{N}` 版本目录。
- `publish/publish_meta.json` 记录 `lastPromote` / `lastShip` / `lastReleaseId`，无 `activeVersion`。
- 门禁 `verify_no_legacy_hardcode.py` 禁止 `publish/v{N}`、objectKey `/v{N}/` 段、`chuanxi`/`*_v5` 等区域/任务硬编码回归。

### 0.1 平台级 Agent 内容供给组织模型

内容生产不按“单脚本生成正文”理解，而按公司治理式 Agent 组织运行：规划、检索、权利、创作、审校、修订、发布和反馈分权协作。总纲见 [`agent_content_supply_operating_model.md`](agent_content_supply_operating_model.md)。

核心原则：

- 上游锁定任务、事实、权利、载体、作者边界和验收标准。
- 中游给 AI 创作自由，允许自主决定标题、结构、叙事节奏、表达风格和信息取舍。
- 下游由独立 gate 审核事实、权利、图文一致、作者边界、非模板感、重复和消费价值。
- Agent 口头成功不具备准出效力；只认结构化 packet、文件 hash、`GateVerdict` 和 `TokenLedger`。
- 单个对象可快速失败并隔离复盘，不得阻塞同批其它可交付对象。

## 1. 入口：人定义生成任务

`qwq-data plan` 把内容指令解析为 `compose_brief`（叙事契约 / imagePlan / imagePolicy / mustIncludeFacts）。
垂类（travel/campus…）数据驱动，无 region/task 专属分支。

### 1.1 `qwq-data data` 命令族总表

| 命令 | 输入 | 输出 | stop-if | handoff |
|---|---|---|---|---|
| `explore` | 任务说明、目标范围、notes、已有目录快照 | 探索包、候选对象清单、候选 sourceKind 白名单、初步检索维度 | 目标对象不完整、主线缺失、无法冻结 baseline | 交给 `baseline` 的覆盖目标与检索维度 |
| `baseline` | 探索包、task manifest、规则 hash | `baseline_freeze_packet.json`、冻结后的范围、门禁阈值、对象列表 | 范围未锁定、对象未稳定、后续 stage 依赖不明确 | 交给 `download` 的冻结范围与阈值 |
| `download` | baseline packet、对象分解计划、lane source plans、source catalog | `batch_manifest.json`、`_shared/source_catalog.json`、对象级 `1.download/{homepage,article,image}_source_plan.json`、`1.download/source_refs.json`、批次级 `sources/{sourceUnitId}/`、`source.quality.json`、`assets/index.json` | 下载失败、来源不带 license / relevance / sourceKind、图片未过安全门、来源质量低于阈值 | 交给 `build` 的可用来源单元、质量分析与图片安全结果 |
| `build` | download 产物、实体主题包、SOP / 模板 | 实体三件套 `page.md`、`_entity.json`、`manifest.json`、`assets/`，以及对象过程树 `1.download..5.review` | 页长不达标、条件画像缺失、资产闭环不完整、模板/平台痕迹存在 | 交给 `content_plan` 的可消费实体成品与来源证据 |
| `content_plan` | download/build 落盘来源、`source.quality.json`、实体主页摘要、`task.yaml` 内容配额 | `_shared/content_plan_packet.json`（篇目+`evidenceRefs`+`entityRefs`+`mustIncludeFacts`）、`content_object_index` 注册、各篇 `3.compose/brief.json` | 篇目无证据引用、B 组线路无联游互证、预置营销 ref、配额未满足 | 交给 `produce` 的已锁定篇目与 brief |
| `produce` | content_plan packet、实体成品、写作契约 | `3.compose/writing_pack.json`、`4.draft/prompt.md`、`4.draft/draft.article.md`、`4.draft/draft_meta.json`、`5.review/review.json`、`5.review/review_gate.json`、对象根 `article.md` / `manifest.json` / `assets/` | 写作包未闭合、草稿不是 `generator=agent`、事实不可回溯、图片未过安全门、正文出现机械标题或模板拼接、`citedSourcePaths` 超出 content_plan 证据 | 交给 `publish` 的 approved 成品、review ledger、provenance |
| `publish` | approved 的对象根、review ledger、entity pages | `publish/posts/...`、`publish/entities/...`、`release/{releaseId}/`、`publish/sample_bundles/{env}.json`、`publish/publish_meta.json` | 对象未 approved、资产闭环缺失、实体主页不存在、review 仍显示 unsafe | 交给 `ship` / importer 的发布包与环境采样包 |
| `workflow` | task manifest、baseline packet、batch manifest、运行状态 | `_shared/task_workflow_state.json`、修复包、重试链、阶段状态 | 未完成必经阶段、达到重试上限、存在未处理的硬阻断 | 只把已过门阶段推进到下游，不绕过 repair |

### 1.2 Ralph Loop 与 Cursor 编排

把业界 Ralph Loop 落成四个固定动作，不允许“看着像自动化”但没有闭环：

- `define`：主 Agent 先定义任务、完成标准、质量阈值和失败上限。
- `execute`：Workflow Orchestrator 只负责分片、并发、调度和结果合并。
- `attempt-exit`：每个阶段完成后尝试进入下游，生成下一阶段输入包。
- `hook-check`：在退出点统一做质量门检查，不满足就阻断。
- `re-inject`：失败必须回灌到原始阶段，生成 repair packet 后重试失败对象，不允许跳步。
- **hook-check 硬规则**：阶段 CLI 返回 done 不等于准出；必须读取 `write_gate_report` / `gate_*.py` 结果，有 issues 则**不得** `--resume` 进入下游。禁止 Agent 口头宣称完成而无 gate 证据。

### 1.2.1 篇目与 ref（证据后置，禁止搜索向预置）

- **task.yaml 只冻结**：`coverageTargets`（实体）与 `content.quotas`。规模化任务使用
  `entityArticlesPerTarget` / `galleryPostsPerTarget` / `entityHomepagesPerTarget`，
  同时校验总量和逐实体分布；**禁止** `plannedRefs` 作为第二真相源。
- **篇目真相源**：`batches/{batch}/_shared/content_plan_packet.json` + `content_object_index.json`。
- **时机**：`content_plan` 在 `build_validate` 之后、`produce_compose` 之前；ref/title 由已下载 `evidenceRefs` 归纳，禁止 download 前预置 `XX攻略` / 营销线路名再凑来源。
- **Source-ready admission**：百级及以上在冻结批次前必须证明候选池产能，而不是等 `build_prepare` 才淘汰。每个候选目标至少要有 homepage/article/image 三路可用 sourceUnit；目标容量不足时先激活已验证 reserve，reserve 用尽后才 `abandon` 并记录 `capacity_ceiling_delta`。
- **B 组线路**：仅当 ≥2 条独立来源出现联游/顺路叙述，或地理邻接且有共享交通/季节证据时立项；不足则 `repair` 回 `download_plan` 补检索，禁止模板大环线填空。

### 来源权利模式

- **SourceUnit 原子性**：一个 URL 快照生成一个 `sourceUnitId`；`source.md`、`source.clean.md`、`assets/index.json` 与物理资产共同构成同一 sourceUnit。文章、图片、视频作品判断必须来自同一个 sourceUnit 内的正文、图片、权利、图文一致和实体匹配证据；不得 A 网页拿文字、B 网页拿图片、C 网页拿评价后合成一个内容对象。实体主页可保留多个候选（百科/官方等），但每个候选都必须独立 sourceUnit 化并分别过门。
- **跨网页拼装硬阻断**：`content_plan` 中 `baseSourceRef`、`assetRefs`、`sourceUnitRefs` 不在同一 sourceUnit 时直接产生 issue，并写 `conflict_ledger.jsonl` 等待批后复核，不进入下游创作。
- **Entity focus gate**：sourceUnit 还必须证明目标实体是主体。`entityFocusVerdict=weak/supporting_only/mismatch/off_entity` 或 `entityFocusScore < 0.50` 的网页只能作为 supporting evidence，不能作为 article `baseSourceRef` 或 image work 主证据。
- `licensed_adaptation`：自有、明确授权、CC 或公版；必须保存 license、terms、credit 与授权快照。**遵从原创、适度润色而非重写，优质原文可大面积保留**。
- `factual_reference_only`：普通网页/百科/攻略经下载与 source gate 准入后，可作为一篇一用的 `baseSourceRef` 底稿；生产阶段仍以最高质量底稿为骨架做适度润色、事实校正、PII/平台痕迹清理和人设轻量适配，禁止脱离底稿总结式重写或编造亲历。
- `blocked`：权利不明、禁止商用、抓取失败或探针页，不得进入 content_plan。
- **版权合规靠来源准入，不靠生产环节强制重写**：进入 `baseDraftText` 的来源统一执行「底稿轻改」范式；不得用「独立重写」把证据链改散，也不得用「重写洗稿」掩盖未准入来源。
- `baseDraftFidelity`（机械文字留存率门）对所有 article/route 底稿生效（下限 55% 防从零另写；上限放宽到 99.5%，仅兜底「零加工整篇照搬」，要求至少完成 PII 脱敏、去语病/错字和人设用词语气适配，**优质原文可大面积保留，无须为去版权而重写**）；`sourceUseMode` 只保留供授权快照/署名留痕，不再决定是否启用本门。
- `_long_phrase_hits`（反抄袭逐句搬运门，≥28 字）不再作为 article/route 主硬门；来源痕迹、PII、事实回溯、跨稿重复和 `baseDraftFidelity` 共同兜底。
- **个人身份信息脱敏（所有来源）**：手机号/微信/QQ/身份证/车牌/私人住址等一律替代处理或隐去（`contactInfo` 门拦成品 PII），不得原样保留，也不得因含 PII 就删整段有效内容。
- **原创忠实（所有来源）**：无论权利模式，成品都必须以**最高质量底稿**为骨架、从多事实源补关键事实并适度润色去语病，**不得直接总结/综述、不得脱离来源大修或编造情节与数据**；由机械 `baseDraftFidelity` + rubric 软轨 `originalityFidelity` 维度 + 事实回溯（旅游/知识类 ≥95%）+ 跨稿重复门共同保障。
- **可读性**：对齐主要来源体裁（加工而非重写腔调）；禁止百科罗列、机械收尾、独立「实用信息」清单块。
- **发布 tagRefs**：`brief.json` / manifest 的 `tagRefs` 必须指向 `publish/tags/**/_definition.json` 已存在路径；禁止扁平的省名/品类名（如 `<region>`/`<category>`）等未发布 tag（`ship` dangling_post_tag_ref）。
- **线路 title**：`publishTitle` / frontmatter `title` 不得嵌入乱序实体名片段，否则 `verify_content_semantics` 的 routeCoverage progression 会在全文（含 frontmatter）判失败。

Cursor 只允许三类执行面：

- `Subagent`：单对象、单阶段、单门；负责局部探索、来源审核、图片审核、草稿创作、审校。
- `Automation`：负责重复性动作，例如批量触发、收集输出、把 gate 结果转成下一步输入。
- `主 Agent`：只负责目标、门槛、收口和最终确认，不直接拼业务正文，不直接做目录推导。

### 1.3 日产 10 万级产能模型

目标不是“跑得快”，而是“对象级可扩展且每一步可重试”：

- 分片键必须是对象稳定键，至少包含 `taskId + objectType + ref`。
- 每个 worker 一次只处理一个对象的一个阶段，不允许一个 Agent 同时跨多个对象写正文。
- 每个阶段必须幂等，允许重跑，但不允许重复造新内容。
- 队列按阶段分层，`download / build / produce / publish` 之间使用显式 handoff packet，不共享隐式上下文。
- 主 Agent 是编排与裁决面，不能成为串行瓶颈；当并发升高时，只扩 Orchestrator 和 Subagent 池，不扩主 Agent 职责。
- 重试预算必须显式定义：对象失败只回灌对象本身，批次失败只回灌共享前置，不允许全局锁回滚整批。
- 人工介入阈值必须显式定义：图片 unsafe、草稿风格不合规、事实证据缺口等问题分别进入 repair、abandon、conflict ledger 或批后人工复核，不可混为“待观察”；运行中不发起人工确认。

### 1.3.1 网站维度内容供给线（site-supply）

网站线是实体线的上游补给模式，不是第二套内容工厂：

- 工作区固定为 `local/data-runtime/site_supply/{vertical}/{siteId}/{batch}`，不得写入实体线 `local/data-runtime/tasks/**` 的候选池、队列状态或临时文件。
- 唯一站点真相源仍是垂类 `source_registry.yaml` 的 `siteCrawlProfile`；`fetchable=false` 或 `crawlAllowed=false` 的站点不得进入批量抓取。
- `controlledTrial.allowed=true` 只允许站点作为受控验证源进入 `site-supply trial --admission-mode controlled_trial`，用于验证 DAG、并发、lane mix、stage evidence、repair/gate 和 readiness；它不代表真实批量抓取授权，不允许 raw fetch，也不得把平台素材标记为可发布资产。
- 前半段只产出 `site_frontier_packet`、`site_candidate_packet`、`site_score_packet`、`site_map_packet` 与 `site_rollup_report`；发布主线只接受 `content_plan_packet` 之后的标准对象。
- 队列分片键为 `vertical|siteId|dateBucket|lane|candidateRef|stage`，`mutexKey` 默认取 `canonicalUrl` 或 `sourceCollectionId`，防止同源重复派生。
- 百级/千级结构试跑使用 `site-supply trial` 生成受控候选并执行 `frontier→candidate→score→map→rollup`，再以 `verify site-scale-readiness --mode trial` 验结构、吞吐、TokenLedger 和 `contentPlanHandoffLaneCounts`。
- 携程/马蜂窝首批 controlled trial 判断门为每站至少 `500 article / 100 image / 50 video`，万级放量按同一 lane mix 放大并以 `--min-article-count / --min-image-count / --min-video-count` 验证全批 handoff 数。
- 万级及以上商业准出必须跑 `python3 quwoquan_data/scripts/cli.py verify site-scale-readiness --mode commercial --vertical <vertical> --batch <batch> --daily-target <N>`，同时证明站点漏斗、吞吐、TokenLedger、release/import、搜索可见和推荐反馈证据。
- trial 模式不得冒充发布准出；缺少 release/import/search/recommendation 只允许作为 warning 留痕，commercial 模式必须硬阻断。

标准站点线阶段：

| 阶段 | 输出 | 准出 |
|---|---|---|
| `site_frontier` | `site_frontier_packet.json` | registry/profile/robots/terms/两年窗口/queue 门 |
| `site_extract` | `site_candidate_packet.json` | URL 归属、正文/资产可读、发布时间、sourceRef 门 |
| `site_score` | `site_score_packet.json` | 质量、权利、去重、低质阻断 |
| `site_map` | `site_map_packet.json` | 只输出 mention_only，handoff 到 content_plan |
| `site_rollup` | `site_rollup_report.json` | 站点漏斗、稳定性、吞吐、E2E 证据 |

### 1.4 统一 packet 与 repair packet

`qwq-data data` 的每一步都必须产出结构化 packet，至少包含：

```json
{
  "schemaVersion": "quwoquan_data.command_packet",
  "taskId": "<vertical>/<dimension>/<region>/<category>/<topic>",
  "batchId": "<batch_id>",
  "command": "download",
  "stage": "source_plan",
  "objectType": "entity|article|image|video",
  "ref": "<object_ref>",
  "inputs": [],
  "outputs": [],
  "gates": [],
  "repair": {
    "required": true,
    "reason": "..."
  },
  "next": {
    "command": "build",
    "stage": "prepare"
  }
}
```

规则：

- `inputs` 必须可回放，不能只写“见上一阶段”。
- `outputs` 必须写到具体目录和文件名，不能只写“已完成”。
- `gates` 必须列出命中的门名和结果，不能只写布尔值。
- `repair` 必须告诉下游为什么失败、要补什么、回到哪一阶段。
- `next` 只允许指向一个明确的下一步，不能同时给多个候选。

## 2. Agent 高质量生产（图文 + 关联实体）

标准三段式：`[CLI compose-brief] → [Agent 创作正文写回草稿] → [CLI review/materialize+gate]`。

- 正文只由会话模型创作（`generator=agent`），脚本不拼正文。
- 草稿可声明 `extractedEntities`（如「洛绒牛场」）；review 据此生成实体 sidecar，无主页者**自动生成关联实体主页** `page.md`，使其可关联查看；发布时仍无主页的 entityRef 被过滤。
- 质量门：三道真实性门（出处/模板指纹/事实可回溯）+ 游记感密度 + 载体一致性 + **图文混合编排门**（figure 跨小节穿插、禁空图块、禁大段无图空档；图多转 gallery 配小字）+ 图片精美门（人脸/水印/近重复/文字占比）。
- **作品准入门（works classifier）**：`compose-brief` 阶段在释放创作之前先判定对象是「作品 / 随记 / 弃稿」。仅 `decision=work`（实体主页 / 文章 / 图片作品）放行进入 Agent 创作，随记（碎片流即时表达）与弃稿（低专业度来源且内容不自证）被阻断、落 `3.compose/works_verdict.json` 审计，**不消耗 Cursor SDK token**。判定真相源：`templates/_registry/catalogs/works_classification.yaml`（阈值/权重/自证等级）+ `content_source_registry.yaml`（来源专业度 `sourceClass→sourceTier`）；实现 `_common/works_classifier.py`，接入 `produce/works_gate.py`，契约门 `qwq-data verify works-classification`。本平台**不生产任何随记**（文字/图片/视频随记）；视频作品当前阶段后置。详见 [`content_supply_commercialization_plan.md`](content_supply_commercialization_plan.md)。

### 2.1 AI 自主创作边界与 Creative Workspace

`ObjectEvidencePacket` 锁事实、权利、素材和载体；`CreativeBrief` 释放创作空间。AI 的自主性只发生在 evidence packet 内，不得越过来源、授权和载体边界。

AI 可以自主决定：

- 标题候选、开头方式、段落结构、叙事节奏和收束方式。
- 读者视角与内容角度，例如规划咨询、体验决策、避坑、摄影审美、知识科普。
- 在证据边界内的信息取舍与前后顺序。
- 表达风格与作者语气，但必须遵守作者披露和可信边界。
- 针对 review 失败点的修订策略。

AI 不可以自主决定：

- 使用未准入来源或无授权素材。
- 混用不同 `sourceCollectionId`、作者、平台或授权凭证的图片。
- 改变内容载体，例如把图片作品写成文章，或把文章降成图库。
- 编造具体事实、亲历、资质、官方背书或商业合作。
- 把待确认 mention 写入 active `entityRefs/tagRefs`。
- 绕过 gate 或用口头完成替代文件与裁决。

创作阶段必须按以下角色链路执行：

1. `Creative Planner Agent`：基于 evidence packet 提出 2-3 个创作方案、`readerPromise`、结构和标题候选。
2. `Creator Agent`：选择通过 creative plan gate 的方案写正文、标题、配文或主页介绍。
3. `Self Critic Agent`：做低成本自检，写 `author_self_check.json`，但没有最终通过权。
4. `Independent Review Agent`：独立审核事实、权利、图文一致、人格边界和消费价值。
5. `Optimizer Agent`：只按 review 指定失败点修订，不重新选源、不扩大事实边界。

### post 最小发布契约（manifest.json）

只保留发布/渲染/出处必需字段：`topicId/contentType/entityRefs/tagRefs/sourceUrls/assets/template/carrier/generator/generatorModel/citedSourceRefs/reviewDecision/articleMarkdown*/articleRenderProfile/publish*/storySpine/sourceTaskId/sourceBatchId`。
中间态（`sourceQuality/relatedSearchPlan/evidenceBundle/sourcePaths`）不进发布契约；最终追责快照只保留在 `5.review/provenance.json`，对象根不再保留根级副本。

### 阶段产物最小契约

批次树是仓外工程过程目录（`QWQ_OUTPUT_ROOT/local/data-runtime/{phase}/{contentType}/{supplyMode}/…`，
见 [`pipeline_directory_layout_spec.md`](pipeline_directory_layout_spec.md) §0.5），默认可重建；
进入模型上下文或高频报告的文件必须瘦身：

- `task_download/inputs/source_plan/*.json`：人工或工具给定 source 列表，保留；这是离线复跑入口。
- `task_download/sources/**`：原文、图片与 `source.quality.json`，保留；review 事实回溯和图片门会读取。
- `posts/{type}/{angle}/{title}/{seq}/3.compose/writing_pack.json`：只保留 `ref/kind/title/byline/carrier/templateId/wordCount/forbiddenPhrases/mustIncludeFacts/sectionIntents/narrativeContract/styleFamily/evidencePoints/assets`；opening guidance、source 明细从真相源即时读取，不落包。
- `posts/{type}/{angle}/{title}/{seq}/4.draft/prompt.md`、`article.md`、`draft_meta.json`：保留；分别是模型输入、人写正文和生成出处。
- `posts/{type}/{angle}/{title}/{seq}/5.review/{ledger.json,review.json,review_gate.json,repair_report.json,provenance.json}`：保留最小 envelope；`review` 落盘只存 decision/issues/check pass 状态，完整诊断留在 `review_gate/repair_report`。
- `posts/{type}/{angle}/{title}/{seq}/`：保留；这是 materialize 成品包，必须包含 `article.md/manifest.json/assets/` 与可选 `5.review/` sidecar。`gallery.md` 仅在 gallery carrier 时作为展示层出现，article 载体不得写入。
- `publish/{posts,entities,tags,index,sample_bundles,env_releases}`：保留；这是发布主线和环境同步输入。

可清理原则：`assistant_tasks/`、`workflow_packets/`、`object_queue/`、过期 `results/*_gate`、失败批次草稿、可从 source/brief 重建的中间分析明细均不进入 post 包；需要审计时从 task/batch 源目录重算。`batch/_shared` 按 `paths.BATCH_SHARED_AUTHORITATIVE_ENTRIES`（不可重算真相源）与 `BATCH_SHARED_RECLAIMABLE_ENTRIES`（可清理层）两分，未登记条目由目录证据链门 BLOCK；仓外 `.qwq_output/runs/**` 只做 index-first 摘要索引，必须回指 `runtimeBatchRoot/taskId/publishRoot/releaseId` 与批次三轴。

## 3. Human-in-loop 标注账本（唯一发布态真相源）

`_common/review_ledger.py`。每个 `ReviewItem`（image/fact/article）含：
`agentJudgment(credible|doubtful)`、`agentScore(1-5)`、`humanJudgment(unjudged|credible|doubtful)`、`humanScore`、`humanOverride(publishable|discard)`、`reprocessCount`。

派生 `publishState ∈ {fix, discard, publishable}`（`resolve_publish_state` 统一推导，不持久化为事实）：

1. 人裁定优先：`humanOverride` 直接置态；`humanJudgment=credible` 或 `humanScore>=3` → publishable；`doubtful` → fix。
2. 人未裁定看 agent：`agentJudgment=doubtful` 必须人确认（`requireHumanWhenDoubtful`）→ fix；`credible` 且 `agentScore>=3` → publishable，否则 fix。
3. 低质量可再加工，`reprocessCount` 累计；超 `maxAttempts(3)` 锁定，除非人裁定 publishable。

review 写 `5.review/ledger/{ref}.json` 与 `entities/{ref}.json`；materialize 随 post 拷入 `posts/.../5.review/`。

`qwq-data annotate`：`--list` 队列；`--ref/--kind/--target` + `--judgment/--score/--override/--reprocess/--note` 下人判定。

## 4. 发布门（promote / ship）

`_common/publish_filter.py` 据账本与实体主页存在性裁决每个 post：
- 文章须 publishable，否则跳过该 post 并报告（不静默 BLOCK 全量）。
- `discard` 图从 `manifest.assets` / 正文 `:::figure` 引用一并剔除并删文件。
- `entityRefs` 中无主页（`entities/{d}/{t}/{name}/page.md` 不存在且 sidecar 未标 hasHomepage）者被过滤。

## 5. 一键发布 + 按环境采样 + 服务侧灌库

`qwq-data ship`：promote（task/release→publish）→ 重建 lookup 索引 → 按环境采样写 sample bundle → 更新 `publish_meta.lastShip` →（可选 `--import`）调用服务侧 importer 灌库。

环境发布必须同时生成 `publish/env_releases/{releaseId}/{env}.json` 与 `consistency-preflight-{env}.json`。上线级 apply、事务边界、回滚和四层验证见 [`environment_data_release_runbook.md`](environment_data_release_runbook.md)。

### 按环境采样（确定性）

`quwoquan_ops/environments/content_sampling_manifest.yaml` 是唯一采样真相源：prod=全量；gamma/beta/alpha 配 `sampleRatio + postCapPerBucket + entityCapPerBucket + maxPosts/maxEntities`。
采样 `rank = sha1(salt|ref) → [0,1)`，`< sampleRatio` 入选，再按 bucket cap / max 截断；同 env/salt 下稳定可重跑。
产出端云桥契约 `publish/sample_bundles/{env}.json`（`{environment, sampleRatio, posts:[postRef], entities:[entityRef], counts}`）。

### 服务侧 importer（真实灌入运行库）

`quwoquan_service/services/content-service/cmd/import`：
- 只读消费 `publish/posts` + `publish/entities`，按 sample bundle 过滤某环境子集；
- 幂等 upsert：posts→`{posts-db}.posts`（`postRef` 唯一索引），entities→`{entities-db}.entities`（`entityRef` 唯一索引）；`createdAt` 仅插入写、`updatedAt` 每次刷新；
- 加载层 `loader.go` 纯函数、可单测（`loader_test.go`，无需 mongo）；
- 写入层 `UpsertPosts/UpsertEntities/EnsureUnique` 由 `mongo_import_test.go` 对真实 mongo 覆盖（插入/字段/幂等重跑/唯一索引/load→upsert 子集）。

```bash
go run ./services/content-service/cmd/import \
  --publish-root ../quwoquan_data/publish \
  --sample-bundle ../quwoquan_data/publish/sample_bundles/gamma.json \
  --mongo-uri mongodb://localhost:27017 --env gamma

# 真实 mongo 写入路径测试（起一次性 mongod，跑完即销毁）
bash quwoquan_service/scripts/content/run_content_import_mongo_test.sh
```

## 6. 测试与门禁（红绿）

| 关注点 | 测试/门禁 |
|---|---|
| asset_id 可读+唯一 | `tests/common/test_asset_id_stability.py` |
| 账本状态机 | `tests/integration/test_review_ledger_state_machine.py` |
| manifest 最小化 + 账本/实体 sidecar + 关联实体主页 | `tests/integration/test_hitl_pipeline.py` |
| annotate CLI + 发布门 | `tests/annotate/test_annotate_publish_filter.py` |
| 确定性采样 + ship e2e | `tests/ship/test_ship_sampling.py` |
| 环境 release contract + 引用闭包 + 生产硬删除审批门 | `tests/ship/test_data_release_consistency.py` |
| 图文混合编排门 | `tests/produce/test_mixed_layout_gate.py` |
| 端到端 pilot 全绿 | `tests/integration/test_verify_pilot_gwt.py` |
| 服务侧 importer 加载 | `quwoquan_service/services/content-service/cmd/import/loader_test.go` |
| 服务侧 importer mongo 写入路径 | `quwoquan_service/services/content-service/cmd/import/mongo_import_test.go`（`run_content_import_mongo_test.sh` 起临时 mongod） |
| 去版本化/去区域硬编码 | `scripts/verify/verify_no_legacy_hardcode.py` |
| CLI-first | `scripts/verify/verify_cli_first.py` |

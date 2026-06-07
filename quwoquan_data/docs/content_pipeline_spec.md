# workflow 内容生产规格（Agent 生产 · Human-in-loop · 一键发布到运行库）

本规格描述从「人定义任务」到「内容灌入各环境运行库」的端到端主线。所有命令统一经 `qwq-data` CLI 暴露。
`workflow run` 是任务级编排入口；`task_download` 是任务级检索规划工作区；对象级 `1.download..5.review` 是唯一成品前过程树。

## 0. 单一主线与去版本化

- `publish/` 是**唯一发布主线**，目录为 `publish/{posts,entities,tags,index,sample_bundles}/`，无 `v{N}` 版本目录。
- `publish/publish_meta.json` 记录 `lastPromote` / `lastShip` / `lastReleaseId`，无 `activeVersion`。
- 门禁 `verify_no_legacy_hardcode.py` 禁止 `publish/v{N}`、objectKey `/v{N}/` 段、`chuanxi`/`*_v5` 等区域/任务硬编码回归。

## 1. 入口：人定义生成任务

`qwq-data plan` 把内容指令解析为 `compose_brief`（叙事契约 / imagePlan / imagePolicy / mustIncludeFacts）。
垂类（travel/campus…）数据驱动，无 region/task 专属分支。

### 1.1 `qwq-data data` 命令族总表

| 命令 | 输入 | 输出 | stop-if | handoff |
|---|---|---|---|---|
| `explore` | 任务说明、目标范围、notes、已有目录快照 | 探索包、候选对象清单、候选 sourceKind 白名单、初步检索维度 | 目标对象不完整、主线缺失、无法冻结 baseline | 交给 `baseline` 的覆盖目标与检索维度 |
| `baseline` | 探索包、task manifest、规则 hash | `baseline_freeze_packet.json`、冻结后的范围、门禁阈值、对象列表 | 范围未锁定、对象未稳定、后续 stage 依赖不明确 | 交给 `download` 的冻结范围与阈值 |
| `download` | baseline packet、对象分解计划、source plan、source catalog | `batch_manifest.json`、`_shared/source_catalog.json`、对象级 `1.download/source_plan.json`、`1.download/sources/{NN}.{sourceKind}/`、`source.quality.json`、`assets/index.json` | 下载失败、来源不带 license / relevance / sourceKind、图片未过安全门、来源质量低于阈值 | 交给 `build` 的可用来源单元、质量分析与图片安全结果 |
| `build` | download 产物、实体主题包、SOP / 模板 | 实体三件套 `page.md`、`_entity.json`、`manifest.json`、`assets/`，以及对象过程树 `1.download..5.review` | 页长不达标、条件画像缺失、资产闭环不完整、模板/平台痕迹存在 | 交给 `produce` 的可消费实体成品和事实摘要 |
| `produce` | baseline packet、实体成品、来源包、检索计划、写作契约 | `3.compose/writing_pack.json`、`4.draft/prompt.md`、`4.draft/draft.article.md`、`4.draft/draft_meta.json`、`5.review/review.json`、`5.review/review_gate.json`、对象根 `article.md` / `manifest.json` / `assets/`、`content_object_index.json` | 写作包未闭合、草稿不是 `generator=agent`、事实不可回溯、图片未过安全门、正文出现机械标题或模板拼接 | 交给 `publish` 的 approved 成品、review ledger、provenance |
| `publish` | approved 的对象根、review ledger、entity pages | `publish/posts/...`、`publish/entities/...`、`release/{releaseId}/`、`publish/sample_bundles/{env}.json`、`publish/publish_meta.json` | 对象未 approved、资产闭环缺失、实体主页不存在、review 仍显示 unsafe | 交给 `ship` / importer 的发布包与环境采样包 |
| `workflow` | task manifest、baseline packet、batch manifest、运行状态 | `_shared/task_workflow_state.json`、修复包、重试链、阶段状态 | 未完成必经阶段、达到重试上限、存在未处理的硬阻断 | 只把已过门阶段推进到下游，不绕过 repair |

### 1.2 Ralph Loop 与 Cursor 编排

把业界 Ralph Loop 落成四个固定动作，不允许“看着像自动化”但没有闭环：

- `define`：主 Agent 先定义任务、完成标准、质量阈值和失败上限。
- `execute`：Workflow Orchestrator 只负责分片、并发、调度和结果合并。
- `attempt-exit`：每个阶段完成后尝试进入下游，生成下一阶段输入包。
- `hook-check`：在退出点统一做质量门检查，不满足就阻断。
- `re-inject`：失败必须回灌到原始阶段，生成 repair packet 后重试失败对象，不允许跳步。

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
- 人工介入阈值必须显式定义：图片 unsafe、草稿风格不合规、事实证据缺口等问题分别进入 repair 或人工复核，不可混为“待观察”。

### 1.4 统一 packet 与 repair packet

`qwq-data data` 的每一步都必须产出结构化 packet，至少包含：

```json
{
  "schemaVersion": "quwoquan_data.command_packet/1",
  "taskId": "旅行/地域/四川省/景区/景区精选",
  "batchId": "e2e_sichuan_20260607",
  "command": "download",
  "stage": "source_plan",
  "objectType": "entity|article|image|video",
  "ref": "地点_景区__峨眉山",
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

### post 最小发布契约（manifest.json）

只保留发布/渲染/出处必需字段：`topicId/contentType/entityRefs/tagRefs/conditionContext/sourceUrls/assets/template/carrier/generator/generatorModel/citedSourceRefs/reviewDecision/articleMarkdown*/articleRenderProfile/publish*/storySpine/sourceTaskId/sourceBatchId`。
中间态（`sourceQuality/relatedSearchPlan/evidenceBundle/sourcePaths`）不进发布契约；最终追责快照只保留在 `5.review/provenance.json`，对象根不再保留根级副本。

### 阶段产物最小契约

`runtime/tasks/{task}/batches/{batch}/...` 是工程过程目录，默认可重建；进入模型上下文或高频报告的文件必须瘦身：

- `task_download/inputs/source_plan/*.json`：人工或工具给定 source 列表，保留；这是离线复跑入口。
- `task_download/sources/**`：原文、图片与 `source.quality.json`，保留；review 事实回溯和图片门会读取。
- `posts/{type}/{angle}/{title}/{seq}/3.compose/writing_pack.json`：只保留 `ref/kind/title/byline/carrier/templateId/wordCount/forbiddenPhrases/mustIncludeFacts/conditionContext/sectionIntents/narrativeContract/styleFamily/evidencePoints/assets/sopExampleRef`；SOP 全文、opening guidance、source 明细从真相源即时读取，不落包。
- `posts/{type}/{angle}/{title}/{seq}/4.draft/prompt.md`、`article.md`、`draft_meta.json`：保留；分别是模型输入、人写正文和生成出处。
- `posts/{type}/{angle}/{title}/{seq}/5.review/{ledger.json,review.json,review_gate.json,repair_report.json,provenance.json}`：保留最小 envelope；`review` 落盘只存 decision/issues/check pass 状态，完整诊断留在 `review_gate/repair_report`。
- `posts/{type}/{angle}/{title}/{seq}/`：保留；这是 materialize 成品包，必须包含 `article.md/manifest.json/assets/` 与可选 `5.review/` sidecar。`gallery.md` 仅在 gallery carrier 时作为展示层出现，article 载体不得写入。
- `publish/{posts,entities,tags,index,sample_bundles,env_releases}`：保留；这是发布主线和环境同步输入。

可清理原则：`assistant_tasks/`、过期 `results/*_gate`、失败批次草稿、可从 source/brief 重建的中间分析明细均不进入 post 包；需要审计时从 task/batch 源目录重算。

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

`deploy/shared/content_sampling_manifest.yaml` 是唯一采样真相源：prod=全量；gamma/beta/alpha 配 `sampleRatio + postCapPerBucket + entityCapPerBucket + maxPosts/maxEntities`。
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

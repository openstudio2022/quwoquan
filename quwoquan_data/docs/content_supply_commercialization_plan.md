# 内容供给商用化蓝图（日产十万级 · 三层 Agent 协同）

本文是「自动化、商用品质、日产十万级内容供给」的总蓝图，回答三个决定形态的关键问题，给出整体架构、职责分工、契约、任务清单、验收标准与路线图。它是规划层真相源，落地细节链接到既有规格，不重复抄写：

- 组织模型与治理边界：[`agent_content_supply_operating_model.md`](agent_content_supply_operating_model.md)
- 端到端生产主线与目录契约：[`content_pipeline_spec.md`](content_pipeline_spec.md)
- 子 Agent 调度与并发：[`subagent_scheduler_spec.md`](subagent_scheduler_spec.md)、[`fanout_scaffold_spec.md`](fanout_scaffold_spec.md)
- 批次稳定性与规模演练：[`batch_stability_e2e_spec.md`](batch_stability_e2e_spec.md)
- 运行 SLO：[`content_ops_slo.md`](content_ops_slo.md)
- 环境数据发布：[`environment_data_release_runbook.md`](environment_data_release_runbook.md)

> 范围声明：本平台**只生产作品**——实体主页、图片作品、文章作品。**不生产任何随记**（文字随记 / 图片随记 / 视频随记）。**视频作品当前阶段后置**，蓝图为其预留 lane 但不进入本期产能。

---

## 0. 目标与成功标准

| 维度 | 目标 |
| --- | --- |
| 产能 | 稳定日产 10 万级内容（实体主页 + 图片作品 + 文章作品**相加**计数） |
| 品质 | 商用可发布：事实可回溯、权利合规、图文一致、非模板感、消费价值达标 |
| 自动化 | 顶层治理 Agent → 执行 Agent → 子任务 Agent 三层协同，人只做抽检与高风险复核 |
| 成本 | 主 token 成本在执行 Agent（当前 Cursor SDK）；准出前置闸口拦截不合格对象，避免无效创作消耗 |
| 可达性 | 规模能力先由队列 / 限流 / 幂等 / 去重 / 成本护栏 / 故障隔离证明，再放大真实生成比例 |

成功的硬定义：百 / 千 / 万级三档端到端跑通且证据闭环（见 §9 验收标准），单对象失败可隔离复盘而不拖批，成本与产能线性可预测。

---

## 1. 三个关键决策（拍板结论）

### 决策一：内容分类——「作品 vs 随记」是准入门，不是事后标签

平台内容二分为**作品**（works）与**随记**（moment）。两者的根本差异不是长度，而是**消费价值密度与可被独立检索 / 推荐的资格**：

- **作品**：实体主页、图片作品、文章作品。有结构、有事实密度或审美价值，值得被收录、检索、推荐、长期沉淀。
- **随记**：碎片流即时表达（社交动态、微博式短贴、短视频流文案）。本平台**不生产**。

**结论**：作品判定是生产线的**准入门**，前置在 `compose-brief`（指令维度）和 `site score`（站点维度），在释放昂贵创作之前裁决。判定不靠人工拍脑袋，而是数据驱动的 `WorksClassifier`：

- 真相源配置：[`templates/_registry/catalogs/works_classification.yaml`](../templates/_registry/catalogs/works_classification.yaml)（阈值、权重、自证质量等级）。
- 来源专业度先验：[`content_source_registry.yaml`](../templates/_registry/catalogs/content_source_registry.yaml) 的 `sourceClass → sourceTier`，经 `_common/content_source_registry.py:resolve_source_class` 解析。
- 判定实现：`_common/works_classifier.py:classify_works`（纯函数，可单测）。
- 产线接入：`produce/works_gate.py:evaluate_object_works`（落 `works_verdict.json` 审计 + 非 work 阻断）、`site_supply/handler.py:build_site_score_packet`（站点全站分类入库，真实候选 moment/abandoned 不进 content_plan）。
- 契约门：`qwq-data verify works-classification`。

**载体判定**：`decision=work` 后再决定载体（article / image gallery / homepage / knowledgeCard），由 `_resolve_work_carrier` 依据叙事体量与图片数量裁决，AI 不得擅自改载体。

**内容自证通道**：高质量（`A-story` / `B-fact`）且有结构的文章，即使来源专业度先验偏低或来源元数据缺失，也直接判作品，不被低来源先验拖累（对齐 article lane「只看内容质量、不按来源类别天然升降级」）。配置项 `contentSignals.selfProveQualityTiers`。

### 决策二：两种工作流并存——站点维度抓取 + 指令维度全网检索

两条工作流共用同一套对象级过程树、质量门和证据链，只是**供给入口**不同：

| 维度 | 站点维度（site supply） | 指令维度（instruction supply） |
| --- | --- | --- |
| 触发 | 给定站点（携程攻略 / Pinterest …），按站点全量抓取候选 | 给定垂类 / 主题指令（旅行垂类 …），全网检索展开实体与篇目 |
| 入口 | `qwq-data site-supply`（candidate → score → handoff → content_plan） | `qwq-data plan`（explore → baseline → download → content_plan） |
| 分类时机 | `build_site_score_packet` 全站分类入库：真实候选经 WorksClassifier 准入，moment/abandoned 不进 content_plan | `compose-brief` 闸口：`evaluate_object_works` 判定，非 work 阻断 |
| 强项 | 单站结构稳定、版权口径集中、可批量物化多 lane | 跨站事实互证、实体覆盖广、可按垂类配额规划 |
| 共用下游 | `produce`（compose-brief → Agent 创作 → review → materialize）→ `publish` → importer | 同左 |

两条线最终都汇入 `content_plan_packet.json` + `content_object_index.json`，进入统一的 `produce/publish` 主线。

### 决策三：标签与实体管理——抽取、规范化、治理、回填、端侧可点击全链路

标签与实体不是发布时补的元数据，而是贯穿生产的一等公民：

1. **抽取（NER）**：草稿 / 候选正文产出 `extractedEntities`、`extractedTagCandidates`。
2. **规范化**：候选对齐到已发布标签树 `publish/tags/**/_definition.json`（去版本化单一主线，无 `v{N}`）与实体库。
3. **治理**：未对齐候选进入 `pending_review`，不得直接成为 active `entityRefs/tagRefs`；只有已发布 mention 才能派生引用。
4. **回填（semanticMentions）**：materialize 阶段基于正文 + `extractedEntities/tagCandidates` 生成 `semanticMentions`（`offset` / `status` / `targetRef`），为端侧标签 / 实体可点击打基础。
5. **端侧内联格式统一**：正文内联引用统一格式（如 `@[label](entity:ID)`），端侧据 `semanticMentions` 渲染为可点击跳转。

> 注意区分两个「v1/tags」概念：数据工程**标签树发布路径** `publish/tags/**`（已去版本化）与 tag service 的 **HTTP API 路径** `/api/v1/tags`（API 版本，正常保留）。二者不是一回事。

---

## 2. 整体架构：三层 Agent 协同

```
┌─────────────────────────────────────────────────────────────┐
│ L0 治理 / 运营 / 监控 Agent（Supply Portfolio Controller）       │
│   定义垂类、目标量、载体比例、预算、放量节奏；只读 gate 证据、不写正文 │
└───────────────┬─────────────────────────────────────────────┘
                │ SupplyPlanPacket / 批次计划 / 放量报告
┌───────────────▼─────────────────────────────────────────────┐
│ L1 执行 Agent（Workflow Orchestrator，不固定为 Codex / Cursor SDK）│
│   分片、并发、调度、结果合并、attempt-exit / hook-check / re-inject │
└───────────────┬─────────────────────────────────────────────┘
                │ ObjectJob（队列执行单元）
┌───────────────▼─────────────────────────────────────────────┐
│ L2 子任务 Agent（叶子）：检索 / 权利 / 策划 / 创作 / 自检 / 审校 / 修订 │
│   在 evidence packet 证据边界内创作；输出经 AgentResultEnvelope 采纳  │
└─────────────────────────────────────────────────────────────┘
```

- **顶层与执行 Agent 不绑定具体实现**：当前验证用 Codex 作 L0/L1、Cursor SDK 作 L2 执行，但契约层不假设具体模型；可替换。
- **token 成本主战场在 L2（Cursor SDK）**：因此所有可在 CLI / 闸口前置裁决的判断（作品准入、来源充分性、权利、配额）都**前置到不耗模型 token 的阶段**，把 L2 创作只留给确定要产出的作品对象。
- **真相源是文件与 gate，不是 Agent 口头声明**：准出只认结构化 packet、文件 hash、`GateVerdict`、`TokenLedger`。

职责分工、禁止事项、各角色产物的完整清单见 [`agent_content_supply_operating_model.md`](agent_content_supply_operating_model.md) §2。

---

## 3. 端到端主线与阶段闸口

复用 `content_pipeline_spec.md` §1.1 的命令族主线，关键闸口标注作品准入位置：

```
指令维度: plan(explore→baseline) → download → content_plan → produce(compose-brief[作品门] → Agent 创作 → self-check → review → materialize[semanticMentions 回填]) → publish → ship/importer
站点维度: site-supply(candidate → score[作品门/全站分类入库] → handoff) → content_plan → produce(...) → publish → ship/importer
```

Ralph Loop 四动作（define / execute / attempt-exit / hook-check / re-inject）与 hook-check 硬规则（CLI done ≠ 准出，必须读 gate 报告）见 `content_pipeline_spec.md` §1.2。

---

## 4. 内容分类契约（WorksClassifier）

### 4.1 判定输入与输出

输入：`source_class`（来源专业度）、`source_text`（底稿正文）、`narrative_volume`、`image_count`、`declared_carrier`、`rights_blocked`。

输出 `works_verdict.json`：

| 字段 | 含义 |
| --- | --- |
| `decision` | `work` / `moment` / `abandoned` |
| `carrier` | work 时的载体：`article` / `image` / `homepage` / `knowledgeCard` |
| `abandonReason` | 非 work 时的原因（如 `casual_moment`、来源不可用） |
| `sourceTier` | 来源专业度档（`tier1..tier4_casual`） |
| `score` | 综合作品分 |
| `reasons` | 可审计判定依据 |

### 4.2 判定逻辑要点

- **图片作品**与**文本作品**走不同路径：图片作品看图片数量 / 质量 / 版权，不被文本质量分误杀。
- **随记归类为 `moment`** 而非 `abandoned`：碎片流来源（`social_feed` / `microblog` / `short_video_feed`）命中 ≥2 个碎片信号判随记；与「来源不可恢复」的弃稿区分。
- **内容自证**：A-story/B-fact + 有结构 → 直接 work，覆盖低来源先验与来源元数据缺失。
- **来源类别不天然拉黑长帖**：`community_post`（社区长经验帖）不在碎片亲和来源列表，其碎片性由内容信号（过短 / 无结构）判定。

### 4.3 接入点与证据

| 接入点 | 文件 | 行为 |
| --- | --- | --- |
| 指令维度 compose-brief | `produce/works_gate.py`、`produce/entity_workflow.py`、`produce/route_workflow.py` | 落 `works_verdict.json`；article/image/gallery 非 work 时阻断 Agent 创作 |
| 站点维度 score | `site_supply/handler.py` | 全站分类入库；真实候选非 work 加 blocker、不 productionEligible；`validationOnly` 候选只审计不阻断 |
| 契约门 | `verify/verify_works_classification.py`（经 `qwq-data verify works-classification`） | 校验 schema / version / 权重覆盖 + 代表样本判定 |

---

## 5. 标签与实体治理（详见决策三）

| 阶段 | 产物 | 门 |
| --- | --- | --- |
| 抽取 | `extractedEntities` / `extractedTagCandidates` | 必须可回溯到正文 offset |
| 规范化 | 对齐 `publish/tags/**/_definition.json`、实体库 | 未对齐 → `pending_review` |
| 回填 | `semanticMentions`（offset/status/targetRef） | 仅已发布 mention 派生 active 引用 |
| 发布 | `tagRefs` / `entityRefs` | dangling ref（无主页 / 未发布 tag）被过滤 |
| 端侧 | 内联 `@[label](entity:ID)` 渲染可点击 | 端云内联格式统一 |

标签树为去版本化单一主线 `publish/tags/**`；门禁 `verify_no_legacy_hardcode.py` 禁止 `publish/v{N}` 回归。

---

## 6. 规模化工程地基（日产十万的前提）

规模能力先由工程地基证明，再放大真实生成比例。地基项与对应规格：

| 地基能力 | 要求 | 真相源 / 状态 |
| --- | --- | --- |
| 队列后端抽象 | QueueBackend 接口隔离，内存 / 持久可换 | **已落地** `task/object_queue.py`（`QUEUE_BACKEND_LOCAL` / `QUEUE_BACKEND_RELIABLETASK`）；scale 门校验日产≥1万须 `reliabletask` |
| per-lane 限流背压 | homepage/article/image 分 lane 限流，过载背压 | **部分**：全局并发 + 失败指数退避 + jitter 防惊群已落地；homepage/article/image 细分限流待补（Phase 0.5 增强） |
| 幂等与崩溃恢复 | objectKey 幂等、stage result 可断点续跑 | **已落地**：稳定 `jobId=sha1(task\|batch\|ref\|stage)` 幂等、lease 租约 + 过期重取、墙钟硬上限、Ralph 断路器 |
| 故障域降级 | 单对象失败隔离为 `abandoned` / `manual_required`，不拖批 | **已落地**（对象级隔离 + 同源互斥 mutexKey） |
| 结构化 metrics | 队列 / token / 缓存命中 / 通过率分位数 | **部分**：stage timing（leasedAt/finishedAt/durationMs）+ run_journal 已落地；分位数大盘待补（Phase 0.5 增强） |
| 成本护栏 | `TokenLedger` 预算 vs 实际、unitPassedCost | **已落地**：队列 token/cost budget 硬上限 + 作品门前置省 token + scale 门强制 `TokenLedger` 证据 |

---

## 7. 质量门与结构化证据链

硬门（任一失败即阻断）：作品准入、出处真实性、模板指纹、事实可回溯、权利 / 安全、载体一致、图文混合编排、图片精美、人格 / 作者边界。

软门 / 批次门：游记感密度、跨稿重复、题材分布、底稿复用、资产复用、作者疲劳。

证据链 packet：`SupplyPlanPacket` → `ObjectJob` → `ObjectEvidencePacket` → `CreativeBrief` → `AgentResultEnvelope` → `GateVerdict` → `TokenLedger` → `FeedbackSignalPacket`。规则：上游可回放、下游只读声明输入、Agent 输出必须经 envelope 采纳。

---

## 8. 任务清单与状态

### 已落地（本期交付，含证据）

- [x] 删除 moment 生产类型；平台只产作品（contentType 范围收敛）。
- [x] 标签树口径全仓统一 `publish/tags`（数据 / 服务 / 规格 / 端侧；`verify_no_legacy_hardcode` 绿）。
- [x] `works_classification.yaml` 配置 + `works_classifier.py` 实现 + 8 项单测绿。
- [x] `content_source_registry.resolve_source_class` 来源专业度桥接 + `sourceTierSignals`。
- [x] 内容自证通道（A-story/B-fact + 结构 → work）。
- [x] `produce/works_gate.py` 接入 compose-brief（entity / route 落 verdict + 非 work 阻断，省 token）。
- [x] 站点维度 WorksClassifier 接入 `site score`（真实候选准入、`validationOnly` 跳过）+ 多 lane handoff。
- [x] 契约门 `qwq-data verify works-classification` 接入 `verify_quwoquan_data.sh`（CLI-first ratchet 绿）。
- [x] 站点维度 e2e（trial）：8 候选 → handoff（article 5 / image 3）passed，零失败；契约测试绿。
- [x] 指令维度 e2e：`test_entity_composer` 7 绿（compose-brief 含作品门 → Agent 草稿 → review → materialize → verify 闭环，作品不误杀）。
- [x] **Phase 2 数据侧 `semanticMentions` 全链路回填**：`build_entities_sidecar` 生成实体 + **标签** mention（`extractedTags`→tag mention，已发布 `published` 可点击 / 未发布 `pending_review` 待治理）；实体路径（`review_entity_draft`）与线路路径（`review_route_draft`）统一生成 sidecar；`materialize` 合并 sidecar mention 进 `manifest.semanticMentions`（按 mentionId 去重，全量含 pending，active 引用由 `published_only` 投影）。服务侧 importer 已就绪消费（entity+tag、pending/published）。新增契约测试：`test_extracted_tags_emit_tag_semantic_mentions`、`test_resolve_semantic_mentions_*`（3 项）。
- [x] **Phase 0.5 工程地基核验**：经勘察确认队列后端抽象 / 幂等 / lease 崩溃恢复 / 退避背压 / 断路器 / token-cost 护栏 / 故障域降级均已落地（详见 §6），剩 per-lane 细分限流与分位数大盘为增强项。
- [x] **Phase 4 scale-readiness 门补充**：`scale_readiness.py` 新增 `contentQualityCoverage`——作品判定纯净性（materialized 对象 `works_verdict.decision` 非 `work` → blocker，随记/弃稿禁入发布）+ `semanticMentions` 覆盖（文章作品 mention 覆盖率过低 → warning）；三形态计数 + 成本（TokenLedger）+ queueBackend 校验本就成熟。`test_scale_readiness` / `test_site_scale_readiness` 共 22 绿。

### 进行中 / 路线图

- [ ] **Phase 2 端侧标签可点击渲染**：数据侧 + 服务侧 mention 契约已闭环，端侧仅有 `semanticMentions` codegen 字段、尚无渲染消费（实体已靠 inline `[名称](/entity/...)` 可点击；标签可点击渲染待端侧落地）。
- [ ] Phase 0.5 增强：homepage/article/image per-lane 细分限流 + 队列/token/通过率分位数大盘。
- [ ] Phase 3 站点线多 lane 物化 content_plan 后置收尾 + 指令线 explore 真检索展开实体（框架已就位，深化 agent 真检索覆盖广度）。
- [ ] Phase 4 `produce_author` resume/spillover 健壮化 + Codex 监控抽检面深化。
- [ ] 视频作品 lane 启用（后置）。

---

## 9. 验收标准（百 / 千 / 万级端到端）

数量口径：**实体主页 + 作品总数相加**。两种工作流分别验收。

| 档位 | 数量 | 重点验证 | 通过判据 |
| --- | --- | --- | --- |
| 百级 | ~100 | 链路正确性、作品门准确率、证据闭环 | 零硬门漏判、单对象隔离生效、证据 packet 完整 |
| 千级 | ~1000 | 并发调度、限流背压、去重、成本线性 | 通过率稳定、无队列雪崩、unitPassedCost 可预测 |
| 万级 | ~10000 | 崩溃恢复、故障隔离、放量节奏、监控分位数 | 断点续跑、失败隔离不拖批、SLO 达标 |

每档必须产出：阶段 stage result + gate report + token ledger + 失败复盘。任一档不达标先阻断、补地基，不放大生成比例。

百 / 千 / 万级的可执行提示词指令见 §10。

---

## 10. 端到端验证提示词指令（两种维度 × 三档）

提示词面向 L0/L1 Agent（治理 + 编排），由其分解为 L2 子任务。两套独立文件：

- 站点维度（携程 / Pinterest）：[`content_supply_site_scale_prompts.md`](content_supply_site_scale_prompts.md)
- 指令维度（旅行垂类）：[`content_supply_instruction_scale_prompts.md`](content_supply_instruction_scale_prompts.md)

每套含百 / 千 / 万三档，数量为实体主页 + 作品总数相加，并显式声明作品门、证据闭环与放量阻断条件。

---

## 11. 剩余风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 工程地基增强项（per-lane 细分限流、分位数大盘）未完成 | 万级放量时 lane 级过载观测/限流粒度不足 | 主体地基已落地（队列抽象/幂等/恢复/退避/成本护栏）；先百/千级验证，达标再补细分 |
| `semanticMentions` 端侧标签可点击渲染（Phase 2 端侧）未闭环 | 标签跳转体验未完整（实体已可点击） | 数据 + 服务侧 mention 契约已闭环且服务侧 importer 就绪；端侧渲染独立工作包，不阻断作品生产 |
| 站点 explore 真检索展开（Phase 3）深化未完成 | 指令维度实体覆盖广度受限 | explore 包 + catalog + gate 框架已就位，可先支撑百/千级 |
| 顶层 / 执行 Agent 可替换但当前仅验证 Codex + Cursor SDK | 换模型需重测 | 契约层不绑定具体模型，envelope / gate 解耦 |
| 数据侧存在他人 in-progress 重构 baseline 失败（`test_article_markdown_contract`、`test_entity_composer::...conditionContext`、`verify` 三项 cleanup/scope/flat-root） | 全量回归非全绿 | 经定位与本期 mention/作品门改动无关；不擅自修他人未完成改动 |

风险登记与状态回写以 [`../../docs/outstanding_risks_backlog.md`](../../docs/outstanding_risks_backlog.md) 为唯一真相源。

# Scaled E2E 修复方案与验收标准

## 目标

本方案针对 `scaled_e2e_20260610` smoke 暴露出的系统性机制问题制定修复路线。修复目标不是清理某个批次目录或改好几篇样例文章，而是在推广到 1000/10000 篇内容前，恢复数据工程生产主线的边界：

```text
CLI prepare(IO/证据/写作契约) -> Agent semantic(并行创作) -> CLI review/materialize/verify
```

任何修复都必须证明以下三件事：

- 低质内容不能被伪装成合格产物。
- 目录污染和路由漂移不能被门禁漏掉。
- smoke 验证本身必须复用规模化生产机制，而不是另写场景脚本。

## 修复原则

1. **机制优先，不修样例**：先补流程、门禁、出处边界，再决定是否重跑 smoke 批次。
2. **CLI-first**：新增能力必须经 `qwq-data` 暴露；`verify/` 只放门禁，不放业务编排。
3. **Agent-only 正文**：脚本不得生成正文，也不得调用 `write_agent_draft()` 冒充 Agent。
4. **对象级并行**：每个 ref 是独立 author job，必须有 checkpoint、lease、retry、repair report。
5. **真相源双向一致**：`content_object_index.json` 与磁盘对象必须互相校验。
6. **低质源前置阻断**：source 不足以支撑写作意图时，不进入 compose。

## 阶段划分

### P0：阻止假绿灯

P0 的目标是先切断“脚本伪信号 + 门禁漏扫 + 低质内容 approved”的路径。P0 未完成前，不允许推广规模化批次。

#### R0.1 禁止新增直跑业务脚本

**问题根因**：`verify/run_scaled_e2e.py` 被新建为直跑业务入口，并被加入 allowlist。

**任务清单**：

- 移除 `cli_first_allowlist.txt` 中新增的 `verify/run_scaled_e2e.py` 豁免。
- 修改 `verify_cli_first.py`：禁止新增 allowlist 行绕过 ratchet；allowlist 只能减少，不能增加。
- 若仍需保留 smoke 入口，只允许薄壳委托 `python3 quwoquan_data/scripts/cli.py ...`，且薄壳不得包含业务逻辑。
- 新增测试覆盖“新增 `__main__` 业务脚本会失败、向 allowlist 新增行会失败”。

**验收标准**：

- `python3 quwoquan_data/scripts/verify/verify_cli_first.py` 通过。
- 新建一个临时直跑脚本的红测会失败。
- `cli_first_allowlist.txt` 不新增 `verify/run_scaled_e2e.py`。
- `verify/` 目录下不存在 download/build/produce/publish 业务编排入口。

#### R0.2 禁止脚本伪造 `generator=agent`

**问题根因**：业务脚本调用 `write_agent_draft()` 写入脚本拼接正文，`draft_meta.generator=agent` 使 provenance 门失效。

**任务清单**：

- 将 `write_agent_draft()` 拆分为 Agent writer 专用入口与测试专用入口。
- 普通 CLI/verify 脚本默认不能调用 Agent writer；调用时必须提供 Agent run context。
- `draft_meta.json` 增加不可伪造证据：
  - `agentRunId`
  - `promptSha256`
  - `writingPackSha256`
  - `sourceBundleSha256`
  - `draftSha256`
- review 校验这些 hash 与实际文件一致。
- 对 `model="scaled-e2e/agent"` 这类脚本伪模型增加阻断规则。

**验收标准**：

- 脚本直接调用 `write_agent_draft()` 的测试失败。
- 缺少 `agentRunId` / hash 的 draft 不能 approved。
- `generatorProvenance` 不再只信任 `generator=agent` 字段。
- 伪造 `draft_meta.generator=agent` 但正文由脚本写入的红测被阻断。

#### R0.3 重复 padding、ref 泄漏、模板句进入 hard gate

**问题根因**：重复段、`碧峰峡_a2` 这类 ref 泄漏、泛化 padding 句没有进入 blocking。

**任务清单**：

- 在 `_common/quality_gates.py` 新增 hard gate：
  - 连续或非连续重复段落；
  - ref/id 泄漏，如 `*_a1`、`*_g2`、`scaled_e2e`；
  - padding 模板句，如 `另外，{name}在{ref}这篇里...`；
  - 泛化无信息句高占比，如 `重要景区/山水与人文资源兼具/适合按季节规划`；
  - 同一句或同 n-gram 出现次数超阈值。
- 将这些 gate 串入 `review_entity_draft()`、`review_route_draft()`、实体主页 review。
- 更新 golden bad samples。

**验收标准**：

- 碧峰峡重复 padding 样例被 hard fail。
- 正文出现 ref 泄漏被 hard fail。
- 重复句凑字数的实体主页被 hard fail。
- `review.json` 中上述问题出现在 `issues`，`decision=revision_needed`。

#### R0.4 低质底稿前置阻断

**问题根因**：坐标页、一行游记、空百科可以进入 compose，后续再靠脚本补内容。

**任务清单**：

- 新增 `base_source_quality_gate`：
  - 去 frontmatter 后有效正文长度；
  - 坐标/目录/版权/导航/平台元信息占比；
  - 信息密度；
  - 情感证据是否只能作为补充，而非主底稿；
  - 是否支撑 `writingIntent`。
- `content_plan` 或 `compose-brief` 前执行该门。
- 源不足时写 repair report，fallback 到 `download`，不得生成 draft。
- 一行游记只能进 `emotionEvidence`，不能作为完整文章 base draft。

**验收标准**：

- `source.md` 只有一行情绪摘录时，不能作为文章底稿。
- 主要内容为坐标/维基导航文本时，不能作为可加工底稿。
- `baseDraftFidelity` 在底稿为空/不可读时失败，而不是返回通过。
- 源质量不足的 ref 停在 `compose-brief` 前，并产生 repair report。

#### R0.5 证据链门扫描孤儿阶段目录

**问题根因**：`iter_batch_object_dirs()` 只扫含 `manifest.json + article.md/gallery.md` 的成品目录，孤儿 `2.quality/3.compose/4.draft/5.review` 不进门。

**任务清单**：

- 扩展 batch object 扫描：
  - 所有含 `1.download`、`2.quality`、`3.compose`、`4.draft`、`5.review` 的 posts 目录都必须进入扫描。
  - 有阶段目录但不在 `content_object_index.json` 的对象报错。
  - 在索引中但磁盘缺对象目录报错。
  - 磁盘对象坐标与索引坐标不一致报错。
- `content_object_index.json` 与磁盘双向校验。
- `_object.json` 阶段状态必须在补齐 `1.download` 后刷新。

**验收标准**：

- `posts/article/攻略/1` 这类孤儿目录被门禁发现。
- 只有 `2.quality/3.compose/4.draft/5.review` 但无成品的目录被门禁发现。
- 坐标漂移后的旧目录不会静默通过。
- `python3 quwoquan_data/scripts/cli.py verify --task <task> --batch <batch>` 能报告孤儿对象。

## P1：恢复规模化执行主线

P1 的目标是把 smoke 验证接回可规模化生产链路。

#### R1.1 Scaled E2E 迁入 `qwq-data` 子命令或 task workflow

**任务清单**：

- 将 smoke 编排迁为 CLI 命令，例如：
  - `qwq-data task scaled-e2e prepare`
  - `qwq-data task scaled-e2e fanout-author`
  - `qwq-data task scaled-e2e rollup`
  - `qwq-data task scaled-e2e verify`
  - 底层仍复用现有 `task run --mode fanout` / `task rollup` / `verify` 主线。
- `TASK_ID/BATCH_ID/ENTITY_SPECS/_TRAVELOGUE_BODY` 从脚本迁出，进入 task spec、source seed、notes 或 fixture。
- CLI prepare 只生成：
  - source plan；
  - content plan；
  - `brief.json`；
  - `writing_pack.json`；
  - `prompt.md`；
  - 占位 draft。
- 不在 CLI 阶段生成正文。

**验收标准**：

- smoke 可通过 `python3 quwoquan_data/scripts/cli.py ...` 运行。
- 删除直跑脚本后仍可完成 prepare。
- CLI prepare 产物中没有非占位正文。
- `verify_cli_first` 与 `verify_no_runtime_draft_kit` 通过。

#### R1.2 Author 阶段 fanout

**任务清单**：

- 按 ref 生成 author job：
  - `ref`
  - `contentObjectDir`
  - `writingPackPath`
  - `promptPath`
  - `sourcePaths`
  - `expectedOutputPaths`
- 使用 object queue/leaf agent 并行执行。
- 每个 leaf agent 只写自己的 `4.draft/draft.article.md` 和 `draft_meta.json`。
- 每个 ref 独立 retry，失败写 repair report，不阻塞全批。

**验收标准**：

- 40 ref 至少能并行执行，报告中有 agent run matrix。
- 单个 ref 失败不会导致整个批次从头重跑。
- `draft_meta.agentRunId` 与 fanout report 对得上。
- 每个 ref 都有 prepare/author/review 状态。

#### R1.3 Object-level checkpoint 与恢复

**任务清单**：

- 每个阶段落 stage result、gate report、repair report。
- 批次总控只汇总对象状态，不直接串行写正文。
- 增量重跑基于对象状态选择 ref。
- 中断恢复时不能靠人工看日志。

**验收标准**：

- kill 掉 fanout 后可 resume。
- 已通过 ref 不重复 author。
- 失败 ref 有明确 fallback stage。
- 批次状态矩阵可列出 pending/running/failed/approved/materialized。

## P2：内容真实性与实体主页治理

#### R2.1 实体主页纳入同等级 review

**任务清单**：

- 实体主页不再由 `_materialize_entity_homepage()` 直接拼接产物。
- 主页也走：
  - base source selection；
  - writing pack；
  - Agent semantic；
  - review；
  - materialize。
- 实体主页禁止 padding 凑字数。
- 源不足时状态为 `needs_source_repair`。

**验收标准**：

- `稻城亚丁是四川重要景区...` 重复主页样例 hard fail。
- 实体主页有独立 review report。
- 主页 source 与正文 hash 可追溯。
- 无可用百科/官方底稿时不产生成品主页。

#### R2.2 `qualityScore` 增加准出阈值

**任务清单**：

- `approved` 不仅要求 `blocking=[]`，还要求 `qualityScore >= threshold`。
- soft gate 数量或关键 soft gate 失败超过阈值时阻断。
- 对不同 carrier/writingIntent 设置不同准出要求。

**验收标准**：

- `travelogueDensity=false` 且质量分低的文章不能 materialize。
- review report 显示 soft failure 对准出的影响。
- golden bad samples 的误放率为 0。

#### R2.3 底稿轻改真实性门补强

**任务清单**：

- `baseDraftFidelity` 在 base 缺失/不可读时返回问题。
- 单向 n-gram 覆盖外，增加：
  - 段落顺序保留；
  - 主题实体覆盖；
  - 来源噪声剔除；
  - 低信息底稿拒绝。
- base source ledger 保证一源一稿。

**验收标准**：

- 从零模板重写不能通过 fidelity。
- 坐标页底稿不能通过 source quality。
- 同一 base source 被多篇认领会失败。

## P3：目录路由与发布面一致性

#### R3.1 content object 坐标不可静默漂移

**任务清单**：

- `register_from_brief()` 禁止空 `titleHint`。
- 已登记 ref 的坐标变化默认失败，除非显式 `--migrate-object-route`。
- 迁移时移动旧目录或写 tombstone，不能留下孤儿。
- gallery `contentType` 从 `carrier` 推导，禁止硬编码 article。

**验收标准**：

- 空 titleHint 红测失败。
- 同一 ref 二次注册到不同目录会失败。
- gallery 不会落入 `posts/article/...`。
- 旧目录残留会被 verify 报告。

#### R3.2 成品发布面只来自当前索引

**任务清单**：

- materialize 前校验 ref 坐标与 `content_object_index` 一致。
- promote 只读取当前索引对象。
- publish report 输出 skipped/orphan/drift 统计。

**验收标准**：

- 不在索引中的 post 不会 publish。
- 索引中 missing 的 post 阻断 publish。
- publish report 可解释每个 skipped ref。

## P4：规模化观测与准入

#### R4.1 批次级观测报告

**任务清单**：

- 输出 batch quality dashboard：
  - source quality 分布；
  - author fanout 状态；
  - review hard/soft failure；
  - retry/repair 次数；
  - orphan/drift 计数；
  - duplicate/padding/ref leak 命中数。

**验收标准**：

- smoke 批次结束后生成单一 JSON + Markdown summary。
- 每个指标能回溯到 ref。
- 指标超阈值时批次不能 promote。

#### R4.2 推广门槛

推广到规模应用前必须全部满足：

- P0 全绿；
- fanout author 可恢复；
- 40 篇 smoke 无伪 agent、无 orphan object、无 low-quality source bypass；
- `verify_quwoquan_data.sh` 通过，且失败不来自已知任务 lint 债；
- 人工抽检不少于 10% 样本，重复/模板/伪内容为 0；
- 产出批次级观测报告。

## 实施顺序

```text
P0.1 CLI-first -> P0.2 generator provenance -> P0.3 内容 hard gate
-> P0.4 source quality -> P0.5 目录孤儿门
-> P1 fanout/workflow -> P2 主页与 fidelity -> P3 路由一致性 -> P4 观测准入
```

不要先重跑或清理 `scaled_e2e_20260610`。只有 P0 验收通过后，才允许重建 smoke 批次作为验证样本。

## 最终验收清单

- `python3 quwoquan_data/scripts/verify/verify_cli_first.py`
- `python3 quwoquan_data/scripts/verify/verify_no_runtime_draft_kit.py`
- `python3 quwoquan_data/scripts/cli.py template lint`
- `python3 quwoquan_data/scripts/cli.py verify --task 旅行/地域/四川省/景区/真实联网发布复核 --batch <new_smoke_batch>`
- `bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`
- 新增红测：
  - 直跑脚本违规；
  - allowlist 新增违规；
  - 脚本伪 `generator=agent`；
  - 低质底稿进入 compose；
  - 重复 padding approved；
  - ref 泄漏 approved；
  - orphan stage directory 漏扫；
  - entity homepage padding 造字数。

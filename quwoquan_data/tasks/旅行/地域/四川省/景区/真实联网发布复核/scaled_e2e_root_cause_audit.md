# Scaled E2E Smoke 根因审计

## 审计目标

本报告不以修复 `scaled_e2e_20260610` 某个样例为目标，而是把该 smoke 批次作为暴露样本，解释为什么一组明显低质、目录污染、规范违规的产物能够被流程推进到 `approved/materialized/publish`，以及这些问题在规模化内容生产中会怎样放大。

审计对象：

- 任务：`旅行/地域/四川省/景区/真实联网发布复核`
- 批次：`scaled_e2e_20260610`
- 规模：10 景区实体、20 篇 article、20 篇 gallery
- 关键脚本：`quwoquan_data/scripts/verify/run_scaled_e2e.py`

## 总体结论

这次 smoke 的失败不是单篇文章写差，也不是某个目录偶然残留，而是职责边界整体被绕过：

```text
应有链路：
CLI prepare(IO/证据/写作契约) -> Agent semantic(并行创作) -> CLI review/materialize/verify

实际链路：
verify/run_scaled_e2e.py 直跑 -> 脚本生成正文/主页 -> 写成 generator=agent -> review 只看被伪造后的信号
```

因此，门禁看到的是“像合格产物的元数据”，而不是“真实合格的内容”。一旦从 40 篇推广到 1000/10000 篇，问题不会自然消失，而会按批量流水线的速度污染发布面。

## 一、流程根因：CLI-first 与 fanout 边界被绕过

### 现象

`run_scaled_e2e.py` 是新增直跑入口，位于 `scripts/verify/`，但实际承担了 reset、联网抓取、source plan、实体主页、content plan、produce、review、publish 和证据链验证。

直接证据：

- 文件头声明直接运行：
  - `PYTHONUNBUFFERED=1 python3 quwoquan_data/scripts/verify/run_scaled_e2e.py`
- 脚本包含固定 `TASK_ID`、`BATCH_ID`、`ENTITY_SPECS`、`_TRAVELOGUE_BODY`。
- `main()` 串行推进所有阶段。

### 根因链

1. smoke 目标被理解为“写一个脚本把批次跑通”，而不是“验证已有 CLI/fanout 生产系统能规模化运行”。
2. `verify/` 目录被误用为业务编排目录，导致验证脚本承载生产能力。
3. `verify_cli_first` 发现新直跑入口后，临时把 `verify/run_scaled_e2e.py` 加进 `cli_first_allowlist.txt`，把 ratchet 门禁变成豁免通道。
4. 40 个 ref 没有拆成 leaf author jobs，全部在 `_compose_and_author()` 串行循环里推进。

### 为什么执行时间长、频繁中断

串行脚本把多个慢阶段耦合在一个进程里：

- Wikimedia/Commons 联网抓取；
- 每个实体和每篇内容的证据分析；
- 40 篇正文生成；
- review、materialize、publish；
- 证据链门。

没有 per-ref lease、checkpoint、重试边界，也没有并行 leaf agent。中断后只能靠日志与磁盘状态恢复，导致“等长命令 -> 中断 -> 人工判断状态 -> 再跑长命令”的低效循环。

### 规模风险

如果 40 篇都需要串行脚本推进，1000 篇会变成不可控长事务。失败恢复粒度仍然是批次级，而不是对象级；一个 ref 的质量问题会拖慢整个批次排障。

## 二、真实性根因：脚本拼正文后冒充 agent

### 现象

`run_scaled_e2e.py` 里 `_article_for_review()` 和 `_gallery_from_assets()` 直接拼接 Markdown 正文，包括固定小标题、固定决策句、固定尾段和 padding 段。

随后 `_compose_and_author()` 调用 `write_agent_draft()`：

```text
脚本模板正文 -> write_agent_draft(... model="scaled-e2e/agent") -> draft_meta.generator="agent"
```

结果：review 的 `generatorProvenance` 看到 `generator=agent`，就认为正文由 Agent 创作。

### 根因链

1. `write_agent_draft()` 是语义层写回 API，但没有调用者边界校验。
2. 生产脚本可以直接调用它并写入 `generator=agent`。
3. `generatorProvenance` 只校验 `draft_meta` 的字段，不校验“谁写入了这个字段”。
4. smoke 为了跑通 review，把脚本生成内容伪装成 agent 产物。

### 质量后果

这使三道真实性门中的第一道变成形式检查。只要脚本写出 `draft_meta.json`，就能绕过“正文必须由会话模型创作”的核心约束。

### 规模风险

任意批量脚本都可以伪造 `generator=agent`。如果不修调用边界，规模化后最危险的不是模型质量差，而是非模型内容被系统误判为模型产出。

## 三、内容质量根因：低质底稿、padding、重复段没有进入 hard gate

### 3.1 实体主页作弊的形成机制

样本：`runtime/tasks/.../entities/地点/景区/稻城亚丁/page.md`

页面出现大量重复句：

```text
稻城亚丁是四川重要景区，山水与人文资源兼具，适合按季节规划行程。
```

来源在 `_materialize_entity_homepage()`：

```text
while len(base_text) < MIN_PAGE_CHARS:
    base_text += pad
```

这不是轻改底稿，而是脚本用泛化句凑字数。更严重的是，实体主页写在 task 根 `entities/.../page.md`，不完全等同于 batch 内 post review 链路，缺少与文章同等级的 review 阻断。

根因：

- 源正文不足时没有回退到 `download/source_repair`；
- `MIN_PAGE_CHARS` 被当成生成目标，而非质量门；
- 缺少重复段、低信息密度、padding 模板句的 hard gate；
- 实体主页未强制走“真实百科底稿轻改 + fidelity + provenance”链路。

### 3.2 文章重复 padding 的形成机制

样本：`posts/article/攻略/碧峰峡慢游一日体验/1/article.md`

重复段：

```text
另外，碧峰峡在碧峰峡_a2这篇里强调慢看与错峰，别用赶场心态压缩体验。
```

来源在 `_article_for_review()`：

```text
while len(compact_body) < 660:
    body += "另外，{name}在{ref}这篇里强调慢看与错峰..."
```

这里同时暴露三个质量问题：

- 机械 padding；
- ref 泄漏到正文；
- 内容没有来自底稿，只是补字数。

### 3.3 为什么 review 仍能 approved

review 通过不是因为质量足够，而是因为阻断条件设计错误：

- `travelogueDensity` 在 `SOFT_CHECKS` 中，失败只扣分，不阻断。
- `proseStyle` 只看机械小标题等有限模式，没有重复段落 hard gate。
- `template_fingerprints` 没覆盖动态 padding 模板。
- `baseDraftFidelity` 在底稿为空或不可读时返回无问题。
- `writingIntentConsistency` 只看关键词桶，不判断内容真实、自然、非重复。
- `generatorProvenance` 信任 `draft_meta.generator=agent`。

样本 review 显示：

```text
travelogueDensity: false
decision: approved
issues: []
```

这说明 soft gate 失败不会进入 `blocking`，只降低 `qualityScore`。但 `qualityScore` 没有准出阈值，仍可 materialize。

### 3.4 原文在哪里

以碧峰峡为例：

- 一行游记摘录：`batches/scaled_e2e_20260610/entities/地点/景区/碧峰峡/1.download/sources/03.travelogue_mafengwo/source.md`
- 百科底稿：`batches/scaled_e2e_20260610/entities/地点/景区/碧峰峡/1.download/sources/01.wikipedia_overview/source.md`
- 写作契约：`posts/article/攻略/碧峰峡慢游一日体验/1/3.compose/writing_pack.json`
- 草稿：`posts/article/攻略/碧峰峡慢游一日体验/1/4.draft/draft.article.md`
- 伪 agent 元数据：`posts/article/攻略/碧峰峡慢游一日体验/1/4.draft/draft_meta.json`
- review：`posts/article/攻略/碧峰峡慢游一日体验/1/5.review/review.json`

关键问题是：`baseSourceRef` 指向百科来源，但正文主体来自脚本模板；一行游记被当成情感证据，却不足以支撑一篇高质量游记。

## 四、目录路由根因：content object 可漂移，孤儿目录不进门

### 现象

`posts/article/攻略/` 下出现：

- `1`、`2`、`3` 等数字目录；
- 正确标题目录；
- 画报标题误落在 article 下；
- 有些目录只有 `2.quality/3.compose/4.draft/5.review`，没有 `1.download` 或 `article.md`。

### 根因链

1. 内容对象路由由 `_shared/content_object_index.json` 维护。
2. `register_from_brief()` 每次会按当前 brief 重新计算 `contentType/angle/title/seq`。
3. 同一 ref 在批次中被不同版本逻辑登记过：
   - 空 `titleHint` -> `posts/article/攻略/{seq}`
   - gallery 被硬编码 `article` -> `posts/article/画报/...`
   - gallery 后来修成 `image` -> `posts/image/画报/...`
4. 新坐标生效后，旧坐标目录不会迁移或删除。
5. materialize 只在当前索引坐标下产出成品，因此旧目录只剩过程阶段。

### 为什么门禁没拦住

`iter_batch_object_dirs()` 对 posts 只枚举有 `manifest.json` 且有 `article.md/gallery.md` 的成品目录。孤儿阶段目录没有成品，不会被扫描。

这导致门禁回答的是：“当前成品对象是否完整”，而不是：“批次目录是否无污染、无孤儿阶段、无路由漂移遗留”。

### 次级问题：`1.download` 快照与 `_object.json`

后补 `1.download` 快照发生在 materialize 之后。如果不刷新 `_object.json`，对象索引里阶段状态可能仍显示 pending。这说明阶段树状态的写入时序也不稳定。

## 五、门禁根因：硬门与软门边界错置

### 现有门禁漏点

| 漏点 | 当前行为 | 后果 |
|---|---|---|
| CLI-first | 新直跑入口可进 allowlist | 新业务脚本绕过 CLI |
| generator provenance | 信任 `draft_meta.generator` | 脚本可冒充 agent |
| low-quality source | 短摘录/坐标页仍可进入 compose | 低质底稿生成低质内容 |
| repetition/padding | 未作为 hard gate | 重复段落可 approved |
| soft gate | 失败只扣分无准出阈值 | `travelogueDensity=false` 仍发布 |
| object routing | 坐标漂移不阻断 | 历史目录残留 |
| directory scan | 只扫成品对象 | 孤儿阶段目录不报错 |
| entity homepage | 未等同 post review | 伪主页可进入 task 根 |

### 根本误差

门禁过多依赖“产物是否有字段/目录/长度”，过少检查“字段是否可信、内容是否来自真实底稿、目录是否是唯一路由结果”。

## 六、规模化前必须补齐的治理

### 6.1 流程治理

- scaled e2e 必须作为 `qwq-data` 命令或 task workflow 暴露，不允许新增直跑业务脚本。
- `verify/` 目录只放门禁，不放生产编排。
- smoke 也必须执行标准三段式，不得为了跑通而合并 Agent semantic 阶段。
- author 阶段必须 fanout：一 ref 一 leaf agent，一对象一 checkpoint。

### 6.2 出处治理

- `write_agent_draft()` 需要调用边界：只能由 agent author 上下文写入，普通 CLI/verify 脚本不得调用。
- `draft_meta` 需要记录不可伪造的 session trace，例如 agent run id、prompt hash、writing_pack hash、source hash。
- review 必须校验草稿正文 hash 与 agent 写回记录一致。

### 6.3 源质量治理

- source 进入 content_plan/compose 前必须有底稿质量门：
  - 正文字数；
  - 非坐标/导航/目录页；
  - 非平台元信息堆积；
  - 信息密度；
  - 可支撑对应 writingIntent。
- 一行体验摘录只能作为情感证据，不能作为完整文章底稿。
- 源不足时写 repair report，回退 download，不生成正文。

### 6.4 内容质量治理

- 重复段落、padding 模板句、ref 泄漏、泛化句进入 hard gate。
- `qualityScore` 需要准出阈值，不能只靠 blocking 为空。
- `travelogueDensity` 对游记/体验类应是 hard gate 或至少低于阈值阻断 materialize。
- `baseDraftFidelity` 在底稿为空/不可读时应失败，而不是返回通过。
- 实体主页与 post 一样需要 review、fidelity、source provenance。

### 6.5 目录治理

- `register_from_brief()` 禁止空 `titleHint`。
- ref 坐标变化必须阻断或自动迁移/清理旧目录。
- 证据链门扫描所有含过程阶段的 posts 目录，不只扫成品目录。
- `content_object_index.json` 与磁盘对象必须双向一致：索引里有的必须存在，磁盘有阶段痕迹的必须在索引中。

### 6.6 观测与报告

规模化批次必须输出：

- ref 级状态矩阵：prepare / author / review / materialize / publish；
- agent fanout 运行矩阵：run id、耗时、失败原因、重试次数；
- source 质量分布；
- review hard/soft failure 分布；
- orphan object / route drift 计数；
- 重复内容与模板命中率。

## 七、整改优先级

### P0：阻止假绿灯

- 禁止脚本伪造 `generator=agent`。
- 删除新增 allowlist 豁免。
- 重复 padding / ref 泄漏 / 低质底稿变 hard gate。
- 证据链门扫描孤儿阶段目录。

### P1：恢复可规模化流程

- scaled e2e 迁入 CLI task workflow。
- author fanout 并行化。
- per-ref checkpoint 与 repair report 闭环。

### P2：提升内容真实性

- 实体主页纳入同等级 review。
- source quality 门前置。
- qualityScore 加准出阈值和分布报告。

## 结语

这次 smoke 的价值不在于“曾经跑出 40/40 approved”，而在于证明当前系统可以被脚本伪信号骗过。规模化之前必须先修边界和门禁，否则越大的批次只会越快地产生低质但看似合格的内容。

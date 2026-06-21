# 指令维度内容供给提示词（旅行垂类 · 百 / 千 / 万级）

本文件是**指令维度**（全网检索展开实体与篇目）端到端内容供给的可执行提示词，面向顶层治理 / 编排 Agent（L0/L1），由其分解为执行子 Agent（L2）任务。配套蓝图见 [`content_supply_commercialization_plan.md`](content_supply_commercialization_plan.md)。

> 命令前缀 `qwq-data` = `python3 quwoquan_data/scripts/cli.py`。所有命令在仓库根目录执行。

---

## 0. 平台铁律（每档都必须遵守，禁止放宽）

1. **只产作品，不产随记**：产出仅限实体主页 / 图片作品 / 文章作品。`compose-brief` 闸口 `evaluate_object_works` 判 `moment` / `abandoned` 的对象被阻断、落 `works_verdict.json`，不进 Agent 创作。视频作品当前后置。
2. **作品门省 token**：作品门在 L2 创作之前裁决，非 work 对象不消耗 Cursor SDK token；内容自证通道保证高质量长文不被低来源先验误杀。
3. **证据后置，禁止搜索向预置**：篇目 ref/title 由已下载 `evidenceRefs` 归纳，禁止 download 前预置「XX攻略」营销线路名再凑来源。B 组线路需 ≥2 条独立来源联游互证。
4. **事实可回溯 + 权利合规**：`licensed_adaptation` 保存 license/terms/credit/授权快照；普通网页只作 `factual_reference_only`，成品必须独立表达；权利不明 / 禁商用 / 抓取失败 = `blocked`，不进 content_plan。
5. **标签 / 实体治理**：草稿声明 `extractedEntities` / `extractedTagCandidates`；只有已发布 mention 派生 active `entityRefs/tagRefs`；`tagRefs` 必须指向 `publish/tags/**/_definition.json` 已存在路径，禁止扁平省名 / 品类名。
6. **准出认文件不认口头**：每阶段读 `write_gate_report` / `gate_*.py` 结果，有 issues 不得 `--resume` 下游；失败回灌原阶段生成 repair packet 重试。
7. **数量口径**：目标数量 = 实体主页 + 作品总数**相加**。

---

## 1. 旅行垂类主线命令族

```
explore（区域→候选实体）→ baseline（冻结范围/阈值）→ download（分 lane 检索抽取 + 图片安全门）
→ content_plan（篇目 + evidenceRefs + entityRefs + mustIncludeFacts）
→ produce（compose-brief[作品门] → Agent 创作 → self-check → review → materialize[semanticMentions 回填]）
→ publish → ship/importer → verify
```

---

## 2. 百级（~100：实体主页 + 作品相加）

**目标**：跑通指令维度全链路正确性、作品门 + 自证通道、证据闭环、标签 / 实体回填。

**分配建议**：实体主页 40（如 40 个景区主页）+ 文章作品 50 + 图片作品 10 = 100。

**编排骨架**：

```bash
TASK=travel_h100; TBATCH=b1
# 1) 探索：区域 → 候选实体
qwq-data explore --task $TASK --regions "云南,四川,西藏" --entity-types "景区,古镇,自然保护区"
# 2) 冻结范围与阈值
qwq-data baseline --task $TASK ...
# 3) 分 lane 检索抽取 + 图片安全门（来源逐条带 license/relevance/sourceKind）
qwq-data download --task $TASK --batch $TBATCH ...
# 4) 篇目规划（证据后置：ref/title 由 evidenceRefs 归纳）
qwq-data content_plan --task $TASK --batch $TBATCH ...
# 5) 生产（compose-brief 作品门 → Agent 创作 → review → materialize）
qwq-data produce --task $TASK --batch $TBATCH ...
# 6) 发布 + 校验
qwq-data publish --task $TASK --batch $TBATCH ...
qwq-data verify --scope current
```

**准出判据（全绿才算通过）**：
- 作品门零硬门漏判；自证通道未误杀高质量长文（抽检 ≥10 个 `works_verdict.json`）。
- 每篇有 `evidenceRefs`，无预置营销 ref；B 组线路有联游互证。
- 实体主页自动生成且无 dangling entityRef；`tagRefs` 全部指向已发布 tag。
- `semanticMentions` 回填生成 offset/status/targetRef（标签 / 实体可点击基础）。

**放量阻断**：硬门漏判、证据不可回溯、dangling ref 或 mention 回填缺失 → 停在百级，修复后重跑。

---

## 3. 千级（~1000）

**目标**：并发调度、per-lane 限流背压、跨稿去重、成本线性、作者疲劳门。

**分配建议**：实体主页 300 + 文章作品 600 + 图片作品 100 = 1000。

**与百级差异**：
- `explore` 扩区域 / 实体类型；`content_plan` 用配额 `entityHomepagesPerTarget` / `entityArticlesPerTarget` / `galleryPostsPerTarget` 控制总量与逐实体分布。
- 用 `workflow` 编排分片并发：

```bash
qwq-data workflow run --task $TASK ...   # 分片 / 并发 / 调度 / 结果合并
```

- 重点观测：批次 reducer 跨稿重复、题材分布、底稿复用、资产复用、作者疲劳。

**准出判据**：
- 跨稿重复门通过，题材分布均衡，无底稿 / 资产违规复用。
- `unitPassedCost` 可预测、随量线性。
- 限流 / 背压生效，无队列雪崩。

**放量阻断**：跨稿重复超阈、成本非线性、并发雪崩 → 停在千级，补 Phase 0.5 工程地基，不进万级。

---

## 4. 万级（~10000）

**目标**：崩溃恢复、故障域隔离、放量节奏、监控分位数、下游闭环、explore 真检索展开。

**分配建议**：实体主页 3000 + 文章作品 6000 + 图片作品 1000 = 10000。

**与千级差异**：
- explore 真检索展开实体（广覆盖），按区域 / 实体类型多批滚动放量。
- 崩溃中断后用 stage result + objectKey 幂等断点续跑（`workflow` resume）。
- 按 SLO 分位数（非算术均值）监控通过率 / 延迟 / 成本。
- 下游闭环：publish → ship/import → search 可见 → 推荐反馈回流。

**准出判据**：
- 断点续跑成功、无重复产出（幂等）。
- 单实体 / 单 lane 失败被隔离，进 `abandoned` / `manual_required`，不拖批。
- 端到端链路闭合：Data → Service → App → Behavior → Recommendation → Observability。
- SLO 达标（见 `content_ops_slo.md`）。

**放量阻断**：恢复失败、故障扩散、下游断点或 SLO 不达标 → 回退千级，修复后再放大。

---

## 5. 与站点维度的关系

指令维度与站点维度共用同一对象级过程树、作品门、质量门、证据链与 `produce/publish` 主线，只是供给入口不同（全网检索 vs 单站抓取）。两条线最终都汇入 `content_plan_packet.json` + `content_object_index.json`。站点维度提示词见 [`content_supply_site_scale_prompts.md`](content_supply_site_scale_prompts.md)。

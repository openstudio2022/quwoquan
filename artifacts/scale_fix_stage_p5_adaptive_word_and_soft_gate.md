# P5 字数门自适应统一口径 + 非致命检查降软扣分

规划真相源：`/Users/zhaoyuxi/.cursor/plans/提示词重构与三类解耦放量_2f1c2e11.plan.md`（P5）。

## 目标（P5 判据）

- 字数门按内容形态自适应（图主导 200 字级 / 长文 600 字级），统一 `route_review` 与 `verify_content_quality` 口径，消除第二真相源。
- 非致命检查（情感词 / 小标题数 / 结尾差异化）降为软扣分（建议 + 降分），不 hard-block。

## 现状核对（先证明真相源）

- **字数门已是单一真相源**：`_common/base_draft.base_draft_readiness`（`ARTICLE_MIN_BASE_DRAFT_CHARS=600` / `RICH_MIXED_MIN_TEXT_CHARS=200`）。`produce/route_review.py`（L518-522）与 `verify/verify_content_quality.py`（L120-134）都已消费它，无裸 `>=600` 第二真相源。本批以契约固化阈值常量，防回退。
- **软门存在第二真相源（本批修复）**：`SOFT_CHECKS` 原本只在 `produce/route_core.py` 内定义 `{travelogueDensity, writingIntentConsistency}`；而 `verify_content_quality._semantic_gate_issues` 把 `writingIntentConsistency` 与 `mechanicalHeading` 当**硬门**直接 hard-block —— review 软、verify 硬，口径漂移。

## 本批改动（单一真相源）

### 软门集合单一真相源

- `quwoquan_data/scripts/_common/quality_gates.py`
  - 新增 `SOFT_QUALITY_GATES = {travelogueDensity, writingIntentConsistency, mechanicalHeading, proseStyle}` + `is_soft_quality_gate()`，作为 review/verify **共用**软门唯一真相源（情感密度 / 写作主线 / 机械小标题 / 机械结尾）。
- `quwoquan_data/scripts/produce/route_core.py`
  - `SOFT_CHECKS = set(quality_gates.SOFT_QUALITY_GATES)`（复用单一真相源，不再各写一套）；机械小标题 `mechanicalHeading` 与机械结尾 `proseStyle` 现也归软门 → route_review 命中只软扣分 + 出建议。
- `quwoquan_data/scripts/verify/verify_content_quality.py`
  - `_semantic_gate_issues(..., advisories=...)`：`writingIntentConsistency` / `mechanicalHeading` 命中只进 `advisories`（软提示），**不**计入 hard FAIL；硬门（图文闭环 / 语域 / 联系方式 / 段内重复）仍 hard-block。
  - `verify_posts(..., advisories=...)` 透传；`main()` 打印软提示（non-blocking）后仅按硬门决定退出码 —— 与 produce review SOFT_CHECKS 同口径。

### 边界（诚实）

- golden set（`measure_gate_goldenset`）的 `_firing_gates` 度量的是这些启发式函数的**检出准确率（firing）**，与「命中后软 / 硬动作」是两件事；软门改动后 golden set 仍 `intercept=1.0 / falsePositive=0.0` 通过，无需改 golden（软门函数仍 firing，只是不再 hard-block）。
- 跨篇反模板硬门（`skeletonSimilarity` 含结尾段相似）与去重（`semanticDuplicate`）仍为硬门，**不**降软：它们防模板农场，不属"结尾差异化"启发式软门范畴。

## 测试与门禁

- 新增 `quwoquan_data/tests/local_contract/common/test_soft_gate_unification__local_contract_test.py`（4 用例）：
  - 软门集合单一真相源 `route_core.SOFT_CHECKS == quality_gates.SOFT_QUALITY_GATES` + 四项非致命检查在集合内。
  - `is_soft_quality_gate` 软 / 硬分类正确。
  - 字数门唯一真相源阈值（600 / 200）。
  - verify 软门只进 advisories 不 hard-block。
- 已接入 `verify_quwoquan_data.sh`（紧随 P4）。
- 回归全绿：`measure_gate_goldenset`（intercept=1.0/fp=0.0）、`test_quality_gates`、`test_content_drift`、`test_handoff`、`test_adaptive_word_gate`、`test_release_integrity_gate`、`test_task_author_review`、`test_route_brief_and_evidence`、`test_creative_autonomy_gate`（共 114 用例通过）。

## 作用域

仅改 `quwoquan_data/**` 与 `artifacts/**`，未触碰 `quwoquan_app/**` 与他流 metadata/_shared 漂移。

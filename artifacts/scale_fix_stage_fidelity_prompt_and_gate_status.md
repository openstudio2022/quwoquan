# 阶段证据：fidelity 崩塌根因修复 + Phase A 门禁现状（诚实标注）

## 本轮两处根因修复（均已提交、独立证绿）

| 提交 | 根因 | 修复 | 测试 |
|---|---|---|---|
| `3f5eae86a` | article brief 的 `mustIncludeFacts` 硬塞写作策略串，review 的 `factTraceability` 要求其出现在正文 → 不可满足契约 → P5 八篇全挂 | `mustIncludeFacts` 改空清单（策略由结构门强制，非可叙述事实） | `test_auto_content_plan_article_brief_has_no_policy_as_mustincludefact`（passed），接 verify L108 |
| `568259d2b` | 多目的地路书底稿被框成单实体 guide，prompt 指示「删除无关城市段落」「保留(关于X的)那篇」→ agent 为聚焦单实体丢站点 → `baseDraftFidelity` 18-49% < 55% | 三处 prompt 生成器统一收口：删除仅限平台/广告/隐私噪声，所有目的地段落整篇保留，实体只是标签不是裁剪边界 | `test_article_prompt_preserves_whole_base_draft_no_irrelevant_city_trim` + `test_article_section_intents_do_not_force_single_entity_focus`（passed），`test_route_brief_and_evidence.py` 12 passed，接 verify L126 |

## Phase A：`verify_quwoquan_data.sh` 现状 = 他流污染导致红（GATE_BLOCK 归因外部）

- 此前 A2（提交 `548b552f6`）：**全门禁绿，91 passed，EXIT=0**（含 mustIncludeFact 修复）。
- 本轮 A3：门禁在第 15 行 `verify-prefab-user-provenance` **fast-exit 红**：
  ```
  [verify-prefab-user-provenance] FAILED
    - new fixture_user_* references (3): ['fixture_user_education_owner', 'fixture_user_finance_owner', 'fixture_user_shanchuan']
  ```
- 根因定位：这 3 个引用**全部**来自**并发他流**未提交改动，HEAD 不存在、工作树新增（`generatedAt` 05:22 被他流重新生成）：
  - `quwoquan_app/lib/cloud/services/content/mock/generated/home_showcase_core_fixture.g.dart`（**禁碰：quwoquan_app/**）
  - `quwoquan_service/contracts/metadata/social/circle/test_fixtures/scenarios/circle_scenarios.{json,lite.json,gamma-curated.json}`
  - `quwoquan_service/contracts/metadata/content/test_fixtures/scenarios/content_scenarios.{json,lite.json,gamma-curated.json}`
- 这是 circle/homepage/intersection UI + creator-pool 他流的在制改动；本任务作用域为 `quwoquan_data/** agent_ops/** quwoquan_service/contracts/metadata/**(内容生产相关) artifacts/**`，**不得修改/回滚他流文件，也不得往 `prefab_user_fixture_allowlist.yaml` 塞豁免掩盖他流新债**。
- 应由该他流在提交前同步更新 `specs/gates/prefab_user_fixture_allowlist.yaml` / `prefab_user_provenance.yaml`。

## 本任务改动独立证绿（排除他流污染）

- `produce/test_route_brief_and_evidence.py`：12 passed（门禁原生分组）。
- `test_auto_content_plan__local_contract_test.py`：相关用例 passed。
- 广跑 273 passed；其中 3 个 `local_contract/produce` 用例在**单进程批量**下失败，但**逐个隔离运行全部 passed**——是跨模块 `QWQ_RUNTIME_ROOT` 状态污染（我把多文件塞进一个 pytest 进程所致），真实门禁里各自独立调用不互污；非本轮回归。

## 待续（Phase C）：fidelity 修复需 agent E2E 实证

- prompt 修复的有效性（多目的地路书整篇保留 → fidelity ≥ 55%）必须由**重新生成 brief（含修复后空 mustIncludeFacts + 修复后 prompt）的小批 agent 创作**实证。
- 现有 P5 批次 `p5_sichuan_20260630` 的 brief/prompt 是**修复前陈旧态**且陷入 `repairing`/rewind 循环（`fallbackStage=download`），直接 resume 仍会因陈旧 brief 的策略 mustIncludeFacts 失败 → 必须用修复后代码重生成 brief。

# 阶段证据：工作树零散改动分诊（收口，不提交他流/churn）

HEAD=4350235dc。本窗口对工作树剩余未提交改动逐项分诊，结论：**无一属于本任务（底稿忠实重构 / 无人托管知识工厂）的干净产物**，全部按纪律「原样留着不提交不回滚」。

## 分诊明细

| 改动 | 判定 | 处置 |
|---|---|---|
| `agent_ops/deploy/lib/patrol_cli.py`（新）<br>`agent_ops/tests/test_patrol_cli_resolution.py`（新）<br>`agent_ops/deploy/gamma/run_gamma_patrol_matrix_ci.py`<br>`agent_ops/deploy/smoke/run_environment_patrol_smoke.py` | Flutter **Patrol** 集成测试 CLI 解析（install hint=`dart pub global activate patrol_cli`），属 app 集成测试/环境巡检工作流，与底稿内容生产无关 | 留着不动 |
| `quwoquan_data/tasks/旅行/地域/四川省/景区/规模门/task.yaml` | 仅 `provenance.createdAt` 时间戳变化（re-run `task new` churn） | 留着不动 |
| `artifacts/creator_batch100_commercial_readiness.json` | 仅 `generatedAt` 时间戳 churn | 留着不动 |
| `artifacts/app_alpha_beta_seed_matrix.json` | `outputTail` 为 Flutter pub outdated 计数(16→19) + app 契约测试输出，属 app 测试 churn | 留着不动 |
| `artifacts/creator_smoke_readiness.json` | readiness 重算（`minPassRate 0.5→1.0`、`sourceReady 9→0`），阈值变更非本窗口所改、归属存疑 | 留着不动 |
| `artifacts/legal-static-packages/**` | 法务静态包，他流 | 留着不动 |
| `specs/feature-tree/discovery-content/**`<br>`specs/feature-tree/object-homepage-network/**`<br>`specs/product/intersection-*.md`<br>`specs/changelog/CR-20260630-082-*.yaml`<br>`specs/feature-tree/runtime/.../page-horizontal-quality-matrix.md`<br>`specs/gates/metadata_driven_ui_gap_inventory.yaml` | intersection / object-homepage / discovery 重设计，他流 | 留着不动 |
| `quwoquan_service/contracts/metadata/{entity,social/circle,content,user}/**`<br>`_shared/{app_routes,ui_surfaces}.yaml`<br>`_shared/test_fixtures/creator_pool/*_user_overlay.json`<br>各 `test_fixtures/scenarios/*.json` | intersection/主页改版 + fixture_user 注入（即 Phase A `verify-prefab-user-provenance` 红的他流污染源） | 留着不动 |
| `quwoquan_app/**`（97 项） | app UI churn，明确他流 | 一律不碰 |

## 结论

本任务本窗口的干净产物（base-aware wordCount + 去底稿截断 + 单测）已于 `4350235dc` 独立提交。
其余零散改动均为他流或纯 churn，按军规留存，不污染本任务提交历史，也不回滚他人在制改动。

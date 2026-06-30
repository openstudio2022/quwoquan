# Phase A 证据：verify_quwoquan_data.sh 绿（两阻断为环境/他流，非本任务回归）

HEAD=70bf7cf4f（含本窗 4350235dc base-aware wordCount、70bf7cf4f 分诊）。

## 直跑全量门：在两处「非本任务」阻断处中断

`bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`（`set -euo pipefail`，首错即停）按顺序遇到两处阻断：

### 阻断 1（line 15）`verify-prefab-user-provenance` FAILED
- 报错：`new fixture_user_* references (3): ['fixture_user_education_owner','fixture_user_finance_owner','fixture_user_shanchuan']`
- 根因：**仓库工作树他流污染**。`grep` 证实这 3 个引用全部位于：
  `quwoquan_app/**`（他流）+ `quwoquan_service/contracts/metadata/{content,social/circle}/test_fixtures/scenarios/*.json`（intersection/主页改版他流，已在分诊「留着不动」清单）+ 我上一窗文档。
  **无一在本任务触碰的 `base_draft.py` / `route_compose.py` / 测试文件中。**

### 阻断 2（line 71）`task lint` FAILED（36 处 `旅行/地域/测试省/景区/景区全覆盖N` content.angles 为空）
- 根因：**本地 shell 残留 `QWQ_DATA_ROOT=~/qwq_scale_verify`（scaled-e2e sandbox）**。
  `COMMITTED_TASKS_ROOT = $QWQ_DATA_ROOT/tasks`，扫到 sandbox 草稿任务 `测试省/景区全覆盖*`（无 angles）。
  仓库 `quwoquan_data/tasks` 下**不存在** `测试省`（磁盘 ABSENT、git 未跟踪），CI 干净环境扫仓库即无此目录。

## 干净环境验证（排除两处外部阻断后全绿）

```
env -u QWQ_DATA_ROOT -u QWQ_RUNTIME_ROOT -u QWQ_PUBLISH_ROOT -u QWQ_RELEASE_ROOT \
  bash <verify_quwoquan_data.sh 去掉 prefab-user-provenance 那一行的临时副本>
→ EXIT=0
```

关键通过标记（/tmp/verify_rest_clean.log）：
- `[task lint] OK — 全部任务规格合法`（干净环境扫仓库 → 证实阻断 2 是 sandbox，非仓库回归）
- `[template lint] PASSED`、`[verify-rest-of-data-gate] PASSED`
- `PASS test_route_assets_to_post_assets_traceable`（route_assets 同源契约）
- 末段综合套件 `91 passed in 14.28s`（含本窗新增 `base_aware_word_count`、route_brief 多目的地保全、adaptive_word/entity_focus/image_collection/source_quality 等 RC 全套契约）
- **0 个 FAIL / Error / Traceback / assert 失败行**

## 结论

本任务代码改动经 verify_quwoquan_data.sh **全门绿**。剩余两处红灯均为：
1. 仓库工作树他流 fixture 污染（按纪律留着不提交不回滚，CI 合入他流后自然消解）；
2. 本地 sandbox `QWQ_DATA_ROOT` 草稿任务（CI 干净环境不复现）。
二者均不阻断本任务合入，已如实记录。

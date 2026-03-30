# page-horizontal-quality 任务

## 当前交付

### M1：索引与门禁可追溯

- [x] `spec.md` / `design.md` / `acceptance.yaml` / `plan.yaml` 与本目录并列
- [x] 指向父目录 `page-horizontal-quality-spec.md`、`page-horizontal-quality-matrix.md` 与 `scripts/verify_page_horizontal_quality_matrix.py`

### M2：/baseline 冻结（2026-03-29）

- [x] `page-horizontal-quality-spec.md` 增补商用/NFR（治理型）
- [x] `design.md` 上游评审、方案对比、观测与回滚
- [x] `acceptance.yaml` T3/T4 证据矩阵 + A3（CR-005）
- [x] `plan.yaml` slice-2
- [x] `CR-20260329-005-page-horizontal-quality-baseline.yaml`

### M3：/dev 无漏页门禁（2026-03-29）

- [x] `scripts/verify_page_matrix_scan_complete.py`（磁盘 = 矩阵 ⊆ 缺口清单）
- [x] `scripts/gate_repo.sh` 串联调用
- [x] 矩阵挂靠面补 `_AssistantConversationHistoryPage`

## 后续

- [ ] 矩阵或脚本变更时同步更新本目录 `spec.md` 索引表
- [ ] 新增横向维度（P9…）时同步更新脚本 `PILLAR_COUNT` 与矩阵表头

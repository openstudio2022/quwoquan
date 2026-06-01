# Phase 0 验收凭证 — 清债 + 真相源收敛

- 阶段：内容飞轮工程 Phase 0（纯 quwoquan_data，不改云侧）
- 状态：PASSED
- 日期：2026-06-01

## 任务完成

### T0-1 删 migrate 真相源残留
- 删除 `quwoquan_data/scripts/task/migrate_history.py`
- 删除 `handler.py` 的 `handle_migrate_history` 与 `migrate-history` 子命令注册
- 删除 `quwoquan_data/tasks/README.md` 的 migrate-history 引用
- 13 个 committed `task.yaml` 的 `provenance.createdBy: migrate_history` → `bootstrap`

### T0-2 sop few-shot 接线（逻辑自治）
- `_common/writing_pack.py`：新增 `_load_sop_fewshot`（只读 `DATA_ROOT/sopExampleRef` 的 example.md + 同目录 guide.md，缺失优雅跳过）
- `build_writing_pack` 注入 `sopExampleRef`/`sopFewshot`；`render_prompt_md` 渲染"写作范例与规范(few-shot)"段
- sop 保持全局单一真相源（`sop/主页/<域>/<类型>/`），不物理拷进任务

### T0-3 修 download 默认零源 bug
- `download/source_inputs.py`：`curated_sources_for_entity` 兼容顶层 `sources` / `payload.sources` / `payload.existingSources`，并兼容 source_id/url 字段名
- `download/prepare.py`：envelope 镜像 `sources`，且不覆盖已存在的预置/Agent source_plan（保留其源）

## gate-out 校验

| 校验 | 命令 | 结果 |
|---|---|---|
| 真相源残引清零 | `rg migrate_history`（全仓） | 0 命中 |
| 任务规格合法 | `cli.py task lint` | OK（13 任务） |
| 子命令已移除 | `cli.py task --help` | 无 migrate-history |
| sop 注入回归 | `tests/test_sop_injection.py` | 4 PASS |
| download 零源回归 | `tests/test_download_source_plan.py` | 2 PASS |
| 全量门禁 | `make verify-quwoquan-data` | PASSED |

两个新测试已挂入 `quwoquan_data/scripts/verify/verify_quwoquan_data.sh`。

## Phase 1 gate-in 就绪声明

- [x] `specs/gates/phase0_acceptance.md` 存在且通过（本文件）
- [x] 稻城亚丁已有 conditionProfile：`quwoquan_data/publish/entities/地点/景区/稻城亚丁/_entity.json`（regions=[高原,山地]/seasons=[夏,秋]/altitudeMeters=4000），`plan/brief._entity_condition_profile` 可读

→ Phase 1 入口条件满足，可开新会话执行 Phase 1（稻城亚丁真实标杆 + 川西/四川景区 fan-out）。

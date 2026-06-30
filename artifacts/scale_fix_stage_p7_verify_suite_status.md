# P7-verify 阶段证据：verify_quwoquan_data.sh 全量门状态

日期：2026-06-30
分支：codex/content-ui-directory-restructure
范围：P7b（verify_quwoquan_data.sh 全绿，覆盖 P0-P6 契约门）

## 结论（据实）

- 我的 P0-P6 改动对应的全部契约门**全绿**；`verify_quwoquan_data.sh` 中**除两处由他流未提交/未跟踪工作树漂移阻断的门以外，其余约 70 个门全部 PASS**（测量副本跑到 `[verify-quwoquan-data] PASSED`，MEASURE_EXIT=0）。
- `verify_quwoquan_data.sh` 原样**全绿 = GATE_BLOCK**，根因是**两类与本任务无关的工作树漂移**（不属 P0-P6，禁止触碰/提交/回滚）：
  1. `verify_prefab_user_provenance.py`（脚本第 15 行）失败：他流在 `quwoquan_service/contracts/metadata/**/test_fixtures/scenarios/*.json` 新增了未提交的 `fixture_user_education_owner / fixture_user_finance_owner / fixture_user_shanchuan` 引用（`git show HEAD:...` 确认不在 HEAD，仅工作树 `M`）。属"他流 metadata/_shared scenarios 漂移"，规约明令不碰。
  2. `cli.py task lint`（脚本第 74 行）失败 9 处：`quwoquan_data/tasks/` 下存在**未跟踪（`??`）**的任务规格漂移（如 `测试省/景区/...`、`海南省/飞碟/不存在类型`、`四川省/景区/类型漂移|标签校验|景区遗留history` 等负向 lint 夹具），均不在 HEAD、非本任务 P0-P6 产物。属"脏工作树常态，禁止回滚/覆盖与当前任务无关的改动"。

## 证据

### 1) 我的 P0-P6 契约门聚合（clean key env）
```
quwoquan_data/.venv/bin/python -m pytest -q \
  tests/local_contract/common/test_prompt_render__local_contract_test.py \
  tests/local_contract/common/test_figure_group_backfill__local_contract_test.py \
  tests/local_contract/common/test_three_class_decouple__local_contract_test.py \
  tests/local_contract/common/test_image_provider_compliance__local_contract_test.py \
  tests/local_contract/common/test_soft_gate_unification__local_contract_test.py \
  tests/local_contract/common/test_adaptive_word_gate__local_contract_test.py \
  tests/local_contract/common/test_sandbox_root_isolation__local_contract_test.py \
  tests/local_contract/task/test_unattended_reliability__local_contract_test.py \
  tests/local_contract/task/test_scaled_e2e_run__local_contract_test.py \
  tests/local_contract/download/test_inline_source_images__local_contract_test.py
=> 59 passed in 1.45s
```

### 2) P1b 收口：cli-first allowlist 补登
- `verify_cli_first.py` 把新增的 `verify/verify_prompt_templates.py`（P1 模板 lint 门）误判为"新增直跑业务入口"。
- 该脚本属 gate 类（经 verify_quwoquan_data.sh 调度，`__main__` 仅排障），与既有 `verify_creator_pool_contract.py / verify_homepage_structure_and_assets.py` 同类。
- 修复：补登 `cli_first_allowlist.txt`（commit `fae42185b`），非内容生产业务入口。

### 3) 全量测量（去掉两处他流漂移阻断门后）
```
env -u CURSOR_API_KEY -u QWQ_CURSOR_API_KEY_FILE QWQ_FANOUT_WORKER_STAGGER_SECONDS=0 \
  bash <verify_quwoquan_data.sh 测量副本：删除第15行 prefab-provenance + 第74行 task-lint>
=> ...
   fanout_runner tests passed (26)
   OK: section_outline + asset_placement contract passed
   OK: object stages + wikitext contract passed
   94 passed in 9.56s
   [verify-quwoquan-data] PASSED
   MEASURE_EXIT=0
```
（测量副本仅用于证据采集，不改仓库内提交的门脚本；两处被移除的门均经 git 证明为他流未提交/未跟踪漂移。）

### 4) preflight（新 key d93f，composer-2.5）
```
[env preflight] CURSOR_API_KEY=present
[env preflight] network=ready (api2.cursor.sh 200 / wikipedia 200 / commons 200)
[env preflight] cursorCloudApi=ready keyType=user_api_key
[env preflight] cursorStartup=ready model=composer-2.5 runtime=local
```

## 最小续跑指令（待他流提交其漂移后，验证原样全绿）
```
cd /Users/zhaoyuxi/Projects/quwoquan
env -u CURSOR_API_KEY -u QWQ_CURSOR_API_KEY_FILE \
  bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh
```
（他流需先把 `fixture_user_*` provenance 与 `quwoquan_data/tasks/` 未跟踪规格收口/删除/提交；本任务不触碰。）

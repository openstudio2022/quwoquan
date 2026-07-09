# Phase 1 验收凭证 — 全自动 ReAct 产线（目标① 全流程自动化）

- 阶段：内容飞轮工程 Phase 1（纯 quwoquan_data，不改云侧）
- 状态：能力就绪 CAPABILITY-READY（工程能力全绿；真实内容产出待运行，见下）
- 日期：2026-06-03

## 目标① 自动化能力裁定

目标①要求：内容生产全流程自动化，人只在入口(任务定义)与出口(抽检)介入。本阶段
补齐了把零散 CLI 串成无人值守闭环所缺的三块能力，使中间环节不再逐步手敲。

## 任务完成（工程能力）

### T1-8 无人值守产线编排器 `qwq-data task run`
- 新增 `quwoquan_data/scripts/task/run.py`：固定 DAG 薄编排壳，串
  download_plan→download_fetch→build_prepare→build_homepage→build_validate→
  produce_compose→produce_author→produce_annotate→produce_review→publish。
- 双类节点：确定性 stage 直接跑既有 handler；Agent checkpoint（source_plan /
  实体主页 / 正文创作）写指引并暂停（退出码 10），物化产物后 `--resume` 自动推进。
- `task_workflow_state.json` 落 `local/data-runtime/tasks/<人读taskId>/batches/<batch>/_shared/`，
  记 completed / waitingCheckpoint / reactRewinds，幂等可 resume；`--until` 早停。
- 在 task handler 注册 `task run`，docstring 同步。

### T1-9 HITL 最小化（人只看真正模糊的项）
- `_common/review_ledger.py` 新增策略 `autoApprove.autoDiscardScoreAtMost`：
  agent 存疑且分≤阈值的「明确违规」(image_safety unsafe=水印/平台标记→1分)
  自动 discard，不占用人工；明确合格(safe→4分)自动 publishable；只有真正模糊
  的 needs_review(人脸边界→2分)才转人工 fix。
- 默认 `autoDiscardScoreAtMost=1`，关闭时退回全转人工行为。

### T1-10 ReAct 自省自动回退（自学习闭环）
- 各 stage gate report 既有的 `fallbackStage` 信号接入编排器：build_validate /
  produce_review 失败时，按 fallbackStage（download→重检索 / compose→重组）
  自动回退 DAG 指针并重跑。
- `reactRewinds[stage]` 计数 + `MAX_REACT_REWINDS=2` 上限，超限转人工，防无限自省。
- 每次回退写 `repair_report`（反思账本：failedStage / issues / rerunChain）。

### 既有能力复核（P1 范围内已落地，本轮核实）
- 实体主页真实链路：`build/homepage.py` 的 prepare 下发主页产出契约 + validate
  采纳门（page.md≥字数门 / _entity.json conditionProfile / manifest）已就绪。
- media 自动化：`media check-images` 真实 CV 体检（人脸/水印/OCR/去重）+ gate，
  失败 `fallbackStage=compose`，缺图回退指针已就绪。
- Agent 检索范式：download source_plan→fetch（裸 GET + body 离线兜底）已就绪。

## gate-out 校验

| 校验 | 命令 | 结果 |
|---|---|---|
| 编排器注册 | `cli.py task run --help` | OK（DAG 10 stage 可见） |
| 编排器 DAG/checkpoint/resume/ReAct 回退 | `tests/local_contract/task/test_workflow_state_machine__local_contract_test.py` + `tests/user_acceptance/workflow/test_task_run_operator_journey__user_acceptance_test.py` | PASS |
| HITL 最小化 | `tests/integration/test_hitl_autopass.py` | 4 PASS |
| 实体主页链路 | `tests/build/test_build_homepage.py` | PASS（既有） |
| 全量门禁 | `make verify-quwoquan-data` | PASSED |

新测试已挂入 `quwoquan_data/scripts/verify/verify_quwoquan_data.sh` Phase 1 块。

## 待运行（不阻断能力就绪，属产线实际执行）

- `publish/entities/` 当前为空（过往清理后未回填）。稻城亚丁真实标杆 + 川西/
  四川景区 fan-out 需走 Agent 联网检索(web_search/浏览器)→实体主页→逐篇正文
  创作的完整 checkpoint 循环，是产线运行而非工程能力建设。
- 运行方式：`qwq-data task run --task 旅行/地域/四川省/景区/景区全覆盖 --batch <b>`，
  在每个 checkpoint 按指引由 Agent 物化真实产物后 `--resume`。

## Phase 2 gate-in 就绪声明

- [x] 全自动 ReAct 产线工程能力就绪（编排器 + HITL 最小化 + 自动回退）。
- [x] `make verify-quwoquan-data` 全绿。
- [ ] 真实内容产出（稻城亚丁标杆 + fan-out）—— 待按产出范围运行。

→ 工程能力满足 Phase 2（云侧效果归因）gate-in；真实内容产出可按确认的范围分批运行。

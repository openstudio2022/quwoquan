# P6 耗时与无人托管可靠性

规划真相源：`/Users/zhaoyuxi/.cursor/plans/提示词重构与三类解耦放量_2f1c2e11.plan.md`（P6）。

## 目标（P6 判据）

- per-worker 预建 warm bridge / 错峰冷启后放行 concurrency=2-3。
- scaled-e2e run 状态机断点续跑 + 单 agent 调用硬超时看门狗 + 后台保活。
- 量化吞吐 vs connection-refused。

## 现状核对（先证明真相源）

唯一 fan-out runner：`agent_ops/runners/fanout_runner.py`（被 `qwq-data task scaled-e2e author-runner` 委托）。核对已有能力，避免重复造第二套：

| 能力 | 现状 | 本批动作 |
|---|---|---|
| 断点续跑（run 状态机） | 已由 `object_queue`（leaf 终态）+ `task_workflow_state.json`（stage 终态）+ `run_matrix.json`（per-ref 记录）承载；`scaled-e2e finalize/run` resume=True 续跑 | 复用，不另起第二套 checkpoint |
| leaf agent 硬超时看门狗 | `default_agent_runner` 已有线程+deadline+queue-terminal 轮询 | 复用 |
| local orchestrator 硬超时看门狗 | local 分支已有 `QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS` 看门狗 | 抽公共 helper |
| **cloud orchestrator 硬超时** | **缺**：cloud 分支裸 `Agent.prompt` 无超时 → 单分区挂起永久阻塞 worker | **本批补齐** |
| startup probe 冷启退避 | 已有（吸收 bridge 冷启 Connection refused 竞态） | 复用 |
| bridge launch 串行锁 + cooldown（managed local） | 已有 `_cursor_bridge_launch_guard` | 复用 |
| **per-worker 错峰冷启 + 预建 warm bridge** | **缺**：`run_fanout` 并行时 `pool.map` 同刻齐发所有 worker 冷启 → 抢端口 Connection refused 风暴 | **本批补齐** |
| **吞吐/connection-refused 量化** | **缺**：summary 只有 startupFailureRate/retryConvergence | **本批补齐** |

## 本批改动（单一真相源，零旁路）

文件：`agent_ops/runners/fanout_runner.py`

### P6a 错峰冷启 + per-worker warm bridge + 冷启并发上限 + 量化

- `COLD_START_MAX_WORKERS`（env `QWQ_FANOUT_COLD_START_MAX_WORKERS`，默认 3，对齐 concurrency=2-3）、`WORKER_STAGGER_SECONDS`（env `QWQ_FANOUT_WORKER_STAGGER_SECONDS`，默认 8s）。
- `_ColdStartReleaser`：用锁串行化"冷启放行"并保证相邻放行最小间隔（错峰，把齐发摊成鱼贯）；`sleep/clock` 可注入便于契约断言。
- `run_assignment(..., cold_start_gate=, prewarm_runner=)`：进 lease 循环前先错峰放行一次，再 per-worker 预建一次 warm bridge（`_prewarm_worker_bridge`，失败只记录不阻断，由 `_process_job` startup 退避兜底）。`WorkerStats` 新增 `prewarmed/prewarm_error/cold_start_wait_seconds`。
- `run_fanout(..., prewarm=False, worker_stagger_seconds=None, cold_start_max_workers=None)`：并行时把线程池并发收敛到 `min(max_workers, cold_start_cap)`（`maxWorkersEffective`），用同一 releaser 错峰；`prewarm=True` 时每 worker 暖机一次（warm-up 复用 `_startup_probe_packet`）。**默认 prewarm=False** 保持直接 API 调用方（测试）确定性；`main()` 对真实 CLI 运行默认 `prewarm=True`，`--no-prewarm` 可关。
- 量化：`summary.throughput`（elapsedSeconds / completedPerMinute / leasedPerMinute / maxWorkersRequested / maxWorkersEffective / coldStartCap / staggerSeconds / prewarmedWorkers / coldStartWaitSeconds / connectionRefused）+ `summary.connectionRefused`（扫 run 记录 error + 暖机 error + orchestration error 中冷启连接拒绝标记 `_is_connection_refused`）。report 与 `run_matrix.json` 同时落盘，便于"吞吐 vs connection-refused"对比审计。
- `main()` 新增 `--worker-stagger-seconds / --cold-start-max-workers / --no-prewarm`。

### P6b cloud orchestrator 硬超时看门狗

- 抽 `_orchestrate_agent_timeout_seconds()`（local/cloud 共用单一真相源；默认 300s、地板 60s，地板可经 `QWQ_ORCHESTRATE_AGENT_TIMEOUT_FLOOR_SECONDS` 下放仅供测试）。
- cloud 分支 `Agent.prompt` 包进独立线程 + `done.wait(timeout)`：超时按 `retryable` 返回，交给 `orchestrate_partition` 的 per-partition 重试 / object_queue backoff 接力，不再永久阻塞。local 分支改用同一 helper。

### 断点续跑与后台保活（复用既有，不造第二套）

- run 状态机断点续跑 = `object_queue` + `task_workflow_state.json` + `run_matrix.json`（已存在，每 leaf/stage 终态即落盘，跨窗口可累积），契约见 `test_scaled_e2e_run`。
- 后台保活 = `agent_ops/runners/cs100_author_resume_loop.sh`（已存在的 resume 循环；其"不得改 workflow_state"契约由 `test_cs100_author_resume_loop_does_not_mutate_workflow_state_json` 守护）。本批不新增第二套保活机制。

## 测试与门禁

新增 `quwoquan_data/tests/local_contract/task/test_unattended_reliability__local_contract_test.py`（8 用例）：

- `_ColdStartReleaser` 错峰间隔（注入时钟）/ 0 间隔不等。
- `_is_connection_refused` 分类。
- `run_assignment` 错峰+暖机各调用一次并记入 stats；暖机失败不崩溃只记录。
- `run_fanout` report/summary 量化 throughput + connectionRefused。
- `run_fanout` 并行并发收敛到 cold-start cap（maxWorkersEffective==cap）。
- cloud orchestrator 硬超时看门狗（挂起 30s，0.5s 看门狗触发 retryable 返回）。

回归：`test_fanout_runner`（26 用例，clean key env 全绿）、`test_scaled_e2e_run`（3 用例 pytest 全绿）。已接入 `verify_quwoquan_data.sh`（紧随 P5）。

> 环境说明：直接用本会话注入的真实 `CURSOR_API_KEY` 跑 `test_fanout_runner` 时，`test_missing_key_blocks_both_runtimes` 会因 `resolve_cursor_api_key()` 仍能从注入 key 文件取到 key 而 started=True（该用例假设"无 key"前置）——这是 P7 真实跑批所需 key 注入的环境产物，非 P6 代码回归；清 key env（`env -u CURSOR_API_KEY -u QWQ_CURSOR_API_KEY_FILE`）后 26 用例全绿。

## 作用域

仅改 `agent_ops/runners/**`、`quwoquan_data/tests/**`、`quwoquan_data/scripts/verify/**`、`artifacts/**`，未触碰 `quwoquan_app/**` 与他流 metadata/_shared 漂移。

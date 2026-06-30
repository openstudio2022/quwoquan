# P6 证据：受限并行（concurrency=2）可行性结论 — GATE_BLOCK（bridge 冷启争用 + 远端分支校验）

## 串行基线（可靠）

`task run --mode single --managed --agent-provider cursor_sdk --model composer-2.5`（concurrency=1，
warm startup probe，本地 cursor SDK）：5 篇文章 author→annotate→review **~440s 完成，未超时**
（~88s/篇含标注+评审）。串行无人托管路径稳定可靠。

## 受限并行（concurrency=2）尝试 — 双路径均阻断

冻结最小 fanout plan（`p6_parallel_20260630`，sourceTaskId 绑定四川批次，concurrency=2，by-leaf），
`task scaled-e2e author-runner --concurrency 2 --max-workers 2 --force-refs <2篇>` content-mode 复用
现有 writing_pack 并行重 author（无重下载）：

| 路径 | 结果 | 耗时 | 证据 |
|---|---|---|---|
| 保留 startup probe（默认 runtime） | **FAIL 快速** | ~142s | `author_runner.startup_probe` → `[validation_error] Failed to verify existence of branch 'codex/content-ui-directory-restructure' in repository openstudio2022/quwoquan`。fanout 并行探针校验**远端分支存在**（cloud dispatch 取向），但本工作分支为本地未推送分支 |
| `--skip-startup-probe`（默认 runtime） | **HANG 超时** | 560s 被杀 | 零输出、run_matrix 0 orchestrator——卡在 worker/bridge 启动前 |
| `--runtime local --skip-startup-probe` | **HANG 超时** | 300s 被杀 | 零输出——2 worker 并发 cursor bridge **冷启无 warm bridge 争用/死锁** |

## 间接并行能力证据（机制层已验）

- P0 N=20 **并发** startup 探针：`bridgeDisconnectRate=0`、`true5xxRate=0`、`authFailures=0`（连接级并发无争用）。
- `fanout_runner` 26 个契约测试通过：含 lease 并发、`test_startup_probe_recovers_after_transient_connection_refused`（connection-refused 恢复）、budget 强制、result-envelope 完成语义。
- 今日 N=3 探针复验：`bridgeDisconnectRate=0`、P95=19.8s。

## 结论（如实 GATE_BLOCK，不假装通过）

受限并行 **本任务环境下未达成端到端真实并行 author**，根因有二（均为环境/基础设施约束，非编排逻辑缺陷）：

1. **bridge 冷启并发争用**：本地 runtime 下 2 个 worker 同时冷启 cursor SDK bridge、无预热 warm bridge 时
   零进展挂起。串行（先 warm probe 再单 worker）则稳定。→ 修复方向：**per-worker 预建 warm bridge**
   或 worker 串行化 bridge 冷启（错峰），再放行并发 author。
2. **cloud dispatch 远端分支校验**：probe 路径要求工作分支存在于远端 `openstudio2022/quwoquan`；本地未推送
   分支被拦。→ 修复方向：cloud 并行前 **push 分支**，或 author-runner 在 `--runtime local` 下跳过远端分支校验。

## 最小续跑指令（待环境补齐后）

```bash
# 1) 预热 warm bridge（先单探针建立可复用 bridge）
qwq-data env cursor-probe --attempts 1 --model composer-2.5
# 2) local 并行（修复 per-worker warm bridge 后）：
QWQ_DATA_ROOT=~/qwq_scale_verify qwq-data task scaled-e2e author-runner \
  --plan p6_parallel_20260630 --concurrency 2 --max-workers 2 --runtime local \
  --model composer-2.5 --source-task 旅行/地域/四川省/景区/创作冒烟试跑 \
  --source-batch p5_sichuan_20260630 \
  --force-refs 都江堰__article_qunar_base_1,九寨沟__article_qunar_base_1 --no-orchestrate
# 或 cloud 并行：先 git push -u origin codex/content-ui-directory-restructure 再去掉 --skip-startup-probe
```

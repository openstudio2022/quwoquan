# 阶段证据 B：P0 N=20 探针重测（载体修复窗口）

## 命令（正确运行时）
```
PATH=$HOME/.local/bin:$PATH  CURSOR_API_KEY=<from QWQ_CURSOR_API_KEY_FILE>
./quwoquan_data/.venv/bin/python quwoquan_data/scripts/cli.py env cursor-probe \
  --model composer-2.5 --runtime local --attempts 20 --startup-timeout-seconds 180 \
  --report-out artifacts/p0_probe_rerun_carrier.json
```

## 结果（全绿，准入 E2E）
```
[env cursor-probe] attempts=20 success=20 authFailures=0 true5xxRate=0.0
  startupTimeoutRate=0.0 coldStart5xxObserved=0 bridgeDisconnectRate=0.0
  startupLatencyP95=41.2439
[env cursor-probe] READY
```
- ready=20/20，auth=0，true5xx=0，timeout=0，bridgeDisconnect=0，other=0
- ready latency min/max = 19.7/55.8s，p95=41.2s
- `issues: []`，`true5xxRate=0.0 < 10%` → **满足 E2E 准入**

token（`crsr_acbc...`，经 `QWQ_CURSOR_API_KEY_FILE` 单一真相源解析）有效，网络健康。

## 运行时 finding（重要，避免误报）
首次用 **system python3** 跑探针得到 20 次 0.03s 瞬时 `primaryClass=other` 失败——
**非 token/网络/5xx 问题**，而是 system python3 缺 `cursor_sdk`。正确运行时是
`quwoquan_data/.venv/bin/python`（含 cursor_sdk）+ `~/.local/bin` 在 PATH（含 `cursor-agent`）。
切换到 venv python 后 20/20 ready。该 finding 已固化进证据，后续 agent 驱动阶段
统一使用 venv python + 补 PATH。

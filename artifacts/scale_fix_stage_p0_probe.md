# 阶段证据：P0 Cursor 启动探针分类修正（timeout 不计 5xx）

归属：AppRoot `content-discovery-to-consumption` → L1 Data content supply → L2 recommendation-ready supply → L3 无人托管创作放量准入（P0 准入门）。

## 问题（断点前已定位）

`artifacts/cursor_probe_20260629_n20.json` 报告 `true5xxRate=1.0`、`successCount=0`，但 20 行终态全是 45s `TimeoutExpired`（`httpStatus:null`）。根因：

- `cursor_startup_probe` 外层重试循环遇 `transient_server_error(5xx)` 会重试，前若干冷启动子尝试看到 5xx 并入 `attempts`；最后一次外层 `subprocess.run` 在 45s 预算耗尽超时返回。
- 返回 payload 顶层 status=`timeout`，但 `attempts` 携带冷启动 5xx 子行，`_cursor_probe_attempt_has_5xx` 据此把整次记为 `true5xx`。
- 本质是 **45s 总预算太短**：冷启动 + warm bridge 复用还没稳定就被切断；冷启动 5xx 是过渡态，不是后端稳定 5xx 结论。

## 修复（不放宽硬门，只纠正过度归因）

文件：`quwoquan_data/scripts/_common/python_runtime.py`、`quwoquan_data/scripts/env/handler.py`

1. 新增 `_cursor_probe_is_startup_timeout(payload)`：终态 status/errorClass/errorCode 为 timeout 即判定。
2. `cursor_startup_probe_suite` 改为**单一 primary 互斥归类**，优先级 `ready > auth > startupTimeout > true5xx > bridgeDisconnect > other`；**终态 timeout 归 `startupTimeout`，永不计 `true5xx`**。
3. 报告新增 `startupTimeoutCount/Rate`、`coldStart5xxObservedCount`（冷启动 5xx 仍如实记录在诊断字段，不参与 true5xx 归因）；schemaVersion 升 `/2`。
4. 放量门维持 `auth==0 且 true5xxRate<10% 且 success>0`；timeout 率高单列 issue 提示拉长超时/warm 复用，不误报成后端 5xx。
5. 单次冷启动超时默认 `45s → 180s`（cursor-probe），preflight/ready 单次探针 `→120s`；bridge 启动超时默认 `30s→60s`。

## 三层测试证据（local_contract，全部通过）

```
.venv/bin/python -m pytest \
  tests/local_contract/env/test_cursor_probe__local_contract_test.py \
  tests/local_contract/task/test_cursor_credentials__local_contract_test.py \
  tests/local_contract/task/test_scaled_e2e_run__local_contract_test.py -q
# 12 passed
```

新增红线用例 `test_cursor_startup_timeout_is_not_counted_as_true_5xx`：终态 timeout（即便冷启动子尝试见 500/503）→ `startupTimeoutCount==2`、`true5xxCount==0`、`coldStart5xxObservedCount==1`、每行 `primaryClass=='startupTimeout'`、issues 不含 "true 5xx rate"。

## 仍待办（后续阶段）

- 真实 N=20 探针重测需 fresh key + 可达 Cursor 后端；上次 preflight 因基础设施 PING 超时断连，真实重测留待 `verify-p0-real-probe`。
- 三测试接入 `verify_quwoquan_data.sh` 留待 `fix-gate-wiring`。

# Phase B 收口:P0 N=20 探针重测通过(可进 E2E)

命令:`env cursor-probe --model composer-2.5 --attempts 20 --startup-timeout-seconds 180`
(key 经 QWQ_CURSOR_API_KEY_FILE 单一真相源导出 CURSOR_API_KEY,不回显)

报告:artifacts/p0_probe_n20.json(schemaVersion .../2)

| 指标 | 值 | 判定 |
|---|---|---|
| attempts | 20 | |
| successCount(ready) | 18 | |
| authFailures | 0 | ✓ key 鉴权正常 |
| true5xxCount / true5xxRate | 0 / 0.0% | ✓ < 10% 阈值,准入 E2E |
| startupTimeoutCount | 0 | ✓ |
| bridgeDisconnectCount | 2 (10%) | 瞬态 bridge 抖动,非 auth/5xx |
| ready | True / issues=[] | ✓ |
| startupLatencyP95 | ~84.8s | warm 复用下冷启动路径偏慢 |

结论:真5xx=0% 远低于 10% 硬门,authFailures=0,准入 P5 scaled-e2e。
2/20 bridgeDisconnect 为瞬态连接抖动(已被 primary 归类为非 5xx),E2E 单次 agent 调用需 bound+续跑兜底。

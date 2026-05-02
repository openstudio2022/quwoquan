# 端云异常观测发布策略

## Alpha

- 启动本机 ES：`make observability-es-up && make observability-es-bootstrap`。
- Product Ops 设置 `PRODUCT_OPS_ES_URL=http://localhost:9200`。
- App 使用 `APP_RUNTIME_ENV=alpha`，允许 mock/remote 双路径验证。
- 验证：`make observability-es-smoke`，并用 `daily-report --env alpha --output json` 生成机器可读日报。

## Beta

- App 使用 `APP_RUNTIME_ENV=beta` 和 beta gateway，禁止读取 Dart mock 数据。
- Product Ops 继续主写 MongoDB，ES mirror 只做异步分析索引；ES 失败不得影响 `/v1/ops/events` 成功响应。
- Cursor Skill 只允许生成分析报告和可复现问题修复 PR，不自动合并。

## Gamma

- 开启日报、聚合和告警阈值验证。
- 不开启自动修复写 PR；所有 fingerprint 只进入人工评审列表。
- 重点校验脱敏策略、采样策略和 `nature/recovery.action` 分流是否符合预期。

## Prod

- 仅允许评审过的字段进入 ES：`traceId/requestId/sessionId/pageVisitId`、页面/operation、runtime failure、业务对象和脱敏后的环境字段。
- 自动修复只能开 PR，不能自动合并、不能绕过 hooks、不能 force push。
- 无可复现证据的问题只进入日报，不改代码。

## 必要命令

```bash
make observability-es-up
make observability-es-bootstrap
make observability-es-smoke
python3 scripts/observability/es_cli.py daily-report --env alpha --output markdown
python3 scripts/observability/es_cli.py daily-report --env beta --output json
```

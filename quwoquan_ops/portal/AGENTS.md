# ops-portal Guide

在 `quwoquan_ops/portal/` 工作时先读 `quwoquan_ops/portal/package.json`。

## 硬约束

- Ops runtime errors 必须使用 `RuntimeError` / `RuntimeErrorResponse` / `RuntimeFailure` / `RuntimeRecoveryPolicy`，不要自造错误模型。
- NodeNext/ESM imports 必须包含显式 `.js` 或 `/index.js`。
- 控制面 generated 文件以 codegen 为真相源，禁止手改 `src/generated/**`。
- 观测、配置、rollout、gate、dependency、runbook 页面展示结构化状态、错误码、恢复建议和证据来源，不只展示 raw 字符串。
- 服务/环境状态必须追溯到 runtime error、stackctl、metrics 或 generated control-plane 真相源；Portal 只展示和操作控制面，不复制服务端配置、错误码或环境拓扑为第二真相源。
- 新增页面或 API client 改动必须补测试，并在 `quwoquan_ops/portal/` 内跑通 `npm test` 与 `npm run build`；触及 runtime error 结构时同步运行 `dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`。

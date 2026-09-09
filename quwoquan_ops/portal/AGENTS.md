# ops-portal Agent Guide

继承根与 `quwoquan_ops/AGENTS.md`，另读本目录 `package.json`。

## Portal 不变量

- runtime errors 只用 `RuntimeError` / `RuntimeErrorResponse` / `RuntimeFailure` / `RuntimeRecoveryPolicy`。
- NodeNext/ESM imports 必须带显式 `.js` 或 `/index.js`。
- `src/generated/**` 只由 codegen 生成，禁止手改。
- 观测、配置、rollout、gate、dependency、runbook 页面展示结构化状态、错误码、恢复建议与证据来源，不能只展示 raw 字符串。
- 服务/环境状态必须追溯到 runtime error、stackctl、metrics 或 generated control-plane 真相源；Portal 只展示和操作，不复制服务端配置、错误码或环境拓扑。

## 验证

新增页面或 API client 改动须补测试，并在本目录运行 `npm test` 和 `npm run build`。触及 runtime error 结构时另运行 `dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`（从仓库根）。

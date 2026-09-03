# ops-portal Codex Guide

在 `quwoquan_ops/portal/` 工作时，除仓库根 `AGENTS.md` 外，先阅读：

1. `specs/feature-tree/README.md` 与目标特性父链
2. `quwoquan_ops/portal/package.json`

## Ops Portal 硬约束

- Ops runtime errors 必须使用 `RuntimeError` / `RuntimeErrorResponse` / `RuntimeFailure` / `RuntimeRecoveryPolicy`，不要自造错误模型。
- NodeNext/ESM imports 必须包含显式 `.js` 或 `/index.js`，与 runtime error cutover 规则保持一致。
- 控制面 generated 文件以 codegen 为真相源，禁止手改 `src/generated/**`。
- 观测、配置、rollout、gate、dependency、runbook 页面要展示结构化状态、错误码、恢复建议和证据来源，不能只展示 raw 字符串。
- 新增页面或 API client 改动必须补测试，并确保在 `quwoquan_ops/portal/` 内执行 `npm test` 与 `npm run build` 通过。

## Portal 领域 E2E

- 若页面展示服务/环境状态，必须追溯到 runtime error、stackctl、metrics 或 generated control-plane 真相源。
- Portal 只负责展示和操作控制面，不得复制服务端配置、错误码或环境拓扑为第二真相源。

## 验证

- `cd quwoquan_ops/portal && npm test`
- `cd quwoquan_ops/portal && npm run build`
- 触及 runtime error 结构时同步运行：`dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`

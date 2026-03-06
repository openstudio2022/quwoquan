# 开发任务：log-schema-and-kv-policy

## 规划任务（文档基线）

- [x] 更新 `docs/personal-assistant/agent-observability-log-design.md`（统一信封 + 两层来源 + 端云Python拉通）
- [x] 更新 `docs/personal-assistant/run-diagnosis-template.md`（跨栈诊断模板）
- [x] 新增 `docs/personal-assistant/log-field-mapping-table.md`（字段映射表）
- [x] 更新 `docs/personal-assistant/tdd-observability-autofix-loop.md`（门禁对齐）

## 实施任务（apply）

- [x] 端侧日志模型：`AppLogEnvelope` 增加 canonical 字段与 legacy 兼容字段
- [x] 端侧日志上下文：`AppLogContext` 增加 source/correlation/span 相关字段
- [x] 默认组件映射：`AppLogService` 按 `AppLogType` 自动补全 `component/target`
- [x] LLM/搜索关键埋点：补齐 `sourceDomain/sourceService/component/target/action/correlationId`
- [ ] 端侧其余埋点补齐（cloudApi/pageAccess/error 路径）
- [ ] 云侧日志字段映射落地（`sourceDomain/sourceService/component/target`）
- [ ] Python worker 字段映射落地（`correlationId/traceId/spanId`）

## 测试与门禁

- [ ] 新增/更新契约测试：`cross_stack_log_contract_test.dart`
- [ ] 回归桶 A/B/C（PA Core）
- [ ] `make gate` 通过

# Personal Assistant Docs

本目录汇总小趣个人私人助手的历史设计与目标方案，作为 `docs` 下的统一查阅入口。

## 文档结构

- `world-class-personal-assistant-design.md`
  - 小趣私人助手完整设计总览（端云架构、协议、Skill/Plugin 扩展、多 Agent 编排、质量门禁）
  - 历史设计文档时间线与关键结论
  - 当前差距与实施路线（X1/X2 为主，X3/X4 预留）
- `personal-assistant-fullstack-standard.md`
  - 个人助理全栈开发标准（Plan/Create/Implement/Verify/Submit）
  - 新版设计交付件规范（组件/包图、用例图、流程图）
  - 协议与质量门禁的统一口径
- `tdd-observability-autofix-loop.md`
  - TDD + 可观测闭环（提前发现问题）
  - 编程助手“编码后自动跑用例→定位→修复”执行手册
- `agent-observability-log-design.md`
  - Agent 全链路可观测日志设计（S0~S11 阶段模型）
  - Debug/Release 日志策略、failureCode 字典、UI 联动日志规范
- `run-diagnosis-template.md`
  - 单次 Run 诊断模板（跨 agent/llm/search/ui 对齐）
  - 根因归类、影响评估、回归验证与结论输出模板
- `log-field-mapping-table.md`
  - 端侧/云侧/Python 三侧日志字段映射表（Canonical）
  - `AppLogType` 到统一 `logType/level/component/target` 映射
  - 关联键（correlationId/traceId/requestId）与跨栈查询模板
- `assistant-rebuild-roadmap-v1.md`
  - 小趣助手“脱胎换骨”重构的 5 个串行里程碑路标
  - 每个里程碑的目标、边界、交付与验收标准
- `assistant-rebuild-design-context-v1.md`
  - 当前系统诊断、目标架构、关键约束与上下文恢复清单
  - 从现有代码热点到目标模块的迁移映射
- `assistant-rebuild-session-prompts-v1.md`
  - 5 个新会话专用启动提示词
  - 每个里程碑的 strict scope、验证要求与结束回写要求

## 已纳入的历史文档范围（已查阅并汇总）

- 产品与总方案
  - `specs/product/assistant-strategy-and-upgrade-analysis.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/design.md`
  - `specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tasks.md`
- 运行与协议
  - `specs/feature-tree/assistant-run-learning/spec.md`
  - `specs/feature-tree/assistant-run-learning/README.md`
  - `specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/assistant-run-io-contract/spec.md`
  - `specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/assistant-run-io-contract/design.md`
  - `specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/assistant-run-io-contract/tasks.md`
- OpenSpec 历史演进
  - `openspec/specs/personal-assistant/spec.md`
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/proposal.md`
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/design.md`
  - `openspec/changes/archive/2026-02-14-assistant-baseline-spec/tasks.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/proposal.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/design.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-ai-native-v1/tasks.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-commercial-v1/design.md`
  - `openspec/changes/archive/2026-02-17-personal-assistant-commercial-v1/tasks.md`
- 运行时与渠道集成
  - `quwoquan_app/personal_assistant/docs/assistent_v1_commercial_spec.md`
  - `quwoquan_app/personal_assistant/docs/openclaw_capability_migration_audit.md`
  - `quwoquan_app/personal_assistant/docs/openclaw_feishu_integration.md`
  - `specs/feature-tree/runtime/runtime-assistant/spec.md`
  - `specs/feature-tree/runtime/runtime-assistant/design.md`
  - `specs/feature-tree/runtime/runtime-assistant/tasks.md`

## 使用建议

- 架构评审先读：`personal-assistant-fullstack-standard.md`
- 背景与演进参考：`world-class-personal-assistant-design.md`
- 本轮“脱胎换骨”重构先读：
  - `assistant-rebuild-roadmap-v1.md`
  - `assistant-rebuild-design-context-v1.md`
  - `assistant-rebuild-session-prompts-v1.md`
- 落地开发时，按“历史基线 -> 当前差距 -> 目标协议 -> 任务分解”顺序执行
- 新增设计文档请优先追加到本目录，并在此文件更新索引

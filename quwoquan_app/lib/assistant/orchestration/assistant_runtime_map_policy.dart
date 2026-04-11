/// 助手编排层 Map 主路径整改锚点（对照 `assistant-internal-map-boundary.md`）。
///
/// 优先序：1) `lib/ui/assistant/**` 持 transcript/codegen；2) 本目录状态机字段迁入契约生成体；
/// 3) `tool/impl` / `llm` 保留 JSON 边界 Map。
///
/// 热点：`local_phase_execution_owner.dart`、`react_runtime.dart`、`llm_provider.dart`。
library;

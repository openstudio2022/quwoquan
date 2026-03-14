// ignore_for_file: unused_element

/// 助理 engine 层字符串治理约束。
///
/// 唯一真相源见 [canonical_truth_sources.md](../../personal_assistant/docs/canonical_truth_sources.md)。
///
/// **约束**：
/// - 禁止在 engine/react/skill/tool 中新增用户可见中文文案和语义词表。
/// - 允许的协议字符串只能来自 enum/schema 映射层。
/// - 语义分类、路由、文案必须由 planner 输出、asset、tool metadata 提供。
/// - 助理协议 metadata 真相源统一位于 `quwoquan_service/contracts/metadata/assistant/`。
/// - `lib/personal_assistant/runtime/generated/` 仅允许 codegen 写入，禁止手写。
/// - `assistant_turn` 是唯一允许的助理输出契约版本，禁止新增任何旧版本读取兼容。
/// - 当前实施阶段仅生成端侧 Dart 协议产物并只做端侧校验，但 schema 设计必须保持端云一体化。
library;

/// 占位常量，供未来迁出文案时引用。
/// 实际用户文案应以 tool_catalog.meta.json、prompt asset 为准。
const String kRuntimeStringGovernancePlaceholder = '';

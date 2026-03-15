import 'package:quwoquan_app/assistant/internal_legacy/runtime/display_text_classifier.dart';

/// 集中管理 assistant 内容过滤逻辑的唯一真相。
///
/// **设计目标**：
/// - 消灭散落在 agent_loop / capability_gateway / session_manager 三处的重复词表。
/// - 所有过滤函数优先使用结构化协议字段（decision.nextAction / degraded / failureCode），
///   文案关键词匹配只作最后一道兜底，应对极少数模型不守约场景。
/// - 词表维护在同一处，避免跨文件不一致漂移。
abstract final class AssistantContentFilters {
  static final DisplayTextClassifier _classifier = DisplayTextClassifier.instance;

  // ---------------------------------------------------------------------------
  // 公开 API
  // ---------------------------------------------------------------------------

  static Future<void> ensureLoaded() => _classifier.ensureLoaded();

  /// 判断文本是否是降级/错误输出（纯文本兜底，优先使用 [ReactRuntimeResult.degraded]）。
  static bool isDegradedText(String text) => _classifier.isDegradedText(text);

  /// 判断文本是否是进度占位（纯文本兜底，优先使用 `decision.nextAction != 'answer'`）。
  ///
  /// 具有 Markdown 结构（含标题/列表/引用/加粗）的文本不视为进度占位。
  static bool isProgressPlaceholder(String text) =>
      _classifier.isProgressPlaceholder(text);

  /// 判断文本是否是 JSON 信封原文（不应展示给用户）。
  static bool isJsonEnvelope(String text) => _classifier.isJsonEnvelopeLike(text);

  /// 综合判断：文本是否不可展示给用户（降级 | 进度占位 | JSON 信封）。
  ///
  /// 用途：session 历史过滤、chunk 流式过滤。
  /// UI 最终展示由 `_resolveAssistantDisplayText` 的 `response.degraded` 早退机制
  /// 独立守护，不经过此函数。
  static bool isNotDisplayable(String text) {
    final t = text.trim();
    if (t.isEmpty) return true;
    return isDegradedText(t) || isProgressPlaceholder(t) || isJsonEnvelope(t);
  }

  /// 判断文本是否应跳过写入 session/memory（降级文本不应污染历史）。
  static bool shouldSkipSessionWrite(String text) => isDegradedText(text);

}

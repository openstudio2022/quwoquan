import 'package:quwoquan_app/assistant/protocol/display_text_classifier.dart';

/// 集中管理 assistant 内容过滤逻辑的唯一真相。
///
/// **设计目标**：
/// - 展示与历史写入不再通过自然语言词表判断业务状态。
/// - 仅保留结构化 envelope 识别，业务分流必须使用 typed state / wire 字段。
abstract final class AssistantContentFilters {
  static final DisplayTextClassifier _classifier =
      DisplayTextClassifier.instance;

  static Future<void> ensureLoaded() => _classifier.ensureLoaded();

  /// 旧自然语言降级判断已禁用；调用方应读取 typed runtime state。
  static bool isDegradedText(String text) => false;

  /// 旧自然语言进度判断已禁用；调用方应读取 typed interaction directive。
  static bool isProgressPlaceholder(String text) =>
      _classifier.isProgressPlaceholder(text);

  /// 判断文本是否是 JSON 信封原文（不应展示给用户）。
  static bool isJsonEnvelope(String text) =>
      _classifier.isJsonEnvelopeLike(text);

  /// 综合判断：文本是否不可展示给用户（降级 | 进度占位 | JSON 信封）。
  static bool isNotDisplayable(String text) {
    final t = text.trim();
    if (t.isEmpty) return true;
    return isJsonEnvelope(t);
  }

  /// 旧自然语言 session 过滤已禁用；是否写入历史由结构化状态决定。
  static bool shouldSkipSessionWrite(String text) => false;
}

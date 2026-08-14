// ASSISTANT_WEAK_TYPE: JSON_BOUNDARY — `card:` fenced JSON 在此一次性解码，
// presentation 层只消费 typed 字段。

import 'dart:convert';
import 'dart:developer' as developer;

/// Markdown 结构化卡片（compare / trend / diagram）payload 的 typed 投影。
class AssistantStructuredCardPayload {
  const AssistantStructuredCardPayload._({
    required this.title,
    required this.mermaid,
    required this.entries,
  });

  final String title;
  final String mermaid;

  /// 除 `title` / `mermaid` 外的开放键值对，保持 payload 原有顺序。
  final List<AssistantStructuredCardEntry> entries;

  /// 解码失败、非对象或空对象一律返回 null，由调用方隐藏该卡片。
  static AssistantStructuredCardPayload? tryParse(String payload) {
    final Object? decoded;
    try {
      decoded = jsonDecode(payload);
    } catch (error, stackTrace) {
      developer.log(
        'assistant structured card payload could not be decoded',
        name: 'assistant.answer_content',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
    if (decoded is! Map || decoded.isEmpty) return null;
    var title = '';
    var mermaid = '';
    final entries = <AssistantStructuredCardEntry>[];
    for (final entry in decoded.entries) {
      final key = entry.key;
      if (key is! String) continue;
      final value = entry.value;
      if (key == 'title') {
        title = value is String ? value.trim() : '';
        continue;
      }
      if (key == 'mermaid') {
        mermaid = value is String ? value.trim() : '';
        continue;
      }
      entries.add(
        AssistantStructuredCardEntry._(key: key, valueText: _valueText(value)),
      );
    }
    return AssistantStructuredCardPayload._(
      title: title,
      mermaid: mermaid,
      entries: List.unmodifiable(entries),
    );
  }

  static String _valueText(Object? value) {
    if (value == null) return '';
    if (value is num || value is bool || value is String) {
      return value.toString();
    }
    return jsonEncode(value);
  }
}

class AssistantStructuredCardEntry {
  const AssistantStructuredCardEntry._({
    required this.key,
    required this.valueText,
  });

  final String key;
  final String valueText;
}

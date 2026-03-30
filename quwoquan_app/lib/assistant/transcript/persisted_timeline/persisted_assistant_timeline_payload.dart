import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';

/// C4 持久化块允许的顶层键（与 [buildPersistedAssistantTurnFields] 及 controller spread 对齐）。
const Set<String> kPersistedAssistantTimelinePayloadKeys = {
  assistantTurnSchemaVersionField,
  assistantJourneyField,
  assistantUiProcessTimelineField,
  assistantProcessTimelineField,
  assistantUnderstandingSnapshotField,
  assistantAnswerProcessingField,
  assistantHistoricalThinkingSnapshotField,
  assistantRetrievalProcessingField,
  assistantProviderReasoningContinuationField,
  assistantDisplayStateField,
  assistantDisplayMarkdownField,
  assistantDisplayPlainTextField,
  assistantFollowupPromptField,
  assistantActionHintsField,
  'assistantElapsedMs',
};

dynamic _deepCloneJson(dynamic value) {
  if (value is Map) {
    return value.map(
      (k, v) => MapEntry(k.toString(), _deepCloneJson(v)),
    );
  }
  if (value is List) {
    return value.map(_deepCloneJson).toList(growable: false);
  }
  return value;
}

/// C4：时间轴上的 assistant_turn 持久化子图（不含 sender / runId 等信封键）。
class PersistedAssistantTimelinePayload {
  PersistedAssistantTimelinePayload._(this._entries);

  final Map<String, dynamic> _entries;

  factory PersistedAssistantTimelinePayload.fromMap(Map<String, dynamic> m) {
    final out = <String, dynamic>{};
    for (final key in kPersistedAssistantTimelinePayloadKeys) {
      if (!m.containsKey(key)) continue;
      out[key] = _deepCloneJson(m[key]);
    }
    return PersistedAssistantTimelinePayload._(out);
  }

  /// 空持久化块（流式占位等）。
  factory PersistedAssistantTimelinePayload.empty() {
    return PersistedAssistantTimelinePayload._(const <String, dynamic>{});
  }

  Map<String, dynamic> toMap() =>
      _entries.map((k, v) => MapEntry(k, _deepCloneJson(v)));

  String get assistantTurnSchemaVersion =>
      (_entries[assistantTurnSchemaVersionField] as String?)?.trim() ?? '';

  Map<String, dynamic> get journey =>
      (_entries[assistantJourneyField] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  int get assistantElapsedMs =>
      (_entries['assistantElapsedMs'] as num?)?.toInt() ?? 0;

  String get displayMarkdown =>
      (_entries[assistantDisplayMarkdownField] as String?)?.trim() ?? '';

  String get displayPlainText =>
      (_entries[assistantDisplayPlainTextField] as String?)?.trim() ?? '';

  PersistedAssistantTimelinePayload copyWithMerged(Map<String, dynamic> patch) {
    final next = Map<String, dynamic>.from(_entries);
    for (final e in patch.entries) {
      if (e.value == null) {
        next.remove(e.key);
      } else {
        next[e.key] = _deepCloneJson(e.value);
      }
    }
    return PersistedAssistantTimelinePayload._(next);
  }
}

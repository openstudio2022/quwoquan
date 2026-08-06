import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart'
    show assistantDisplayStateField;
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_assistant_turn_contract.dart';

/// C4 持久化块允许的顶层键（与 [buildPersistedAssistantTurnFields] 及 controller spread 对齐）。
const Set<String> kPersistedAssistantTimelinePayloadKeys = {
  assistantJourneyField,
  assistantProcessTimelineField,
  assistantUnderstandingSnapshotField,
  assistantAnswerProcessingField,
  assistantHistoricalThinkingSnapshotField,
  assistantRetrievalProcessingField,
  assistantProviderReasoningContinuationField,
  assistantSystemContextEnvelopeField,
  assistantUnderstandingResultField,
  assistantTaskGraphField,
  assistantOrchestratorStateField,
  assistantTurnSynthesisStateField,
  assistantDisplayStateField,
  assistantDisplayMarkdownField,
  assistantDisplayPlainTextField,
  assistantFollowupPromptField,
  assistantActionHintsField,
  assistantBoundaryOutcomeField,
  'assistantElapsedMs',
};

dynamic _deepCloneJson(dynamic value) {
  if (value is Map) {
    return value.map((k, v) => MapEntry(k.toString(), _deepCloneJson(v)));
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

  Map<String, dynamic> get journey =>
      (_entries[assistantJourneyField] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  int get assistantElapsedMs =>
      (_entries['assistantElapsedMs'] as num?)?.toInt() ?? 0;

  String get displayMarkdown =>
      (_entries[assistantDisplayMarkdownField] as String?)?.trim() ?? '';

  String get displayPlainText =>
      (_entries[assistantDisplayPlainTextField] as String?)?.trim() ?? '';

  Map<String, dynamic> get assistantBoundaryOutcome =>
      (_entries[assistantBoundaryOutcomeField] as Map?)
          ?.cast<String, dynamic>() ??
      const <String, dynamic>{};

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

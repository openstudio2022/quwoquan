import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/transcript/replay/assistant_replay_record.dart';

/// 从运行响应构造 C6 回放记录（对齐 controller `_storeAssistantReplayRecord`）。
class AssistantReplayRecordFactory {
  AssistantReplayRecordFactory._();

  static AssistantReplayRecord build({
    required String messageId,
    required String query,
    required AssistantRunResponse response,
    required Map<String, dynamic> replayPayload,
    required Map<String, dynamic> runArtifactsMap,
    required String answerText,
    required String displayPlainText,
    List<Map<String, dynamic>> uiReferences = const <Map<String, dynamic>>[],
    Map<String, dynamic> uiUsageStats = const <String, dynamic>{},
  }) {
    final structured = response.structuredResponse.isEmpty
        ? const <String, dynamic>{}
        : response.structuredResponse;
    final refs = uiReferences.isNotEmpty
        ? uiReferences
        : ((structured['uiReferences'] as List?)
                ?.whereType<Map>()
                .map((e) => e.cast<String, dynamic>())
                .toList(growable: false) ??
            const <Map<String, dynamic>>[]);
    final stats = uiUsageStats.isNotEmpty
        ? uiUsageStats
        : ((structured['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{});
    return AssistantReplayRecord(
      messageId: messageId,
      runId: response.runId ?? '',
      traceId: response.traceId ?? '',
      query: query,
      answer: answerText,
      displayPlainText: displayPlainText,
      runArtifacts: runArtifactsMap,
      createdAt: DateTime.now().toIso8601String(),
      uiReferences: refs,
      uiUsageStats: stats,
      queryPlan: (replayPayload['queryPlan'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      policyDecision:
          (replayPayload['policyDecision'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      roundTraces: (replayPayload['roundTraces'] as List?)
              ?.whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      webSearchDiagnostics:
          (replayPayload['webSearchDiagnostics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
    );
  }
}

import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/transcript/replay/assistant_replay_record.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';

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
    final queryPlan =
        (replayPayload['queryPlan'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          'queryTasks':
              (structured['queryTasks'] as List?) ?? const <dynamic>[],
          'intentGraph':
              (structured['intentGraph'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
        };
    final policyDecision =
        (replayPayload['policyDecision'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          assistantRetrievalOutcomeField: response.retrievalOutcome.toJson(),
          assistantAnswerGateDecisionField: response.answerGateDecision
              .toJson(),
          'answerDecision':
              response.runArtifacts?.answerDecision.toWireMap() ??
              const <String, dynamic>{},
        };
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
      queryPlan: queryPlan,
      policyDecision: policyDecision,
      roundTraces:
          (replayPayload['roundTraces'] as List?)
              ?.whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      webSearchDiagnostics:
          (replayPayload['webSearchDiagnostics'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }
}

Map<String, dynamic> buildAssistantReplayPayloadFromTraces(
  List<AssistantTraceEvent> traces,
) {
  Map<String, dynamic> webSearchDiagnostics = const <String, dynamic>{};
  for (var i = traces.length - 1; i >= 0; i--) {
    final trace = traces[i];
    if (trace.type != AssistantTraceEventType.toolResult &&
        trace.type != AssistantTraceEventType.toolError) {
      continue;
    }
    final data = trace.data ?? const <String, dynamic>{};
    final diagnostics =
        (data['diagnostics'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (diagnostics.isNotEmpty) {
      webSearchDiagnostics = diagnostics;
      break;
    }
  }
  for (var i = traces.length - 1; i >= 0; i--) {
    final trace = traces[i];
    if (trace.type != AssistantTraceEventType.toolResult) continue;
    final data = trace.data ?? const <String, dynamic>{};
    final queryPlan = (data['queryPlan'] as Map?)?.cast<String, dynamic>();
    final policyDecision = (data['policyDecision'] as Map?)
        ?.cast<String, dynamic>();
    final roundTraces = (data['roundTraces'] as List?)
        ?.whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
    if (queryPlan != null || policyDecision != null || roundTraces != null) {
      return <String, dynamic>{
        'queryPlan': queryPlan ?? const <String, dynamic>{},
        'policyDecision': policyDecision ?? const <String, dynamic>{},
        'roundTraces': roundTraces ?? const <Map<String, dynamic>>[],
        'webSearchDiagnostics': webSearchDiagnostics,
      };
    }
  }
  return <String, dynamic>{
    'queryPlan': const <String, dynamic>{},
    'policyDecision': const <String, dynamic>{},
    'roundTraces': const <Map<String, dynamic>>[],
    'webSearchDiagnostics': webSearchDiagnostics,
  };
}

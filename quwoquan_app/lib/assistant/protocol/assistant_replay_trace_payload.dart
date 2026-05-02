import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// 从 trace 列表提取 C6 回放用 payload（与 [AssistantConversationController] 记录逻辑一致）。
class AssistantReplayTracePayload {
  const AssistantReplayTracePayload({
    required this.queryPlan,
    required this.policyDecision,
    required this.roundTraces,
    required this.webSearchDiagnostics,
  });

  final Map<String, dynamic> queryPlan;
  final Map<String, dynamic> policyDecision;
  final List<Map<String, dynamic>> roundTraces;
  final Map<String, dynamic> webSearchDiagnostics;

  Map<String, dynamic> toPayloadMap() => <String, dynamic>{
    'queryPlan': queryPlan,
    'policyDecision': policyDecision,
    'roundTraces': roundTraces,
    'webSearchDiagnostics': webSearchDiagnostics,
  };

  static AssistantReplayTracePayload fromTraces(
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
        return AssistantReplayTracePayload(
          queryPlan: queryPlan ?? const <String, dynamic>{},
          policyDecision: policyDecision ?? const <String, dynamic>{},
          roundTraces: roundTraces ?? const <Map<String, dynamic>>[],
          webSearchDiagnostics: webSearchDiagnostics,
        );
      }
    }
    return AssistantReplayTracePayload(
      queryPlan: const <String, dynamic>{},
      policyDecision: const <String, dynamic>{},
      roundTraces: const <Map<String, dynamic>>[],
      webSearchDiagnostics: webSearchDiagnostics,
    );
  }
}

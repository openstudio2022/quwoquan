import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_diagnostics_helper.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_usage_stats.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

Map<String, dynamic> buildStructuredResponseDomainResults({
  required List<AssistantToolResultRow> toolResults,
  required List<Map<String, dynamic>> toolErrors,
}) {
  return <String, dynamic>{
    'toolResults': toolResults
        .map((item) => item.toJson())
        .toList(growable: false),
    'toolErrors': toolErrors,
  };
}

Map<String, dynamic> buildStructuredResponseRetrievalFeedback({
  required List<AssistantToolResultRow> toolResults,
  required int toolErrorCount,
}) {
  return <String, dynamic>{
    'hasToolResult': toolResults.isNotEmpty,
    'toolResultCount': toolResults.length,
    'toolErrorCount': toolErrorCount,
    'qualityScore': () {
      for (final r in toolResults.reversed) {
        final data = r.dataPayload;
        final qs = (data['qualityScore'] as num?)?.toDouble();
        if (qs != null) return qs;
      }
      return 0.0;
    }(),
    'roundTraces': toolResults
        .where(
          (r) =>
              AssistantToolNames.isRetrievalName(r.toolName) ||
              r.dataPayload['stepId'] != null,
        )
        .map((r) {
          final data = r.dataPayload;
          return <String, dynamic>{
            'stepId': (data['stepId'] ?? r.toolCallId).toString(),
            'tool': data['tool']?.toString() ?? r.toolName,
            'success': data['success'] == true,
            'qualityScore': (data['qualityScore'] as num?)?.toDouble() ?? 0.0,
            'authorityScore':
                (data['authorityScore'] as num?)?.toDouble() ?? 0.0,
            'totalReferences': (data['totalReferences'] as int?) ?? 0,
          };
        })
        .toList(growable: false),
    'eligible':
        toolResults.isNotEmpty &&
        toolResults.any((r) {
          final data = r.dataPayload;
          if (data['success'] != true) return false;
          final qs = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
          return qs >= 0.35;
        }),
    'gaps': toolResults.isEmpty
        ? <String>['no_search_result']
        : toolResults
              .where((r) {
                final data = r.dataPayload;
                final qs = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
                return data['success'] != true || qs < 0.35;
              })
              .map(
                (r) =>
                    'low_quality_result:${(r.dataPayload['stepId'] ?? r.toolCallId).toString()}',
              )
              .toList(growable: false),
  };
}

Map<String, dynamic> buildStructuredResponseLearningSignals({
  required AssistantAnswerPayloadReadView apv,
  required String learningSatisfaction,
  required double modelSelfScore,
}) {
  return <String, dynamic>{
    'profileTagDelta': apv.diagnosticsEmergedTagMaps,
    'retrievalStrategyOutcome': 'not_generated',
    'answerFormatOutcome': 'not_generated',
    'satisfactionProxy': learningSatisfaction,
    'modelSelfScore': modelSelfScore,
  };
}

Map<String, dynamic> buildStructuredResponseDiagnostics({
  required Map<String, dynamic> diagnosticsMap,
  required String synthesisReason,
  required int toolResultCount,
  required int toolErrorCount,
  required bool webEvidenceGatePassed,
  required Map<String, dynamic> qualityGates,
}) {
  return <String, dynamic>{
    ...diagnosticsMap,
    'synthesisReason': synthesisReason,
    'toolResultCount': toolResultCount,
    'toolErrorCount': toolErrorCount,
    'webEvidenceGatePassed': webEvidenceGatePassed,
    'qualityGates': qualityGates,
  };
}

Map<String, dynamic> buildStructuredResponseUiUsageStats({
  required List<AssistantTraceEvent> traces,
  required AssistantRunRequest request,
  required List<AssistantSubagentRunRecord> subagentRuns,
  required String outputText,
}) {
  return buildUiUsageStats(
    traces: traces,
    request: request,
    subagentRuns: subagentRuns,
    outputText: outputText,
  );
}

List<Map<String, dynamic>> buildStructuredResponseUiTimeline({
  required List<AssistantSubagentRunRecord> subagentRuns,
}) {
  return AssistantPipelineDiagnosticsHelper()
      .buildUiTimeline(subagentRuns: subagentRuns)
      .map((item) => item.toJson())
      .toList(growable: false);
}

Map<String, dynamic> assembleStructuredResponseRoot({
  required Map<String, dynamic> enrichedAnswerPayload,
  required Map<String, dynamic> rootPayload,
}) {
  return <String, dynamic>{...enrichedAnswerPayload, ...rootPayload};
}

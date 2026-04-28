import 'dart:math' as math;

import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';

import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

class EvidenceDigestPhase implements Phase {
  const EvidenceDigestPhase({
    RetrievalOutcomeResolver retrievalOutcomeResolver =
        const RetrievalOutcomeResolver(),
  }) : _retrievalOutcomeResolver = retrievalOutcomeResolver;

  final RetrievalOutcomeResolver _retrievalOutcomeResolver;

  @override
  String get phaseId => 'evidence_digest';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final executionSnapshot = input.state.executionPhaseSnapshot;
    if (executionSnapshot is! ExecutionPhaseSuccess) {
      return PhaseOutput(state: input.state);
    }
    final phaseOneResult = executionSnapshot.phaseOneResult;
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    if (latestUserQuery.isEmpty) {
      return PhaseOutput(state: input.state);
    }
    final synthesisReadiness = executionSnapshot.synthesisReadiness;
    final toolResults = executionSnapshot.toolResults.isNotEmpty
        ? executionSnapshot.toolResults
        : _collectToolResults(phaseOneResult.traces);
    final fallbackSnapshot = _buildFallbackRetrievalProcessing(
      toolResults: toolResults,
      synthesisReadiness: synthesisReadiness,
    );
    final boundaryPolicy = executionSnapshot.answerBoundaryPolicy;
    final evidenceEvaluation = executionSnapshot.evidenceEvaluation;
    final retrievalOutcome = _retrievalOutcomeResolver.resolve(
      policy: boundaryPolicy,
      retrievalProcessing: fallbackSnapshot,
      evidenceEvaluation: evidenceEvaluation,
      synthesisReadiness: synthesisReadiness,
      searchPlans: searchPlansFromTaskGraph(input.state.taskGraph),
      toolResults: toolResults,
    );
    final stageBlocked =
        !synthesisReadiness.ready ||
        (retrievalOutcome.evidenceRequired && !retrievalOutcome.retrievalReady);
    var snapshot = _normalizeRetrievalSnapshot(
      snapshot:
          retrievalOutcome.retrievalProcessing.processedDocumentCount > 0 ||
              retrievalOutcome.retrievalProcessing.acceptedDocumentCount > 0 ||
              retrievalOutcome.retrievalProcessing.processingSummary
                  .trim()
                  .isNotEmpty
          ? retrievalOutcome.retrievalProcessing
          : fallbackSnapshot,
      fallbackSnapshot: fallbackSnapshot,
      blocked: stageBlocked,
      blockedMessage: _buildRetrievalBlockedMessage(
        retrievalOutcome.summary.trim().isNotEmpty
            ? retrievalOutcome.summary
            : synthesisReadiness.reason,
      ),
    );
    if (!stageBlocked &&
        snapshot.processingSummary.trim().isEmpty &&
        retrievalOutcome.summary.trim().isNotEmpty) {
      snapshot = RetrievalProcessingSnapshot(
        searchedDocumentCount: snapshot.searchedDocumentCount,
        processedDocumentCount: snapshot.processedDocumentCount,
        acceptedDocumentCount: snapshot.acceptedDocumentCount,
        processingSummary: retrievalOutcome.summary.trim(),
        selectedKeyPoints: snapshot.selectedKeyPoints,
        expansionReason: retrievalOutcome.expansionReason.trim().isNotEmpty
            ? retrievalOutcome.expansionReason
            : snapshot.expansionReason,
        acceptedReferences: snapshot.acceptedReferences,
      );
    }
    if (stageBlocked) {
      _emitRetrievalProcessing(input: input, snapshot: snapshot, blocked: true);
    }
    return PhaseOutput(
      state: input.state.copyWith(retrievalProcessing: snapshot),
    );
  }

  RetrievalProcessingSnapshot _buildFallbackRetrievalProcessing({
    required List<AssistantToolResultRow> toolResults,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    final acceptedReferences = _extractAcceptedReferences(toolResults);
    final processedDocumentCount = _resolveProcessedDocumentCount(
      toolResults: toolResults,
      acceptedDocumentCount: acceptedReferences.length,
    );
    final searchedDocumentCount = _resolveSearchedDocumentCount(
      toolResults: toolResults,
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedReferences.length,
    );
    final selectedKeyPoints = _fallbackSelectedKeyPoints(
      acceptedReferences: acceptedReferences,
      toolResults: toolResults,
    );
    return RetrievalProcessingSnapshot(
      searchedDocumentCount: searchedDocumentCount,
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedReferences.length,
      processingSummary: '',
      selectedKeyPoints: selectedKeyPoints,
      expansionReason: '',
      acceptedReferences: acceptedReferences,
    );
  }

  RetrievalProcessingSnapshot _normalizeRetrievalSnapshot({
    required RetrievalProcessingSnapshot snapshot,
    required RetrievalProcessingSnapshot fallbackSnapshot,
    required bool blocked,
    required String blockedMessage,
  }) {
    if (!blocked) {
      return snapshot;
    }
    return RetrievalProcessingSnapshot(
      searchedDocumentCount: snapshot.searchedDocumentCount > 0
          ? snapshot.searchedDocumentCount
          : fallbackSnapshot.searchedDocumentCount,
      processedDocumentCount: snapshot.processedDocumentCount > 0
          ? snapshot.processedDocumentCount
          : fallbackSnapshot.processedDocumentCount,
      acceptedDocumentCount: snapshot.acceptedDocumentCount > 0
          ? snapshot.acceptedDocumentCount
          : fallbackSnapshot.acceptedDocumentCount,
      processingSummary: snapshot.processingSummary.trim(),
      selectedKeyPoints: const <String>[],
      expansionReason: snapshot.expansionReason.trim(),
      acceptedReferences: snapshot.acceptedReferences.isNotEmpty
          ? snapshot.acceptedReferences
          : fallbackSnapshot.acceptedReferences,
    );
  }

  List<AssistantToolResultRow> _collectToolResults(
    List<AssistantTraceEvent> traces,
  ) {
    return traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(AssistantToolResultRow.fromTraceEvent)
        .toList(growable: false);
  }

  List<RetrievalProcessingReference> _extractAcceptedReferences(
    List<AssistantToolResultRow> toolResults,
  ) {
    final byUrl = <String, RetrievalProcessingReference>{};
    for (final item in toolResults) {
      final data = item.dataPayload;
      final references =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final reference in references) {
        final title = SafeReferenceNormalizer.normalizeText(
          (reference['title'] as String?)?.trim() ?? '',
        );
        final url = (reference['url'] as String?)?.trim() ?? '';
        final source = SafeReferenceNormalizer.normalizeText(
          (reference['source'] as String?)?.trim() ??
              (reference['sourceHost'] as String?)?.trim() ??
              '',
        );
        final snippet = SafeReferenceNormalizer.normalizeSnippet(
          (reference['snippet'] as String?)?.trim() ?? '',
        );
        final key = url.isNotEmpty ? url : '$title::$source';
        if (key.trim().isEmpty || byUrl.containsKey(key)) {
          continue;
        }
        if (title.isEmpty && url.isEmpty && source.isEmpty) {
          continue;
        }
        final sanitized = RetrievalProcessingReference(
          title: title,
          url: url,
          source: source,
          snippet: snippet,
        );
        if (!_hasRenderableReference(sanitized)) {
          continue;
        }
        byUrl[key] = sanitized;
      }
    }
    return byUrl.values.take(5).toList(growable: false);
  }

  int _resolveSearchedDocumentCount({
    required List<AssistantToolResultRow> toolResults,
    required int processedDocumentCount,
    required int acceptedDocumentCount,
  }) {
    var maxSearched = math.max(processedDocumentCount, acceptedDocumentCount);
    var summed = 0;
    for (final item in toolResults) {
      final data = item.dataPayload;
      final rerankStats = (data['rerankStats'] as Map?)
          ?.cast<String, dynamic>();
      final total =
          (rerankStats?['candidateCount'] as num?)?.toInt() ??
          (data['candidateCount'] as num?)?.toInt() ??
          (data['totalCandidates'] as num?)?.toInt() ??
          (data['totalReferences'] as num?)?.toInt() ??
          ((data['references'] as List?)?.length ?? 0);
      if (total > maxSearched) {
        maxSearched = total;
      }
      summed += total;
    }
    if (summed > maxSearched) {
      maxSearched = summed;
    }
    return maxSearched;
  }

  int _resolveProcessedDocumentCount({
    required List<AssistantToolResultRow> toolResults,
    required int acceptedDocumentCount,
  }) {
    var maxProcessed = acceptedDocumentCount;
    var summed = 0;
    for (final item in toolResults) {
      final data = item.dataPayload;
      final total = (data['totalReferences'] as num?)?.toInt() ?? 0;
      if (total > maxProcessed) {
        maxProcessed = total;
      }
      summed += total;
    }
    if (summed > maxProcessed) {
      maxProcessed = summed;
    }
    return maxProcessed;
  }

  List<String> _fallbackSelectedKeyPoints({
    required List<RetrievalProcessingReference> acceptedReferences,
    required List<AssistantToolResultRow> toolResults,
  }) {
    final points = <String>[];
    final seen = <String>{};

    void collect(String raw) {
      final value = _sanitizeKeyPoint(raw);
      if (value.isEmpty || value.length < 6 || !seen.add(value)) return;
      points.add(value);
    }

    for (final item in toolResults) {
      final data = item.dataPayload;
      final summary = (data['summary'] as String?)?.trim() ?? '';
      if (summary.isNotEmpty) collect(summary);
      final hits =
          (data['hits'] as List?)?.whereType<Map>().toList(growable: false) ??
          const <Map>[];
      for (final hit in hits) {
        final snippet = (hit['snippet'] as String?)?.trim() ?? '';
        if (snippet.isNotEmpty && snippet.length > 10) {
          collect(snippet);
        }
        if (points.length >= 5) break;
      }
      if (points.length >= 5) break;
    }
    if (points.length < 3) {
      for (final reference in acceptedReferences) {
        if (reference.snippet.trim().length > 10) {
          collect(reference.snippet);
        }
        if (points.length >= 5) break;
      }
    }
    return points.take(5).toList(growable: false);
  }

  void _emitRetrievalProcessing({
    required PhaseInput input,
    required RetrievalProcessingSnapshot snapshot,
    required bool blocked,
  }) {
    ProcessTimelineEmitter(
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
    ).commit(
      stepId: ProcessStepId.retrievalProcessing,
      scope: UserEventScope.skill,
      headline: snapshot.processingSummary.trim(),
      detail: '',
      phaseId: 'aggregating',
      actionCode: 'assess_evidence',
      reasonCode: blocked
          ? 'need_more_evidence'
          : (snapshot.expansionReason.trim().isEmpty
                ? 'evidence_ready'
                : 'need_more_evidence'),
      payload: <String, dynamic>{
        'summary': snapshot.processingSummary.trim(),
        'status': blocked ? JourneyStageStatus.blocked.wireName : '',
        'references': snapshot.acceptedReferences
            .map((item) => item.toJson())
            .toList(growable: false),
        'retrievalProcessing': snapshot.toJson(),
      },
    );
  }

  String _buildRetrievalBlockedMessage(String rawReason) {
    return rawReason.trim();
  }

  bool _hasRenderableReference(RetrievalProcessingReference reference) {
    return reference.title.isNotEmpty ||
        reference.url.isNotEmpty ||
        reference.source.isNotEmpty;
  }

  String _sanitizeKeyPoint(String raw) {
    return SafeReferenceNormalizer.normalizeFact(raw);
  }
}

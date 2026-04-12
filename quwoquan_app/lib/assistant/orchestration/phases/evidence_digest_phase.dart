import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';

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
    final executionSnapshot = input.state.executionBridgeSnapshot;
    final phaseOneResult = executionSnapshot['phaseOneResult'];
    if (phaseOneResult is! ReactRuntimeResult) {
      return PhaseOutput(state: input.state);
    }
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    if (latestUserQuery.isEmpty) {
      return PhaseOutput(state: input.state);
    }
    final synthesisReadiness =
        executionSnapshot['synthesisReadiness'] is SynthesisReadinessResult
        ? executionSnapshot['synthesisReadiness'] as SynthesisReadinessResult
        : const SynthesisReadinessResult();
    final toolResults = executionSnapshot['toolResults'] is List
        ? (executionSnapshot['toolResults'] as List)
              .whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false)
        : _collectToolResults(phaseOneResult.traces);
    final fallbackSnapshot = _buildFallbackRetrievalProcessing(
      toolResults: toolResults,
      synthesisReadiness: synthesisReadiness,
    );
    final boundaryPolicy =
        executionSnapshot['answerBoundaryPolicy'] is AnswerBoundaryPolicy
        ? executionSnapshot['answerBoundaryPolicy'] as AnswerBoundaryPolicy
        : const AnswerBoundaryPolicy();
    final evidenceEvaluation =
        executionSnapshot['evidenceEvaluation'] is EvidenceEvaluationResult
        ? executionSnapshot['evidenceEvaluation'] as EvidenceEvaluationResult
        : const EvidenceEvaluationResult();
    final retrievalOutcome = executionSnapshot[assistantRetrievalOutcomeField]
            is RetrievalOutcome
        ? executionSnapshot[assistantRetrievalOutcomeField] as RetrievalOutcome
        : _retrievalOutcomeResolver.resolve(
            policy: boundaryPolicy,
            retrievalProcessing: fallbackSnapshot,
            evidenceEvaluation: evidenceEvaluation,
            synthesisReadiness: synthesisReadiness,
            queryTasks: input.state.queryTasks,
            toolResults: toolResults,
            referenceNowIso:
                input.state.intentGraph?.queryNormalization.referenceNowIso ?? '',
            timezone:
                input.state.intentGraph?.queryNormalization.timezone ?? '',
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
    if (!stageBlocked && snapshot.processingSummary.trim().isEmpty) {
      final readyNarrative = _synthesizeReadyProcessingSummary(
        understanding: input.state.understandingSnapshot,
        references: snapshot.acceptedReferences,
        keyPoints: snapshot.selectedKeyPoints,
      );
      if (readyNarrative.isNotEmpty) {
        snapshot = RetrievalProcessingSnapshot(
          processedDocumentCount: snapshot.processedDocumentCount,
          acceptedDocumentCount: snapshot.acceptedDocumentCount,
          processingSummary: readyNarrative,
          selectedKeyPoints: snapshot.selectedKeyPoints,
          expansionReason: snapshot.expansionReason,
          acceptedReferences: snapshot.acceptedReferences,
        );
      }
    }
    final updatedExecutionSnapshot = <String, dynamic>{
      ...executionSnapshot,
      'retrievalProcessing': snapshot.toJson(),
      assistantRetrievalOutcomeField: retrievalOutcome.toJson(),
      'blockedProcessStepId': stageBlocked
          ? ProcessStepId.retrievalProcessing.wireName
          : '',
      'blockedProcessMessage': stageBlocked
          ? _buildRetrievalBlockedMessage(
              retrievalOutcome.summary.trim().isNotEmpty
                  ? retrievalOutcome.summary
                  : synthesisReadiness.reason,
            )
          : '',
      'skipAnswerStage': stageBlocked,
    };
    if (stageBlocked) {
      _emitRetrievalProcessing(input: input, snapshot: snapshot, blocked: true);
    }
    return PhaseOutput(
      state: input.state.copyWith(
        executionBridgeSnapshot: updatedExecutionSnapshot,
        retrievalProcessing: snapshot,
      ),
    );
  }

  RetrievalProcessingSnapshot _buildFallbackRetrievalProcessing({
    required List<Map<String, dynamic>> toolResults,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    final acceptedReferences = _extractAcceptedReferences(toolResults);
    final processedDocumentCount = _resolveProcessedDocumentCount(
      toolResults: toolResults,
      acceptedDocumentCount: acceptedReferences.length,
    );
    final selectedKeyPoints = _fallbackSelectedKeyPoints(
      acceptedReferences: acceptedReferences,
      toolResults: toolResults,
    );
    return RetrievalProcessingSnapshot(
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedReferences.length,
      processingSummary: '',
      selectedKeyPoints: selectedKeyPoints,
      expansionReason: synthesisReadiness.ready
          ? ''
          : synthesisReadiness.reason.trim(),
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
      processedDocumentCount: snapshot.processedDocumentCount > 0
          ? snapshot.processedDocumentCount
          : fallbackSnapshot.processedDocumentCount,
      acceptedDocumentCount: snapshot.acceptedDocumentCount > 0
          ? snapshot.acceptedDocumentCount
          : fallbackSnapshot.acceptedDocumentCount,
      processingSummary: blockedMessage.trim(),
      selectedKeyPoints: const <String>[],
      expansionReason: snapshot.expansionReason.trim().isNotEmpty
          ? snapshot.expansionReason.trim()
          : fallbackSnapshot.expansionReason,
      acceptedReferences: snapshot.acceptedReferences.isNotEmpty
          ? snapshot.acceptedReferences
          : fallbackSnapshot.acceptedReferences,
    );
  }

  List<Map<String, dynamic>> _collectToolResults(
    List<AssistantTraceEvent> traces,
  ) {
    return traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(
          (event) => <String, dynamic>{
            'message': event.message,
            'data': event.data ?? const <String, dynamic>{},
            'toolCallId': event.toolCallId ?? '',
          },
        )
        .toList(growable: false);
  }

  List<RetrievalProcessingReference> _extractAcceptedReferences(
    List<Map<String, dynamic>> toolResults,
  ) {
    final byUrl = <String, RetrievalProcessingReference>{};
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
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

  int _resolveProcessedDocumentCount({
    required List<Map<String, dynamic>> toolResults,
    required int acceptedDocumentCount,
  }) {
    var maxProcessed = acceptedDocumentCount;
    var summed = 0;
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
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
    required List<Map<String, dynamic>> toolResults,
  }) {
    final points = <String>[];
    final seen = <String>{};

    void collect(String raw) {
      final value = _sanitizeKeyPoint(raw);
      if (value.isEmpty || value.length < 6 || !seen.add(value)) return;
      points.add(value);
    }

    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
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

  /// Ready 链路下，当 resolver 未给出 summary 时，用理解快照关注点 + 证据片段生成用户可见的处理摘要。
  String _synthesizeReadyProcessingSummary({
    required RunArtifactsUnderstandingSnapshot understanding,
    required List<RetrievalProcessingReference> references,
    required List<String> keyPoints,
  }) {
    final concerns = understanding.concernPoints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (concerns.isEmpty) {
      return '';
    }
    var confirm = '';
    for (final ref in references) {
      final snippet = ref.snippet.trim();
      if (snippet.length >= 6) {
        confirm = snippet;
        break;
      }
    }
    if (confirm.isEmpty) {
      for (final point in keyPoints) {
        final trimmed = point.trim();
        if (trimmed.length >= 6) {
          confirm = trimmed;
          break;
        }
      }
    }
    if (confirm.isEmpty) {
      return '';
    }
    final punctuated = confirm.endsWith('。') ||
            confirm.endsWith('！') ||
            confirm.endsWith('？')
        ? confirm
        : '$confirm。';
    final joined = concerns.join('、');
    return '围绕你刚才最关心的$joined，现在已经能直接确认的是：$punctuated其余背景线索我不会直接带进最终答案。';
  }
}

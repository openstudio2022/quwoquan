import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/understanding_user_facing_summary.dart';

import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

class EvidenceDigestPhase implements Phase {
  const EvidenceDigestPhase();

  @override
  String get phaseId => 'evidence_digest';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = input.request is AssistantRunRequest
        ? input.request as AssistantRunRequest
        : AssistantRunRequest.fromJson((input.request as dynamic).toJson());
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
    final understandingSnapshot = input.state.understandingSnapshot;
    final toolResults = _collectToolResults(phaseOneResult.traces);
    final fallbackSnapshot = _buildFallbackRetrievalProcessing(
      toolResults: toolResults,
      understandingSnapshot: understandingSnapshot,
      synthesisReadiness: synthesisReadiness,
    );
    final stageBlocked = !synthesisReadiness.ready;
    final snapshot = _normalizeRetrievalSnapshot(
      snapshot: fallbackSnapshot,
      fallbackSnapshot: fallbackSnapshot,
      blocked: stageBlocked,
      blockedMessage: _buildRetrievalBlockedMessage(synthesisReadiness.reason),
    );
    final updatedExecutionSnapshot = <String, dynamic>{
      ...executionSnapshot,
      'retrievalProcessing': snapshot.toJson(),
      'blockedProcessStepId': stageBlocked
          ? ProcessStepId.retrievalProcessing.wireName
          : '',
      'blockedProcessMessage': stageBlocked
          ? _buildRetrievalBlockedMessage(synthesisReadiness.reason)
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
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
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
    final processingSummary = _buildFallbackProcessingSummary(
      understandingSnapshot: understandingSnapshot,
      selectedKeyPoints: selectedKeyPoints,
      acceptedReferenceCount: acceptedReferences.length,
    );
    return RetrievalProcessingSnapshot(
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedReferences.length,
      processingSummary: processingSummary,
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
    final detail = blocked
        ? ''
        : buildUnderstandingDetail(snapshot.selectedKeyPoints);
    ProcessTimelineEmitter(
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
    ).commit(
      stepId: ProcessStepId.retrievalProcessing,
      scope: UserEventScope.skill,
      headline: snapshot.processingSummary.trim(),
      detail: detail,
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
    final reason = rawReason.trim();
    if (reason.isEmpty) {
      return '这次拿到的结果还不够稳定，我先不继续往下生成答案。';
    }
    return '这次拿到的结果还不够稳定，$reason';
  }

  bool _hasRenderableReference(RetrievalProcessingReference reference) {
    return reference.title.isNotEmpty ||
        reference.url.isNotEmpty ||
        reference.source.isNotEmpty;
  }

  String _sanitizeKeyPoint(String raw) {
    return SafeReferenceNormalizer.normalizeFact(raw);
  }

  String _buildFallbackProcessingSummary({
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required List<String> selectedKeyPoints,
    required int acceptedReferenceCount,
  }) {
    final focusSummary = understandingSnapshot.concernPoints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .take(2)
        .join('、');
    final lead = focusSummary.isNotEmpty
        ? '围绕你刚才最关心的$focusSummary'
        : '顺着你刚才最关心的结果';
    final strongestFacts = selectedKeyPoints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .take(2)
        .toList(growable: false);
    if (strongestFacts.isNotEmpty) {
      final facts = strongestFacts.join('；');
      return '$lead，现在已经能直接确认的是：$facts。其余背景线索我不会直接带进最终答案。';
    }
    if (acceptedReferenceCount > 0) {
      return '$lead，我已经先把真正能直接支撑回答的依据收拢出来了，其余只作为背景线索保留。';
    }
    return '$lead，我还在继续筛掉噪音，只保留能直接支撑回答的依据。';
  }
}

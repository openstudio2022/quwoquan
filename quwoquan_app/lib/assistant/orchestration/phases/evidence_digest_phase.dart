import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/conversation_spine.dart';
import 'package:quwoquan_app/assistant/orchestration/model_output_extractors.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_trace_event.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/understanding_user_facing_summary.dart';

import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

class EvidenceDigestPhase implements Phase {
  const EvidenceDigestPhase({this.runtime, this.templateCatalogRuntime});

  final ReactRuntime? runtime;
  final TemplateCatalogRuntime? templateCatalogRuntime;

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

  Future<RetrievalProcessingSnapshot?> _digestWithModel({
    required PhaseInput input,
    required AssistantRunRequest request,
    required String latestUserQuery,
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required SynthesisReadinessResult synthesisReadiness,
    required List<Map<String, dynamic>> toolResults,
    required RetrievalProcessingSnapshot fallbackSnapshot,
    required ProcessTimelineEmitter processEmitter,
  }) async {
    final effectiveRuntime = runtime;
    if (effectiveRuntime == null || toolResults.isEmpty) {
      return null;
    }
    final effectiveTemplateRuntime =
        templateCatalogRuntime ?? TemplateCatalogRuntime();
    await effectiveTemplateRuntime.ensureLoaded(
      forceRefresh: input.state.bootstrapContext?.forceRefreshCatalog ?? false,
    );
    final templateVersion = effectiveTemplateRuntime.latestVersionFor(
      'evidence_digest',
      fallback: '',
    );
    final bootstrapContext = input.state.bootstrapContext;
    final evidenceContext = <String, dynamic>{
      'toolResults': toolResults,
      'acceptedReferences': fallbackSnapshot.acceptedReferences
          .map((item) => item.toJson())
          .toList(growable: false),
      'processedDocumentCount': fallbackSnapshot.processedDocumentCount,
      'acceptedDocumentCount': fallbackSnapshot.acceptedDocumentCount,
    };
    final currentRuntimeState = <String, dynamic>{
      'dialogueState': <String, dynamic>{
        'problemClass': input.state.intentGraph?.problemClass.wireName ?? '',
        'answerShape': input.state.intentGraph?.answerShape.wireName ?? '',
        'synthesisReady': synthesisReadiness.ready,
        'synthesisReason': synthesisReadiness.reason,
      },
    };
    final dialogueContinuity = <String, dynamic>{
      'continuityMode':
          bootstrapContext?.contextContinuityPolicy.continuityMode.wireName ??
          '',
      'previousUnderstandingSnapshot':
          bootstrapContext?.previousUnderstandingSnapshot.toJson() ??
          const <String, dynamic>{},
      'previousAnswerProcessing':
          bootstrapContext?.previousAnswerProcessing.toJson() ??
          const <String, dynamic>{},
      'historicalThinkingSnapshot':
          bootstrapContext?.historicalThinkingSnapshot.toJson() ??
          const <String, dynamic>{},
      'previousAnswerSummary': bootstrapContext?.previousAnswerSummary ?? '',
    };
    final conversationSpine = buildConversationSpine(
      stageId: 'retrieval_processing',
      userQuery: latestUserQuery,
      userGoal: input.state.intentGraph?.userGoal ?? '',
      primarySkill: input.state.intentGraph?.primarySkill ?? '',
      problemClass: input.state.intentGraph?.problemClass.wireName ?? '',
      answerShape: input.state.intentGraph?.answerShape.wireName ?? '',
      historyAssessment: mergeHistoryAssessments(<Map<String, dynamic>>[
        buildHistoryAssessmentFromPolicy(
          policy:
              bootstrapContext?.contextContinuityPolicy ??
              const ContextContinuityPolicy(),
          overrideSlots:
              bootstrapContext?.continuityOverrideSlots ??
              const <String, dynamic>{},
        ),
        buildHistoryAssessmentFromSnapshot(
          snapshot:
              bootstrapContext?.historicalThinkingSnapshot ??
              const RunArtifactsHistoricalThinkingSnapshot(),
        ),
      ]),
      stageState: <String, dynamic>{
        'allowedChoices': const <String>['answer', 'replan'],
        'answerReady': synthesisReadiness.ready,
        'replanRequested': !synthesisReadiness.ready,
        if (!synthesisReadiness.ready &&
            synthesisReadiness.reason.trim().isNotEmpty)
          'replanReason': synthesisReadiness.reason.trim(),
      },
    );
    final digestMessages = <Map<String, dynamic>>[
      <String, dynamic>{
        'role': 'system',
        'content': _buildEvidenceDigestNarrativeBaton(
          understandingSnapshot: understandingSnapshot,
          dialogueContinuity: dialogueContinuity,
        ),
      },
      <String, dynamic>{'role': 'user', 'content': latestUserQuery},
    ];
    final digestTemplateVariables = <String, dynamic>{
      'userQuery': latestUserQuery,
      'conversationSpine': jsonEncode(conversationSpine),
      'understandingSnapshot': jsonEncode(understandingSnapshot.toJson()),
      'evidenceContext': jsonEncode(evidenceContext),
      'currentRuntimeState': jsonEncode(currentRuntimeState),
      'dialogueContinuity': jsonEncode(dialogueContinuity),
    };
    var streamedProcessingSummary = '';
    void forwardTrace(AssistantTraceEvent event) {
      input.onTraceEvent?.call(
        event.copyWith(visibility: TraceVisibility.internal),
      );
      if (event.type == AssistantTraceEventType.thinkingProgress &&
          event.data?['streaming'] == true &&
          event.data?['extracted'] == true &&
          event.data?['fieldPath'] == 'retrievalProcessing.processingSummary') {
        streamedProcessingSummary = _mergeStableNarrativeText(
          previous: streamedProcessingSummary,
          incoming: event.message,
        );
        processEmitter.pushDelta(
          stepId: ProcessStepId.retrievalProcessing,
          scope: UserEventScope.skill,
          delta: event.message,
          phaseId: 'evidence_digest',
          actionCode: 'assess_evidence',
          reasonCode: 'digest_evidence',
          payload: const <String, dynamic>{
            'fieldPath': 'retrievalProcessing.processingSummary',
          },
        );
      }
    }

    var rawOutput = await effectiveRuntime.streamStructuredOutput(
      messages: digestMessages,
      onDelta: (_) {},
      streamJsonFieldPaths: const <String>[
        'retrievalProcessing.processingSummary',
      ],
      templateContext: request.contextScopeHint,
      templateVariables: digestTemplateVariables,
      templateId: 'evidence_digest',
      templateVersion: templateVersion,
      sessionId: request.sessionId ?? 'default',
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent == null ? null : forwardTrace,
      streamTraceStage: 'evidence_digest',
      structuredPhaseId: 'evidence_digest',
      emitVisibleStreamTrace: false,
    );
    if (rawOutput.trim().isEmpty) {
      final fallbackResult = await effectiveRuntime.run(
        messages: digestMessages,
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: 'evidence_digest',
        templateVersion: templateVersion,
        templateContext: request.contextScopeHint,
        templateVariables: digestTemplateVariables,
        sessionId: request.sessionId ?? 'default',
        runId: input.runId,
        traceId: input.traceId,
        onTraceEvent: input.onTraceEvent == null ? null : forwardTrace,
        callOptions: const LlmCallOptions(
          temperature: 0.1,
          maxTokens: 800,
          forceJsonObject: true,
          timeoutSeconds: 20,
          streamJsonFieldPaths: <String>[
            'retrievalProcessing.processingSummary',
          ],
        ),
      );
      rawOutput = fallbackResult.finalText;
    }
    final parsed =
        LlmResponseParser.parse(rawOutput).json ?? const <String, dynamic>{};
    final payload = parsed['retrievalProcessing'] is Map
        ? (parsed['retrievalProcessing'] as Map).cast<String, dynamic>()
        : parsed;
    if (payload.isEmpty ||
        !payload.containsKey('processingSummary') &&
            !payload.containsKey('selectedKeyPoints')) {
      final naturalLanguageSnapshot = _tryExtractFromNaturalLanguage(
        rawOutput,
        fallbackSnapshot,
      );
      return _withStableProcessingSummary(
        snapshot: naturalLanguageSnapshot,
        streamedProcessingSummary: streamedProcessingSummary,
      );
    }
    return _withStableProcessingSummary(
      snapshot: _mergeRetrievalProcessing(
        raw: payload,
        fallbackSnapshot: fallbackSnapshot,
      ),
      streamedProcessingSummary: streamedProcessingSummary,
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

  RetrievalProcessingSnapshot _mergeRetrievalProcessing({
    required Map<String, dynamic> raw,
    required RetrievalProcessingSnapshot fallbackSnapshot,
  }) {
    final parsed = RetrievalProcessingSnapshot.fromJson(raw);
    final parsedSelectedKeyPoints = parsed.selectedKeyPoints
        .map(_sanitizeKeyPoint)
        .where((item) => item.isNotEmpty)
        .take(5)
        .toList(growable: false);
    final parsedAcceptedReferences = parsed.acceptedReferences
        .map(_sanitizeAcceptedReference)
        .where(_hasRenderableReference)
        .take(5)
        .toList(growable: false);
    return RetrievalProcessingSnapshot(
      processedDocumentCount: parsed.processedDocumentCount > 0
          ? parsed.processedDocumentCount
          : fallbackSnapshot.processedDocumentCount,
      acceptedDocumentCount: parsed.acceptedDocumentCount > 0
          ? parsed.acceptedDocumentCount
          : fallbackSnapshot.acceptedDocumentCount,
      processingSummary: parsed.processingSummary.trim().isNotEmpty
          ? parsed.processingSummary.trim()
          : fallbackSnapshot.processingSummary,
      selectedKeyPoints: parsedSelectedKeyPoints.isNotEmpty
          ? parsedSelectedKeyPoints
          : fallbackSnapshot.selectedKeyPoints,
      expansionReason: parsed.expansionReason.trim().isNotEmpty
          ? parsed.expansionReason.trim()
          : fallbackSnapshot.expansionReason,
      acceptedReferences: parsedAcceptedReferences.isNotEmpty
          ? parsedAcceptedReferences
          : fallbackSnapshot.acceptedReferences,
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

  RetrievalProcessingSnapshot? _tryExtractFromNaturalLanguage(
    String rawText,
    RetrievalProcessingSnapshot fallbackSnapshot,
  ) {
    final text = rawText.trim();
    if (text.isEmpty) return null;

    final points = <String>[];
    final seen = <String>{};
    void collect(String raw) {
      final value = raw.trim();
      if (value.isEmpty || value.length < 6 || !seen.add(value)) return;
      points.add(value);
    }

    final listItemRe = RegExp(r'[-•]\s*(.+?)(?:\n|$)');
    final numberedRe = RegExp(r'\d+[.、]\s*(.+?)(?:\n|$)');
    for (final pattern in <RegExp>[listItemRe, numberedRe]) {
      for (final match in pattern.allMatches(text)) {
        final point = match.group(1)?.trim() ?? '';
        collect(point);
        if (points.length >= 5) break;
      }
      if (points.length >= 5) break;
    }

    final sentences = text.split(RegExp(r'[。\n]'));
    final summary = sentences
        .map((s) => s.trim())
        .where((s) => s.length > 10 && !s.startsWith('[') && !s.startsWith('{'))
        .take(1)
        .join();

    if (summary.isEmpty && points.isEmpty) return null;

    return RetrievalProcessingSnapshot(
      processedDocumentCount: fallbackSnapshot.processedDocumentCount,
      acceptedDocumentCount: fallbackSnapshot.acceptedDocumentCount,
      processingSummary: summary.isNotEmpty
          ? summary
          : fallbackSnapshot.processingSummary,
      selectedKeyPoints: points.isNotEmpty
          ? points
          : fallbackSnapshot.selectedKeyPoints,
      expansionReason: fallbackSnapshot.expansionReason,
      acceptedReferences: fallbackSnapshot.acceptedReferences,
    );
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

  RetrievalProcessingSnapshot? _withStableProcessingSummary({
    required RetrievalProcessingSnapshot? snapshot,
    required String streamedProcessingSummary,
  }) {
    if (snapshot == null) {
      return null;
    }
    final mergedSummary = _mergeStableNarrativeFinalText(
      streamed: streamedProcessingSummary,
      finalized: snapshot.processingSummary,
    );
    return RetrievalProcessingSnapshot(
      processedDocumentCount: snapshot.processedDocumentCount,
      acceptedDocumentCount: snapshot.acceptedDocumentCount,
      processingSummary: mergedSummary,
      selectedKeyPoints: snapshot.selectedKeyPoints,
      expansionReason: snapshot.expansionReason,
      acceptedReferences: snapshot.acceptedReferences,
    );
  }

  RetrievalProcessingReference _sanitizeAcceptedReference(
    RetrievalProcessingReference reference,
  ) {
    return RetrievalProcessingReference(
      title: SafeReferenceNormalizer.normalizeText(reference.title),
      url: reference.url.trim(),
      source: SafeReferenceNormalizer.normalizeText(reference.source),
      snippet: SafeReferenceNormalizer.normalizeSnippet(reference.snippet),
    );
  }

  bool _hasRenderableReference(RetrievalProcessingReference reference) {
    return reference.title.isNotEmpty ||
        reference.url.isNotEmpty ||
        reference.source.isNotEmpty;
  }

  String _sanitizeKeyPoint(String raw) {
    return SafeReferenceNormalizer.normalizeFact(raw);
  }

  String _mergeStableNarrativeText({
    required String previous,
    required String incoming,
  }) {
    if (incoming.isEmpty) return previous;
    if (previous.isEmpty) return incoming;
    if (previous.endsWith(incoming) || previous.contains(incoming)) {
      return previous;
    }
    if (incoming.endsWith(previous)) {
      return incoming;
    }
    final maxOverlap = previous.length < incoming.length
        ? previous.length
        : incoming.length;
    for (var overlap = maxOverlap; overlap > 0; overlap--) {
      if (previous.substring(previous.length - overlap) ==
          incoming.substring(0, overlap)) {
        return '$previous${incoming.substring(overlap)}';
      }
    }
    return '$previous$incoming';
  }

  String _mergeStableNarrativeFinalText({
    required String streamed,
    required String finalized,
  }) {
    final streamedText = streamed.trim();
    final finalizedText = finalized.trim();
    if (streamedText.isEmpty) return finalizedText;
    if (finalizedText.isEmpty) return streamedText;
    if (finalizedText == streamedText) {
      return streamedText;
    }
    if (streamedText.startsWith(finalizedText)) {
      return streamedText;
    }
    final overlap = _suffixPrefixOverlap(streamedText, finalizedText);
    if (overlap > 0 && overlap < finalizedText.length) {
      return '$streamedText${finalizedText.substring(overlap)}'.trim();
    }
    return streamedText;
  }

  int _suffixPrefixOverlap(String left, String right) {
    final maxOverlap = left.length < right.length ? left.length : right.length;
    for (var overlap = maxOverlap; overlap > 0; overlap--) {
      if (left.substring(left.length - overlap) ==
          right.substring(0, overlap)) {
        return overlap;
      }
    }
    return 0;
  }

  String _buildEvidenceDigestNarrativeBaton({
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required Map<String, dynamic> dialogueContinuity,
  }) {
    final lines = <String>['连续叙事接力：请沿用这轮已经确认的目标与口吻，继续说明哪些信息真正可用，不要另起一套检索报告。'];
    final understandingSummary = understandingSnapshot.userFacingSummary.trim();
    if (understandingSummary.isNotEmpty) {
      lines.add('上一阶段已确认：$understandingSummary');
    }
    final mismatchSignal =
        ((dialogueContinuity['historicalThinkingSnapshot'] as Map?)
                ?.cast<String, dynamic>())?['mismatchSignal']
            ?.toString()
            .trim() ??
        '';
    if (mismatchSignal.isNotEmpty) {
      lines.add('本轮纠偏提醒：$mismatchSignal');
    }
    return lines.join('\n');
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

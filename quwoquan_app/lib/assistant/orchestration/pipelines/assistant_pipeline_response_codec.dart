import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';

mixin AssistantPipelineResponseCodecMixin {
  List<Map<String, dynamic>> normalizeToolCalls(Object? value) {
    if (value is List) {
      return value
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
    }
    if (value is Map) return <Map<String, dynamic>>[value.cast<String, dynamic>()];
    return const <Map<String, dynamic>>[];
  }

  Map<String, dynamic> normalizeMap(Object? value) {
    if (value is Map) {
      return value.cast<String, dynamic>();
    }
    if (value is String && value.trim().isNotEmpty) {
      return <String, dynamic>{'text': value.trim()};
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> preferStructuredMap(
    Map<String, dynamic>? primary,
    Map<String, dynamic> fallback,
  ) {
    if (primary != null && hasStructuredContent(primary)) {
      return primary;
    }
    if (hasStructuredContent(fallback)) {
      return fallback;
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> materializedUnderstandingSnapshotRaw({
    required Map<String, dynamic> answerPayload,
    required Map<String, dynamic> carriedUnderstandingSnapshot,
    required ConversationStateDecision stateDecision,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    final current = AssistantAnswerPayloadReadView(
      answerPayload,
    ).understandingSnapshotMap;
    if (!hasStructuredContent(carriedUnderstandingSnapshot)) {
      return preferStructuredMap(current, const <String, dynamic>{});
    }
    if (shouldAllowSecondTurnUnderstandingRewrite(
      stateDecision: stateDecision,
      synthesisReadiness: synthesisReadiness,
    )) {
      return preferStructuredMap(current, carriedUnderstandingSnapshot);
    }
    return carriedUnderstandingSnapshot;
  }

  Map<String, dynamic> materializedHistoricalThinkingSnapshotRaw({
    required Map<String, dynamic> answerPayload,
    required Map<String, dynamic> carriedHistoricalThinkingSnapshot,
    required ConversationStateDecision stateDecision,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    final current = AssistantAnswerPayloadReadView(
      answerPayload,
    ).historicalThinkingSnapshotMap;
    if (!hasStructuredContent(carriedHistoricalThinkingSnapshot)) {
      return preferStructuredMap(current, const <String, dynamic>{});
    }
    if (shouldAllowSecondTurnUnderstandingRewrite(
      stateDecision: stateDecision,
      synthesisReadiness: synthesisReadiness,
    )) {
      return preferStructuredMap(current, carriedHistoricalThinkingSnapshot);
    }
    return carriedHistoricalThinkingSnapshot;
  }

  bool shouldAllowSecondTurnUnderstandingRewrite({
    required ConversationStateDecision stateDecision,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    return stateDecision.nextActionType == AssistantNextAction.toolCall ||
        stateDecision.nextActionType == AssistantNextAction.replan ||
        stateDecision.finalAnswerModeType == FinalAnswerMode.replan ||
        synthesisReadiness.replanTask != null;
  }

  Map<String, dynamic> dialogueScriptForModel(DialogueRoundScript script) {
    final json = Map<String, dynamic>.from(script.toJson());
    json.remove('routingCatalogVersion');
    json.remove('eventCatalogVersion');
    return json;
  }

  List<Map<String, dynamic>> subagentRunsForModel(
    List<AssistantSubagentRunRecord> runs,
  ) {
    return runs.map((r) => r.toModelJson()).toList(growable: false);
  }

  Map<String, dynamic> normalizeModelSelfScore(Object? value) {
    final mapped = normalizeMap(value);
    if (mapped.isNotEmpty) return mapped;
    return const <String, dynamic>{'score': 0, 'reason': 'not_provided'};
  }

  List<String> normalizeStringList(Object? value) {
    if (value is List) {
      return value
          .where((item) => item != null)
          .map((item) => item.toString())
          .where((item) => item.trim().isNotEmpty)
          .toList(growable: false);
    }
    if (value is String && value.trim().isNotEmpty) {
      return <String>[value.trim()];
    }
    return const <String>[];
  }

  List<Map<String, dynamic>> normalizeMapList(
    Object? value, {
    required String textKey,
  }) {
    if (value is List) {
      return value
          .map((item) {
            if (item is Map) return item.cast<String, dynamic>();
            if (item is String && item.trim().isNotEmpty) {
              return <String, dynamic>{textKey: item.trim()};
            }
            return null;
          })
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
    }
    if (value is Map) {
      return <Map<String, dynamic>>[value.cast<String, dynamic>()];
    }
    if (value is String && value.trim().isNotEmpty) {
      return <Map<String, dynamic>>[
        <String, dynamic>{textKey: value.trim()},
      ];
    }
    return const <Map<String, dynamic>>[];
  }

  Map<String, dynamic> mergeSelfCheck({
    required Map<String, dynamic> answerPayload,
    required bool answerEligible,
    required String synthesisReason,
    required bool evidenceGatePassed,
  }) {
    final base = Map<String, dynamic>.from(
      AssistantAnswerPayloadReadView(answerPayload).selfCheckMap,
    );
    final failed = <String>[
      ...((base['failedItems'] as List?)?.whereType<String>() ??
          const <String>[]),
      if (!answerEligible && synthesisReason.isNotEmpty) synthesisReason,
      if (!evidenceGatePassed) 'web_evidence_threshold_not_met',
    ];
    return <String, dynamic>{
      ...base,
      'passed': answerEligible && failed.isEmpty,
      'failedChecks': failed,
    };
  }

  String extractUiSummary(
    Map<String, dynamic> answerPayload,
    String fallback,
  ) {
    final turn = tryParseAssistantTurnOutput(answerPayload);
    final apv = AssistantAnswerPayloadReadView(answerPayload);
    final interpretation =
        turn?.interpretation ?? apv.resultInterpretationTrimmed;
    if (interpretation.isNotEmpty) return interpretation;
    final text = turn?.resultText ?? apv.resultTextTrimmed;
    if (text.isNotEmpty) return text;
    return fallback;
  }

  bool isRealtimeLikeRequest({
    required String fallbackProblemClass,
    required Map<String, dynamic> answerPayload,
  }) {
    final apv = AssistantAnswerPayloadReadView(answerPayload);
    final payloadProblemClass = apv.problemClassRootTrimmedLower.isNotEmpty
        ? apv.problemClassRootTrimmedLower
        : (apv.decisionMap['problemClass'] as String?)?.trim().toLowerCase() ??
              '';
    if (payloadProblemClass.isNotEmpty) {
      return parseProblemClass(payloadProblemClass) ==
          ProblemClass.realtimeInfo;
    }
    return parseProblemClass(fallbackProblemClass) == ProblemClass.realtimeInfo;
  }

  bool toolContributesUiReferences(
    String toolName, {
    required bool allowLocationContext,
    ToolMetadataRegistry? toolMetadataRegistry,
  }) {
    final normalized = toolName.trim();
    if (normalized.isEmpty) return false;
    return toolMetadataRegistry?.contributesUiReferences(
          normalized,
          allowLocationContext: allowLocationContext,
        ) ??
        false;
  }

  String resolveExperimentBucket(Map<String, dynamic> hint, String fallback) {
    final raw = (hint['experimentBucket'] as String?)?.trim() ?? '';
    if (raw.isNotEmpty) return raw;
    return fallback;
  }

  bool hasStructuredContent(Map<String, dynamic> value) {
    for (final item in value.values) {
      if (item is String && item.trim().isNotEmpty) return true;
      if (item is num && item != 0) return true;
      if (item is bool && item) return true;
      if (item is List && item.isNotEmpty) return true;
      if (item is Map && item.isNotEmpty) return true;
    }
    return false;
  }

  bool usedHeuristicFallback(List<AssistantTraceEvent> traces) {
    for (final event in traces) {
      if (event.type != AssistantTraceEventType.assistantDelta) continue;
      final data = event.data ?? const <String, dynamic>{};
      final path = (data['modelPath'] as String?)?.trim() ?? '';
      if (path != 'fallback_local') continue;
      final parsed = LlmResponseParser.parse(event.message);
      if (!parsed.ok) {
        final raw = event.message.trim();
        if (raw.isNotEmpty) return true;
        continue;
      }
      final payload = parsed.json ?? const <String, dynamic>{};
      final diagnostics =
          (payload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      if (diagnostics['heuristicFallbackUsed'] == true) {
        return true;
      }
      final messageKind = parseMessageKind(
        (payload['messageKind'] as String?)?.trim() ?? '',
      );
      final phaseId = (payload['phaseId'] as String?)?.trim() ?? '';
      final turnPhase = (payload['turnPhase'] as String?)?.trim() ?? '';
      final isAnswerLike =
          messageKind == AssistantMessageKind.answer ||
          phaseId == 'answering' ||
          turnPhase == 'answer';
      if (isAnswerLike && parsed.userMarkdown.isNotEmpty) {
        return true;
      }
    }
    return false;
  }

  bool hasDegradedTrace(List<AssistantTraceEvent> traces) {
    for (final event in traces) {
      if (event.type != AssistantTraceEventType.assistantDelta) continue;
      final data = event.data ?? const <String, dynamic>{};
      if (data['degraded'] == true) return true;
    }
    return false;
  }

  List<Map<String, dynamic>> extractWebEvidencePacks(
    List<AssistantToolResultRow> toolResults,
  ) {
    final packs = <Map<String, dynamic>>[];
    for (final item in toolResults) {
      final data = item.dataPayload;
      if (!data.containsKey('coverage') ||
          !data.containsKey('confidence') ||
          !data.containsKey('freshnessHours')) {
        continue;
      }
      packs.add(<String, dynamic>{
        'coverage': _asDouble(data['coverage']),
        'confidence': _asDouble(data['confidence']),
        'freshnessHours': _asDouble(data['freshnessHours']),
        'authorityScore': _asDouble(data['authorityScore']),
        'authoritativeCount': _asDouble(data['authoritativeCount']),
        'totalReferences': _asDouble(data['totalReferences']),
        'qualityScore': _asDouble(data['qualityScore']),
        'freshScore': _asDouble(data['freshScore']),
        'facts': data['facts'] ?? const <Map<String, dynamic>>[],
      });
    }
    return packs;
  }

  Map<String, dynamic> buildDomainResultsForSynthesis(
    List<AssistantTraceEvent> traces,
  ) {
    final toolResults = traces
        .where((e) => e.type == AssistantTraceEventType.toolResult)
        .map(AssistantToolResultRow.fromTraceEvent)
        .toList(growable: false);
    final toolErrors = traces
        .where((e) => e.type == AssistantTraceEventType.toolError)
        .map(
          (e) => <String, dynamic>{
            'message': e.message,
            'data': e.data ?? const <String, dynamic>{},
          },
        )
        .toList(growable: false);
    final webEvidencePacks = extractWebEvidencePacks(toolResults);
    return <String, dynamic>{
      'toolResults': toolResults.map((item) => item.toJson()).toList(growable: false),
      'toolErrors': toolErrors,
      'toolResultCount': toolResults.length,
      'toolErrorCount': toolErrors.length,
      'webEvidencePacks': webEvidencePacks,
    };
  }

  String extractUiMarkdown(Map<String, dynamic> answerPayload) {
    final apv = AssistantAnswerPayloadReadView(answerPayload);
    final resultMap = apv.resultMap;
    final nextAction = (resultMap['nextAction'] as String?)?.trim() ?? '';
    if (nextAction.isNotEmpty &&
        nextAction != AssistantNextAction.answer.wireName &&
        nextAction != AssistantNextAction.abort.wireName) {
      return '';
    }
    final userMd =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          apv.userMarkdownTrimmed,
          allowJsonExtraction: false,
        );
    if (isRenderableAssistantAnswerText(userMd)) {
      return userMd;
    }
    final resultText =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          (resultMap['text'] as String?)?.trim() ?? '',
          allowJsonExtraction: false,
        );
    if (!isRenderableAssistantAnswerText(resultText)) {
      return '';
    }
    return resultText;
  }

  /// 将 LLM 最终文本解析为结构化的 answerPayload Map。
  ///
  /// LLM JSON → [tryParseAssistantTurnOutput()] 类型化对象 → answerPayload Map。
  /// 字段名字符串只在 [tryParseAssistantTurnOutput()] 内出现（见 02-dart-coding §5.1）。
  Map<String, dynamic> parseAnswerPayload({
    required String rawFinalText,
    required List<AssistantTraceEvent> traces,
  }) {
    final parseResult = LlmResponseParser.parse(rawFinalText);
    final parsed = parseResult.json ?? <String, dynamic>{};
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn != null) {
      final json = turn.toJson();
      final result = (json['result'] as Map?)?.cast<String, dynamic>() ??
          <String, dynamic>{'text': rawFinalText};
      final understandingSnapshot = normalizeMap(parsed['understandingSnapshot']);
      final retrievalProcessing = normalizeMap(parsed['retrievalProcessing']);
      final answerProcessing = normalizeMap(parsed['answerProcessing']);
      final historicalThinkingSnapshot = normalizeMap(
        parsed['historicalThinkingSnapshot'],
      );
      final journey = normalizeMap(parsed['journey']);
      final aggregationState = normalizeMap(parsed['aggregationState']);
      final nextAction = turn.decision.nextAction.wireName;
      if (nextAction.isNotEmpty && nextAction != AssistantNextAction.unknown.wireName) {
        result['nextAction'] = nextAction;
      }
      json['result'] = result;
      if (understandingSnapshot.isNotEmpty) {
        json['understandingSnapshot'] = understandingSnapshot;
      }
      if (retrievalProcessing.isNotEmpty) {
        json['retrievalProcessing'] = retrievalProcessing;
      }
      if (answerProcessing.isNotEmpty) {
        json['answerProcessing'] = answerProcessing;
      }
      if (historicalThinkingSnapshot.isNotEmpty) {
        json['historicalThinkingSnapshot'] = historicalThinkingSnapshot;
      }
      if (journey.isNotEmpty) {
        json['journey'] = journey;
      }
      if (aggregationState.isNotEmpty) {
        json['aggregationState'] = aggregationState;
      }
      json['parseStatus'] = parsed.isEmpty ? 'fallback_text' : 'assistant_turn_parsed';
      return json;
    }

    final decisionMap = (parsed['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final resultMap = (parsed['result'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{};
    if ((resultMap['text'] as String?)?.trim().isEmpty ?? true) {
      resultMap['text'] = rawFinalText;
    }

    final fallbackJson = <String, dynamic>{
      'contractId': (parsed['contractId'] as String?)?.trim() ?? '',
      'decision': <String, dynamic>{
        'nextAction': (decisionMap['nextAction'] as String?)?.trim() ?? '',
      },
      'messageKind': (parsed['messageKind'] as String?)?.trim().isNotEmpty == true
          ? (parsed['messageKind'] as String).trim()
          : AssistantMessageKind.fallback.wireName,
      'userMarkdown': (parsed['userMarkdown'] as String?)?.trim() ?? rawFinalText,
      'result': resultMap,
      'displayState': (parsed['displayState'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'evidence': normalizeMapList(parsed['evidence'], textKey: 'text'),
      'reasoningBasis': normalizeMapList(
        parsed['reasoningBasis'],
        textKey: AssistantTurnReasoningBasisItemFields.text,
      ),
      'selfCheck': normalizeMap(parsed['selfCheck']),
      'diagnostics': normalizeMap(parsed['diagnostics']),
      'modelSelfScore': normalizeMap(parsed['modelSelfScore']),
      'askUser': normalizeMap(parsed['askUser']),
      'toolCalls': normalizeToolCalls(parsed['toolCalls']),
      'slotState': normalizeMap(parsed['slotState']),
      'subagentPlan': normalizeMapList(parsed['subagentPlan'], textKey: 'goal'),
      'intentGraph': normalizeMap(parsed['intentGraph']),
      'skillRuns': normalizeMapList(parsed['skillRuns'], textKey: 'goal'),
      'aggregationState': normalizeMap(parsed['aggregationState']),
      'journey': normalizeMap(parsed['journey']),
      'missingContextSlots': normalizeStringList(parsed['missingContextSlots']),
      'fillGuidance': normalizeMapList(
        parsed['fillGuidance'],
        textKey: AssistantTurnFillGuidanceItemFields.guidance,
      ),
      'followupPrompt': (parsed['followupPrompt'] as String?)?.trim() ?? '',
      'phaseId': (parsed['phaseId'] as String?)?.trim() ?? '',
      'actionCode': (parsed['actionCode'] as String?)?.trim() ?? '',
      'reasonCode': (parsed['reasonCode'] as String?)?.trim() ?? '',
      'reasonShort': (parsed['reasonShort'] as String?)?.trim() ?? '',
      'understandingSnapshot': normalizeMap(parsed['understandingSnapshot']),
      'retrievalProcessing': normalizeMap(parsed['retrievalProcessing']),
      'answerProcessing': normalizeMap(parsed['answerProcessing']),
      'historicalThinkingSnapshot':
          normalizeMap(parsed['historicalThinkingSnapshot']),
      'sessionPreferenceFacts': normalizeMapList(
        parsed['sessionPreferenceFacts'],
        textKey: 'key',
      ),
      'longTermPreferenceFacts': normalizeMapList(
        parsed['longTermPreferenceFacts'],
        textKey: 'key',
      ),
      'parseStatus': parsed.isEmpty ? 'fallback_text' : 'json_parsed',
    };
    return AssistantTurnOutput.fromJson(fallbackJson).toJson();
  }

  bool isRenderableAssistantAnswerText(String text) {
    return AssistantDisplayTextResolver.isRenderableDisplayText(text);
  }

  String traceToolName(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    return (data['toolName'] as String?)?.trim() ?? '';
  }

  List<Map<String, dynamic>> buildContextSlots(
    ContextAssemblyResult contextAssembly,
  ) {
    final sourceStatus =
        (contextAssembly.contextEnvelope['sourceStatus'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final missing =
        (contextAssembly.contextEnvelope['missingSlots'] as List?)
            ?.whereType<String>()
            .toSet() ??
        <String>{};
    return sourceStatus.entries
        .map((entry) {
          final statusText = entry.value.toString().toLowerCase();
          final status = missing.contains(entry.key) || statusText == 'missing'
              ? 'need_query'
              : (statusText == 'empty' ? 'unavailable' : 'ready');
          return <String, dynamic>{
            'slotId': entry.key,
            'status': status,
            'source': 'context_assembly',
            'value': entry.value,
            'queryPlan': status == 'need_query'
                ? <String, dynamic>{
                    'reason': 'slot_missing',
                    'singleTopicQuery': entry.key,
                  }
                : null,
          };
        })
        .toList(growable: false);
  }

  List<String> buildNextActions(
    ContextAssemblyResult contextAssembly,
    SynthesisReadinessResult synthesisReadiness,
  ) {
    final out = <String>[];
    for (final task in contextAssembly.fillTasks) {
      out.add(task.reason);
    }
    if (!synthesisReadiness.ready && synthesisReadiness.replanTask != null) {
      out.add(synthesisReadiness.reason);
    }
    return out;
  }

  String resolveDisplayPlainText({
    required Map<String, dynamic> answerPayload,
    required String displayMarkdown,
  }) {
    final apv = AssistantAnswerPayloadReadView(answerPayload);
    final normalizedMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          displayMarkdown,
          allowJsonExtraction: false,
        );
    final plainFromMarkdown = sanitizeDisplayPlainCandidate(
      AssistantDisplayTextResolver.stripMarkdown(normalizedMarkdown),
    );
    final result = apv.resultMap;
    final directText = sanitizeDisplayPlainCandidate(
      (result['text'] as String?)?.trim() ?? '',
    );
    if (plainFromMarkdown.isNotEmpty) return plainFromMarkdown;
    if (directText.isNotEmpty) {
      return directText;
    }
    final summaryText = sanitizeDisplayPlainCandidate(
      (result['summary'] as String?)?.trim() ?? '',
    ).trim();
    if (summaryText.isNotEmpty) return summaryText;
    final interpretationText = sanitizeDisplayPlainCandidate(
      (result['interpretation'] as String?)?.trim() ?? '',
    ).trim();
    if (interpretationText.isNotEmpty) return interpretationText;
    return normalizedMarkdown.trim();
  }

  String _safeString(Object? raw) => raw?.toString() ?? '';

  double _asDouble(Object? raw) {
    if (raw is num) return raw.toDouble();
    return double.tryParse(raw?.toString() ?? '') ?? 0;
  }

  String sanitizeDisplayPlainCandidate(String value) {
    return value.trim();
  }
}

import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/model_output_extractors.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';

/// Understand: intent graph, domain selection, dialogue round script.
class UnderstandPhase implements Phase {
  UnderstandPhase({
    this.domainRouter,
    this.dialogueStateRuntime,
    this.modeDecider = const ModeDecider(),
    this.runtime,
    this.templateCatalogRuntime,
  });

  final AssistantDomainRouter? domainRouter;
  final DialogueStateRuntime? dialogueStateRuntime;
  final ModeDecider modeDecider;
  final ReactRuntime? runtime;
  final TemplateCatalogRuntime? templateCatalogRuntime;

  @override
  String get phaseId => 'understand';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = input.request is AssistantRunRequest
        ? input.request as AssistantRunRequest
        : AssistantRunRequest.fromJson((input.request as dynamic).toJson());
    final bootstrapContext = input.state.bootstrapContext;
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final mergedScopeHint = _mergedScopeHint(
      request: request,
      bootstrapContext: bootstrapContext,
    );
    if (latestUserQuery.isEmpty) {
      return PhaseOutput(state: input.state);
    }

    final hintedIntentRaw =
        (request.contextScopeHint['precomputedIntentGraph'] as Map?)
            ?.cast<String, dynamic>() ??
        (request.contextScopeHint['intentGraph'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (hintedIntentRaw.isNotEmpty) {
      try {
        final hinted = IntentGraph.fromJson(hintedIntentRaw);
        final normalizedIntent = _normalizeIntentGraph(
          request: request,
          intentGraph: hinted,
          fallbackDomainId: hinted.primarySkill.trim().isNotEmpty
              ? hinted.primarySkill.trim()
              : _domainRouter.fallbackDomainId,
          recallResult: bootstrapContext?.recallResult,
          bootstrapContext: bootstrapContext,
          previousRunArtifacts: input.state.previousRunArtifacts,
        );
        final domainId = normalizedIntent.primarySkill.trim().isNotEmpty
            ? normalizedIntent.primarySkill.trim()
            : _domainRouter.fallbackDomainId;
        final dialogueRoundScript = await _dialogueStateRuntime
            .buildRoundScript(
              domainId: domainId,
              userQuery: latestUserQuery,
              contextScopeHint: mergedScopeHint,
              forceRefreshCatalog:
                  bootstrapContext?.forceRefreshCatalog ?? false,
            );
        final modeDecision = modeDecider.decide(
          intentGraph: normalizedIntent,
          recallResult: bootstrapContext?.recallResult,
        );
        return PhaseOutput(
          state: input.state.copyWith(
            intentGraph: normalizedIntent,
            queryTasks: normalizedIntent.queryTasks,
            dialogueRoundScript: dialogueRoundScript,
            executionPreparation: AssistantExecutionPreparation(
              domainId: domainId,
              modeDecision: modeDecision,
            ),
          ),
        );
      } catch (_) {
        // Fall through to model understanding.
      }
    }

    final modelIntentGraph = await _resolveIntentGraphWithModel(
      request: request,
      bootstrapContext: bootstrapContext,
      latestUserQuery: latestUserQuery,
      previousRunArtifacts: input.state.previousRunArtifacts,
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
    );
    if (modelIntentGraph != null) {
      final normalizedIntent = _normalizeIntentGraph(
        request: request,
        intentGraph: modelIntentGraph,
        fallbackDomainId: modelIntentGraph.primarySkill.trim().isNotEmpty
            ? modelIntentGraph.primarySkill.trim()
            : _domainRouter.fallbackDomainId,
        recallResult: bootstrapContext?.recallResult,
        bootstrapContext: bootstrapContext,
        previousRunArtifacts: input.state.previousRunArtifacts,
      );
      final domainId = normalizedIntent.primarySkill.trim().isNotEmpty
          ? normalizedIntent.primarySkill.trim()
          : _domainRouter.fallbackDomainId;
      final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
        domainId: domainId,
        userQuery: latestUserQuery,
        contextScopeHint: mergedScopeHint,
        forceRefreshCatalog: bootstrapContext?.forceRefreshCatalog ?? false,
      );
      final modeDecision = modeDecider.decide(
        intentGraph: normalizedIntent,
        recallResult: bootstrapContext?.recallResult,
      );
      return PhaseOutput(
        state: input.state.copyWith(
          intentGraph: normalizedIntent,
          queryTasks: normalizedIntent.queryTasks,
          dialogueRoundScript: dialogueRoundScript,
          executionPreparation: AssistantExecutionPreparation(
            domainId: domainId,
            modeDecision: modeDecision,
          ),
        ),
      );
    }

    final intentGraph = _buildFallbackIntentGraph(
      request: request,
      bootstrapContext: bootstrapContext,
      latestUserQuery: latestUserQuery,
      fallbackDomainId: _domainRouter.fallbackDomainId,
      recallResult: bootstrapContext?.recallResult,
      previousRunArtifacts: input.state.previousRunArtifacts,
    );
    final domainId = intentGraph.primarySkill.trim().isNotEmpty
        ? intentGraph.primarySkill.trim()
        : _domainRouter.fallbackDomainId;
    final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: domainId,
      userQuery: latestUserQuery,
      contextScopeHint: mergedScopeHint,
      forceRefreshCatalog: bootstrapContext?.forceRefreshCatalog ?? false,
    );
    final modeDecision = modeDecider.decide(
      intentGraph: intentGraph,
      recallResult: bootstrapContext?.recallResult,
    );

    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: intentGraph,
        queryTasks: intentGraph.queryTasks,
        dialogueRoundScript: dialogueRoundScript,
        executionPreparation: AssistantExecutionPreparation(
          domainId: domainId,
          modeDecision: modeDecision,
        ),
      ),
    );
  }

  IntentGraph _normalizeIntentGraph({
    required AssistantRunRequest request,
    required IntentGraph intentGraph,
    required String fallbackDomainId,
    required RecallResult? recallResult,
    required AssistantBootstrapContext? bootstrapContext,
    required RunArtifacts? previousRunArtifacts,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final previousIntentGraph = bootstrapContext?.previousIntentGraph;
    final primarySkill = intentGraph.primarySkill.trim().isNotEmpty
        ? intentGraph.primarySkill.trim()
        : continuationActive &&
              previousIntentGraph?.primarySkill.trim().isNotEmpty == true
        ? previousIntentGraph!.primarySkill.trim()
        : fallbackDomainId;
    final secondarySkills = intentGraph.secondarySkills
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty && item != primarySkill)
        .toList(growable: false);
    final mode =
        (intentGraph.globalConstraints['mode'] as String?)?.trim() ?? '';
    final normalizedProblemClass = _normalizeProblemClass(
      raw: intentGraph.problemClass.wireName,
      primarySkill: primarySkill,
      mode: mode,
      secondarySkills: secondarySkills,
      request: request,
    );
    final effectiveAuthorityDomains = intentGraph.authorityDomains.isNotEmpty
        ? intentGraph.authorityDomains
        : _hintedAuthorityDomains(
            request: request,
            bootstrapContext: bootstrapContext,
            continuationActive: continuationActive,
          );
    final effectiveFreshnessHoursMax = intentGraph.freshnessHoursMax > 0
        ? intentGraph.freshnessHoursMax
        : _hintedFreshnessHoursMax(
            request: request,
            bootstrapContext: bootstrapContext,
            continuationActive: continuationActive,
          );
    final effectiveAnswerShape =
        intentGraph.answerShape != AnswerShape.unspecified
        ? intentGraph.answerShape
        : continuationActive &&
              previousIntentGraph?.answerShape != AnswerShape.unspecified
        ? previousIntentGraph!.answerShape
        : intentGraph.answerShape;
    final effectiveFreshnessNeed =
        intentGraph.freshnessNeed != FreshnessNeed.unspecified
        ? intentGraph.freshnessNeed
        : continuationActive &&
              previousIntentGraph?.freshnessNeed != FreshnessNeed.unspecified
        ? previousIntentGraph!.freshnessNeed
        : intentGraph.freshnessNeed;
    return IntentGraph(
      userGoal: intentGraph.userGoal.trim().isNotEmpty
          ? intentGraph.userGoal.trim()
          : (request.messages.isNotEmpty ? request.messages.last.content : ''),
      problemShape: intentGraph.problemShape == ProblemShape.unknown
          ? (secondarySkills.isEmpty
                ? ProblemShape.singleSkill
                : ProblemShape.multiSkill)
          : intentGraph.problemShape,
      primarySkill: primarySkill,
      problemClass: parseProblemClass(normalizedProblemClass),
      inferredMotive: intentGraph.inferredMotive.trim(),
      secondarySkills: secondarySkills,
      targetObject: intentGraph.targetObject.trim().isNotEmpty
          ? intentGraph.targetObject.trim()
          : (continuationActive
                ? previousIntentGraph?.targetObject.trim() ?? ''
                : ''),
      userJobToBeDone: intentGraph.userJobToBeDone.trim().isNotEmpty
          ? intentGraph.userJobToBeDone.trim()
          : (continuationActive
                ? previousIntentGraph?.userJobToBeDone.trim() ?? ''
                : ''),
      hardConstraints: intentGraph.hardConstraints.isNotEmpty
          ? intentGraph.hardConstraints
          : (continuationActive
                ? previousIntentGraph?.hardConstraints ?? const <String>[]
                : const <String>[]),
      softConstraints: intentGraph.softConstraints.isNotEmpty
          ? intentGraph.softConstraints
          : (continuationActive
                ? previousIntentGraph?.softConstraints ?? const <String>[]
                : const <String>[]),
      excludedScopes: intentGraph.excludedScopes.isNotEmpty
          ? intentGraph.excludedScopes
          : (continuationActive
                ? previousIntentGraph?.excludedScopes ?? const <String>[]
                : const <String>[]),
      freshnessNeed: effectiveFreshnessNeed,
      answerShape: effectiveAnswerShape,
      mustVerifyClaims: intentGraph.mustVerifyClaims,
      requiresExternalEvidence:
          intentGraph.requiresExternalEvidence ||
          request.contextScopeHint['requiresExternalEvidence'] == true ||
          (continuationActive &&
              previousIntentGraph?.requiresExternalEvidence == true),
      entityAnchors: intentGraph.entityAnchors.isNotEmpty
          ? intentGraph.entityAnchors
          : (continuationActive
                ? previousIntentGraph?.entityAnchors ?? const <String>[]
                : const <String>[]),
      negativeKeywords: intentGraph.negativeKeywords.isNotEmpty
          ? intentGraph.negativeKeywords
          : (continuationActive
                ? previousIntentGraph?.negativeKeywords ?? const <String>[]
                : const <String>[]),
      queryNormalization: _normalizeQueryNormalization(
        queryNormalization: intentGraph.queryNormalization,
        latestUserQuery: request.messages.isNotEmpty
            ? request.messages.last.content
            : '',
        bootstrapContext: bootstrapContext,
      ),
      queryTasks: intentGraph.queryTasks,
      contextSlots: _mergeContextSlots(
        current: intentGraph.contextSlots,
        bootstrapContext: bootstrapContext,
        previousIntentGraph: previousIntentGraph,
        previousRunArtifacts: previousRunArtifacts,
        continuationActive: continuationActive,
      ),
      globalConstraints: _mergeGlobalConstraints(
        current: intentGraph.globalConstraints,
        bootstrapContext: bootstrapContext,
        previousIntentGraph: previousIntentGraph,
        continuationActive: continuationActive,
      ),
      clarificationNeeded: intentGraph.clarificationNeeded,
      recallResult: recallResult,
      authorityDomains: effectiveAuthorityDomains,
      freshnessHoursMax: effectiveFreshnessHoursMax,
    );
  }

  String _normalizeProblemClass({
    required String raw,
    required String primarySkill,
    required String mode,
    required List<String> secondarySkills,
    required AssistantRunRequest request,
  }) {
    return _normalizeProblemClassForQuery(
      raw: raw,
      primarySkill: primarySkill,
      mode: mode,
      secondarySkills: secondarySkills,
      queryText: request.messages.isNotEmpty
          ? request.messages.last.content
          : '',
    );
  }

  String _normalizeProblemClassForQuery({
    required String raw,
    required String primarySkill,
    required String mode,
    required List<String> secondarySkills,
    required String queryText,
  }) {
    final normalized = parseProblemClass(raw.trim()).wireName;
    return normalized.isNotEmpty ? normalized : ProblemClass.general.wireName;
  }

  Future<IntentGraph?> _resolveIntentGraphWithModel({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required String latestUserQuery,
    required RunArtifacts? previousRunArtifacts,
    required String runId,
    required String traceId,
    void Function(dynamic event)? onTraceEvent,
  }) async {
    final runtime = this.runtime;
    if (runtime == null) return null;
    final templateRuntime = _templateCatalogRuntime;
    await templateRuntime.ensureLoaded(
      forceRefresh: bootstrapContext?.forceRefreshCatalog ?? false,
    );
    final templateVersion = templateRuntime.latestVersionFor(
      'planner.global_plan',
      fallback: '',
    );
    final contextEnvelopeJson = jsonEncode(
      inputSafeContextEnvelope(bootstrapContext, request, previousRunArtifacts),
    );
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode.wireName ?? '';
    final problemClass =
        bootstrapContext?.contextContinuityPolicy.problemClass.trim() ?? '';
    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        <String, dynamic>{
          'role': 'system',
          'content': _buildIntentPlanningContext(
            query: latestUserQuery,
            bootstrapContext: bootstrapContext,
            continuityMode: continuityMode,
            problemClass: problemClass,
          ),
        },
        for (final item in request.messages)
          <String, dynamic>{'role': item.role, 'content': item.content},
      ],
      maxIterations: 1,
      goal: latestUserQuery,
      availableToolNamesOverride: const <String>[],
      templateId: 'planner.global_plan',
      templateVersion: templateVersion,
      templateContext: request.contextScopeHint,
      templateVariables: <String, dynamic>{
        'userQuery': latestUserQuery,
        'skillCatalog': bootstrapContext?.skillCatalog ?? '',
        'contextEnvelope': contextEnvelopeJson,
        'userProfileSnapshot': jsonEncode(request.userProfileSnapshot),
        'historicalRetrievalFeedback': jsonEncode(
          request.contextScopeHint['historicalRetrievalFeedback'] ??
              const <String, dynamic>{},
        ),
        'domainLearningSignals': jsonEncode(
          request.contextScopeHint['domainLearningSignals'] ??
              const <String, dynamic>{},
        ),
        'skillExecutionShell': const SkillExecutionShell().toJson(),
      },
      sessionId: bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent == null
          ? null
          : (event) => onTraceEvent(
              event.copyWith(visibility: TraceVisibility.internal),
            ),
      callOptions: const LlmCallOptions(
        temperature: 0.2,
        maxTokens: 1400,
        forceJsonObject: true,
        timeoutSeconds: 20,
      ),
    );
    final parsed =
        LlmResponseParser.parse(result.finalText).json ?? <String, dynamic>{};
    final turn = tryParseAssistantTurnOutput(parsed);
    return extractIntentGraphFromModelPayload(parsed, parsedTurn: turn);
  }

  Map<String, dynamic> inputSafeContextEnvelope(
    AssistantBootstrapContext? bootstrapContext,
    AssistantRunRequest request,
    RunArtifacts? previousRunArtifacts,
  ) {
    final envelope = bootstrapContext == null
        ? const <String, dynamic>{}
        : <String, dynamic>{
            'historySummary': bootstrapContext.historySummary,
            'recalledTexts': bootstrapContext.recalledTexts,
            if (bootstrapContext.previousIntentGraph != null)
              'previousIntentGraph': bootstrapContext.previousIntentGraph!
                  .toJson(),
            if (bootstrapContext.previousAnswerSummary.isNotEmpty)
              'previousAnswerSummary': bootstrapContext.previousAnswerSummary,
            'continuityPolicy': bootstrapContext.contextContinuityPolicy
                .toJson(),
            if (bootstrapContext.continuityOverrideSlots.isNotEmpty)
              'continuityOverrideSlots':
                  bootstrapContext.continuityOverrideSlots,
            if (previousRunArtifacts != null)
              'previousSlotState': previousRunArtifacts.slotState.toJson(),
            if (previousRunArtifacts?.domainPolicyBundle != null)
              'previousDomainPolicyBundle': previousRunArtifacts
                  ?.domainPolicyBundle
                  ?.toJson(),
          };
    return <String, dynamic>{
      ...envelope,
      'deviceProfile': request.deviceProfile,
      'deviceModel': request.deviceModel,
      'deviceOs': request.deviceOs,
      'gpsLocation': request.gpsLocation,
      'contextScopeHint': request.contextScopeHint,
    };
  }

  String _buildIntentPlanningContext({
    required String query,
    required AssistantBootstrapContext? bootstrapContext,
    required String continuityMode,
    required String problemClass,
  }) {
    return [
      '当前用户问题：$query',
      if (bootstrapContext?.historySummary.trim().isNotEmpty == true)
        '最近历史摘要：${bootstrapContext!.historySummary.trim()}',
      if (continuityMode.isNotEmpty) '连续性判断：$continuityMode',
      if (problemClass.isNotEmpty) '已知问题类型提示：$problemClass',
      if (bootstrapContext?.previousIntentGraph != null)
        '上一轮意图：${jsonEncode(bootstrapContext!.previousIntentGraph!.toJson())}',
      if (bootstrapContext?.previousAnswerSummary.trim().isNotEmpty == true)
        '上一轮回答摘要：${bootstrapContext!.previousAnswerSummary.trim()}',
      if (bootstrapContext?.continuityOverrideSlots.isNotEmpty == true)
        '用户本轮显式覆盖：${jsonEncode(bootstrapContext!.continuityOverrideSlots)}',
      '请直接输出 assistant_turn JSON，并把结构化意图完整放入 intentGraph。',
    ].join('\n');
  }

  Map<String, dynamic> _mergedScopeHint({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
  }) {
    return <String, dynamic>{
      ...request.contextScopeHint,
      if (bootstrapContext?.continuityOverrideSlots.isNotEmpty == true)
        'continuityOverrideSlots': bootstrapContext!.continuityOverrideSlots,
    };
  }

  IntentGraph _buildFallbackIntentGraph({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required String latestUserQuery,
    required String fallbackDomainId,
    required RecallResult? recallResult,
    required RunArtifacts? previousRunArtifacts,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final previousIntentGraph = bootstrapContext?.previousIntentGraph;
    final hintedProblemClassRaw =
        (request.contextScopeHint['problemClass'] as String?)
                ?.trim()
                .isNotEmpty ==
            true
        ? (request.contextScopeHint['problemClass'] as String).trim()
        : bootstrapContext?.contextContinuityPolicy.problemClass.trim() ?? '';
    final hintedProblemClass = parseProblemClass(hintedProblemClassRaw);
    final problemClass = hintedProblemClassRaw.isEmpty
        ? (continuationActive && previousIntentGraph != null
              ? previousIntentGraph.problemClass
              : ProblemClass.general)
        : hintedProblemClass;
    final primarySkill =
        continuationActive &&
            previousIntentGraph?.primarySkill.trim().isNotEmpty == true
        ? previousIntentGraph!.primarySkill.trim()
        : fallbackDomainId;
    return IntentGraph(
      userGoal: latestUserQuery,
      problemShape:
          continuationActive &&
              previousIntentGraph?.problemShape != ProblemShape.unknown
          ? previousIntentGraph!.problemShape
          : ProblemShape.singleSkill,
      primarySkill: primarySkill,
      problemClass: problemClass,
      inferredMotive: latestUserQuery,
      targetObject: continuationActive
          ? previousIntentGraph?.targetObject ?? ''
          : '',
      userJobToBeDone: continuationActive
          ? previousIntentGraph?.userJobToBeDone ?? ''
          : '',
      hardConstraints: continuationActive
          ? previousIntentGraph?.hardConstraints ?? const <String>[]
          : const <String>[],
      softConstraints: continuationActive
          ? previousIntentGraph?.softConstraints ?? const <String>[]
          : const <String>[],
      excludedScopes: continuationActive
          ? previousIntentGraph?.excludedScopes ?? const <String>[]
          : const <String>[],
      freshnessNeed: continuationActive
          ? previousIntentGraph?.freshnessNeed ?? FreshnessNeed.unspecified
          : FreshnessNeed.unspecified,
      answerShape: continuationActive
          ? previousIntentGraph?.answerShape ?? AnswerShape.unspecified
          : AnswerShape.unspecified,
      mustVerifyClaims: problemClass == ProblemClass.realtimeInfo,
      requiresExternalEvidence:
          request.contextScopeHint['requiresExternalEvidence'] == true ||
          (continuationActive &&
              previousIntentGraph?.requiresExternalEvidence == true),
      entityAnchors: continuationActive
          ? previousIntentGraph?.entityAnchors ?? const <String>[]
          : const <String>[],
      negativeKeywords: continuationActive
          ? previousIntentGraph?.negativeKeywords ?? const <String>[]
          : const <String>[],
      queryNormalization: _normalizeQueryNormalization(
        queryNormalization:
            previousIntentGraph?.queryNormalization ??
            const QueryNormalization(),
        latestUserQuery: latestUserQuery,
        bootstrapContext: bootstrapContext,
      ),
      contextSlots: _mergeContextSlots(
        current: previousIntentGraph?.contextSlots ?? const <String, dynamic>{},
        bootstrapContext: bootstrapContext,
        previousIntentGraph: previousIntentGraph,
        previousRunArtifacts: previousRunArtifacts,
        continuationActive: continuationActive,
      ),
      globalConstraints: _mergeGlobalConstraints(
        current:
            previousIntentGraph?.globalConstraints ?? const <String, dynamic>{},
        bootstrapContext: bootstrapContext,
        previousIntentGraph: previousIntentGraph,
        continuationActive: continuationActive,
      ),
      recallResult: recallResult,
      authorityDomains: _hintedAuthorityDomains(
        request: request,
        bootstrapContext: bootstrapContext,
        continuationActive: continuationActive,
      ),
      freshnessHoursMax: _hintedFreshnessHoursMax(
        request: request,
        bootstrapContext: bootstrapContext,
        continuationActive: continuationActive,
      ),
    );
  }

  bool _isContinuationContext(AssistantBootstrapContext? bootstrapContext) {
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode ??
        ContextContinuityMode.unknown;
    return continuityMode != ContextContinuityMode.unknown &&
        continuityMode != ContextContinuityMode.freshTopic;
  }

  List<String> _hintedAuthorityDomains({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required bool continuationActive,
  }) {
    final fromRequest =
        (request.contextScopeHint['authorityDomains'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (fromRequest.isNotEmpty) return fromRequest;
    if (continuationActive &&
        bootstrapContext?.previousIntentGraph?.authorityDomains.isNotEmpty ==
            true) {
      return bootstrapContext!.previousIntentGraph!.authorityDomains;
    }
    return const <String>[];
  }

  int _hintedFreshnessHoursMax({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required bool continuationActive,
  }) {
    final fromRequest =
        (request.contextScopeHint['freshnessHoursMax'] as num?)?.toInt() ?? 0;
    if (fromRequest > 0) return fromRequest;
    if (continuationActive &&
        (bootstrapContext?.previousIntentGraph?.freshnessHoursMax ?? 0) > 0) {
      return bootstrapContext!.previousIntentGraph!.freshnessHoursMax;
    }
    return 0;
  }

  QueryNormalization _normalizeQueryNormalization({
    required QueryNormalization queryNormalization,
    required String latestUserQuery,
    required AssistantBootstrapContext? bootstrapContext,
  }) {
    final hints = <String>{
      ...queryNormalization.hints.map((item) => item.trim()),
    };
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode.wireName ?? '';
    if (continuityMode.isNotEmpty) {
      hints.add('continuity:$continuityMode');
    }
    return QueryNormalization(
      normalizedQuery: queryNormalization.normalizedQuery.trim().isNotEmpty
          ? queryNormalization.normalizedQuery.trim()
          : latestUserQuery.trim(),
      rewrittenQuery: queryNormalization.rewrittenQuery.trim().isNotEmpty
          ? queryNormalization.rewrittenQuery.trim()
          : latestUserQuery.trim(),
      issues: queryNormalization.issues,
      language: queryNormalization.language,
      hints: hints.where((item) => item.isNotEmpty).toList(growable: false),
    );
  }

  Map<String, dynamic> _mergeContextSlots({
    required Map<String, dynamic> current,
    required AssistantBootstrapContext? bootstrapContext,
    required IntentGraph? previousIntentGraph,
    required RunArtifacts? previousRunArtifacts,
    required bool continuationActive,
  }) {
    final merged = <String, dynamic>{
      if (continuationActive && previousIntentGraph != null)
        ...previousIntentGraph.contextSlots,
      ...current,
    };
    final continuity = bootstrapContext?.contextContinuityPolicy;
    if (continuity != null) {
      merged['continuity'] = <String, dynamic>{
        'mode': continuity.continuityMode.wireName,
        'explicitContinuation': continuity.explicitContinuation,
        'referenceQueries': continuity.referenceQueries,
        if (bootstrapContext?.previousAnswerSummary.isNotEmpty == true)
          'previousAnswerSummary': bootstrapContext!.previousAnswerSummary,
      };
    }
    if (bootstrapContext?.continuityOverrideSlots.isNotEmpty == true) {
      merged['overrideSlots'] = bootstrapContext!.continuityOverrideSlots;
    }
    final slotState = previousRunArtifacts?.slotState;
    if (continuationActive &&
        slotState != null &&
        slotState.slotValues.isNotEmpty) {
      merged['carriedSlotValues'] = _slotSnapshotMap(slotState);
    }
    if (continuationActive &&
        slotState != null &&
        slotState.missingSlots.isNotEmpty) {
      merged['carriedMissingSlots'] = slotState.missingSlots;
    }
    return merged;
  }

  Map<String, dynamic> _mergeGlobalConstraints({
    required Map<String, dynamic> current,
    required AssistantBootstrapContext? bootstrapContext,
    required IntentGraph? previousIntentGraph,
    required bool continuationActive,
  }) {
    final merged = <String, dynamic>{
      if (continuationActive && previousIntentGraph != null)
        ...previousIntentGraph.globalConstraints,
      ...current,
    };
    final continuity = bootstrapContext?.contextContinuityPolicy;
    if (continuity != null) {
      merged['continuityMode'] = continuity.continuityMode.wireName;
      merged['explicitContinuation'] = continuity.explicitContinuation;
      if (continuity.referenceQueries.isNotEmpty) {
        merged['referenceQueries'] = continuity.referenceQueries;
      }
    }
    if (bootstrapContext?.previousAnswerSummary.isNotEmpty == true) {
      merged['previousAnswerSummary'] = bootstrapContext!.previousAnswerSummary;
    }
    return merged;
  }

  Map<String, dynamic> _slotSnapshotMap(SlotStateSnapshot slotState) {
    final slots = <String, dynamic>{};
    for (final entry in slotState.slotValues.entries) {
      final snapshot = entry.value;
      final slotId = snapshot.slotId.trim().isNotEmpty
          ? snapshot.slotId.trim()
          : entry.key.trim();
      if (slotId.isEmpty) continue;
      slots[slotId] = <String, dynamic>{
        'value': snapshot.value,
        'status': snapshot.status.wireName,
        'source': snapshot.source,
        if (snapshot.evidenceIds.isNotEmpty)
          'evidenceIds': snapshot.evidenceIds,
      };
    }
    return slots;
  }

  AssistantDomainRouter get _domainRouter =>
      domainRouter ?? AssistantDomainRouter();

  DialogueStateRuntime get _dialogueStateRuntime =>
      dialogueStateRuntime ?? DialogueStateRuntime();

  TemplateCatalogRuntime get _templateCatalogRuntime =>
      templateCatalogRuntime ?? TemplateCatalogRuntime();
}

import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_trace_event.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/model_output_extractors.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/understanding_user_facing_summary.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
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
      allowLocationHints:
          bootstrapContext?.contextContinuityPolicy.allowLocationHints ?? false,
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
        final understandingSnapshot = _fallbackUnderstandingSnapshot(
          intentGraph: normalizedIntent,
          latestUserQuery: latestUserQuery,
        );
        _emitUnderstandingSnapshot(
          input: input,
          snapshot: understandingSnapshot,
        );
        return PhaseOutput(
          state: input.state.copyWith(
            intentGraph: normalizedIntent,
            understandingSnapshot: understandingSnapshot,
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

    final modelUnderstanding = await _resolveIntentGraphWithModel(
      request: request,
      bootstrapContext: bootstrapContext,
      latestUserQuery: latestUserQuery,
      previousRunArtifacts: input.state.previousRunArtifacts,
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
      processEmitter: ProcessTimelineEmitter(
        runId: input.runId,
        traceId: input.traceId,
        onTraceEvent: input.onTraceEvent,
      ),
    );
    if (modelUnderstanding != null) {
      final modelIntentGraph = modelUnderstanding.intentGraph;
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
      final understandingSnapshot = modelUnderstanding.understandingSnapshot;
      _emitUnderstandingSnapshot(input: input, snapshot: understandingSnapshot);
      return PhaseOutput(
        state: input.state.copyWith(
          intentGraph: normalizedIntent,
          understandingSnapshot: understandingSnapshot,
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
    final understandingSnapshot = _fallbackUnderstandingSnapshot(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
    );
    _emitUnderstandingSnapshot(input: input, snapshot: understandingSnapshot);

    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: intentGraph,
        understandingSnapshot: understandingSnapshot,
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
              previousIntentGraph != null &&
              previousIntentGraph.answerShape != AnswerShape.unspecified
        ? previousIntentGraph.answerShape
        : intentGraph.answerShape;
    final effectiveFreshnessNeed =
        intentGraph.freshnessNeed != FreshnessNeed.unspecified
        ? intentGraph.freshnessNeed
        : continuationActive &&
              previousIntentGraph != null &&
              previousIntentGraph.freshnessNeed != FreshnessNeed.unspecified
        ? previousIntentGraph.freshnessNeed
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

  Future<_ResolvedUnderstanding?> _resolveIntentGraphWithModel({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required String latestUserQuery,
    required RunArtifacts? previousRunArtifacts,
    required String runId,
    required String traceId,
    void Function(dynamic event)? onTraceEvent,
    required ProcessTimelineEmitter processEmitter,
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
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode.wireName ?? '';
    final problemClass =
        bootstrapContext?.contextContinuityPolicy.problemClass.trim() ?? '';
    final sharedContextJson = jsonEncode(
      _plannerSharedContextPayload(
        bootstrapContext: bootstrapContext,
        request: request,
        previousRunArtifacts: previousRunArtifacts,
      ),
    );
    final currentRuntimeStateJson = jsonEncode(
      _plannerCurrentRuntimeStatePayload(
        bootstrapContext: bootstrapContext,
        request: request,
        previousRunArtifacts: previousRunArtifacts,
        continuityMode: continuityMode,
        problemClass: problemClass,
      ),
    );
    final dialogueContinuityJson = jsonEncode(
      _plannerDialogueContinuityPayload(
        bootstrapContext: bootstrapContext,
        request: request,
        previousRunArtifacts: previousRunArtifacts,
        continuityMode: continuityMode,
        problemClass: problemClass,
      ),
    );
    final mergedScopeHint = _mergedScopeHint(
      request: request,
      bootstrapContext: bootstrapContext,
      allowLocationHints:
          bootstrapContext?.contextContinuityPolicy.allowLocationHints ?? false,
    );
    final plannerMessages = _plannerMessages(
      request: request,
      bootstrapContext: bootstrapContext,
    );
    final plannerMessagesPayload = <Map<String, dynamic>>[
      <String, dynamic>{
        'role': 'system',
        'content': _buildIntentPlanningContext(
          continuityMode: continuityMode,
          problemClass: problemClass,
        ),
      },
      for (final item in plannerMessages)
        <String, dynamic>{'role': item.role, 'content': item.content},
    ];
    final plannerTemplateVars = <String, dynamic>{
      'userQuery': latestUserQuery,
      'skillCatalog': bootstrapContext?.skillCatalog ?? '',
      'sharedContext': sharedContextJson,
      'currentRuntimeState': currentRuntimeStateJson,
      'dialogueContinuity': dialogueContinuityJson,
    };
    void forwardTrace(AssistantTraceEvent event) {
      onTraceEvent?.call(event.copyWith(visibility: TraceVisibility.internal));
      if (event.type == AssistantTraceEventType.thinkingProgress &&
          event.data?['streaming'] == true &&
          event.data?['extracted'] == true &&
          event.data?['fieldPath'] ==
              'understandingSnapshot.userFacingSummary') {
        processEmitter.pushDelta(
          stepId: ProcessStepId.understanding,
          scope: UserEventScope.root,
          delta: event.message,
          phaseId: 'understanding',
          actionCode: 'frame_problem',
          reasonCode: 'align_goal',
          payload: const <String, dynamic>{
            'fieldPath': 'understandingSnapshot.userFacingSummary',
          },
        );
      }
    }

    var rawOutput = await runtime.streamStructuredOutput(
      messages: plannerMessagesPayload,
      onDelta: (_) {},
      streamJsonFieldPaths: const <String>[
        'understandingSnapshot.userFacingSummary',
      ],
      templateContext: mergedScopeHint,
      templateVariables: plannerTemplateVars,
      templateId: 'planner.global_plan',
      templateVersion: templateVersion,
      sessionId: bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent == null ? null : forwardTrace,
      streamTraceStage: 'understanding',
      structuredPhaseId: 'understanding',
      emitVisibleStreamTrace: false,
    );
    if (rawOutput.trim().isEmpty) {
      final fallbackResult = await runtime.run(
        messages: plannerMessagesPayload,
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: 'planner.global_plan',
        templateVersion: templateVersion,
        templateContext: mergedScopeHint,
        templateVariables: plannerTemplateVars,
        sessionId: bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent == null ? null : forwardTrace,
        callOptions: const LlmCallOptions(
          temperature: 0.2,
          maxTokens: 1400,
          forceJsonObject: true,
          timeoutSeconds: 20,
          streamJsonFieldPaths: <String>[
            'understandingSnapshot.userFacingSummary',
          ],
        ),
      );
      rawOutput = fallbackResult.finalText;
    }
    final parsed = LlmResponseParser.parse(rawOutput).json ?? <String, dynamic>{};
    final turn = tryParseAssistantTurnOutput(parsed);
    final intentGraph = extractIntentGraphFromModelPayload(
      parsed,
      parsedTurn: turn,
    );
    if (intentGraph == null) return null;
    return _ResolvedUnderstanding(
      intentGraph: intentGraph,
      understandingSnapshot: _normalizeUnderstandingSnapshot(
        snapshot: parsed['understandingSnapshot'] is Map
            ? RunArtifactsUnderstandingSnapshot.fromJson(
                (parsed['understandingSnapshot'] as Map)
                    .cast<String, dynamic>(),
              )
            : const RunArtifactsUnderstandingSnapshot(),
        intentGraph: intentGraph,
        latestUserQuery: latestUserQuery,
      ),
    );
  }

  RunArtifactsUnderstandingSnapshot _fallbackUnderstandingSnapshot({
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) {
    final concernPoints = <String>[
      ...intentGraph.hardConstraints.map((item) => item.trim()),
      ...intentGraph.softConstraints.map((item) => item.trim()),
    ].where((item) => item.isNotEmpty).take(3).toList(growable: false);
    final queryDesignSummary = intentGraph.queryTasks.isNotEmpty
        ? '先按${intentGraph.queryTasks.take(2).map((item) => item.effectiveLabel.trim()).where((item) => item.isNotEmpty).join('、')}这几路信息分开核对。'
        : '先把最影响结论的关键信息拆开核对。';
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: intentGraph.userGoal.trim().isNotEmpty
          ? intentGraph.userGoal.trim()
          : latestUserQuery,
      userFacingSummary: buildUnderstandingUserFacingSummary(
        intentSummary: intentGraph.userGoal.trim().isNotEmpty
            ? intentGraph.userGoal.trim()
            : latestUserQuery,
        concernPoints: concernPoints,
        queryDesignSummary: queryDesignSummary,
      ),
      concernPoints: concernPoints,
      emotionSignal: 'neutral',
      queryDesignSummary: queryDesignSummary,
      queryGroups: _buildUnderstandingQueryGroups(intentGraph.queryTasks),
    );
  }

  RunArtifactsUnderstandingSnapshot _normalizeUnderstandingSnapshot({
    required RunArtifactsUnderstandingSnapshot snapshot,
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) {
    final normalizedIntent = snapshot.intentSummary.trim().isNotEmpty
        ? snapshot.intentSummary.trim()
        : (intentGraph.userGoal.trim().isNotEmpty
              ? intentGraph.userGoal.trim()
              : latestUserQuery);
    final normalizedConcernPoints = snapshot.concernPoints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .take(3)
        .toList(growable: false);
    final normalizedQueryDesign = snapshot.queryDesignSummary.trim().isNotEmpty
        ? snapshot.queryDesignSummary.trim()
        : _fallbackUnderstandingSnapshot(
            intentGraph: intentGraph,
            latestUserQuery: latestUserQuery,
          ).queryDesignSummary;
    final normalizedQueryGroups = snapshot.queryGroups.isNotEmpty
        ? snapshot.queryGroups
        : _buildUnderstandingQueryGroups(intentGraph.queryTasks);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: normalizedIntent,
      userFacingSummary: snapshot.userFacingSummary.trim().isNotEmpty
          ? snapshot.userFacingSummary.trim()
          : buildUnderstandingUserFacingSummary(
              intentSummary: normalizedIntent,
              concernPoints: normalizedConcernPoints,
              queryDesignSummary: normalizedQueryDesign,
            ),
      concernPoints: normalizedConcernPoints,
      emotionSignal: snapshot.emotionSignal,
      queryDesignSummary: normalizedQueryDesign,
      queryGroups: normalizedQueryGroups,
      assumptions: snapshot.assumptions,
      mismatchSignal: snapshot.mismatchSignal,
      carryForwardFacts: snapshot.carryForwardFacts,
      discardedAssumptions: snapshot.discardedAssumptions,
    );
  }

  List<RunArtifactsUnderstandingQueryGroup> _buildUnderstandingQueryGroups(
    List<QueryTask> queryTasks,
  ) {
    final grouped = <String, List<String>>{};
    final reasons = <String, String>{};
    for (final task in queryTasks) {
      final dimension = task.dimensionLabel.trim().isNotEmpty
          ? task.dimensionLabel.trim()
          : (task.effectiveLabel.trim().isNotEmpty
                ? task.effectiveLabel.trim()
                : '综合');
      final query = task.query.trim();
      if (query.isEmpty) {
        continue;
      }
      grouped.putIfAbsent(dimension, () => <String>[]).add(query);
      reasons[dimension] = task.label.trim();
    }
    return grouped.entries
        .map(
          (entry) => RunArtifactsUnderstandingQueryGroup(
            dimension: entry.key,
            queries: entry.value.toSet().toList(growable: false),
            why: reasons[entry.key]?.trim() ?? '',
          ),
        )
        .toList(growable: false);
  }

  void _emitUnderstandingSnapshot({
    required PhaseInput input,
    required RunArtifactsUnderstandingSnapshot snapshot,
  }) {
    final detail = buildUnderstandingDetail(snapshot.concernPoints);
    ProcessTimelineEmitter(
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
    ).commit(
      stepId: ProcessStepId.understanding,
      scope: UserEventScope.root,
      headline: snapshot.userFacingSummary.trim(),
      detail: detail,
      phaseId: 'understanding',
      actionCode: 'frame_problem',
      reasonCode: 'align_goal',
      payload: <String, dynamic>{
        'summary': snapshot.userFacingSummary.trim(),
        'understandingSnapshot': snapshot.toJson(),
      },
    );
  }

  Map<String, dynamic> inputSafeContextEnvelope(
    AssistantBootstrapContext? bootstrapContext,
    AssistantRunRequest request,
    RunArtifacts? previousRunArtifacts,
  ) {
    final continuityPolicy =
        bootstrapContext?.contextContinuityPolicy ??
        const ContextContinuityPolicy();
    final sanitizedScopeHint = _sanitizePlannerScopeHint(
      request.contextScopeHint,
      allowLocationHints: continuityPolicy.allowLocationHints,
    );
    return <String, dynamic>{
      'recalledTexts':
          continuityPolicy.allowLongtermMemory && bootstrapContext != null
          ? bootstrapContext.recalledTexts
          : const <String>[],
      'deviceProfile': request.deviceProfile,
      'deviceModel': request.deviceModel,
      'deviceOs': request.deviceOs,
      'gpsLocation': continuityPolicy.allowLocationHints
          ? request.gpsLocation
          : const <String, dynamic>{},
      'contextScopeHint': sanitizedScopeHint,
    };
  }

  Map<String, dynamic> _plannerSharedContextPayload({
    required AssistantBootstrapContext? bootstrapContext,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
  }) {
    return <String, dynamic>{
      'contextEnvelope': inputSafeContextEnvelope(
        bootstrapContext,
        request,
        previousRunArtifacts,
      ),
      'userProfileSnapshot': request.userProfileSnapshot,
      'historicalRetrievalFeedback':
          (request.contextScopeHint['historicalRetrievalFeedback'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'domainLearningSignals':
          (request.contextScopeHint['domainLearningSignals'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    };
  }

  Map<String, dynamic> _plannerCurrentRuntimeStatePayload({
    required AssistantBootstrapContext? bootstrapContext,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
    required String continuityMode,
    required String problemClass,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final previousIntentGraph = continuationActive
        ? bootstrapContext?.previousIntentGraph
        : null;
    return <String, dynamic>{
      'dialogueState': <String, dynamic>{
        'continuityMode': continuityMode,
        'problemClassHint': problemClass,
        'continuationActive': continuationActive,
        'sessionId':
            bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
      },
      'slotStateSnapshot': continuationActive
          ? previousRunArtifacts?.slotState.toJson() ??
                const <String, dynamic>{}
          : const <String, dynamic>{},
      'contextSlots': continuationActive
          ? previousIntentGraph?.contextSlots ?? const <String, dynamic>{}
          : const <String, dynamic>{},
      'domainPolicyBundle': continuationActive
          ? previousRunArtifacts?.domainPolicyBundle?.toJson() ??
                const <String, dynamic>{}
          : const <String, dynamic>{},
      'skillExecutionShell': const SkillExecutionShell().toJson(),
    };
  }

  Map<String, dynamic> _plannerDialogueContinuityPayload({
    required AssistantBootstrapContext? bootstrapContext,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
    required String continuityMode,
    required String problemClass,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final allowHistorySummary =
        continuationActive &&
        bootstrapContext?.contextContinuityPolicy.allowHistorySummary == true;
    final previousUnderstandingSnapshot =
        continuationActive &&
            bootstrapContext != null &&
            _hasStructuredContent(
              bootstrapContext.previousUnderstandingSnapshot.toJson(),
            )
        ? bootstrapContext.previousUnderstandingSnapshot.toJson()
        : const <String, dynamic>{};
    final previousAnswerProcessing =
        continuationActive &&
            bootstrapContext != null &&
            _hasStructuredContent(
              bootstrapContext.previousAnswerProcessing.toJson(),
            )
        ? bootstrapContext.previousAnswerProcessing.toJson()
        : const <String, dynamic>{};
    final historicalThinkingSnapshot =
        continuationActive &&
            bootstrapContext != null &&
            _hasStructuredContent(
              bootstrapContext.historicalThinkingSnapshot.toJson(),
            )
        ? bootstrapContext.historicalThinkingSnapshot.toJson()
        : const <String, dynamic>{};
    return <String, dynamic>{
      'continuityMode': continuityMode,
      'problemClassHint': problemClass,
      'historySummary': allowHistorySummary
          ? bootstrapContext?.historySummary ?? ''
          : '',
      'previousIntentGraph':
          continuationActive && bootstrapContext?.previousIntentGraph != null
          ? bootstrapContext!.previousIntentGraph!.toJson()
          : const <String, dynamic>{},
      'previousUnderstandingSnapshot': previousUnderstandingSnapshot,
      'previousAnswerProcessing': previousAnswerProcessing,
      'previousSlotState': continuationActive
          ? previousRunArtifacts?.slotState.toJson() ??
                const <String, dynamic>{}
          : const <String, dynamic>{},
      'previousAnswerSummary': continuationActive
          ? bootstrapContext?.previousAnswerSummary ?? ''
          : '',
      'historicalThinkingSnapshot': historicalThinkingSnapshot,
      if (continuationActive &&
          bootstrapContext?.continuityOverrideSlots.isNotEmpty == true)
        'continuityOverrideSlots': bootstrapContext!.continuityOverrideSlots,
    };
  }

  String _buildIntentPlanningContext({
    required String continuityMode,
    required String problemClass,
  }) {
    return [
      '请把公共外壳中的 shared_context / current_runtime_state / dialogue_continuity 当作唯一上下文入口。',
      if (continuityMode.isNotEmpty) '连续性判断：$continuityMode',
      if (problemClass.isNotEmpty) '已知问题类型提示：$problemClass',
      '如果本轮是在纠正上一轮理解，优先修正旧假设。',
      '请直接输出 assistant_turn JSON，并把结构化意图完整放入 intentGraph。',
    ].join('\n');
  }

  Map<String, dynamic> _mergedScopeHint({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required bool allowLocationHints,
  }) {
    return <String, dynamic>{
      ..._sanitizePlannerScopeHint(
        request.contextScopeHint,
        allowLocationHints: allowLocationHints,
      ),
      if (bootstrapContext?.providerReasoningContinuation.trim().isNotEmpty ==
          true)
        'providerReasoningContinuation': bootstrapContext!
            .providerReasoningContinuation
            .trim(),
      if (bootstrapContext?.continuityOverrideSlots.isNotEmpty == true)
        'continuityOverrideSlots': bootstrapContext!.continuityOverrideSlots,
    };
  }

  List<AssistantRunMessage> _plannerMessages({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    if (continuationActive) {
      return request.messages;
    }
    if (request.messages.isEmpty) {
      return const <AssistantRunMessage>[];
    }
    return <AssistantRunMessage>[request.messages.last];
  }

  bool _hasStructuredContent(Map<String, dynamic> value) {
    for (final item in value.values) {
      if (item is String && item.trim().isNotEmpty) return true;
      if (item is num && item != 0) return true;
      if (item is bool && item) return true;
      if (item is List && item.isNotEmpty) return true;
      if (item is Map && item.isNotEmpty) return true;
    }
    return false;
  }

  Map<String, dynamic> _sanitizePlannerScopeHint(
    Map<String, dynamic> scopeHint, {
    required bool allowLocationHints,
  }) {
    if (scopeHint.isEmpty) {
      return const <String, dynamic>{};
    }
    final sanitized = Map<String, dynamic>.from(scopeHint);
    for (final key in const <String>[
      'runArtifacts',
      'previousRunArtifacts',
      'machineEnvelope',
      'displayMarkdown',
      'displayPlainText',
      'journey',
      'uiProcessTimeline',
      'uiProcessTimelineV2',
      'assistantResponse',
    ]) {
      sanitized.remove(key);
    }
    if (allowLocationHints) {
      return sanitized;
    }
    for (final key in const <String>[
      'city',
      'lat',
      'lng',
      'gpsCity',
      'gpsLat',
      'gpsLng',
      'recentCityMentions',
      'locationPrecision',
      'locationTimestamp',
    ]) {
      sanitized.remove(key);
    }
    return sanitized;
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
              previousIntentGraph != null &&
              previousIntentGraph.problemShape != ProblemShape.unknown
          ? previousIntentGraph.problemShape
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
        if (continuationActive &&
            bootstrapContext?.previousAnswerSummary.isNotEmpty == true)
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
    if (continuationActive &&
        bootstrapContext?.previousAnswerSummary.isNotEmpty == true) {
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

class _ResolvedUnderstanding {
  const _ResolvedUnderstanding({
    required this.intentGraph,
    required this.understandingSnapshot,
  });

  final IntentGraph intentGraph;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
}

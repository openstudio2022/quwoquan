// ASSISTANT_WEAK_TYPE: LLM_RAW | EXTENSION_MAP — 理解阶段模板变量与 answer 轨 Map；稳定字段走 codegen/View。

import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/intent_task_compiler.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_context_scope_hint_view.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_builder.dart';
import 'package:quwoquan_app/assistant/orchestration/task_scheduler.dart';
import 'package:quwoquan_app/assistant/intent/model_output_extractors.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/conversation_spine.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

const RelativeTimeResolver _relativeTimeResolver = RelativeTimeResolver();

/// Understand: typed understanding, task graph, and dialogue round script.
class UnderstandPhase implements Phase {
  UnderstandPhase({
    this.domainRouter,
    this.dialogueStateRuntime,
    this.modeDecider = const ModeDecider(),
    this.runtime,
    this.templateCatalogRuntime,
    this.toolMetadataRegistry,
    this.skillLoader,
    this.skillRouter,
  });

  final AssistantDomainRouter? domainRouter;
  final DialogueStateRuntime? dialogueStateRuntime;
  final ModeDecider modeDecider;
  final ReactRuntime? runtime;
  final TemplateCatalogRuntime? templateCatalogRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final PersonalAssistantSkillLoader? skillLoader;
  final PersonalAssistantSkillRouter? skillRouter;

  @override
  String get phaseId => 'understand';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final bootstrapContext = input.state.bootstrapContext;
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final runtimeToolNames =
        runtime?.listAvailableToolNames() ?? const <String>[];
    final availableToolNames = runtimeToolNames.isNotEmpty
        ? runtimeToolNames
        : const <String>['search', 'web_search'];
    final temporalReference = _relativeTimeResolver.resolveReferenceContext(
      referenceNowIso: contextScopeHintView.stringValue('referenceNowIso'),
      timezone: contextScopeHintView.stringValue('timezone'),
    );
    final inlinePlanningOwnsUnderstanding =
        contextScopeHintView.value('inlinePlanningOwnsUnderstanding') == true;
    final mergedScopeHint = _mergedScopeHint(
      request: request,
      bootstrapContext: bootstrapContext,
      allowLocationHints:
          bootstrapContext?.contextContinuityPolicy.allowLocationHints ?? false,
      referenceNowIso: temporalReference.referenceNowIso,
      timezone: temporalReference.timezone,
    );
    if (latestUserQuery.isEmpty) {
      return PhaseOutput(state: input.state);
    }

    final hintedUnderstanding = _typedUnderstandingFromScopeHint(
      contextScopeHintView,
    );
    final resolvedUnderstanding =
        hintedUnderstanding ??
        (!inlinePlanningOwnsUnderstanding
            ? await _resolveTypedUnderstandingWithModel(
                request: request,
                bootstrapContext: bootstrapContext,
                contextAssembly: input.state.contextAssembly,
                latestUserQuery: latestUserQuery,
                previousRunArtifacts: input.state.previousRunArtifacts,
                temporalReference: temporalReference,
                runId: input.runId,
                traceId: input.traceId,
                onTraceEvent: input.onTraceEvent,
                processEmitter: ProcessTimelineEmitter(
                  runId: input.runId,
                  traceId: input.traceId,
                  onTraceEvent: input.onTraceEvent,
                ),
              )
            : null) ??
        _fallbackTypedUnderstanding(latestUserQuery);
    final typedState = _buildTypedUnderstandingStateFromContracts(
      understandingResult: resolvedUnderstanding.understandingResult,
      taskGraph: resolvedUnderstanding.taskGraph,
    );
    final domainId = _domainIdForTypedUnderstanding(
      typedState.understandingResult,
    );
    final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: domainId,
      userQuery: latestUserQuery,
      contextScopeHint: mergedScopeHint,
      forceRefreshCatalog: bootstrapContext?.forceRefreshCatalog ?? false,
    );
    final modeDecision = modeDecider.decide(
      understandingResult: typedState.understandingResult,
      taskGraph: typedState.taskGraph,
      recallResult: bootstrapContext?.recallResult,
    );
    final executionPreparation = await _executionPreparationResolver
        .resolveTyped(
          domainId: domainId,
          base: AssistantExecutionPreparation(
            domainId: domainId,
            modeDecision: modeDecision,
          ),
          userQuery: latestUserQuery,
          understandingResult: typedState.understandingResult,
          taskGraph: typedState.taskGraph,
          request: request,
          dialogueRoundScript: dialogueRoundScript,
          previousRunArtifacts: input.state.previousRunArtifacts,
          runtimeToolNames: availableToolNames,
        );
    final understandingSnapshot = resolvedUnderstanding.understandingSnapshot;
    _emitUnderstandingSnapshot(input: input, snapshot: understandingSnapshot);

    return PhaseOutput(
      state: input.state.copyWith(
        systemContextEnvelope:
            input.state.bootstrapContext?.systemContextEnvelope ??
            input.state.systemContextEnvelope,
        understandingResult: typedState.understandingResult,
        taskGraph: typedState.taskGraph,
        orchestratorState: typedState.orchestratorState,
        turnSynthesisState: typedState.turnSynthesisState,
        understandingSnapshot: understandingSnapshot,
        dialogueRoundScript: dialogueRoundScript,
        executionPreparation: executionPreparation,
      ),
    );
  }

  _ResolvedUnderstanding? _typedUnderstandingFromScopeHint(
    AssistantPipelineContextScopeHintView contextScopeHint,
  ) {
    final understandingRaw =
        contextScopeHint.precomputedUnderstandingResult.isNotEmpty
        ? contextScopeHint.precomputedUnderstandingResult
        : contextScopeHint.understandingResult;
    if (understandingRaw.isEmpty) {
      return null;
    }
    final understandingResult = UnderstandingResult.fromJson(understandingRaw);
    if (understandingResult.intents.isEmpty) {
      return null;
    }
    final taskGraphRaw = contextScopeHint.precomputedTaskGraph.isNotEmpty
        ? contextScopeHint.precomputedTaskGraph
        : contextScopeHint.taskGraph;
    final taskGraph = taskGraphRaw.isEmpty
        ? const IntentTaskCompiler().compile(understandingResult)
        : TaskGraph.fromJson(taskGraphRaw);
    return _ResolvedUnderstanding(
      understandingResult: understandingResult,
      taskGraph: taskGraph.tasks.isEmpty
          ? const IntentTaskCompiler().compile(understandingResult)
          : taskGraph,
      understandingSnapshot: _fallbackTypedUnderstandingSnapshot(
        understandingResult: understandingResult,
      ),
    );
  }

  _ResolvedUnderstanding _fallbackTypedUnderstanding(String latestUserQuery) {
    final understandingResult = UnderstandingResult(
      intents: <IntentNode>[
        IntentNode(
          intentId: 'intent_primary',
          intentType: 'general.retrieve',
          goal: latestUserQuery,
          requiresEvidence: true,
        ),
      ],
      dialogueTransitionDecision: const DialogueTransitionDecision(
        nextTurnMode: NextTurnMode.continueExecution,
      ),
    );
    final taskGraph = const IntentTaskCompiler().compile(understandingResult);
    return _ResolvedUnderstanding(
      understandingResult: understandingResult,
      taskGraph: taskGraph,
      understandingSnapshot: _fallbackTypedUnderstandingSnapshot(
        understandingResult: understandingResult,
      ),
    );
  }

  _TypedUnderstandingState _buildTypedUnderstandingStateFromContracts({
    required UnderstandingResult understandingResult,
    required TaskGraph taskGraph,
  }) {
    final effectiveTaskGraph = taskGraph.tasks.isEmpty
        ? const IntentTaskCompiler().compile(understandingResult)
        : taskGraph;
    final transition = understandingResult.dialogueTransitionDecision;
    final primaryIntentId = understandingResult.intents.isNotEmpty
        ? understandingResult.intents.first.intentId
        : '';
    final interactionDirective = _interactionDirectiveFromTypedTransition(
      transition: transition,
      intentId: primaryIntentId,
    );
    return _TypedUnderstandingState(
      understandingResult: understandingResult,
      taskGraph: effectiveTaskGraph,
      orchestratorState: const TaskScheduler()
          .schedule(effectiveTaskGraph)
          .copyWithInteractionDirective(interactionDirective),
      turnSynthesisState: TurnSynthesisState(
        interactionDirective: interactionDirective,
        completedIntentIds: transition.nextTurnMode == NextTurnMode.answer
            ? <String>[primaryIntentId]
            : const <String>[],
        remainingIntentIds:
            transition.nextTurnMode == NextTurnMode.continueExecution ||
                transition.nextTurnMode == NextTurnMode.askUser
            ? <String>[primaryIntentId]
            : const <String>[],
        blockedIntentIds: transition.nextTurnMode == NextTurnMode.blocked
            ? <String>[primaryIntentId]
            : const <String>[],
      ),
    );
  }

  InteractionDirective _interactionDirectiveFromTypedTransition({
    required DialogueTransitionDecision transition,
    required String intentId,
  }) {
    switch (transition.nextTurnMode) {
      case NextTurnMode.askUser:
        return InteractionDirective(
          kind: InteractionDirectiveKind.clarify,
          intentId: transition.clarificationTargetIntentId.trim().isNotEmpty
              ? transition.clarificationTargetIntentId.trim()
              : intentId,
        );
      case NextTurnMode.blocked:
        return InteractionDirective(
          kind: InteractionDirectiveKind.blocked,
          intentId: intentId,
        );
      case NextTurnMode.answer:
        return InteractionDirective(
          kind: transition.canAnswerPartially
              ? InteractionDirectiveKind.partialAnswer
              : InteractionDirectiveKind.finalAnswer,
          intentId: intentId,
        );
      case NextTurnMode.continueExecution:
        return const InteractionDirective();
    }
  }

  String _domainIdForTypedUnderstanding(
    UnderstandingResult understandingResult,
  ) {
    if (understandingResult.intents.isEmpty) {
      return _domainRouter.fallbackDomainId;
    }
    final type = understandingResult.intents.first.intentType.trim();
    final separatorIndex = type.indexOf('.');
    final domainId = separatorIndex > 0
        ? type.substring(0, separatorIndex)
        : type;
    return domainId.trim().isEmpty ? _domainRouter.fallbackDomainId : domainId;
  }

  RunArtifactsUnderstandingSnapshot _fallbackTypedUnderstandingSnapshot({
    required UnderstandingResult understandingResult,
  }) {
    final primaryGoal = understandingResult.intents.isNotEmpty
        ? understandingResult.intents.first.goal.trim()
        : '';
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: primaryGoal,
      userFacingSummary: primaryGoal,
      retrievalDesignNarrative: understandingResult.intents
          .where((intent) => intent.requiresEvidence)
          .map((intent) => intent.goal.trim())
          .where((goal) => goal.isNotEmpty)
          .join('；'),
    );
  }

  Future<_ResolvedUnderstanding?> _resolveTypedUnderstandingWithModel({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required ContextAssemblyResult? contextAssembly,
    required String latestUserQuery,
    required RunArtifacts? previousRunArtifacts,
    required TemporalReferenceContext temporalReference,
    required String runId,
    required String traceId,
    AssistantTraceEventSink? onTraceEvent,
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
    final searchIterationState = _plannerSearchIterationState(
      request: request,
      bootstrapContext: bootstrapContext,
    );
    final recentDialogueRounds =
        bootstrapContext?.recentDialogueRounds ??
        coerceRecentDialogueRounds(
          AssistantPipelineContextScopeHintView(
            request.contextScopeHint,
          ).value(AssistantPipelineStateKeys.recentDialogueRounds),
        );
    final conversationSpineJson =
        ConsolePrettyLogFormatter.prettyJsonLikeString(
          buildConversationSpine(
            stageId: 'understanding',
            userQuery: latestUserQuery,
            problemClass: problemClass,
            historyAssessment: buildHistoryAssessmentFromPolicy(
              policy:
                  bootstrapContext?.contextContinuityPolicy ??
                  const ContextContinuityPolicy(),
              overrideSlots:
                  bootstrapContext?.continuityOverrideSlots ??
                  const <String, Object?>{},
            ),
            stageState: <String, dynamic>{
              'allowedChoices': const <String>[
                'tool_call',
                'ask_user',
                'answer',
              ],
              'continuationActive': _isContinuationContext(bootstrapContext),
            },
          ),
        );
    final sharedContextJson = ConsolePrettyLogFormatter.prettyJsonLikeString(
      _plannerSharedContextPayload(
        bootstrapContext: bootstrapContext,
        contextAssembly: contextAssembly,
        request: request,
        previousRunArtifacts: previousRunArtifacts,
        temporalReference: temporalReference,
      ),
    );
    final currentRuntimeStateJson =
        ConsolePrettyLogFormatter.prettyJsonLikeString(
          _plannerCurrentRuntimeStatePayload(
            bootstrapContext: bootstrapContext,
            request: request,
            previousRunArtifacts: previousRunArtifacts,
            continuityMode: continuityMode,
            problemClass: problemClass,
            temporalReference: temporalReference,
            searchIterationState: searchIterationState,
          ),
        );
    final dialogueContinuityJson =
        ConsolePrettyLogFormatter.prettyJsonLikeString(
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
      referenceNowIso: temporalReference.referenceNowIso,
      timezone: temporalReference.timezone,
    );
    final plannerMessages = _plannerMessages(
      request: request,
      bootstrapContext: bootstrapContext,
    );
    final plannerMessagesPayload = <Map<String, dynamic>>[
      for (final item in plannerMessages)
        <String, dynamic>{'role': item.role, 'content': item.content},
    ];
    final plannerTemplateVars = buildPlannerTemplateVariables(
      userQuery: latestUserQuery,
      skillCatalog: bootstrapContext?.skillCatalog ?? '',
      conversationSpineJson: conversationSpineJson,
      sharedContextJson: sharedContextJson,
      currentRuntimeStateJson: currentRuntimeStateJson,
      dialogueContinuityJson: dialogueContinuityJson,
      recentDialogueRoundsJson: ConsolePrettyLogFormatter.prettyJsonLikeString(
        recentDialogueRounds,
      ),
      searchIterationStateJson: ConsolePrettyLogFormatter.prettyJsonLikeString(
        searchIterationState,
      ),
      continuityMode: continuityMode,
      problemClass: problemClass,
    );
    var streamedUserFacingSummary = '';
    void forwardTrace(AssistantTraceEvent event) {
      onTraceEvent?.call(event.copyWith(visibility: TraceVisibility.internal));
      if (event.type == AssistantTraceEventType.thinkingProgress &&
          event.data?['streaming'] == true &&
          event.data?['extracted'] == true &&
          event.data?['fieldPath'] ==
              'understandingSnapshot.userFacingSummary') {
        streamedUserFacingSummary = _mergeStableNarrativeText(
          previous: streamedUserFacingSummary,
          incoming: event.message,
        );
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
        sessionId:
            bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
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
    final parsed =
        LlmResponseParser.parse(rawOutput).json ?? <String, dynamic>{};
    final turn = tryParseAssistantTurnOutput(parsed);
    final understandingResult = extractUnderstandingResultFromModelPayload(
      parsed,
      parsedTurn: turn,
    );
    if (understandingResult == null) return null;
    final parsedTaskGraph = extractTaskGraphFromModelPayload(
      parsed,
      parsedTurn: turn,
    );
    final taskGraph = parsedTaskGraph?.tasks.isNotEmpty == true
        ? parsedTaskGraph!
        : const IntentTaskCompiler().compile(understandingResult);
    final parsedSnapshot = parsed['understandingSnapshot'] is Map
        ? parseRunArtifactsUnderstandingSnapshotFromMap(
            (parsed['understandingSnapshot'] as Map).cast<String, Object?>(),
          )
        : const RunArtifactsUnderstandingSnapshot();
    final stabilizedSnapshot = RunArtifactsUnderstandingSnapshot(
      intentSummary: parsedSnapshot.intentSummary,
      userFacingSummary: _mergeStableNarrativeFinalText(
        streamed: streamedUserFacingSummary,
        finalized: parsedSnapshot.userFacingSummary,
      ),
      retrievalDesignNarrative: parsedSnapshot.retrievalDesignNarrative,
      concernPoints: parsedSnapshot.concernPoints,
      emotionSignal: parsedSnapshot.emotionSignal,
      resolutionItems: parsedSnapshot.resolutionItems,
      assumptions: parsedSnapshot.assumptions,
      mismatchSignal: parsedSnapshot.mismatchSignal,
      carryForwardFacts: parsedSnapshot.carryForwardFacts,
      discardedAssumptions: parsedSnapshot.discardedAssumptions,
    );
    return _ResolvedUnderstanding(
      understandingResult: understandingResult,
      taskGraph: taskGraph,
      understandingSnapshot: stabilizedSnapshot,
    );
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

  void _emitUnderstandingSnapshot({
    required PhaseInput input,
    required RunArtifactsUnderstandingSnapshot snapshot,
  }) {
    ProcessTimelineEmitter(
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent,
    ).commit(
      stepId: ProcessStepId.understanding,
      scope: UserEventScope.root,
      headline: snapshot.userFacingSummary.trim(),
      detail: '',
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
    ContextAssemblyResult? contextAssembly,
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
          : const <String, Object?>{},
      'availableGeoContext':
          contextAssembly != null &&
              hasAvailableGeoContext(contextAssembly.availableGeoContext)
          ? contextAssembly.availableGeoContext.toJson()
          : const <String, Object?>{},
      'contextScopeHint': sanitizedScopeHint,
    };
  }

  Map<String, dynamic> _plannerSharedContextPayload({
    required AssistantBootstrapContext? bootstrapContext,
    required ContextAssemblyResult? contextAssembly,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
    required TemporalReferenceContext temporalReference,
  }) {
    final calendarContext = _relativeTimeResolver.buildCalendarContext(
      reference: temporalReference,
    );
    return <String, dynamic>{
      'systemContextEnvelope':
          bootstrapContext?.systemContextEnvelope.toJson() ??
          const SystemContextEnvelope().toJson(),
      'contextEnvelope': inputSafeContextEnvelope(
        bootstrapContext,
        request,
        contextAssembly,
        previousRunArtifacts,
      ),
      'recentDialogueRounds':
          bootstrapContext?.recentDialogueRounds ??
          coerceRecentDialogueRounds(
            AssistantPipelineContextScopeHintView(
              request.contextScopeHint,
            ).value(AssistantPipelineStateKeys.recentDialogueRounds),
          ),
      'temporalReference': <String, dynamic>{
        'referenceNowIso': temporalReference.referenceNowIso,
        'timezone': temporalReference.timezone,
        'calendarContext': calendarContext,
      },
    };
  }

  Map<String, dynamic> _plannerCurrentRuntimeStatePayload({
    required AssistantBootstrapContext? bootstrapContext,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
    required String continuityMode,
    required String problemClass,
    required TemporalReferenceContext temporalReference,
    required Map<String, dynamic> searchIterationState,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final calendarContext = _relativeTimeResolver.buildCalendarContext(
      reference: temporalReference,
    );
    return <String, dynamic>{
      'dialogueState': <String, dynamic>{
        'continuityMode': continuityMode,
        'problemClassHint': problemClass,
        'continuationActive': continuationActive,
        'sessionId':
            bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
        'referenceNowIso': temporalReference.referenceNowIso,
        'timezone': temporalReference.timezone,
        'calendarContext': calendarContext,
        'searchIterationState': searchIterationState,
      },
      'slotStateSnapshot': continuationActive
          ? previousRunArtifacts?.slotState.toJson() ??
                const <String, Object?>{}
          : const <String, Object?>{},
      'contextSlots': const <String, Object?>{},
      'domainPolicyBundle': continuationActive
          ? previousRunArtifacts?.domainPolicyBundle?.toJson() ??
                const <String, Object?>{}
          : const <String, Object?>{},
      'skillExecutionShell': const SkillExecutionShell().toJson(),
    };
  }

  Map<String, dynamic> _plannerSearchIterationState({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
  }) {
    final scopedStateRaw = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    ).mapValue(AssistantPipelineStateKeys.searchIterationState);
    if (scopedStateRaw.isNotEmpty) {
      return scopedStateRaw;
    }
    return <String, dynamic>{
      'maxIterations': request.maxIterations,
      'currentIteration': 1,
      'rounds': const <Map<String, dynamic>>[],
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
        : const <String, Object?>{};
    final previousAnswerProcessing =
        continuationActive &&
            bootstrapContext != null &&
            _hasStructuredContent(
              bootstrapContext.previousAnswerProcessing.toJson(),
            )
        ? bootstrapContext.previousAnswerProcessing.toJson()
        : const <String, Object?>{};
    final historicalThinkingSnapshot =
        continuationActive &&
            bootstrapContext != null &&
            _hasStructuredContent(
              bootstrapContext.historicalThinkingSnapshot.toJson(),
            )
        ? bootstrapContext.historicalThinkingSnapshot.toJson()
        : const <String, Object?>{};
    final previousUnderstandingResult =
        continuationActive &&
            bootstrapContext != null &&
            _hasTypedUnderstandingResult(bootstrapContext.previousUnderstandingResult)
        ? bootstrapContext.previousUnderstandingResult.toJson()
        : const <String, Object?>{};
    final previousTaskGraph =
        continuationActive &&
            bootstrapContext != null &&
            _hasTypedTaskGraph(bootstrapContext.previousTaskGraph)
        ? bootstrapContext.previousTaskGraph.toJson()
        : const <String, Object?>{};
    return <String, dynamic>{
      'continuityMode': continuityMode,
      'problemClassHint': problemClass,
      'recentDialogueRounds':
          bootstrapContext?.recentDialogueRounds ??
          coerceRecentDialogueRounds(
            AssistantPipelineContextScopeHintView(
              request.contextScopeHint,
            ).value(AssistantPipelineStateKeys.recentDialogueRounds),
          ),
      'historySummary': allowHistorySummary
          ? bootstrapContext?.historySummary ?? ''
          : '',
      'previousUnderstandingResult': previousUnderstandingResult,
      'previousTaskGraph': previousTaskGraph,
      'previousUnderstandingSnapshot': previousUnderstandingSnapshot,
      'previousAnswerProcessing': previousAnswerProcessing,
      'previousSlotState': continuationActive
          ? previousRunArtifacts?.slotState.toJson() ??
                const <String, Object?>{}
          : const <String, Object?>{},
      'previousAnswerSummary': continuationActive
          ? bootstrapContext?.previousAnswerSummary ?? ''
          : '',
      'historicalThinkingSnapshot': historicalThinkingSnapshot,
      if (continuationActive &&
          bootstrapContext?.continuityOverrideSlots.isNotEmpty == true)
        'continuityOverrideSlots': bootstrapContext!.continuityOverrideSlots,
    };
  }

  Map<String, dynamic> _mergedScopeHint({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required bool allowLocationHints,
    required String referenceNowIso,
    required String timezone,
  }) {
    return <String, dynamic>{
      ..._sanitizePlannerScopeHint(
        request.contextScopeHint,
        allowLocationHints: allowLocationHints,
      ),
      if (referenceNowIso.trim().isNotEmpty) 'referenceNowIso': referenceNowIso,
      if (timezone.trim().isNotEmpty) 'timezone': timezone,
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
    final limit =
        bootstrapContext?.recentDialogueRoundsLimit ??
        resolveRecentDialogueRoundsLimit(request.contextScopeHint);
    final policy =
        bootstrapContext?.contextContinuityPolicy ??
        const ContextContinuityPolicy();
    final isolatePlannerTurn =
        !policy.explicitContinuation &&
        (policy.continuityMode == ContextContinuityMode.freshTopic ||
            policy.continuityMode == ContextContinuityMode.unknown);
    final effectiveLimit = isolatePlannerTurn ? 0 : limit;
    return trimMessagesToRecentRounds(request.messages, limit: effectiveLimit);
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

  bool _hasTypedUnderstandingResult(UnderstandingResult value) {
    return value.intents.isNotEmpty;
  }

  bool _hasTypedTaskGraph(TaskGraph value) {
    return value.tasks.isNotEmpty;
  }

  Map<String, dynamic> _sanitizePlannerScopeHint(
    Map<String, dynamic> scopeHint, {
    required bool allowLocationHints,
  }) {
    if (scopeHint.isEmpty) {
      return const <String, Object?>{};
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

  bool _isContinuationContext(AssistantBootstrapContext? bootstrapContext) {
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode ??
        ContextContinuityMode.unknown;
    return continuityMode != ContextContinuityMode.unknown &&
        continuityMode != ContextContinuityMode.freshTopic;
  }

  AssistantDomainRouter get _domainRouter =>
      domainRouter ?? AssistantDomainRouter();

  DialogueStateRuntime get _dialogueStateRuntime =>
      dialogueStateRuntime ?? DialogueStateRuntime();

  TemplateCatalogRuntime get _templateCatalogRuntime =>
      templateCatalogRuntime ?? TemplateCatalogRuntime();

  PersonalAssistantSkillLoader get _skillLoader =>
      skillLoader ?? const PersonalAssistantSkillLoader();

  PersonalAssistantSkillRouter get _skillRouter =>
      skillRouter ?? const PersonalAssistantSkillRouter();

  ExecutionPreparationResolver get _executionPreparationResolver =>
      ExecutionPreparationResolver(
        domainRouter: _domainRouter,
        templateCatalogRuntime: _templateCatalogRuntime,
        skillLoader: _skillLoader,
        skillRouter: _skillRouter,
        toolMetadataRegistry: toolMetadataRegistry,
      );
}

class _ResolvedUnderstanding {
  const _ResolvedUnderstanding({
    required this.understandingResult,
    required this.taskGraph,
    required this.understandingSnapshot,
  });

  final UnderstandingResult understandingResult;
  final TaskGraph taskGraph;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
}

class _TypedUnderstandingState {
  const _TypedUnderstandingState({
    required this.understandingResult,
    required this.taskGraph,
    required this.orchestratorState,
    required this.turnSynthesisState,
  });

  final UnderstandingResult understandingResult;
  final TaskGraph taskGraph;
  final ConversationOrchestratorState orchestratorState;
  final TurnSynthesisState turnSynthesisState;
}

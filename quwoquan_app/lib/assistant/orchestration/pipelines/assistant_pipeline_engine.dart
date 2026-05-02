import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/observability_payload_builder.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_context_scope_hint_view.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_response_codec.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_subagent_plan_codec.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_precomputed_contracts.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_diagnostics.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_diagnostics_helper.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_failure_messages.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_recovery_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_prompt_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_structured_response_assembler.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_synthesis_assessment.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_synthesis_template_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_usage_stats.dart'
    as usage_stats;
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_variables_view.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_builder.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_typed_turn_decision_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/assistant/contracts/skill_route_contract.dart';
import 'package:quwoquan_app/assistant/contracts/skill_synthesis_contract.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/conversation_spine.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_boundary_error_mapper.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/answer_gate_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_usage_ledger_entry.dart';
import 'package:quwoquan_app/assistant/prompt_template/runtime/prompt_snippet_renderer.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/phase_one_direct_answer_gate.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/bootstrap_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/response_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
part 'assistant_pipeline_structured_response_part.dart';

// ─────────────────────────────────────────────────────────────────────────
// Assistant Pipeline Engine — core execution, synthesis, and materialization.
// Observability → ObservabilityPayloadBuilder (standalone)
// Session APIs → AssistantAgentLoop (inlined)
// ─────────────────────────────────────────────────────────────────────────
const RelativeTimeResolver _templateRelativeTimeResolver =
    RelativeTimeResolver();

class LocalPhaseExecutionOwner with AssistantPipelineResponseCodecMixin {
  LocalPhaseExecutionOwner(
    this._runtime, {
    required AssistantSessionManager sessionManager,
    required AssistantMemoryRepository memoryRepository,
    ToolMetadataRegistry? toolMetadataRegistry,
    PersonalAssistantContextOrchestrator? contextOrchestrator,
    DialogueStateRuntime? dialogueStateRuntime,
    AssistantDomainRouter? domainRouter,
    TemplateCatalogRuntime? templateCatalogRuntime,
    PersonalAssistantSkillLoader? skillLoader,
    PersonalAssistantSkillRouter? skillRouter,
    RecallCoordinator? recallCoordinator,
    ModeDecider? modeDecider,
    BaselineKernel? baselineKernel,
    AnswerBoundaryResolver? answerBoundaryResolver,
  }) : _sessionManager = sessionManager,
       _memoryRepository = memoryRepository,
       _toolMetadataRegistry = toolMetadataRegistry,
       _contextOrchestrator =
           contextOrchestrator ?? const PersonalAssistantContextOrchestrator(),
       _dialogueStateRuntime = dialogueStateRuntime ?? DialogueStateRuntime(),
       _domainRouter = domainRouter ?? AssistantDomainRouter(),
       _templateCatalogRuntime =
           templateCatalogRuntime ?? TemplateCatalogRuntime(),
       _skillLoader = skillLoader ?? const PersonalAssistantSkillLoader(),
       _skillRouter = skillRouter ?? const PersonalAssistantSkillRouter(),
       _recallCoordinator = recallCoordinator ?? RecallCoordinator(),
       _modeDecider = modeDecider ?? const ModeDecider(),
       _baselineKernel = baselineKernel ?? const BaselineKernel(),
       _answerBoundaryResolver =
           answerBoundaryResolver ?? const AnswerBoundaryResolver();

  final ReactRuntime _runtime;
  final AssistantSessionManager _sessionManager;
  final AssistantMemoryRepository _memoryRepository;
  final ToolMetadataRegistry? _toolMetadataRegistry;
  final PersonalAssistantContextOrchestrator _contextOrchestrator;
  final DialogueStateRuntime _dialogueStateRuntime;
  final AssistantDomainRouter _domainRouter;

  AssistantSessionManager get sessionManager => _sessionManager;
  AssistantDomainRouter get domainRouter => _domainRouter;
  ToolMetadataRegistry? get toolMetadataRegistry => _toolMetadataRegistry;
  final TemplateCatalogRuntime _templateCatalogRuntime;
  final PersonalAssistantSkillLoader _skillLoader;
  final PersonalAssistantSkillRouter _skillRouter;
  final RecallCoordinator _recallCoordinator;
  final ModeDecider _modeDecider;
  final BaselineKernel _baselineKernel;
  final AnswerBoundaryResolver _answerBoundaryResolver;
  final AssistantPipelineSubagentPlanCodec _subagentPlanCodec =
      const AssistantPipelineSubagentPlanCodec();
  final RetrievalOutcomeResolver _retrievalOutcomeResolver =
      const RetrievalOutcomeResolver();
  final AnswerGateResolver _answerGateResolver = const AnswerGateResolver();
  final PromptSnippetRenderer _promptSnippetRenderer = PromptSnippetRenderer();

  static void Function(String delta)? _buildThinkingDeltaForwarder(
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  ) {
    if (onTraceEvent == null) return null;
    // 仅用于开启 provider 侧流式输出。真正带 phase 的 thinking trace
    // 由 react_runtime 在收到 delta 时直接落库并转发，避免这里丢失阶段信息。
    return (_) {};
  }

  Future<String> _renderPromptSnippet(
    String snippetId, {
    Map<String, dynamic> variables = const <String, dynamic>{},
  }) {
    return _promptSnippetRenderer.renderSnippet(
      snippetId,
      variables: variables,
    );
  }

  static void Function(AssistantTraceEvent event)?
  _buildAnswerProcessTraceForwarder(
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  ) {
    if (onTraceEvent == null) return null;
    final processEmitter = ProcessTimelineEmitter(
      runId: runId ?? '',
      traceId: traceId ?? '',
      onTraceEvent: onTraceEvent,
    );
    return (event) {
      onTraceEvent(event);
      if (event.type == AssistantTraceEventType.thinkingProgress &&
          event.data?[AssistantPipelineDiagnosticsKeys.streaming] == true &&
          event.data?[AssistantPipelineDiagnosticsKeys.extracted] == true) {
        final fieldPath =
            (event.data?[AssistantPipelineDiagnosticsKeys.fieldPath] as String?)
                ?.trim() ??
            '';
        if (fieldPath ==
                AssistantPipelineDiagnosticsKeys.retrievalProcessingSummary ||
            fieldPath ==
                AssistantPipelineDiagnosticsKeys
                    .answerProcessingReadinessSummary) {
          processEmitter.pushDelta(
            stepId: ProcessStepId.retrievalProcessing,
            scope: UserEventScope.aggregation,
            delta: event.message,
            phaseId: AssistantPipelineDiagnosticsKeys.answeringPhaseId,
            actionCode: AssistantPipelineDiagnosticsKeys.assessEvidenceAction,
            reasonCode: AssistantPipelineDiagnosticsKeys.digestEvidenceReason,
            payload: <String, dynamic>{
              AssistantPipelineDiagnosticsKeys.fieldPath: fieldPath,
            },
          );
        }
      }
    };
  }

  String _mergeStableNarrativeDeltaText({
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
    for (var overlap = maxOverlap; overlap > 0; overlap -= 1) {
      if (previous.substring(previous.length - overlap) ==
          incoming.substring(0, overlap)) {
        return '$previous${incoming.substring(overlap)}';
      }
    }
    return '$previous$incoming';
  }

  static void Function(AssistantTraceEvent event)? _withTraceVisibility(
    void Function(AssistantTraceEvent event)? onTraceEvent,
    TraceVisibility visibility,
  ) {
    if (onTraceEvent == null) return null;
    return (event) => onTraceEvent(event.copyWith(visibility: visibility));
  }

  Future<AssistantRunResponse> run(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    // 外层安全网：捕获所有未预期异常（sessionManager/objectbox/template 等），
    // 确保 agentLoop.run() 永远返回结构化响应，不向调用方上抛。
    // capability_gateway 的 catch 块仅用于 HTTP/网络级错误兜底。
    try {
      return await _runImpl(request, onTraceEvent: onTraceEvent);
    } catch (error, stackTrace) {
      if (kDebugMode) {
        debugPrint('[AgentLoop] uncaught: $error');
        debugPrint('$stackTrace');
      }
      final boundaryOutcome = const AssistantBoundaryErrorMapper().failed(
        boundary: 'assistant_turn',
        stage: 'pipeline',
        code: 'ASSISTANT.SYSTEM.internal_error',
        kind: RuntimeFailureKind.internal,
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'errorType',
            value: error.runtimeType.toString(),
          ),
        ],
      );
      return AssistantRunResponse(
        finalText: assistantPipelineInternalErrorMessage(),
        degraded: true,
        errorCode: 'internal_error',
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'agent_loop_uncaught: ${error.runtimeType}: $error',
            timestamp: DateTime.now(),
            data: <String, dynamic>{
              AssistantPipelineDiagnosticsKeys.errorType: error.runtimeType
                  .toString(),
              AssistantPipelineDiagnosticsKeys.stackSnippet: stackTrace
                  .toString()
                  .substring(0, math.min(400, stackTrace.toString().length)),
            },
          ),
        ],
        structuredResponse: <String, dynamic>{
          'assistantBoundaryOutcome': boundaryOutcome.toJson(),
        },
      );
    }
  }

  Future<AssistantRunResponse> _runImpl(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final runId =
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final traceId = request.traceId ?? runId;
    final executionSnapshot = await executeBridge(
      request,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
    final shortCircuitResponse = switch (executionSnapshot) {
      ExecutionPhaseShortCircuit(:final response) => response,
      ExecutionPhaseSuccess() => null,
    };
    if (shortCircuitResponse != null) {
      return shortCircuitResponse;
    }
    final response = await synthesizeBridge(
      request,
      executionSnapshot: executionSnapshot,
      onTraceEvent: onTraceEvent,
    );
    return finalizeBridge(
      request,
      executionSnapshot: executionSnapshot,
      response: response,
    );
  }

  Future<ExecutionPhaseSnapshot> executeBridgeFromState(
    AssistantRunRequest request, {
    required AgentExecutionState state,
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final bridgedRequest = AssistantRunRequest.fromJson(<String, dynamic>{
      ...request.toJson(),
      'contextScopeHint': buildCompatibilityContextScopeHint(
        request: request,
        state: state,
      ),
    });
    return executeBridge(
      bridgedRequest,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
  }

  Future<ExecutionPhaseSnapshot> executeBridge(
    AssistantRunRequest request, {
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final effectiveRunId =
        runId ??
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final effectiveTraceId = traceId ?? request.traceId ?? effectiveRunId;
    final requestedSessionId = request.sessionId ?? 'default';
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content
        : '';
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final precomputedBootstrap = recoverPrecomputedBootstrap(
      contextScopeHintView.raw,
      defaultRecentDialogueRoundsLimit: defaultRecentDialogueRoundsLimit,
    );
    final precomputedUnderstand = recoverPrecomputedUnderstand(
      contextScopeHintView.raw,
    );
    final precomputedRetrieval = recoverPrecomputedRetrieval(
      contextScopeHintView.raw,
    );
    final precomputedExecutionPreparation =
        recoverPrecomputedExecutionPreparation(
          contextScopeHintView.raw,
          precomputedUnderstand: precomputedUnderstand,
          precomputedRetrieval: precomputedRetrieval,
        );
    final supplementalTraces = <AssistantTraceEvent>[];
    void emitSupplementalTrace(AssistantTraceEvent event) {
      supplementalTraces.add(event);
      onTraceEvent?.call(event);
    }

    await _sessionManager.load();
    final ownerState = await _resolveExecutionOwnerState(
      request: request,
      precomputedBootstrap: precomputedBootstrap,
      precomputedUnderstand: precomputedUnderstand,
      precomputedExecutionPreparation: precomputedExecutionPreparation,
      runId: effectiveRunId,
      traceId: effectiveTraceId,
      onTraceEvent: emitSupplementalTrace,
    );
    final bootstrapContext =
        ownerState.bootstrapContext ?? const AssistantBootstrapContext();
    final sessionId = bootstrapContext.sessionId.trim().isNotEmpty
        ? bootstrapContext.sessionId.trim()
        : (requestedSessionId == 'assistant'
              ? _sessionManager.resolveAssistantSessionForQuery(latestUserQuery)
              : requestedSessionId);
    final contextContinuityPolicy = bootstrapContext.contextContinuityPolicy;
    final continuationActive =
        contextContinuityPolicy.continuityMode ==
            ContextContinuityMode.sameTopic ||
        contextContinuityPolicy.continuityMode ==
            ContextContinuityMode.explicitFollowUp;
    final templateContext = sanitizeModelTemplateContext(
      contextScopeHintView.raw,
      continuationActive: continuationActive,
      previousRunArtifacts: ownerState.previousRunArtifacts,
    );
    final historySummary = bootstrapContext.historySummary;
    final recalledTexts = bootstrapContext.recalledTexts;
    final contextAssembly =
        ownerState.contextAssembly ?? const ContextAssemblyResult();
    final forceRefreshDynamicCatalog =
        bootstrapContext.forceRefreshCatalog ||
        contextScopeHintView.forceRefreshCatalog;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshDynamicCatalog,
    );
    await _toolMetadataRegistry?.ensureLoaded();
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = bootstrapContext.domainCatalog;
    final domainCatalogVersion = bootstrapContext.domainCatalogVersion;
    final skillCatalog = bootstrapContext.skillCatalog;
    final planView = assistantPlanViewFromTypedMainline(
      understandingResult: ownerState.understandingResult,
      taskGraph: ownerState.taskGraph,
    );
    if (planView == null) {
      throw StateError(
        'executeBridge missing typed understanding after owner resolution',
      );
    }
    final resolvedExecutionPreparation = ownerState.executionPreparation;
    if (resolvedExecutionPreparation == null) {
      throw StateError(
        'executeBridge missing executionPreparation after owner resolution',
      );
    }
    final domainId = resolvedExecutionPreparation.domainId.trim().isNotEmpty
        ? resolvedExecutionPreparation.domainId.trim()
        : (planView.primarySkill.trim().isNotEmpty
              ? planView.primarySkill.trim()
              : _domainRouter.fallbackDomainId);
    final problemShape = planView.problemShape.wireName;
    final modeDecision = resolvedExecutionPreparation.modeDecision;
    final intentTraceEvent = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'understanding_result_resolved',
      timestamp: DateTime.now(),
      runId: effectiveRunId,
      traceId: effectiveTraceId,
      visibility: TraceVisibility.internal,
      data: <String, dynamic>{
        ...planView.toJson(),
        'agentMode': modeDecision.mode.name,
        'agentModeReason': modeDecision.reason,
      },
    );
    onTraceEvent?.call(intentTraceEvent);
    final dialogueRoundScript =
        ownerState.dialogueRoundScript ??
        await _dialogueStateRuntime.buildRoundScript(
          domainId: domainId,
          userQuery: latestUserQuery,
          contextScopeHint: templateContext,
          forceRefreshCatalog: forceRefreshDynamicCatalog,
        );
    final skillContext = ResolvedSkillContext(
      skillName: resolvedExecutionPreparation.skillName,
      instructionMarkdown:
          resolvedExecutionPreparation.skillInstructionMarkdown,
      executionShell: resolvedExecutionPreparation.executionShell,
      allowedTools: resolvedExecutionPreparation.allowedToolNames,
    );
    final effectiveExecutionShell = resolvedExecutionPreparation.executionShell;
    final previousSlotState = resolvedExecutionPreparation.previousSlotState;
    final previousDomainPolicyBundle =
        resolvedExecutionPreparation.previousDomainPolicyBundle;
    final plannerTemplateVersion =
        resolvedExecutionPreparation.plannerTemplateVersion;
    final synthTemplateVersion =
        resolvedExecutionPreparation.synthTemplateVersion;
    final fusionSynthTemplateVersion =
        resolvedExecutionPreparation.fusionSynthTemplateVersion;
    final effectiveToolNames = resolvedExecutionPreparation.allowedToolNames;
    final skillPersona = resolvedExecutionPreparation.skillPersona;
    final retrievalPolicy = await _loadRetrievalPolicy(domainId);
    final effectiveSearchPlans = searchPlansFromTaskGraph(ownerState.taskGraph);
    final answerBoundaryPolicy = _answerBoundaryResolver.resolve(
      planView: planView,
      contextAssembly: contextAssembly,
      retrievalPolicy: retrievalPolicy,
      searchPlans: effectiveSearchPlans,
    );
    final conversationSpine = buildConversationSpine(
      stageId: 'understanding',
      userQuery: request.messages.isEmpty ? '' : request.messages.last.content,
      userGoal: planView.userGoal,
      primarySkill: planView.primarySkill,
      problemClass: planView.problemClass.wireName,
      answerShape: planView.answerShape.wireName,
      historyAssessment: buildHistoryAssessmentFromPolicy(
        policy: contextContinuityPolicy,
        overrideSlots:
            precomputedBootstrap?.continuityOverrideSlots ??
            const <String, dynamic>{},
      ),
      stageState: <String, dynamic>{
        'allowedChoices': <String>[
          AssistantNextAction.toolCall.wireName,
          AssistantNextAction.askUser.wireName,
          AssistantNextAction.answer.wireName,
        ],
        'continuationActive':
            contextContinuityPolicy.continuityMode ==
                ContextContinuityMode.sameTopic ||
            contextContinuityPolicy.continuityMode ==
                ContextContinuityMode.explicitFollowUp,
      },
    );
    final searchIterationState = _seedSearchIterationState(
      request: request,
      searchPlans: effectiveSearchPlans,
    );
    final recentDialogueRounds =
        precomputedBootstrap?.recentDialogueRounds ??
        coerceRecentDialogueRounds(
          contextScopeHintView.value(
            AssistantPipelinePromptKeys.recentDialogueRounds,
          ),
        );
    final temporalReference = _templateRelativeTimeResolver
        .resolveReferenceContext(
          referenceNowIso: _firstNonEmptyText(<String?>[
            contextScopeHintView.stringValue(
              AssistantPipelinePromptKeys.referenceNowIso,
            ),
          ]),
          timezone: _firstNonEmptyText(<String?>[
            contextScopeHintView.stringValue(
              AssistantPipelinePromptKeys.timezone,
            ),
          ]),
        );
    final calendarContext = _templateRelativeTimeResolver.buildCalendarContext(
      reference: temporalReference,
    );
    final templateVariables = buildPipelineTemplateVariables(
      bundle: AssistantPipelineTemplateBundle(
        request: request,
        contextAssembly: contextAssembly,
        domainId: domainId,
        domainSkillInstruction: skillContext.instructionMarkdown,
        domainSkillName: skillContext.skillName,
        availableToolNames: effectiveToolNames,
        toolGuidelines:
            _toolMetadataRegistry?.invocationGuidelinesForTools(
              effectiveToolNames,
            ) ??
            const <Map<String, dynamic>>[],
        conversationSpine: conversationSpine,
        searchIterationState: searchIterationState,
        temporalReference: temporalReference,
        calendarContext: calendarContext,
        dialogueRoundScript: dialogueRoundScript,
        skillExecutionShell: effectiveExecutionShell,
        skillPersona: skillPersona,
        skillCatalog: skillCatalog,
        previousSlotState: previousSlotState,
        previousDomainPolicyBundle: previousDomainPolicyBundle,
        planView: planView,
        searchPlans: effectiveSearchPlans,
        answerBoundaryPolicy: answerBoundaryPolicy,
        previousAnswerSummary:
            precomputedBootstrap?.previousAnswerSummary ?? '',
        continuityPolicy: contextContinuityPolicy,
        continuityOverrideSlots:
            precomputedBootstrap?.continuityOverrideSlots ??
            const <String, dynamic>{},
      ),
      recentDialogueRounds: recentDialogueRounds,
    );
    if (!contextAssembly.canEnterDomain) {
      final blocked = _buildBlockedResponse(
        runId: effectiveRunId,
        traceId: effectiveTraceId,
        contextAssembly: contextAssembly,
      );
      for (final event in blocked.traces) {
        onTraceEvent?.call(event);
      }
      await AssistantAgentLoopDevLogger.instance.writeRun(
        request: request,
        response: blocked,
        sessionId: sessionId,
        runId: effectiveRunId,
      );
      return ExecutionPhaseShortCircuit(response: blocked);
    }
    final modelMessages = trimMessagesToRecentRounds(
      request.messages,
      limit:
          precomputedBootstrap?.recentDialogueRoundsLimit ??
          resolveRecentDialogueRoundsLimit(contextScopeHintView.raw),
    );
    final messages = modelMessages
        .map((m) => <String, dynamic>{'role': m.role, 'content': m.content})
        .toList(growable: true);
    final dataLayerBuffer = StringBuffer();
    dataLayerBuffer.writeln('<dialogue_state>');
    dataLayerBuffer.writeln(
      ConsolePrettyLogFormatter.prettyJsonLikeString(
        dialogueScriptForModel(dialogueRoundScript),
      ),
    );
    dataLayerBuffer.writeln('</dialogue_state>');
    dataLayerBuffer.writeln();
    dataLayerBuffer.writeln('<context_slots>');
    dataLayerBuffer.writeln(
      ConsolePrettyLogFormatter.prettyJsonLikeString(
        contextAssembly.contextEnvelope,
      ),
    );
    dataLayerBuffer.writeln('</context_slots>');
    if (previousSlotState.slotValues.isNotEmpty ||
        previousSlotState.missingSlots.isNotEmpty) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<slot_state_snapshot>');
      dataLayerBuffer.writeln(
        ConsolePrettyLogFormatter.prettyJsonLikeString(
          previousSlotState.toJson(),
        ),
      );
      dataLayerBuffer.writeln('</slot_state_snapshot>');
    }
    if (previousDomainPolicyBundle != null) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<domain_policy_bundle>');
      dataLayerBuffer.writeln(
        ConsolePrettyLogFormatter.prettyJsonLikeString(
          previousDomainPolicyBundle.toJson(),
        ),
      );
      dataLayerBuffer.writeln('</domain_policy_bundle>');
    }
    if (historySummary.isNotEmpty) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<session_history>');
      dataLayerBuffer.writeln(historySummary);
      dataLayerBuffer.writeln('</session_history>');
    }
    if (recalledTexts.isNotEmpty) {
      final cleanRecall = recalledTexts
          .map((text) => text.trim())
          .where(
            (t) =>
                t.isNotEmpty &&
                !AssistantContentFilters.isJsonEnvelope(t) &&
                !AssistantDisplayTextResolver.containsInternalProcessFragment(
                  t,
                ) &&
                !t.startsWith('{'),
          )
          .join('\n');
      if (cleanRecall.isNotEmpty) {
        dataLayerBuffer.writeln();
        dataLayerBuffer.writeln('<memory_recall>');
        dataLayerBuffer.writeln(cleanRecall);
        dataLayerBuffer.writeln('</memory_recall>');
      }
    }
    if (request.capabilityCatalog.isNotEmpty) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<capability_catalog>');
      dataLayerBuffer.writeln(
        AssistantCapabilityCatalog.toPromptText(request.capabilityCatalog),
      );
      dataLayerBuffer.writeln('</capability_catalog>');
    }
    if (templateContext.isNotEmpty) {
      final anchorText = _formatContextAnchor(templateContext);
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<context_anchor>');
      dataLayerBuffer.writeln(anchorText);
      dataLayerBuffer.writeln('</context_anchor>');
    }
    if (request.isRewrite) {
      final ri = request.rewriteInstruction!;
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<rewrite_instruction>');
      dataLayerBuffer.writeln(ri.systemPromptInjection);
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('original_query=${ri.originalQuery}');
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('previous_answer=');
      dataLayerBuffer.writeln(ri.previousAnswer);
      dataLayerBuffer.writeln('</rewrite_instruction>');
    }
    messages.insert(0, <String, dynamic>{
      'role': 'system',
      'content': dataLayerBuffer.toString(),
    });
    final runStartAt = DateTime.now();
    await _safeWriteLogEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: effectiveRunId,
        traceId: effectiveTraceId,
        component: 'assistant_pipeline_engine',
        action: 'run_start',
      ),
      payload: AppPerfProbe.snapshot(
        event: 'operation',
        route: '/assistant/run',
        operation: 'agent_run_start',
      ),
      summaryPayload: <String, dynamic>{
        'event': 'operation',
        'operation': 'agent_run_start',
        'domainId': domainId,
        'problemShape': problemShape,
        'skillName': skillContext.skillName,
        'toolCount': effectiveToolNames.length,
        'templateId': 'planner.global_plan',
      },
    );
    final rewriteToolNames = request.shouldSkipSearch
        ? const <String>[]
        : effectiveToolNames;
    final rewriteMaxIterations = 1;
    final result = await _runtime.run(
      messages: messages,
      maxIterations: rewriteMaxIterations,
      goal: latestUserQuery,
      availableToolNamesOverride: rewriteToolNames,
      templateId: 'planner.global_plan',
      templateVersion: plannerTemplateVersion,
      templateContext: templateContext,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: effectiveRunId,
      traceId: effectiveTraceId,
      onTraceEvent: onTraceEvent,
      onDelta: _buildThinkingDeltaForwarder(
        onTraceEvent,
        effectiveRunId,
        effectiveTraceId,
      ),
    );
    List<AssistantToolResultRow> collectToolResults(
      ReactRuntimeResult runtimeResult,
    ) {
      return runtimeResult.traces
          .where((event) => event.type == AssistantTraceEventType.toolResult)
          .map(AssistantToolResultRow.fromTraceEvent)
          .toList(growable: false);
    }

    List<EvidenceLedgerEntry> mergeEvidenceLedgerEntries({
      required List<EvidenceLedgerEntry> current,
      required List<EvidenceLedgerEntry> carried,
    }) {
      final merged = <EvidenceLedgerEntry>[];
      final seen = <String>{};
      String keyOf(EvidenceLedgerEntry entry) {
        final evidenceId = entry.evidenceId.trim();
        if (evidenceId.isNotEmpty) return evidenceId;
        final url = entry.url.trim();
        if (url.isNotEmpty) return '${entry.dimension.trim()}::$url';
        return '${entry.dimension.trim()}::${entry.title.trim()}::${entry.snippet.trim()}';
      }

      for (final entry in <EvidenceLedgerEntry>[...current, ...carried]) {
        final key = keyOf(entry);
        if (key.trim().isEmpty || !seen.add(key)) continue;
        merged.add(entry);
      }
      return merged;
    }

    AssistantPipelineSynthesisAssessment computeSynthesisReadiness(
      ReactRuntimeResult runtimeResult,
      List<AssistantToolResultRow> toolResults,
    ) {
      final carriedEvidenceLedger =
          continuationActive &&
              planView.problemClass != ProblemClass.realtimeInfo
          ? (ownerState.previousRunArtifacts?.evidenceLedger ??
                const <EvidenceLedgerEntry>[])
          : const <EvidenceLedgerEntry>[];
      final blockingDimensions = _blockingEvidenceDimensions(
        searchPlans: effectiveSearchPlans,
        toolResults: toolResults,
      );
      final currentEvidenceLedger = _baselineKernel.buildEvidenceLedger(
        domainId: domainId,
        toolResults: _toolResultsForEvidenceLedger(toolResults),
        slotState: previousSlotState,
        retrievalPolicy: retrievalPolicy,
      );
      final mergedEvidenceLedger = mergeEvidenceLedgerEntries(
        current: currentEvidenceLedger,
        carried: carriedEvidenceLedger,
      );
      final hasToolResult =
          toolResults.isNotEmpty || mergedEvidenceLedger.isNotEmpty;
      final evidenceEvaluation = _baselineKernel.evaluateEvidence(
        ledger: mergedEvidenceLedger,
        evidenceRequired: answerBoundaryPolicy.evidenceRequired,
        authorityRequired: answerBoundaryPolicy.authorityRequired,
        freshnessHoursMax: answerBoundaryPolicy.freshnessHoursMax,
        blockingDimensions: blockingDimensions,
      );
      final synthesisReadiness = _contextOrchestrator.checkSynthesisReadiness(
        query: request.messages.isNotEmpty ? request.messages.last.content : '',
        finalText: runtimeResult.finalText,
        hasToolResult: hasToolResult,
        problemClass: planView.problemClassWireName,
        contextAssembly: contextAssembly,
        planView: planView,
        searchPlans: effectiveSearchPlans,
        boundaryPolicy: answerBoundaryPolicy,
        evidenceEvaluation: evidenceEvaluation,
      );
      return AssistantPipelineSynthesisAssessment(
        synthesisReadiness: synthesisReadiness,
        evidenceLedger: mergedEvidenceLedger,
        evidenceEvaluation: evidenceEvaluation,
      );
    }

    final toolResults = collectToolResults(result);
    final synthesisAssessment = computeSynthesisReadiness(result, toolResults);
    final mergedResult = result;
    final finalToolResults = identical(mergedResult, result)
        ? toolResults
        : collectToolResults(mergedResult);
    final finalSynthesisAssessment = identical(mergedResult, result)
        ? synthesisAssessment
        : computeSynthesisReadiness(mergedResult, finalToolResults);
    final finalSynthesisReadiness = finalSynthesisAssessment.synthesisReadiness;
    return ExecutionPhaseSuccess(
      runId: effectiveRunId,
      traceId: effectiveTraceId,
      runStartAt: runStartAt,
      sessionId: sessionId,
      latestUserQuery: latestUserQuery,
      domainId: domainId,
      contextAssembly: contextAssembly,
      understandingResult: ownerState.understandingResult,
      taskGraph: ownerState.taskGraph,
      orchestratorState: ownerState.orchestratorState,
      turnSynthesisState: ownerState.turnSynthesisState,
      dialogueRoundScript: dialogueRoundScript,
      domainCatalog: domainCatalog,
      domainCatalogVersion: domainCatalogVersion,
      allowedToolNames: effectiveToolNames,
      executionShell: effectiveExecutionShell,
      previousSlotState: previousSlotState,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
      retrievalPolicy: retrievalPolicy,
      answerBoundaryPolicy: answerBoundaryPolicy,
      understandingSnapshot: ownerState.understandingSnapshot.toJson(),
      templateVariables: templateVariables,
      messages: messages,
      synthTemplateVersion: synthTemplateVersion,
      fusionSynthTemplateVersion: fusionSynthTemplateVersion,
      phaseOneResult: mergedResult,
      synthesisReadiness: finalSynthesisReadiness,
      evidenceLedger: finalSynthesisAssessment.evidenceLedger,
      evidenceEvaluation: finalSynthesisAssessment.evidenceEvaluation,
      toolResults: finalToolResults,
      supplementalTraces: supplementalTraces,
    );
  }

  Future<AgentExecutionState> _resolveExecutionOwnerState({
    required AssistantRunRequest request,
    required PrecomputedBootstrap? precomputedBootstrap,
    required PrecomputedUnderstand? precomputedUnderstand,
    required AssistantExecutionPreparation? precomputedExecutionPreparation,
    required String runId,
    required String traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    var state = _buildPrecomputedExecutionState(
      request: request,
      precomputedBootstrap: precomputedBootstrap,
      precomputedUnderstand: precomputedUnderstand,
      precomputedExecutionPreparation: precomputedExecutionPreparation,
    );
    final hasExplicitOwnerInputs =
        state.understandingResult.intents.isNotEmpty ||
        precomputedExecutionPreparation != null;
    if ((state.bootstrapContext == null || state.contextAssembly == null) &&
        hasExplicitOwnerInputs) {
      final compatBootstrap = await _buildCompatibilityBootstrapState(request);
      state = state.copyWith(
        bootstrapContext:
            state.bootstrapContext ?? compatBootstrap.bootstrapContext,
        contextAssembly:
            state.contextAssembly ?? compatBootstrap.contextAssembly,
      );
    }
    if (state.bootstrapContext == null || state.contextAssembly == null) {
      final bootstrapOutput = await _bootstrapPhase.run(
        PhaseInput(
          request: request,
          state: state,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent,
        ),
      );
      state = bootstrapOutput.state ?? state;
    }
    final hasUnderstanding = state.understandingResult.intents.isNotEmpty;
    final hasExecutionDomainId =
        state.executionPreparation?.domainId.trim().isNotEmpty == true;
    if (!hasUnderstanding || !hasExecutionDomainId) {
      final understandOutput = await _understandPhase.run(
        PhaseInput(
          request: request,
          state: state,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent,
        ),
      );
      state = understandOutput.state ?? state;
    }
    final hasSearchPlans = state.taskGraph.tasks.isNotEmpty;
    final hasExecutionDetails =
        state.executionPreparation?.hasExecutionDetails ?? false;
    final hasExplicitPreparedExecution =
        precomputedExecutionPreparation?.hasExecutionDetails ?? false;
    final shouldRunRetrievalDesign =
        !hasExplicitPreparedExecution &&
        (!hasExecutionDetails || !hasSearchPlans);
    if (shouldRunRetrievalDesign) {
      final retrievalOutput = await _retrievalDesignPhase.run(
        PhaseInput(
          request: request,
          state: state,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent,
        ),
      );
      state = retrievalOutput.state ?? state;
    }
    return state;
  }

  AgentExecutionState _buildPrecomputedExecutionState({
    required AssistantRunRequest request,
    required PrecomputedBootstrap? precomputedBootstrap,
    required PrecomputedUnderstand? precomputedUnderstand,
    required AssistantExecutionPreparation? precomputedExecutionPreparation,
  }) {
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final typedUnderstanding = _recoverTypedUnderstandingResult(
      contextScopeHintView,
    );
    final typedTaskGraph = _recoverTypedTaskGraph(contextScopeHintView);
    return AgentExecutionState(
      bootstrapContext: precomputedBootstrap == null
          ? null
          : AssistantBootstrapContext(
              sessionId: precomputedBootstrap.sessionId,
              latestUserQuery: precomputedBootstrap.latestUserQuery,
              historySummary: precomputedBootstrap.historySummary,
              systemContextEnvelope: precomputedBootstrap.systemContextEnvelope,
              recentDialogueRounds: precomputedBootstrap.recentDialogueRounds,
              recentDialogueRoundsLimit:
                  precomputedBootstrap.recentDialogueRoundsLimit,
              recalledTexts: precomputedBootstrap.recalledTexts,
              previousAnswerSummary: precomputedBootstrap.previousAnswerSummary,
              previousUnderstandingResult:
                  precomputedBootstrap.previousUnderstandingResult,
              previousTaskGraph: precomputedBootstrap.previousTaskGraph,
              previousUnderstandingSnapshot:
                  precomputedBootstrap.previousUnderstandingSnapshot,
              previousAnswerProcessing:
                  precomputedBootstrap.previousAnswerProcessing,
              historicalThinkingSnapshot:
                  precomputedBootstrap.historicalThinkingSnapshot,
              providerReasoningContinuation:
                  precomputedBootstrap.providerReasoningContinuation,
              sessionHistoryState: precomputedBootstrap.sessionHistoryState,
              contextContinuityPolicy: precomputedBootstrap.continuityPolicy,
              continuityOverrideSlots:
                  precomputedBootstrap.continuityOverrideSlots,
              recallResult: precomputedBootstrap.recallResult,
              forceRefreshCatalog: precomputedBootstrap.forceRefreshCatalog,
              domainCatalog: precomputedBootstrap.domainCatalog,
              domainCatalogVersion: precomputedBootstrap.domainCatalogVersion,
              fullSkillCatalog: precomputedBootstrap.fullSkillCatalog,
              skillCatalog: precomputedBootstrap.skillCatalog,
            ),
      contextAssembly: precomputedBootstrap?.contextAssembly,
      previousRunArtifacts:
          precomputedBootstrap?.previousRunArtifacts ??
          recoverPreviousRunArtifacts(contextScopeHintView.raw),
      systemContextEnvelope:
          precomputedBootstrap?.systemContextEnvelope ??
          const SystemContextEnvelope(),
      dialogueRoundScript: precomputedUnderstand?.dialogueRoundScript,
      understandingResult: typedUnderstanding ?? const UnderstandingResult(),
      taskGraph: typedTaskGraph ?? const TaskGraph(),
      executionPreparation: precomputedExecutionPreparation,
    );
  }

  UnderstandingResult? _recoverTypedUnderstandingResult(
    AssistantPipelineContextScopeHintView contextScopeHint,
  ) {
    final raw = contextScopeHint.precomputedUnderstandingResult.isNotEmpty
        ? contextScopeHint.precomputedUnderstandingResult
        : contextScopeHint.understandingResult;
    if (raw.isEmpty) {
      return null;
    }
    try {
      final result = UnderstandingResult.fromJson(raw);
      return result.intents.isEmpty ? null : result;
    } catch (_) {
      return null;
    }
  }

  TaskGraph? _recoverTypedTaskGraph(
    AssistantPipelineContextScopeHintView contextScopeHint,
  ) {
    final raw = contextScopeHint.precomputedTaskGraph.isNotEmpty
        ? contextScopeHint.precomputedTaskGraph
        : contextScopeHint.taskGraph;
    if (raw.isEmpty) {
      return null;
    }
    try {
      final result = TaskGraph.fromJson(raw);
      return result.tasks.isEmpty ? null : result;
    } catch (_) {
      return null;
    }
  }

  Future<_CompatibilityBootstrapState> _buildCompatibilityBootstrapState(
    AssistantRunRequest request,
  ) async {
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content
        : '';
    final requestedSessionId = request.sessionId ?? 'default';
    final sessionId = requestedSessionId == 'assistant'
        ? _sessionManager.resolveAssistantSessionForQuery(latestUserQuery)
        : requestedSessionId;
    final priorSessionHistory = _sessionManager
        .getOrCreateSession(sessionId)
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    final recentDialogueRoundsLimit = resolveRecentDialogueRoundsLimit(
      contextScopeHintView.raw,
    );
    final olderRecentDialogueRoundsLimit =
        resolveOlderRecentDialogueRoundsLimit(contextScopeHintView.raw);
    final continuityPolicy = _contextOrchestrator.buildContinuityPolicy(
      query: latestUserQuery,
      sessionHistory: priorSessionHistory,
      recentRoundsLimit: recentDialogueRoundsLimit,
      recentOlderRoundsLimit: olderRecentDialogueRoundsLimit,
    );
    if (latestUserQuery.isNotEmpty) {
      _sessionManager.appendMessage(
        sessionId: sessionId,
        role: 'user',
        content: latestUserQuery,
      );
    }
    final enableChatRecent = _hasCapability(
      request.capabilityCatalog,
      AssistantCapabilityCatalog.chatRecent,
    );
    final enableChatLongterm = _hasCapability(
      request.capabilityCatalog,
      AssistantCapabilityCatalog.chatLongterm,
    );
    final historySummary =
        enableChatRecent && continuityPolicy.allowHistorySummary
        ? _sessionManager.summarizeRecent(
            sessionId,
            roundsLimit: recentDialogueRoundsLimit,
            roundsOlderLimit: olderRecentDialogueRoundsLimit,
          )
        : '';
    final recentDialogueRounds = _sessionManager.recentDialogueRounds(
      sessionId,
      limit: recentDialogueRoundsLimit,
      olderLimit: olderRecentDialogueRoundsLimit,
    );
    final recalledTexts =
        enableChatLongterm && continuityPolicy.allowLongtermMemory
        ? (await _memoryRepository.recallByText(
            query: latestUserQuery,
            limit: 3,
          )).map((item) => item.text.toString()).toList(growable: false)
        : const <String>[];
    final contextAssembly = _contextOrchestrator.assemble(
      query: latestUserQuery,
      historySummary: historySummary,
      recalledTexts: recalledTexts,
      deviceProfile: request.deviceProfile,
      deviceModel: request.deviceModel,
      deviceOs: request.deviceOs,
      gpsLocation: request.gpsLocation,
      contextScopeHint: contextScopeHintView.raw,
      continuityPolicy: continuityPolicy,
    );
    final forceRefreshCatalog = contextScopeHintView.forceRefreshCatalog;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await _toolMetadataRegistry?.ensureLoaded();
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = await _domainRouter.availableDomains(
      forceRefresh: forceRefreshCatalog,
      contextScopeHint: contextScopeHintView.raw,
    );
    final domainCatalogVersion = await _domainRouter.catalogVersion(
      forceRefresh: false,
      contextScopeHint: contextScopeHintView.raw,
    );
    final fullSkillCatalog = await _domainRouter.buildSkillCatalogPrompt(
      contextScopeHint: contextScopeHintView.raw,
    );
    final allManifests = await _domainRouter.availableSkillManifests(
      contextScopeHint: contextScopeHintView.raw,
    );
    final recallResult = _recallCoordinator.recall(
      latestUserQuery,
      allManifests,
    );
    final skillCatalog = recallResult.toPlannerSkillCatalog(
      fullCatalog: fullSkillCatalog,
      fallbackDomainId: _domainRouter.fallbackDomainId,
    );
    return _CompatibilityBootstrapState(
      bootstrapContext: AssistantBootstrapContext(
        sessionId: sessionId,
        latestUserQuery: latestUserQuery,
        historySummary: historySummary,
        recentDialogueRounds: recentDialogueRounds,
        recentDialogueRoundsLimit: recentDialogueRoundsLimit,
        recalledTexts: recalledTexts,
        sessionHistoryState: _sessionManager.historyStateOf(sessionId),
        contextContinuityPolicy: continuityPolicy,
        recallResult: recallResult,
        forceRefreshCatalog: forceRefreshCatalog,
        domainCatalog: domainCatalog,
        domainCatalogVersion: domainCatalogVersion,
        fullSkillCatalog: fullSkillCatalog,
        skillCatalog: skillCatalog,
      ),
      contextAssembly: contextAssembly,
    );
  }

  Future<AssistantRunResponse> synthesizeBridge(
    AssistantRunRequest request, {
    required ExecutionPhaseSnapshot executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return SynthesisRunner(
      buildDraft: synthesizeDraftBridge,
      materialize: ResponseMaterializer(owner: this).materialize,
    ).synthesize(
      request,
      executionSnapshot: executionSnapshot,
      onTraceEvent: onTraceEvent,
    );
  }

  Future<SynthesisDraft> synthesizeDraftBridge(
    AssistantRunRequest request, {
    required ExecutionPhaseSnapshot executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    if (executionSnapshot is! ExecutionPhaseSuccess) {
      throw StateError(
        'synthesizeDraftBridge requires a successful execution snapshot',
      );
    }
    final runId = executionSnapshot.runId;
    final traceId = executionSnapshot.traceId;
    final sessionId = executionSnapshot.sessionId;
    final latestUserQuery = executionSnapshot.latestUserQuery.trim();
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final domainId = executionSnapshot.domainId.trim();
    final contextAssembly = executionSnapshot.contextAssembly;
    final planView = assistantPlanViewFromTypedMainline(
      understandingResult: executionSnapshot.understandingResult,
      taskGraph: executionSnapshot.taskGraph,
    );
    if (planView == null) {
      throw StateError('synthesis missing typed understanding');
    }
    final dialogueRoundScript = executionSnapshot.dialogueRoundScript;
    final domainCatalog = executionSnapshot.domainCatalog;
    final domainCatalogVersion = executionSnapshot.domainCatalogVersion;
    final allowedToolNames = executionSnapshot.allowedToolNames;
    final effectiveExecutionShell = executionSnapshot.executionShell;
    final previousSlotState = executionSnapshot.previousSlotState;
    final previousDomainPolicyBundle =
        executionSnapshot.previousDomainPolicyBundle;
    final retrievalPolicy = executionSnapshot.retrievalPolicy;
    final answerBoundaryPolicy = executionSnapshot.answerBoundaryPolicy;
    final templateVariables = executionSnapshot.templateVariables;
    final templateVariablesView = executionSnapshot.templateVariablesReadView;
    final templateContext = sanitizeModelTemplateContext(
      contextScopeHintView.raw,
      continuationActive: _hasContinuationCarryoverContext(
        templateVariablesView,
      ),
      previousRunArtifacts: recoverPreviousRunArtifacts(
        contextScopeHintView.raw,
      ),
    );
    final messages = executionSnapshot.messages;
    final synthTemplateVersion = executionSnapshot.synthTemplateVersion;
    final phaseOneResult = executionSnapshot.phaseOneResult;
    final synthesisReadiness = executionSnapshot.synthesisReadiness;
    final supplementalTraces = executionSnapshot.supplementalTraces;

    final domainResultsForSynthesis = buildDomainResultsForSynthesis(
      phaseOneResult.traces,
    );
    final executionSearchPlans = searchPlansFromTaskGraph(
      executionSnapshot.taskGraph,
    );
    final synthesisSearchPlans = SearchPlanItem.toJsonList(
      executionSearchPlans,
    );
    final bootstrapPayload = contextScopeHintView.precomputedBootstrap;
    final continuityPolicyForSynthesis =
        bootstrapPayload[AssistantPipelineStateKeys.contextContinuityPolicy]
            is Map
        ? ContextContinuityPolicy.fromJson(
            (bootstrapPayload[AssistantPipelineStateKeys
                        .contextContinuityPolicy]
                    as Map)
                .cast<String, dynamic>(),
          )
        : const ContextContinuityPolicy();
    final phaseOneText = phaseOneResult.finalText;
    final phaseOneAnswerPayload = parseAnswerPayload(
      rawFinalText: phaseOneText,
      traces: phaseOneResult.traces,
    );
    final previousRunArtifactsForSynthesis = recoverPreviousRunArtifacts(
      contextScopeHintView.raw,
    );
    final previousUnderstandingSnapshotForSynthesis =
        (bootstrapPayload[AssistantPipelineStateKeys
                    .previousUnderstandingSnapshot]
                as Map?)
            ?.cast<String, dynamic>() ??
        contextScopeHintView.previousUnderstandingSnapshot;
    Map<String, dynamic> stagePayloadMap(
      Map<String, dynamic> payload,
      String key,
    ) {
      final raw = payload[key];
      if (raw is Map) {
        return raw.cast<String, dynamic>();
      }
      return const <String, dynamic>{};
    }

    var carriedUnderstandingSnapshot = _normalizedUnderstandingSnapshotMap(
      raw: preferStructuredMap(
        executionSnapshot.understandingSnapshot,
        preferStructuredMap(
          previousUnderstandingSnapshotForSynthesis,
          previousRunArtifactsForSynthesis?.understandingSnapshot.toJson() ??
              const <String, dynamic>{},
        ),
      ),
      planView: planView,
      searchPlans: executionSearchPlans,
      latestUserQuery: latestUserQuery,
    );
    var carriedRetrievalProcessing = preferStructuredMap(
      previousRunArtifactsForSynthesis?.retrievalProcessing.toJson(),
      const <String, dynamic>{},
    );
    var blockedProcessStepId = ProcessStepId.unknown;
    var blockedProcessMessage = '';
    final historicalThinkingSnapshotForSynthesis =
        (bootstrapPayload[AssistantPipelineStateKeys.historicalThinkingSnapshot]
                as Map?)
            ?.cast<String, dynamic>() ??
        contextScopeHintView.historicalThinkingSnapshot;
    var carriedHistoricalThinkingSnapshot = preferStructuredMap(
      historicalThinkingSnapshotForSynthesis,
      previousRunArtifactsForSynthesis?.historicalThinkingSnapshot.toJson() ??
          const <String, dynamic>{},
    );
    void refreshPhaseOneStructuredCarryover(Map<String, dynamic> payload) {
      carriedUnderstandingSnapshot = preferStructuredMap(
        _normalizedUnderstandingSnapshotMap(
          raw: stagePayloadMap(
            payload,
            AssistantPipelineStateKeys.understandingSnapshot,
          ),
          planView: planView,
          searchPlans: executionSearchPlans,
          latestUserQuery: latestUserQuery,
        ),
        carriedUnderstandingSnapshot,
      );
      carriedRetrievalProcessing = preferStructuredMap(
        stagePayloadMap(
          payload,
          AssistantPipelineStateKeys.retrievalProcessing,
        ),
        carriedRetrievalProcessing,
      );
      carriedHistoricalThinkingSnapshot = preferStructuredMap(
        stagePayloadMap(
          payload,
          AssistantPipelineStateKeys.historicalThinkingSnapshot,
        ),
        carriedHistoricalThinkingSnapshot,
      );
    }

    final evidenceEvaluationForSynthesis =
        executionSnapshot.evidenceEvaluation as EvidenceEvaluationResult? ??
        const EvidenceEvaluationResult();
    final templateDialogueState = templateVariablesView.dialogueStateMap;
    final synthesisTemporalReference = _templateRelativeTimeResolver
        .resolveReferenceContext(
          referenceNowIso: _firstNonEmptyText(<String?>[
            contextScopeHintView.stringValue(
              AssistantPipelinePromptKeys.referenceNowIso,
            ),
            templateDialogueState['referenceNowIso'] as String?,
          ]),
          timezone: _firstNonEmptyText(<String?>[
            contextScopeHintView.stringValue(
              AssistantPipelinePromptKeys.timezone,
            ),
            templateDialogueState['timezone'] as String?,
          ]),
        );
    final synthesisCalendarContext = _templateRelativeTimeResolver
        .buildCalendarContext(reference: synthesisTemporalReference);
    final sharedContextForSynthesis = <String, dynamic>{
      AssistantPipelinePromptKeys.contextEnvelope:
          contextAssembly.contextEnvelope,
      AssistantPipelinePromptKeys.recentDialogueRounds:
          templateVariablesView.recentDialogueRounds,
      AssistantPipelinePromptKeys.temporalReference: <String, dynamic>{
        AssistantPipelinePromptKeys.referenceNowIso:
            synthesisTemporalReference.referenceNowIso,
        AssistantPipelinePromptKeys.timezone:
            synthesisTemporalReference.timezone,
        AssistantPipelinePromptKeys.calendarContext: synthesisCalendarContext,
      },
    };
    final currentRuntimeStateForSynthesis = <String, dynamic>{
      AssistantPipelinePromptKeys.dialogueState: <String, dynamic>{
        AssistantPipelinePromptKeys.calendarContext: synthesisCalendarContext,
        AssistantPipelinePromptKeys.referenceNowIso:
            synthesisTemporalReference.referenceNowIso,
        AssistantPipelinePromptKeys.timezone:
            synthesisTemporalReference.timezone,
      },
    };
    final dialogueContinuityForSynthesis = <String, dynamic>{
      AssistantPipelinePromptKeys.continuityMode:
          continuityPolicyForSynthesis.continuityMode.wireName,
    };
    final licensedRetrievalProcessingForSynthesis =
        _licensedRetrievalProcessingForSynthesis(carriedRetrievalProcessing);
    final synthesisSearchIterationState = _buildSynthesisSearchIterationState(
      templateVariables: templateVariablesView,
      phaseOneTraces: phaseOneResult.traces,
      fallbackSearchPlans: executionSearchPlans,
      maxIterations: request.totalModelStageBudget,
      acceptedEvidenceCount:
          licensedRetrievalProcessingForSynthesis.acceptedReferences.length,
      missingDimensions: evidenceEvaluationForSynthesis.missingDimensions,
      answerReady: synthesisReadiness.ready,
    );
    currentRuntimeStateForSynthesis['dialogueState'] = <String, dynamic>{
      ...((currentRuntimeStateForSynthesis['dialogueState'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{}),
      'searchIterationState': synthesisSearchIterationState.toJson(),
    };
    final hasLicensedEvidenceForSynthesis =
        licensedRetrievalProcessingForSynthesis.processingSummary
            .trim()
            .isNotEmpty ||
        licensedRetrievalProcessingForSynthesis.selectedKeyPoints.isNotEmpty ||
        licensedRetrievalProcessingForSynthesis.acceptedReferences.isNotEmpty;
    final evidenceContextForSynthesis = <String, dynamic>{
      'planView': planView.toJson(),
      'searchPlans': synthesisSearchPlans,
      AssistantPipelineStateKeys.retrievalProcessing:
          licensedRetrievalProcessingForSynthesis.toJson(),
      'evidenceEvaluation': evidenceEvaluationForSynthesis.toJson(),
      if (!hasLicensedEvidenceForSynthesis)
        'domainResults': domainResultsForSynthesis,
      if (!hasLicensedEvidenceForSynthesis)
        'webEvidencePacks':
            domainResultsForSynthesis['webEvidencePacks'] ?? const <Object?>[],
      'contextSlots': buildContextSlots(contextAssembly),
      'entityRefs': planView.entityRefs,
    };
    final synthesisConversationSpine = buildConversationSpine(
      stageId: AssistantPipelineDiagnosticsKeys.answeringPhaseId,
      userQuery: latestUserQuery,
      userGoal: planView.userGoal.trim().isNotEmpty
          ? planView.userGoal.trim()
          : latestUserQuery,
      primarySkill: planView.primarySkill.trim().isNotEmpty
          ? planView.primarySkill.trim()
          : domainId,
      problemClass: planView.problemClassWireName,
      answerShape: planView.answerShape.wireName,
      historyAssessment: mergeHistoryAssessments(<Map<String, dynamic>>[
        buildHistoryAssessmentFromPolicy(
          policy: continuityPolicyForSynthesis,
          overrideSlots:
              (bootstrapPayload['continuityOverrideSlots'] as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
        ),
        carriedHistoricalThinkingSnapshot,
      ]),
      stageState: <String, dynamic>{
        'allowedChoices': <String>[
          AssistantNextAction.answer.wireName,
          AssistantNextAction.toolCall.wireName,
          AssistantNextAction.askUser.wireName,
        ],
        'answerReadyHint': synthesisReadiness.ready,
        'answerStageBudget': request.answerStageBudget,
        'maxRequeryRounds': request.maxRequeryRounds,
        'budgetExhausted': request.maxRequeryRounds <= 0,
        if (synthesisReadiness.reason.trim().isNotEmpty)
          'insufficientEvidenceReason': synthesisReadiness.reason.trim(),
      },
    );
    final synthesisTemplateBundle = AssistantPipelineSynthesisTemplateBundle(
      templateVariables: templateVariables,
      conversationSpine: synthesisConversationSpine,
      userGoal: planView.userGoal.trim().isNotEmpty
          ? planView.userGoal.trim()
          : latestUserQuery,
      understandingSnapshot: carriedUnderstandingSnapshot,
      retrievalProcessing: licensedRetrievalProcessingForSynthesis.toJson(),
      sharedContext: sharedContextForSynthesis,
      currentRuntimeState: currentRuntimeStateForSynthesis,
      dialogueContinuity: dialogueContinuityForSynthesis,
      evidenceContext: evidenceContextForSynthesis,
      searchIterationState: synthesisSearchIterationState.toJson(),
      planViewJson: jsonEncode(planView.toJson()),
      searchPlansJson: synthesisSearchPlans,
      entityRefs: planView.entityRefs,
      searchPlans: synthesisSearchPlans,
      answerShape: planView.answerShape.wireName,
      recentDialogueRounds: templateVariablesView.recentDialogueRounds,
    );
    final synthesisTemplateVars = buildSynthesisTemplateVariables(
      bundle: synthesisTemplateBundle,
    );
    List<Map<String, dynamic>> buildSynthesisInput() {
      return <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{'role': 'user', 'content': latestUserQuery},
      ];
    }

    final rawPhaseOneTurn = _tryParseAssistantTurnFromRawText(phaseOneText);
    final rawPhaseOneProjection = rawPhaseOneTurn != null
        ? AssistantDisplayTextResolver.projectTurn(rawPhaseOneTurn)
        : null;
    final phaseOneExecutionSignalsPresent = _hasPhaseOneExecutionSignals(
      phaseOneResult.traces,
    );
    final rawDirectAnswerDecision = _phaseOneDirectAnswerGate.evaluate(
      rawFinalText: phaseOneText,
      synthesisReadiness: synthesisReadiness,
      executionSignalsPresent: phaseOneExecutionSignalsPresent,
    );
    final explicitPhaseOneSkillRunPlans = _subagentPlanCodec
        .buildExplicitSkillRunPlans(
          answerPayload: phaseOneAnswerPayload,
          latestUserQuery: latestUserQuery,
          fallbackProblemClass: planView.problemClassWireName,
          primaryDomainId: domainId,
        );
    final phaseOneContinuationCarryover = _hasContinuationCarryoverContext(
      AssistantPipelineTemplateVariablesView.fromMap(synthesisTemplateVars),
    );
    final phaseOneCompatDirectAnswer =
        rawDirectAnswerDecision.reason ==
        PhaseOneDirectAnswerReason.compatDirectAnswer;
    final suppressDerivedPhaseOneSkillRunPlans =
        phaseOneContinuationCarryover || phaseOneCompatDirectAnswer;
    final derivedPhaseOneSkillRunPlans =
        explicitPhaseOneSkillRunPlans.isEmpty &&
            !suppressDerivedPhaseOneSkillRunPlans
        ? _subagentPlanCodec.buildDerivedSkillRunPlansFromIntent(
            planView: planView,
            latestUserQuery: latestUserQuery,
            primaryDomainId: domainId,
          )
        : const <SubagentPlan>[];
    var effectivePhaseOneText = phaseOneText;
    var effectivePhaseOneAnswerPayload = phaseOneAnswerPayload;
    var effectivePhaseOneTurn = rawPhaseOneTurn;
    var effectivePhaseOneProjection = rawPhaseOneProjection;
    var effectivePhaseOneTraces = List<AssistantTraceEvent>.of(
      phaseOneResult.traces,
    );
    var effectivePhaseOneDegraded = phaseOneResult.degraded;
    var effectivePhaseOneFailureCode = phaseOneResult.failureCode;
    var directAnswerDecision = rawDirectAnswerDecision;
    var phaseOneRecoveryApplied = false;
    var phaseOneModelRepairApplied = false;
    var phaseOneModelRepairAttempted = false;
    var phaseOneModelRepairProducedText = false;
    var phaseOneModelRepairFailureCode = '';
    final phaseOneHasFallbackSignal =
        effectivePhaseOneTurn != null &&
        (effectivePhaseOneTurn.nextActionType == AssistantNextAction.abort ||
            effectivePhaseOneTurn.messageKindType ==
                AssistantMessageKind.fallback);
    final shouldIgnorePhaseOneArtifact =
        !phaseOneExecutionSignalsPresent &&
        (effectivePhaseOneDegraded ||
            effectivePhaseOneFailureCode.trim().isNotEmpty ||
            phaseOneHasFallbackSignal);
    if (shouldIgnorePhaseOneArtifact) {
      effectivePhaseOneText = '';
      effectivePhaseOneAnswerPayload = const <String, dynamic>{};
      effectivePhaseOneTurn = null;
      effectivePhaseOneProjection = null;
      effectivePhaseOneDegraded = false;
      effectivePhaseOneFailureCode = '';
      directAnswerDecision = const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.artifactIgnored,
      );
    }
    final allowPhaseOneContractRepair =
        explicitPhaseOneSkillRunPlans.isEmpty &&
        (!phaseOneExecutionSignalsPresent ||
            phaseOneContinuationCarryover ||
            planView.answerShape == AnswerShape.directAnswer);
    if (explicitPhaseOneSkillRunPlans.isEmpty &&
        synthesisReadiness.ready &&
        !shouldIgnorePhaseOneArtifact &&
        allowPhaseOneContractRepair &&
        rawDirectAnswerDecision.reason.repairable) {
      final recoveredPhaseOneEnvelopeText =
          _recoverPhaseOneDirectAnswerEnvelopeText(
            rawText: phaseOneText,
            traces: phaseOneResult.traces,
            templateVariables: synthesisTemplateVars,
          );
      if (recoveredPhaseOneEnvelopeText.isNotEmpty) {
        effectivePhaseOneText = recoveredPhaseOneEnvelopeText;
        effectivePhaseOneAnswerPayload = parseAnswerPayload(
          rawFinalText: recoveredPhaseOneEnvelopeText,
          traces: effectivePhaseOneTraces,
        );
        effectivePhaseOneTurn = _tryParseAssistantTurnFromRawText(
          recoveredPhaseOneEnvelopeText,
        );
        effectivePhaseOneProjection = effectivePhaseOneTurn != null
            ? AssistantDisplayTextResolver.projectTurn(effectivePhaseOneTurn)
            : null;
        directAnswerDecision = _phaseOneDirectAnswerGate.evaluate(
          rawFinalText: recoveredPhaseOneEnvelopeText,
          synthesisReadiness: synthesisReadiness,
          executionSignalsPresent: phaseOneExecutionSignalsPresent,
        );
        phaseOneRecoveryApplied = directAnswerDecision.shouldSkipSynthesis;
      }
    }
    final phaseOneHasRenderableContent =
        effectivePhaseOneProjection?.hasRenderableContent ??
        (() {
          final phaseOneAnswerView = AssistantAnswerPayloadReadView(
            effectivePhaseOneAnswerPayload,
          );
          return phaseOneAnswerView.userMarkdownTrimmed.isNotEmpty ||
              phaseOneAnswerView.resultTextTrimmed.isNotEmpty;
        })();
    final phaseOneHasRenderableAnswer = _hasRenderableAnswerPayload(
      payload: effectivePhaseOneAnswerPayload,
      turn: effectivePhaseOneTurn,
      projectionRenderableContent:
          effectivePhaseOneProjection?.hasRenderableContent ?? false,
    );
    final shouldAttemptPhaseOneModelRepair =
        explicitPhaseOneSkillRunPlans.isEmpty &&
        synthesisReadiness.ready &&
        !shouldIgnorePhaseOneArtifact &&
        !directAnswerDecision.shouldSkipSynthesis &&
        phaseOneHasRenderableAnswer &&
        allowPhaseOneContractRepair &&
        directAnswerDecision.reason.repairable;
    if (shouldAttemptPhaseOneModelRepair) {
      phaseOneModelRepairAttempted = true;
      final phaseOneRepairResult =
          await _repairPhaseOneDirectAnswerEnvelopeText(
            rawText: effectivePhaseOneText,
            traces: effectivePhaseOneTraces,
            messages: messages,
            latestUserQuery: latestUserQuery,
            templateContext: templateContext,
            templateVariables: synthesisTemplateVars,
            sessionId: sessionId,
            runId: runId,
            traceId: traceId,
            onTraceEvent: onTraceEvent,
          );
      if (phaseOneRepairResult.traces.isNotEmpty) {
        effectivePhaseOneTraces = <AssistantTraceEvent>[
          ...effectivePhaseOneTraces,
          ...phaseOneRepairResult.traces,
        ];
      }
      phaseOneModelRepairFailureCode = phaseOneRepairResult.failureCode;
      if (phaseOneRepairResult.finalText.isNotEmpty) {
        phaseOneModelRepairProducedText = true;
        effectivePhaseOneText = phaseOneRepairResult.finalText;
        effectivePhaseOneAnswerPayload = parseAnswerPayload(
          rawFinalText: phaseOneRepairResult.finalText,
          traces: effectivePhaseOneTraces,
        );
        effectivePhaseOneTurn = _tryParseAssistantTurnFromRawText(
          phaseOneRepairResult.finalText,
        );
        effectivePhaseOneProjection = effectivePhaseOneTurn != null
            ? AssistantDisplayTextResolver.projectTurn(effectivePhaseOneTurn)
            : null;
        effectivePhaseOneDegraded = phaseOneRepairResult.degraded;
        effectivePhaseOneFailureCode = phaseOneRepairResult.failureCode;
        directAnswerDecision = _phaseOneDirectAnswerGate.evaluate(
          rawFinalText: phaseOneRepairResult.finalText,
          synthesisReadiness: synthesisReadiness,
          executionSignalsPresent: phaseOneExecutionSignalsPresent,
        );
        phaseOneModelRepairApplied = directAnswerDecision.shouldSkipSynthesis;
      }
    }
    refreshPhaseOneStructuredCarryover(effectivePhaseOneAnswerPayload);
    var streamedRetrievalProcessingSummary = '';
    var streamedAnswerReadinessSummary = '';
    final baseSynthesisTraceForwarder = _buildAnswerProcessTraceForwarder(
      onTraceEvent,
      runId,
      traceId,
    );
    void captureStreamedSummaries(AssistantTraceEvent event) {
      if (event.type != AssistantTraceEventType.thinkingProgress) {
        return;
      }
      final data = event.data ?? const <String, dynamic>{};
      if (data[AssistantPipelineDiagnosticsKeys.streaming] != true ||
          data[AssistantPipelineDiagnosticsKeys.extracted] != true) {
        return;
      }
      if (event.message.isEmpty) {
        return;
      }
      final fieldPath =
          (data[AssistantPipelineDiagnosticsKeys.fieldPath] as String?)
              ?.trim() ??
          '';
      if (fieldPath ==
          AssistantPipelineDiagnosticsKeys.retrievalProcessingSummary) {
        streamedRetrievalProcessingSummary = _mergeStableNarrativeDeltaText(
          previous: streamedRetrievalProcessingSummary,
          incoming: event.message,
        );
        return;
      }
      if (fieldPath ==
          AssistantPipelineDiagnosticsKeys.answerProcessingReadinessSummary) {
        streamedAnswerReadinessSummary = _mergeStableNarrativeDeltaText(
          previous: streamedAnswerReadinessSummary,
          incoming: event.message,
        );
      }
    }

    final synthesisTraceForwarder = baseSynthesisTraceForwarder == null
        ? null
        : (AssistantTraceEvent event) {
            captureStreamedSummaries(event);
            baseSynthesisTraceForwarder(event);
          };
    var templateVersionUsed = synthTemplateVersion;
    var phaseOneRoute = 'formal_synthesis';
    ReactRuntimeResult mergedResult;
    late final Map<String, dynamic> answerPayloadBeforeSubagent;
    late final List<SubagentPlan> skillRunPlans;
    final suppressDerivedPlanForDirectAnswer =
        planView.answerShape == AnswerShape.directAnswer;
    final suppressDerivedPlanExecution =
        directAnswerDecision.shouldSkipSynthesis ||
        phaseOneRecoveryApplied ||
        phaseOneModelRepairApplied;
    final phaseOneSkillRunPlans = explicitPhaseOneSkillRunPlans.isNotEmpty
        ? explicitPhaseOneSkillRunPlans
        : ((suppressDerivedPlanExecution || suppressDerivedPlanForDirectAnswer)
              ? const <SubagentPlan>[]
              : derivedPhaseOneSkillRunPlans);
    if (phaseOneSkillRunPlans.isNotEmpty) {
      phaseOneRoute = 'phase_one_subagent_ready';
      final shortcutTrace = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'phase one subagent plan ready, skip pre-fusion synthesis',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        visibility: TraceVisibility.system,
        data: <String, dynamic>{
          'stage': 'phase_one_subagent_ready',
          'reason': 'phase_one_subagent_plan_owner',
          'subagentPlanCount': phaseOneSkillRunPlans.length,
          'planSource': explicitPhaseOneSkillRunPlans.isNotEmpty
              ? 'phase_one'
              : 'intent_secondary_skills',
        },
      );
      onTraceEvent?.call(shortcutTrace);
      mergedResult = ReactRuntimeResult(
        finalText: effectivePhaseOneText,
        traces: <AssistantTraceEvent>[
          ...effectivePhaseOneTraces,
          shortcutTrace,
        ],
        degraded: effectivePhaseOneDegraded,
        failureCode: effectivePhaseOneFailureCode,
      );
      answerPayloadBeforeSubagent = effectivePhaseOneAnswerPayload;
      skillRunPlans = phaseOneSkillRunPlans;
    } else if (blockedProcessStepId == ProcessStepId.retrievalProcessing &&
        !directAnswerDecision.shouldSkipSynthesis &&
        phaseOneHasRenderableAnswer &&
        synthesisReadiness.replanTask == null) {
      final preserveRenderablePhaseOne = phaseOneHasRenderableAnswer;
      phaseOneRoute = preserveRenderablePhaseOne
          ? 'retrieval_blocked_renderable'
          : 'retrieval_blocked';
      final shortcutTrace = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'retrieval processing blocked, stop synthesis',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        visibility: TraceVisibility.system,
        data: <String, dynamic>{
          'stage': 'retrieval_blocked',
          'reason': blockedProcessMessage,
          'renderableAnswerPreserved': preserveRenderablePhaseOne,
        },
      );
      onTraceEvent?.call(shortcutTrace);
      if (preserveRenderablePhaseOne) {
        mergedResult = ReactRuntimeResult(
          finalText: effectivePhaseOneText,
          traces: <AssistantTraceEvent>[
            ...effectivePhaseOneTraces,
            shortcutTrace,
          ],
          degraded: effectivePhaseOneDegraded,
          failureCode: effectivePhaseOneFailureCode,
        );
        answerPayloadBeforeSubagent = effectivePhaseOneAnswerPayload;
      } else {
        final failureMessage = blockedProcessMessage.isNotEmpty
            ? blockedProcessMessage
            : assistantPipelineDefaultFailureMessageForStep(
                ProcessStepId.retrievalProcessing,
              );
        mergedResult = ReactRuntimeResult(
          finalText: _buildStageFailureAssistantTurnEnvelopeText(
            stepId: ProcessStepId.retrievalProcessing,
            failureCode: 'retrieval_processing_blocked',
            failureMessage: failureMessage,
          ),
          traces: <AssistantTraceEvent>[
            ...effectivePhaseOneTraces,
            shortcutTrace,
          ],
          degraded: true,
          failureCode: 'retrieval_processing_blocked',
        );
        answerPayloadBeforeSubagent = parseAnswerPayload(
          rawFinalText: mergedResult.finalText,
          traces: mergedResult.traces,
        );
      }
      skillRunPlans = const <SubagentPlan>[];
    } else {
      if (directAnswerDecision.shouldSkipSynthesis) {
        phaseOneRoute = 'phase_one_direct_answer';
        templateVersionUsed = PhaseOneDirectAnswerGate.directTemplateVersion;
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'phase one answer ready, continue streamed synthesis',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            visibility: TraceVisibility.system,
            data: <String, dynamic>{
              'stage': 'phase_one_direct_answer',
              'reason': directAnswerDecision.reasonWireName,
            },
          ),
        );
      }
      final synthesisInput = buildSynthesisInput();
      final answerStageBudget = synthesisReadiness.ready
          ? 1
          : request.answerStageBudget;
      final answerStageToolNames =
          synthesisReadiness.ready || request.maxRequeryRounds <= 0
          ? const <String>[]
          : allowedToolNames;
      var synthesisResult = const ReactRuntimeResult(
        finalText: '',
        traces: <AssistantTraceEvent>[],
        degraded: true,
        failureCode: AssistantFailureCode.answerStreamFailed,
      );
      final canStreamSynthesis =
          synthesisReadiness.ready && _runtime.supportsStructuredStreaming;
      if (canStreamSynthesis) {
        final maxAnswerStreamAttempts = directAnswerDecision.shouldSkipSynthesis
            ? 1
            : 2;
        ReactRuntimeResult? streamedSynthesisResult;
        for (
          var attempt = 1;
          attempt <= maxAnswerStreamAttempts;
          attempt += 1
        ) {
          streamedAnswerReadinessSummary = '';
          var sawAnswerDelta = false;
          var providerFailureCode = AssistantFailureCode.none;
          var providerFailureDiagnostics = <String, dynamic>{};
          final streamedText = await _runtime.streamSynthesis(
            messages: synthesisInput,
            goal: latestUserQuery,
            onDelta: (delta) {
              if (delta.trim().isNotEmpty) {
                sawAnswerDelta = true;
              }
            },
            streamJsonFieldPaths: const <String>[
              AssistantPipelineDiagnosticsKeys.retrievalProcessingSummary,
              AssistantPipelineDiagnosticsKeys.answerProcessingReadinessSummary,
            ],
            templateContext: templateContext,
            templateVariables: synthesisTemplateVars,
            templateId: 'synthesizer.final_answer',
            templateVersion: synthTemplateVersion,
            sessionId: sessionId,
            runId: runId,
            traceId: traceId,
            onTraceEvent: synthesisTraceForwarder,
            onStreamFailure: (failureCode, diagnostics) {
              providerFailureCode = failureCode;
              providerFailureDiagnostics = <String, dynamic>{...diagnostics};
            },
          );
          if (streamedText.trim().isNotEmpty && sawAnswerDelta) {
            final synthesisInputText = synthesisInput
                .map((item) => (item['content'] ?? '').toString())
                .join('\n');
            final outputTokens = usage_stats.estimateTokenCount(streamedText);
            final inputTokens = usage_stats.estimateTokenCount(
              synthesisInputText,
            );
            final synthesisTrace = AssistantTraceEvent(
              type: AssistantTraceEventType.lifecycleStart,
              message: 'llm request synthesis stream',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              visibility: TraceVisibility.system,
              data: <String, dynamic>{
                'stage': 'synthesis_stream',
                'attempt': attempt,
                'estimatedTokens': outputTokens,
                'usageEntries': <Map<String, dynamic>>[
                  LlmUsageLedgerEntry(
                    provider: 'synthesis_stream',
                    modelId: 'streaming_final_answer',
                    modelRef: 'streaming_final_answer',
                    streaming: true,
                    source: 'estimated',
                    inputTokens: inputTokens,
                    outputTokens: outputTokens,
                    totalTokens: inputTokens + outputTokens,
                    latencyMs: 0,
                  ).toJson(),
                ],
              },
            );
            onTraceEvent?.call(synthesisTrace);
            streamedSynthesisResult = ReactRuntimeResult(
              finalText: streamedText,
              traces: <AssistantTraceEvent>[synthesisTrace],
            );
            break;
          }
          final answerStreamFailureCode = sawAnswerDelta
              ? AssistantFailureCode.answerStreamFailed
              : AssistantFailureCode.answerStreamNotStarted;
          final failureTrace = AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleEnd,
            message: attempt < maxAnswerStreamAttempts
                ? 'answer stream failed, retry synthesis'
                : 'answer stream failed, stop synthesis',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            visibility: TraceVisibility.system,
            data: <String, dynamic>{
              'stage': 'synthesis_stream',
              'failureCode': answerStreamFailureCode,
              'providerFailureCode': providerFailureCode,
              'attempt': attempt,
              'maxAttempts': maxAnswerStreamAttempts,
              'retrying': attempt < maxAnswerStreamAttempts,
              if (providerFailureDiagnostics.isNotEmpty)
                'diagnostics': providerFailureDiagnostics,
            },
          );
          onTraceEvent?.call(failureTrace);
          if (attempt >= maxAnswerStreamAttempts) {
            synthesisResult = ReactRuntimeResult(
              finalText: _buildStageFailureAssistantTurnEnvelopeText(
                stepId: ProcessStepId.answerOrganization,
                failureCode: answerStreamFailureCode,
                failureMessage: assistantPipelineDefaultFailureMessageForStep(
                  ProcessStepId.answerOrganization,
                ),
              ),
              traces: <AssistantTraceEvent>[failureTrace],
              degraded: true,
              failureCode: answerStreamFailureCode,
            );
          }
        }
        if (streamedSynthesisResult != null) {
          synthesisResult = streamedSynthesisResult;
        } else if (!directAnswerDecision.shouldSkipSynthesis &&
            (synthesisResult.degraded ||
                synthesisResult.failureCode.trim().isNotEmpty)) {
          final fallbackTrace = AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'answer stream failed, fallback to non-stream synthesis',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            visibility: TraceVisibility.system,
            data: <String, dynamic>{
              'stage': 'synthesis_non_stream_fallback',
              'previousFailureCode': synthesisResult.failureCode,
            },
          );
          onTraceEvent?.call(fallbackTrace);
          try {
            final nonStreamSynthesisResult = await _runtime.run(
              messages: synthesisInput,
              maxIterations: answerStageBudget,
              goal: latestUserQuery,
              availableToolNamesOverride: answerStageToolNames,
              templateId: 'synthesizer.final_answer',
              templateVersion: synthTemplateVersion,
              templateContext: templateContext,
              templateVariables: synthesisTemplateVars,
              sessionId: sessionId,
              runId: runId,
              traceId: traceId,
              onTraceEvent: synthesisTraceForwarder,
              callOptions: const LlmCallOptions.synthesis(),
              onDelta: _buildThinkingDeltaForwarder(
                onTraceEvent,
                runId,
                traceId,
              ),
            );
            if (nonStreamSynthesisResult.finalText.trim().isNotEmpty) {
              synthesisResult = ReactRuntimeResult(
                finalText: nonStreamSynthesisResult.finalText,
                traces: <AssistantTraceEvent>[
                  ...synthesisResult.traces,
                  fallbackTrace,
                  ...nonStreamSynthesisResult.traces,
                ],
                degraded: nonStreamSynthesisResult.degraded,
                failureCode: nonStreamSynthesisResult.failureCode,
                runtimeFailure:
                    nonStreamSynthesisResult.effectiveRuntimeFailure,
              );
            }
          } catch (error) {
            final fallbackFailureTrace = AssistantTraceEvent(
              type: AssistantTraceEventType.lifecycleEnd,
              message: 'non-stream synthesis fallback failed',
              timestamp: DateTime.now(),
              runId: runId,
              traceId: traceId,
              visibility: TraceVisibility.system,
              data: <String, dynamic>{
                'stage': 'synthesis_non_stream_fallback',
                'failureCode': AssistantFailureCode.answerStreamFailed,
                'reason': error.toString(),
              },
            );
            onTraceEvent?.call(fallbackFailureTrace);
            synthesisResult = ReactRuntimeResult(
              finalText: synthesisResult.finalText,
              traces: <AssistantTraceEvent>[
                ...synthesisResult.traces,
                fallbackTrace,
                fallbackFailureTrace,
              ],
              degraded: synthesisResult.degraded,
              failureCode: synthesisResult.failureCode,
              runtimeFailure: synthesisResult.effectiveRuntimeFailure,
            );
          }
        }
      } else {
        synthesisResult = await _runtime.run(
          messages: synthesisInput,
          maxIterations: answerStageBudget,
          goal: latestUserQuery,
          availableToolNamesOverride: answerStageToolNames,
          templateId: 'synthesizer.final_answer',
          templateVersion: synthTemplateVersion,
          templateContext: templateContext,
          templateVariables: synthesisTemplateVars,
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          onTraceEvent: synthesisTraceForwarder,
          callOptions: const LlmCallOptions.synthesis(),
          onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
        );
      }
      if (!synthesisResult.degraded && synthesisResult.failureCode.isEmpty) {
        synthesisResult = await _repairInvalidSynthesisResult(
          currentResult: synthesisResult,
          synthesisInput: synthesisInput,
          latestUserQuery: latestUserQuery,
          templateContext: templateContext,
          carriedUnderstandingSnapshot: carriedUnderstandingSnapshot,
          carriedRetrievalProcessing: carriedRetrievalProcessing,
          carriedHistoricalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
          templateVariables: synthesisTemplateVars,
          streamedRetrievalProcessingSummary:
              streamedRetrievalProcessingSummary,
          streamedAnswerReadinessSummary: streamedAnswerReadinessSummary,
          templateId: 'synthesizer.final_answer',
          templateVersion: synthTemplateVersion,
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          onTraceEvent: synthesisTraceForwarder,
        );
      }
      final synthesisResultTurn = _tryParseAssistantTurnFromRawText(
        synthesisResult.finalText,
      );
      final synthesisResultProjection = synthesisResultTurn != null
          ? AssistantDisplayTextResolver.projectTurn(synthesisResultTurn)
          : null;
      final synthesisResultPayload = parseAnswerPayload(
        rawFinalText: synthesisResult.finalText,
        traces: synthesisResult.traces,
      );
      final synthesisHasRenderableAnswer = _hasRenderableAnswerPayload(
        payload: synthesisResultPayload,
        turn: synthesisResultTurn,
        projectionRenderableContent:
            synthesisResultProjection?.hasRenderableContent ?? false,
      );
      if (directAnswerDecision.shouldSkipSynthesis &&
          phaseOneHasRenderableAnswer &&
          (synthesisResult.degraded ||
              synthesisResult.failureCode.trim().isNotEmpty) &&
          !synthesisHasRenderableAnswer) {
        final preserveTrace = AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleEnd,
          message: 'synthesis failed, preserve phase one direct answer',
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          visibility: TraceVisibility.system,
          data: <String, dynamic>{
            'stage': 'phase_one_direct_answer_preserved',
            'failureCode': synthesisResult.failureCode,
          },
        );
        onTraceEvent?.call(preserveTrace);
        synthesisResult = ReactRuntimeResult(
          finalText: effectivePhaseOneText,
          traces: <AssistantTraceEvent>[
            ...synthesisResult.traces,
            preserveTrace,
          ],
          degraded: false,
          failureCode: '',
        );
      }
      mergedResult = ReactRuntimeResult(
        finalText: _ensureAssistantTurnEnvelopeText(synthesisResult.finalText),
        traces: <AssistantTraceEvent>[
          ...effectivePhaseOneTraces,
          ...synthesisResult.traces,
        ],
        degraded: synthesisResult.degraded,
        failureCode: synthesisResult.failureCode,
        runtimeFailure: synthesisResult.effectiveRuntimeFailure,
      );
      answerPayloadBeforeSubagent = parseAnswerPayload(
        rawFinalText: mergedResult.finalText,
        traces: mergedResult.traces,
      );
      final answerPayloadBeforeSubagentView = AssistantAnswerPayloadReadView(
        answerPayloadBeforeSubagent,
      );
      final effectivePhaseOneAnswerPayloadView = AssistantAnswerPayloadReadView(
        effectivePhaseOneAnswerPayload,
      );
      if (answerPayloadBeforeSubagentView.subagentPlanMaps.isEmpty &&
          effectivePhaseOneAnswerPayloadView.subagentPlanMaps.isNotEmpty) {
        answerPayloadBeforeSubagent['subagentPlan'] =
            effectivePhaseOneAnswerPayloadView.subagentPlanMaps;
      }
      final suppressPostSynthesisSkillRunPlans =
          directAnswerDecision.shouldSkipSynthesis ||
          phaseOneRecoveryApplied ||
          phaseOneModelRepairApplied ||
          phaseOneCompatDirectAnswer ||
          (planView.answerShape == AnswerShape.directAnswer &&
              phaseOneHasRenderableAnswer);
      skillRunPlans = suppressPostSynthesisSkillRunPlans
          ? const <SubagentPlan>[]
          : _subagentPlanCodec.buildSkillRunPlans(
              planView: planView,
              answerPayload: answerPayloadBeforeSubagent,
              latestUserQuery: latestUserQuery,
              primaryDomainId: domainId,
            );
    }
    final phaseOneAnswerPayloadDiagnosticsView = AssistantAnswerPayloadReadView(
      effectivePhaseOneAnswerPayload,
    );
    final phaseOneRoutingDiagnostics = AssistantPipelineDiagnosticsHelper()
        .buildPhaseOneRoutingDiagnostics(
          phaseOneRoute: phaseOneRoute,
          synthesisReadinessReady: synthesisReadiness.ready,
          synthesisReadinessReason: synthesisReadiness.reason,
          rawDirectAnswerReason: rawDirectAnswerDecision.reasonWireName,
          directAnswerReason: directAnswerDecision.reasonWireName,
          directAnswerShouldSkipSynthesis:
              directAnswerDecision.shouldSkipSynthesis,
          phaseOneRecoveryApplied: phaseOneRecoveryApplied,
          phaseOneModelRepairApplied: phaseOneModelRepairApplied,
          phaseOneModelRepairAttempted: phaseOneModelRepairAttempted,
          phaseOneModelRepairProducedText: phaseOneModelRepairProducedText,
          phaseOneModelRepairFailureCode: phaseOneModelRepairFailureCode,
          phaseOneParsedContractTurn: effectivePhaseOneTurn != null,
          phaseOneNextAction:
              effectivePhaseOneTurn?.nextActionType.wireName ??
              phaseOneAnswerPayloadDiagnosticsView.nextActionWireName,
          phaseOneMessageKind:
              effectivePhaseOneTurn?.messageKindType.wireName ??
              phaseOneAnswerPayloadDiagnosticsView.messageKindTrimmed,
          phaseOnePhaseId:
              effectivePhaseOneTurn?.phaseIdType.wireName ??
              phaseOneAnswerPayloadDiagnosticsView.phaseIdTrimmed,
          phaseOneActionCode:
              effectivePhaseOneTurn?.actionCodeType.wireName ??
              phaseOneAnswerPayloadDiagnosticsView.actionCodeTrimmed,
          phaseOneReasonCode:
              effectivePhaseOneTurn?.reasonCodeType.wireName ??
              phaseOneAnswerPayloadDiagnosticsView.reasonCodeTrimmed,
          phaseOneHasRenderableContent: phaseOneHasRenderableContent,
          phaseOneExplicitSkillRunPlanCount:
              explicitPhaseOneSkillRunPlans.length,
          phaseOneDerivedSkillRunPlanCount: derivedPhaseOneSkillRunPlans.length,
          phaseOneSkillRunPlanCount: phaseOneSkillRunPlans.length,
          typedExecutionReady: phaseOneSkillRunPlans.isNotEmpty,
          phaseOneSkillRunPlanSource: phaseOneSkillRunPlans.isNotEmpty
              ? (explicitPhaseOneSkillRunPlans.isNotEmpty
                    ? 'phase_one'
                    : 'intent_secondary_skills')
              : 'none',
          phaseOneExecutionSignalsPresent: phaseOneExecutionSignalsPresent,
          phaseOneContinuationCarryover: phaseOneContinuationCarryover,
          allowPhaseOneContractRepair: allowPhaseOneContractRepair,
          phaseOneSkillRunPlans: phaseOneSkillRunPlans
              .map((item) => item.toJson())
              .toList(growable: false),
          templateVersionUsed: templateVersionUsed,
        );
    final primaryToolResults = mergedResult.traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(AssistantToolResultRow.fromTraceEvent)
        .toList(growable: false);
    final primaryUiReferences = _buildUiReferences(
      primaryToolResults,
      isRealtimeLike: isRealtimeLikeRequest(
        fallbackProblemClass: planView.problemClassWireName,
        answerPayload: answerPayloadBeforeSubagent,
      ),
    );
    final primaryAcceptedEvidence = _uiReferenceWireMaps(primaryUiReferences);
    final primarySkillRun = _buildPrimarySkillRun(
      planView: planView,
      domainId: domainId,
      answerPayload: answerPayloadBeforeSubagent,
      result: mergedResult,
      executionShell: effectiveExecutionShell,
      references: primaryAcceptedEvidence,
    );
    final skillRouteOutput = _buildSkillRouteOutput(
      userQuery: latestUserQuery,
      planView: planView,
      primaryDomainId: domainId,
      executionShell: effectiveExecutionShell,
      subagentPlans: skillRunPlans,
    );
    final subagentRuns = await _executeSubagentPlans(
      answerPayload: <String, dynamic>{
        ...answerPayloadBeforeSubagent,
        'subagentPlan': skillRunPlans
            .map((item) => item.toJson())
            .toList(growable: false),
      },
      request: request,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      templateContext: templateContext,
      templateVariables: templateVariables,
      onTraceEvent: onTraceEvent,
    );
    final skillRuns = <SkillRun>[
      primarySkillRun,
      ...subagentRuns.map(_skillRunFromCurrentSubagentRun),
    ];
    final aggregationState = _buildAggregationState(
      planView: planView,
      skillRuns: skillRuns,
      answerPayload: answerPayloadBeforeSubagent,
    );
    final primarySkillSynthesisResult = _buildPrimarySkillSynthesisResult(
      primaryDomainId: domainId,
      answerPayload: answerPayloadBeforeSubagent,
      fallbackSummary: primarySkillRun.resultSummary,
      acceptedEvidence: primaryAcceptedEvidence,
      answerReady: primarySkillRun.answerReady,
    );
    final skillSynthesisInput = SkillSynthesisInput.fromExecution(
      userQuery: latestUserQuery,
      skillRoute: skillRouteOutput,
      subagentRuns: subagentRuns,
      primarySkillResult: primarySkillSynthesisResult,
      sessionSummary: templateVariablesView.hasContinuationCarryoverContext
          ? templateVariablesView.recentDialogueRounds
                .map(
                  (item) => (item['assistantSummary'] as String?)?.trim() ?? '',
                )
                .where((item) => item.isNotEmpty)
                .join(' | ')
          : '',
    );
    if (subagentRuns.isNotEmpty) {
      final runsForModel = subagentRunsForModel(subagentRuns);
      final fusionTemplateVars = buildFusionTemplateVariables(
        bundle: synthesisTemplateBundle,
        skillRuns: skillRuns
            .map((item) => item.toJson())
            .toList(growable: false),
        aggregationState: aggregationState.toJson(),
        subagentRuns: runsForModel,
        skillSynthesis: skillSynthesisInput.toJson(),
      );
      templateVersionUsed = synthTemplateVersion;
      final subagentSynthesisInput = <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{
          'role': 'system',
          'content':
              'skill_synthesis_input: ${jsonEncode(skillSynthesisInput.toJson())}',
        },
        <String, dynamic>{
          'role': 'system',
          'content': 'subagent_runs=${jsonEncode(runsForModel)}',
        },
        <String, dynamic>{
          'role': 'system',
          'content': await _renderPromptSnippet(
            'synthesis_aggregation',
            variables: <String, dynamic>{
              'anchorReminder': '',
              'continuationReminder': '',
            },
          ),
        },
        <String, dynamic>{'role': 'user', 'content': latestUserQuery},
      ];
      var subagentSynthesis = await _runtime.run(
        messages: subagentSynthesisInput,
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: 'synthesizer.final_answer',
        templateVersion: synthTemplateVersion,
        templateContext: templateContext,
        templateVariables: fusionTemplateVars,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: synthesisTraceForwarder,
        callOptions: const LlmCallOptions.synthesis(),
        onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
      );
      subagentSynthesis = await _repairInvalidSynthesisResult(
        currentResult: subagentSynthesis,
        synthesisInput: subagentSynthesisInput,
        latestUserQuery: latestUserQuery,
        templateContext: templateContext,
        carriedUnderstandingSnapshot: carriedUnderstandingSnapshot,
        carriedRetrievalProcessing: carriedRetrievalProcessing,
        carriedHistoricalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
        templateVariables: fusionTemplateVars,
        streamedRetrievalProcessingSummary: streamedRetrievalProcessingSummary,
        streamedAnswerReadinessSummary: streamedAnswerReadinessSummary,
        templateId: 'synthesizer.final_answer',
        templateVersion: synthTemplateVersion,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: synthesisTraceForwarder,
      );
      mergedResult = ReactRuntimeResult(
        finalText: _ensureAssistantTurnEnvelopeText(
          subagentSynthesis.finalText,
        ),
        traces: <AssistantTraceEvent>[
          ...mergedResult.traces,
          ...subagentSynthesis.traces,
        ],
        degraded: mergedResult.degraded || subagentSynthesis.degraded,
        failureCode: subagentSynthesis.failureCode.isNotEmpty
            ? subagentSynthesis.failureCode
            : mergedResult.failureCode,
        runtimeFailure:
            subagentSynthesis.effectiveRuntimeFailure ??
            mergedResult.effectiveRuntimeFailure,
      );
    }
    final responseTraces = <AssistantTraceEvent>[
      ...supplementalTraces,
      ...mergedResult.traces,
    ];
    var finalResult = ReactRuntimeResult(
      finalText: mergedResult.finalText,
      traces: responseTraces,
      degraded: mergedResult.degraded,
      failureCode: mergedResult.failureCode,
      runtimeFailure: mergedResult.effectiveRuntimeFailure,
    );
    var finalResultTurn = _tryParseAssistantTurnFromRawText(
      finalResult.finalText,
    );
    var finalResultProjection = finalResultTurn != null
        ? AssistantDisplayTextResolver.projectTurn(finalResultTurn)
        : null;
    var finalResponseHasRenderableContent =
        finalResultProjection?.hasRenderableContent ?? false;
    var finalResponseIsFallback =
        finalResultTurn?.messageKindType == AssistantMessageKind.fallback ||
        finalResultTurn?.nextActionType == AssistantNextAction.abort;
    if (blockedProcessStepId == ProcessStepId.unknown &&
        finalResponseIsFallback &&
        (finalResult.failureCode.trim().isNotEmpty ||
            !finalResponseHasRenderableContent)) {
      blockedProcessStepId = ProcessStepId.answerOrganization;
      blockedProcessMessage = assistantPipelineDefaultFailureMessageForStep(
        ProcessStepId.answerOrganization,
      );
      finalResult = ReactRuntimeResult(
        finalText: _buildStageFailureAssistantTurnEnvelopeText(
          stepId: ProcessStepId.answerOrganization,
          failureCode: 'answer_organization_failed',
          failureMessage: blockedProcessMessage,
        ),
        traces: responseTraces,
        degraded: true,
        failureCode: 'answer_organization_failed',
        runtimeFailure: RuntimeFailure(
          code: 'ASSISTANT.SYSTEM.answer_organization_failed',
          origin: RuntimeFailureOrigin.system,
          kind: RuntimeFailureKind.internal,
          nature: RuntimeFailureNature.bug,
          location: const RuntimeFailureLocation(
            businessObject: 'assistant_turn',
            functionModule: 'assistant_pipeline_engine',
          ),
          context: const RuntimeFailureContext(),
        ),
      );
      finalResultTurn = _tryParseAssistantTurnFromRawText(
        finalResult.finalText,
      );
      finalResultProjection = finalResultTurn != null
          ? AssistantDisplayTextResolver.projectTurn(finalResultTurn)
          : null;
      finalResponseHasRenderableContent =
          finalResultProjection?.hasRenderableContent ?? false;
      finalResponseIsFallback =
          finalResultTurn?.messageKindType == AssistantMessageKind.fallback ||
          finalResultTurn?.nextActionType == AssistantNextAction.abort;
    }
    return SynthesisDraft(
      runId: runId,
      traceId: traceId,
      sessionId: sessionId,
      contextAssembly: contextAssembly,
      synthesisReadiness: synthesisReadiness,
      finalResult: finalResult,
      planView: planView,
      skillRuns: skillRuns,
      aggregationState: aggregationState,
      subagentPlan: skillRunPlans,
      subagentRuns: subagentRuns,
      dialogueRoundScript: dialogueRoundScript,
      candidateDomains: domainCatalog,
      skillExecutionShell: effectiveExecutionShell,
      templateVersionUsed: templateVersionUsed,
      domainCatalogVersion: domainCatalogVersion,
      retrievalPolicy: retrievalPolicy,
      answerBoundaryPolicy: answerBoundaryPolicy,
      previousSlotState: previousSlotState,
      phaseOneRoutingDiagnostics: phaseOneRoutingDiagnostics,
      understandingSnapshot: carriedUnderstandingSnapshot,
      retrievalProcessing: carriedRetrievalProcessing,
      historicalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
      streamedRetrievalProcessingSummary: streamedRetrievalProcessingSummary,
      streamedAnswerReadinessSummary: streamedAnswerReadinessSummary,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
      profileUpdateProposal: _buildProfileUpdateProposal(request: request),
      responseDegraded:
          (!finalResponseHasRenderableContent || finalResponseIsFallback) &&
          (finalResult.degraded || hasDegradedTrace(finalResult.traces)),
      blockedProcessStepId: blockedProcessStepId,
      blockedProcessMessage: blockedProcessMessage,
      skillSynthesisInput: skillSynthesisInput,
      skillSynthesisOutput: SkillSynthesisOutput.fromStructuredAnswer(
        answerPayload: finalResultTurn?.toEnvelopeMap() ?? <String, dynamic>{},
        input: skillSynthesisInput,
        aggregationState: aggregationState,
        synthesisReadiness: synthesisReadiness,
      ),
    );
  }

  Future<Map<String, dynamic>> materializeStructuredResponseFromDraft(
    AssistantRunRequest request, {
    required SynthesisDraft draft,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return _buildStructuredResponse(
      request: request,
      contextAssembly: draft.contextAssembly,
      synthesisReadiness: draft.synthesisReadiness,
      result: draft.finalResult,
      planView: draft.planView,
      searchPlans: draft.planView.searchPlans,
      skillRuns: draft.skillRuns,
      aggregationState: draft.aggregationState,
      subagentPlan: draft.subagentPlan,
      subagentRuns: draft.subagentRuns,
      skillSynthesisInput: draft.skillSynthesisInput,
      skillSynthesisOutput: draft.skillSynthesisOutput,
      dialogueRoundScript: draft.dialogueRoundScript,
      candidateDomains: draft.candidateDomains,
      skillExecutionShell: draft.skillExecutionShell,
      templateVersionUsed: draft.templateVersionUsed,
      domainCatalogVersion: draft.domainCatalogVersion,
      sessionId: draft.sessionId,
      retrievalPolicy: draft.retrievalPolicy,
      answerBoundaryPolicy: draft.answerBoundaryPolicy,
      previousSlotState: draft.previousSlotState,
      phaseOneRoutingDiagnostics: draft.phaseOneRoutingDiagnostics,
      carriedUnderstandingSnapshot: draft.understandingSnapshot,
      carriedRetrievalProcessing: draft.retrievalProcessing,
      carriedHistoricalThinkingSnapshot: draft.historicalThinkingSnapshot,
      streamedRetrievalProcessingSummary:
          draft.streamedRetrievalProcessingSummary,
      streamedAnswerReadinessSummary: draft.streamedAnswerReadinessSummary,
      previousDomainPolicyBundle: draft.previousDomainPolicyBundle,
      blockedProcessStepId: draft.blockedProcessStepId,
      blockedProcessMessage: draft.blockedProcessMessage,
      onTraceEvent: onTraceEvent,
      runId: draft.runId,
      traceId: draft.traceId,
    );
  }

  Future<AssistantRunResponse> finalizeBridge(
    AssistantRunRequest request, {
    required ExecutionPhaseSnapshot executionSnapshot,
    required AssistantRunResponse response,
  }) {
    return buildFinalizeRunner().finalize(
      request,
      executionSnapshot: executionSnapshot,
      response: response,
    );
  }

  Future<void> _safeWriteLogEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required AppLogContext context,
    required dynamic payload,
    required Map<String, dynamic> summaryPayload,
    bool hasError = false,
  }) async {
    try {
      await AppLogService.instance.writeEvent(
        logType: logType,
        level: level,
        context: context,
        payload: payload,
        summaryPayload: summaryPayload,
        hasError: hasError,
      );
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AgentLoop] log write skipped: $error');
      }
    }
  }

  Future<ReactRuntimeResult> _repairInvalidSynthesisResult({
    required ReactRuntimeResult currentResult,
    required List<Map<String, dynamic>> synthesisInput,
    required String latestUserQuery,
    required Map<String, dynamic> templateContext,
    required Map<String, dynamic> carriedUnderstandingSnapshot,
    required Map<String, dynamic> carriedRetrievalProcessing,
    required Map<String, dynamic> carriedHistoricalThinkingSnapshot,
    required Map<String, dynamic> templateVariables,
    required String streamedRetrievalProcessingSummary,
    required String streamedAnswerReadinessSummary,
    required String templateId,
    required String templateVersion,
    required String sessionId,
    required String runId,
    required String traceId,
    required void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final templateVariablesView =
        AssistantPipelineTemplateVariablesView.fromMap(templateVariables);
    final repairReason = _synthesisRepairReason(
      currentResult.finalText,
      templateVariables: templateVariablesView,
    );
    if (repairReason == null) {
      return currentResult;
    }
    final repairTrace = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'repair invalid synthesis output',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      visibility: TraceVisibility.internal,
      data: <String, dynamic>{
        'stage': 'synthesis_repair',
        'reason': repairReason,
      },
    );
    onTraceEvent?.call(repairTrace);
    final repaired = await _runtime.run(
      messages: <Map<String, dynamic>>[
        ...synthesisInput,
        <String, dynamic>{
          'role': 'system',
          'content': await _buildSynthesisRepairInstruction(
            repairReason: repairReason,
            templateVariables: templateVariablesView,
          ),
        },
      ],
      maxIterations: 1,
      goal: latestUserQuery,
      availableToolNamesOverride: const <String>[],
      templateId: templateId,
      templateVersion: templateVersion,
      templateContext: templateContext,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: _withTraceVisibility(
        onTraceEvent,
        TraceVisibility.internal,
      ),
      callOptions: const LlmCallOptions.synthesis(),
      onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
    );
    if (_needsSynthesisRepair(
      repaired.finalText,
      templateVariables: templateVariablesView,
    )) {
      Map<String, dynamic> payloadMap(
        Map<String, dynamic> payload,
        String key,
      ) {
        final raw = payload[key];
        if (raw is Map) {
          return raw.cast<String, dynamic>();
        }
        return const <String, dynamic>{};
      }

      Map<String, dynamic> mergedStageMap({
        required Map<String, dynamic> primary,
        required Map<String, dynamic> fallback,
        required String narrativeKey,
        required String streamedNarrative,
      }) {
        final merged = Map<String, dynamic>.from(
          preferStructuredMap(primary, fallback),
        );
        final stabilizedNarrative = _mergeStableNarrativeFinalText(
          streamed: streamedNarrative,
          finalized: _firstNonEmptyText(<String?>[
            (primary[narrativeKey] as String?)?.trim(),
            (fallback[narrativeKey] as String?)?.trim(),
          ]),
        );
        if (stabilizedNarrative.isNotEmpty) {
          merged[narrativeKey] = stabilizedNarrative;
        }
        return merged;
      }

      Map<String, dynamic> firstStructuredMap(
        List<Map<String, dynamic>> candidates,
      ) {
        for (final candidate in candidates) {
          if (hasStructuredContent(candidate)) {
            return candidate;
          }
        }
        return const <String, dynamic>{};
      }

      Map<String, dynamic> payloadFromAssistantDeltaTraces(
        List<AssistantTraceEvent> traces,
      ) {
        Map<String, dynamic> fallbackPayload = const <String, dynamic>{};
        for (final trace in traces.reversed) {
          if (trace.type != AssistantTraceEventType.assistantDelta) {
            continue;
          }
          final payload = parseAnswerPayload(
            rawFinalText: trace.message,
            traces: traces,
          );
          if (!hasStructuredContent(payload)) {
            continue;
          }
          final hasStageSnapshots =
              hasStructuredContent(
                payloadMap(
                  payload,
                  AssistantPipelineStateKeys.understandingSnapshot,
                ),
              ) ||
              hasStructuredContent(
                payloadMap(
                  payload,
                  AssistantPipelineStateKeys.retrievalProcessing,
                ),
              ) ||
              hasStructuredContent(
                payloadMap(
                  payload,
                  AssistantPipelineStateKeys.answerProcessing,
                ),
              );
          if (hasStageSnapshots) {
            return payload;
          }
          if (fallbackPayload.isEmpty) {
            fallbackPayload = payload;
          }
        }
        return fallbackPayload;
      }

      final repairedPayload = parseAnswerPayload(
        rawFinalText: repaired.finalText,
        traces: repaired.traces,
      );
      final currentPayload = parseAnswerPayload(
        rawFinalText: currentResult.finalText,
        traces: currentResult.traces,
      );
      final repairedTracePayload = payloadFromAssistantDeltaTraces(
        repaired.traces,
      );
      final currentTracePayload = payloadFromAssistantDeltaTraces(
        currentResult.traces,
      );
      final fallbackRetrievalProcessing =
          firstStructuredMap(<Map<String, dynamic>>[
            payloadMap(
              repairedTracePayload,
              AssistantPipelineStateKeys.retrievalProcessing,
            ),
            payloadMap(
              currentTracePayload,
              AssistantPipelineStateKeys.retrievalProcessing,
            ),
            payloadMap(
              currentPayload,
              AssistantPipelineStateKeys.retrievalProcessing,
            ),
            carriedRetrievalProcessing,
          ]);
      final fallbackAnswerProcessing =
          firstStructuredMap(<Map<String, dynamic>>[
            payloadMap(
              repairedTracePayload,
              AssistantPipelineStateKeys.answerProcessing,
            ),
            payloadMap(
              currentTracePayload,
              AssistantPipelineStateKeys.answerProcessing,
            ),
            payloadMap(
              currentPayload,
              AssistantPipelineStateKeys.answerProcessing,
            ),
          ]);
      final fallbackUnderstandingSnapshot =
          firstStructuredMap(<Map<String, dynamic>>[
            payloadMap(
              repairedTracePayload,
              AssistantPipelineStateKeys.understandingSnapshot,
            ),
            payloadMap(
              currentTracePayload,
              AssistantPipelineStateKeys.understandingSnapshot,
            ),
            payloadMap(
              currentPayload,
              AssistantPipelineStateKeys.understandingSnapshot,
            ),
            carriedUnderstandingSnapshot,
          ]);
      final fallbackHistoricalThinkingSnapshot =
          firstStructuredMap(<Map<String, dynamic>>[
            payloadMap(
              repairedTracePayload,
              AssistantPipelineStateKeys.historicalThinkingSnapshot,
            ),
            payloadMap(
              currentTracePayload,
              AssistantPipelineStateKeys.historicalThinkingSnapshot,
            ),
            payloadMap(
              currentPayload,
              AssistantPipelineStateKeys.historicalThinkingSnapshot,
            ),
            carriedHistoricalThinkingSnapshot,
          ]);
      final fallbackSlotState = firstStructuredMap(<Map<String, dynamic>>[
        payloadMap(repairedTracePayload, AssistantPipelineStateKeys.slotState),
        payloadMap(currentTracePayload, AssistantPipelineStateKeys.slotState),
        payloadMap(currentPayload, AssistantPipelineStateKeys.slotState),
      ]);
      final mergedRetrievalProcessing = mergedStageMap(
        primary: firstStructuredMap(<Map<String, dynamic>>[
          payloadMap(
            repairedPayload,
            AssistantPipelineStateKeys.retrievalProcessing,
          ),
          payloadMap(
            repairedTracePayload,
            AssistantPipelineStateKeys.retrievalProcessing,
          ),
        ]),
        fallback: fallbackRetrievalProcessing,
        narrativeKey: 'processingSummary',
        streamedNarrative: streamedRetrievalProcessingSummary,
      );
      final mergedAnswerProcessing = mergedStageMap(
        primary: firstStructuredMap(<Map<String, dynamic>>[
          payloadMap(
            repairedPayload,
            AssistantPipelineStateKeys.answerProcessing,
          ),
          payloadMap(
            repairedTracePayload,
            AssistantPipelineStateKeys.answerProcessing,
          ),
        ]),
        fallback: fallbackAnswerProcessing,
        narrativeKey: 'readinessSummary',
        streamedNarrative: streamedAnswerReadinessSummary,
      );
      final recoveryPayload = <String, dynamic>{
        ...repairedPayload,
        AssistantPipelineStateKeys.understandingSnapshot:
            firstStructuredMap(<Map<String, dynamic>>[
              payloadMap(
                repairedPayload,
                AssistantPipelineStateKeys.understandingSnapshot,
              ),
              payloadMap(
                repairedTracePayload,
                AssistantPipelineStateKeys.understandingSnapshot,
              ),
              fallbackUnderstandingSnapshot,
            ]),
        AssistantPipelineStateKeys.retrievalProcessing:
            mergedRetrievalProcessing,
        AssistantPipelineStateKeys.answerProcessing: mergedAnswerProcessing,
        AssistantPipelineStateKeys.historicalThinkingSnapshot:
            firstStructuredMap(<Map<String, dynamic>>[
              payloadMap(
                repairedPayload,
                AssistantPipelineStateKeys.historicalThinkingSnapshot,
              ),
              payloadMap(
                repairedTracePayload,
                AssistantPipelineStateKeys.historicalThinkingSnapshot,
              ),
              fallbackHistoricalThinkingSnapshot,
            ]),
        AssistantPipelineStateKeys.slotState:
            firstStructuredMap(<Map<String, dynamic>>[
              payloadMap(repairedPayload, AssistantPipelineStateKeys.slotState),
              payloadMap(
                repairedTracePayload,
                AssistantPipelineStateKeys.slotState,
              ),
              fallbackSlotState,
            ]),
      };
      final fallbackPayload = <String, dynamic>{
        ...currentPayload,
        AssistantPipelineStateKeys.understandingSnapshot:
            fallbackUnderstandingSnapshot,
        AssistantPipelineStateKeys.retrievalProcessing:
            fallbackRetrievalProcessing,
        AssistantPipelineStateKeys.answerProcessing: mergedAnswerProcessing,
        AssistantPipelineStateKeys.historicalThinkingSnapshot:
            fallbackHistoricalThinkingSnapshot,
        AssistantPipelineStateKeys.slotState: fallbackSlotState,
      };
      final recoveredMarkdown = _recoverDisplayMarkdownFromInvalidSynthesis(
        primaryText: repaired.finalText,
        primaryTraces: repaired.traces,
        fallbackText: currentResult.finalText,
        fallbackTraces: currentResult.traces,
      );
      if (recoveredMarkdown.isNotEmpty) {
        return ReactRuntimeResult(
          finalText: _buildRecoveredAssistantTurnEnvelopeText(
            recoveredMarkdown: recoveredMarkdown,
            failureCode: 'invalid_synthesis_output',
            payloadBundle: AssistantPipelineRecoveryPayloadBundle.fromWireMaps(
              recoveryPayload: recoveryPayload,
              fallbackPayload: fallbackPayload,
            ),
          ),
          traces: <AssistantTraceEvent>[
            ...currentResult.traces,
            repairTrace,
            ...repaired.traces,
          ],
          degraded: false,
          failureCode: '',
        );
      }
      final plainMarkdownRecovery = await _runtime.run(
        messages: <Map<String, dynamic>>[
          ...synthesisInput,
          <String, dynamic>{
            'role': 'system',
            'content': await _renderPromptSnippet(
              'plain_markdown_recovery',
              variables: <String, dynamic>{
                'anchorReminder':
                    templateVariablesView.requiredTopicAnchors.isEmpty
                    ? ''
                    : await _renderPromptSnippet(
                        'synthesis_anchor_reminder',
                        variables: <String, dynamic>{
                          'anchors': templateVariablesView.requiredTopicAnchors
                              .join('、'),
                        },
                      ),
              },
            ),
          },
        ],
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: templateId,
        templateVersion: templateVersion,
        templateContext: templateContext,
        templateVariables: templateVariables,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: _withTraceVisibility(
          onTraceEvent,
          TraceVisibility.internal,
        ),
        callOptions: const LlmCallOptions(
          temperature: 0.2,
          maxTokens: 1600,
          forceJsonObject: false,
          timeoutSeconds: 30,
        ),
        onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
      );
      final recoveredPlainMarkdown =
          _recoverDisplayMarkdownFromInvalidSynthesis(
            primaryText: plainMarkdownRecovery.finalText,
            primaryTraces: plainMarkdownRecovery.traces,
            fallbackText: '',
            fallbackTraces: const <AssistantTraceEvent>[],
          );
      if (recoveredPlainMarkdown.isNotEmpty) {
        return ReactRuntimeResult(
          finalText: _buildRecoveredAssistantTurnEnvelopeText(
            recoveredMarkdown: recoveredPlainMarkdown,
            failureCode: 'invalid_synthesis_output',
            payloadBundle: AssistantPipelineRecoveryPayloadBundle.fromWireMaps(
              recoveryPayload: recoveryPayload,
              fallbackPayload: fallbackPayload,
            ),
          ),
          traces: <AssistantTraceEvent>[
            ...currentResult.traces,
            repairTrace,
            ...repaired.traces,
            ...plainMarkdownRecovery.traces,
          ],
          degraded: false,
          failureCode: '',
        );
      }
      final degradedEnvelope = _buildDegradedAssistantTurnEnvelopeText(
        failureCode: 'invalid_synthesis_output',
      );
      return ReactRuntimeResult(
        finalText: degradedEnvelope,
        traces: <AssistantTraceEvent>[
          ...currentResult.traces,
          repairTrace,
          ...repaired.traces,
          ...plainMarkdownRecovery.traces,
        ],
        degraded: true,
        failureCode: 'invalid_synthesis_output',
      );
    }
    return ReactRuntimeResult(
      finalText: repaired.finalText,
      traces: <AssistantTraceEvent>[
        ...currentResult.traces,
        repairTrace,
        ...repaired.traces,
      ],
      degraded: repaired.degraded,
      failureCode: repaired.failureCode,
    );
  }

  bool _needsSynthesisRepair(
    String rawText, {
    AssistantPipelineTemplateVariablesView templateVariables =
        const AssistantPipelineTemplateVariablesView.empty(),
  }) {
    return _synthesisRepairReason(
          rawText,
          templateVariables: templateVariables,
        ) !=
        null;
  }

  String? _synthesisRepairReason(
    String rawText, {
    AssistantPipelineTemplateVariablesView templateVariables =
        const AssistantPipelineTemplateVariablesView.empty(),
  }) {
    final trimmed = rawText.trim();
    if (trimmed.isEmpty) return 'empty_or_missing_display';
    if (_containsXmlToolCallMarkup(trimmed)) return 'xml_tool_markup';
    final parseResult = LlmResponseParser.parse(trimmed);
    if (!parseResult.ok) return 'unparseable_envelope';
    final parsed = parseResult.json!;
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn == null) {
      return 'invalid_assistant_turn';
    }
    final nextAction = turn.nextActionType;
    if (nextAction == AssistantNextAction.unknown) {
      return 'unknown_next_action';
    }
    if (nextAction == AssistantNextAction.toolCall) {
      return 'tool_call_not_final_answer';
    }
    if (turn.messageKindType == AssistantMessageKind.progress) {
      return 'progress_not_final_answer';
    }
    final projectedMarkdown = AssistantDisplayTextResolver.projectTurn(
      turn,
    ).markdown;
    if (projectedMarkdown.isEmpty) return 'empty_projected_markdown';
    if (AssistantContentFilters.isJsonEnvelope(projectedMarkdown) ||
        AssistantContentFilters.isProgressPlaceholder(projectedMarkdown) ||
        _containsXmlToolCallMarkup(projectedMarkdown)) {
      return 'non_renderable_markdown';
    }
    if (_missingRequiredTopicAnchor(
      projectedMarkdown,
      templateVariables: templateVariables,
    )) {
      return 'missing_topic_anchor';
    }
    return null;
  }

  bool _containsXmlToolCallMarkup(String text) =>
      _containsAnyMarker(text, const <String>[
        '<tool_call>',
        '</tool_call>',
        '<function=',
        '</function>',
        '<parameter=',
        '</parameter>',
      ]);

  bool _containsAnyMarker(String text, List<String> markers) {
    for (final marker in markers) {
      if (text.contains(marker)) return true;
    }
    return false;
  }

  int _countSentenceTerminators(String text) {
    var count = 0;
    for (final rune in text.runes) {
      if (_isSentenceTerminatorRune(rune)) count += 1;
    }
    return count;
  }

  bool _containsSentenceTerminator(String text) {
    for (final rune in text.runes) {
      if (_isSentenceTerminatorRune(rune)) return true;
    }
    return false;
  }

  bool _containsCjkOrAsciiLetterOrDigit(String text) {
    for (final rune in text.runes) {
      if ((rune >= 48 && rune <= 57) ||
          (rune >= 65 && rune <= 90) ||
          (rune >= 97 && rune <= 122) ||
          (rune >= 0x4e00 && rune <= 0x9fff)) {
        return true;
      }
    }
    return false;
  }

  bool _isSentenceTerminatorRune(int rune) {
    return rune == 0x3002 ||
        rune == 0xff01 ||
        rune == 0xff1f ||
        rune == 0xff1b ||
        rune == 0x3b ||
        rune == 0x2e ||
        rune == 0x21 ||
        rune == 0x3f;
  }

  Future<String> _buildSynthesisRepairInstruction({
    required String repairReason,
    required AssistantPipelineTemplateVariablesView templateVariables,
  }) async {
    final anchors = _requiredTopicAnchors(templateVariables);
    final renderedAnchorReminder = anchors.isEmpty
        ? ''
        : await _renderPromptSnippet(
            'synthesis_anchor_reminder',
            variables: <String, dynamic>{'anchors': anchors.join('、')},
          );
    final anchorReminder = renderedAnchorReminder;
    final continuationReminder =
        templateVariables.hasContinuationCarryoverContext
        ? await _renderPromptSnippet(
            'continuation_reminder',
            variables: <String, dynamic>{
              'continuityMode': templateVariables.continuityMode.name,
            },
          )
        : '';
    final rendered = await _renderPromptSnippet(
      'synthesis_repair',
      variables: <String, dynamic>{
        'repairReason': repairReason,
        'anchorReminder': anchorReminder,
        'continuationReminder': continuationReminder,
      },
    );
    final repairHeader = _buildSynthesisRepairFallback(repairReason);
    if (rendered.isEmpty) return repairHeader;
    if (rendered.contains('assistant_turn_repair|')) return rendered;
    return '$repairHeader\n$rendered';
  }

  AssistantTurnOutput? _tryParseAssistantTurnFromRawText(String rawText) {
    final parsed = LlmResponseParser.parse(rawText).json;
    if (parsed == null) return null;
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn == null) return null;
    return AssistantDisplayTextResolver.normalizeTurn(turn);
  }

  Future<ReactRuntimeResult> _repairPhaseOneDirectAnswerEnvelopeText({
    required String rawText,
    required List<AssistantTraceEvent> traces,
    required List<Map<String, dynamic>> messages,
    required String latestUserQuery,
    required Map<String, dynamic> templateContext,
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    required String sessionId,
    required String runId,
    required String traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final templateVariablesView =
        AssistantPipelineTemplateVariablesView.fromMap(templateVariables);
    final recoveredMarkdown = _recoverDisplayMarkdownFromInvalidSynthesis(
      primaryText: rawText,
      primaryTraces: traces,
      fallbackText: '',
      fallbackTraces: const <AssistantTraceEvent>[],
    );
    if (recoveredMarkdown.isEmpty ||
        AssistantContentFilters.isJsonEnvelope(recoveredMarkdown) ||
        AssistantContentFilters.isProgressPlaceholder(recoveredMarkdown) ||
        _containsXmlToolCallMarkup(recoveredMarkdown)) {
      return const ReactRuntimeResult(
        finalText: '',
        traces: <AssistantTraceEvent>[],
      );
    }
    final repairTrace = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'phase one direct answer contract repair',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      visibility: TraceVisibility.internal,
      data: <String, dynamic>{
        'stage': 'phase_one_direct_answer_repair',
        'continuation': templateVariablesView.hasContinuationCarryoverContext,
      },
    );
    onTraceEvent?.call(repairTrace);
    final repaired = await _runtime.run(
      messages: <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{
          'role': 'system',
          'content': await _buildPhaseOneDirectAnswerRepairInstruction(
            recoveredMarkdown: recoveredMarkdown,
            latestUserQuery: latestUserQuery,
            templateVariables: templateVariables,
          ),
        },
      ],
      maxIterations: 1,
      goal: latestUserQuery,
      availableToolNamesOverride: const <String>[],
      templateId: 'phase.output_contract.plan',
      templateVersion: _templateCatalogRuntime.latestVersionFor(
        'phase.output_contract.plan',
      ),
      templateContext: templateContext,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: _withTraceVisibility(
        onTraceEvent,
        TraceVisibility.internal,
      ),
      callOptions: const LlmCallOptions.synthesis(),
      onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
    );
    final repairedTurn = _tryParseAssistantTurnFromRawText(repaired.finalText);
    if (repairedTurn != null &&
        _synthesisRepairReason(
              repaired.finalText,
              templateVariables: templateVariablesView,
            ) ==
            null) {
      return ReactRuntimeResult(
        finalText: jsonEncode(repairedTurn.toEnvelopeMap()),
        traces: <AssistantTraceEvent>[repairTrace, ...repaired.traces],
        degraded: repaired.degraded,
        failureCode: repaired.failureCode,
      );
    }
    final repairedMarkdown = _recoverDisplayMarkdownFromInvalidSynthesis(
      primaryText: repaired.finalText,
      primaryTraces: repaired.traces,
      fallbackText: recoveredMarkdown,
      fallbackTraces: traces,
    );
    if (repairedMarkdown.isEmpty ||
        AssistantContentFilters.isJsonEnvelope(repairedMarkdown) ||
        AssistantContentFilters.isProgressPlaceholder(repairedMarkdown) ||
        _containsXmlToolCallMarkup(repairedMarkdown) ||
        _missingRequiredTopicAnchor(
          repairedMarkdown,
          templateVariables: templateVariablesView,
        )) {
      return ReactRuntimeResult(
        finalText: '',
        traces: <AssistantTraceEvent>[repairTrace, ...repaired.traces],
        degraded: repaired.degraded,
        failureCode: repaired.failureCode,
      );
    }
    return ReactRuntimeResult(
      finalText: _buildRecoveredAssistantTurnEnvelopeText(
        recoveredMarkdown: repairedMarkdown,
        failureCode: 'phase_one_answer_repair',
        payloadBundle: AssistantPipelineRecoveryPayloadBundle.fromWireMaps(
          recoveryPayload: parseAnswerPayload(
            rawFinalText: repaired.finalText,
            traces: repaired.traces,
          ),
          fallbackPayload: parseAnswerPayload(
            rawFinalText: rawText,
            traces: traces,
          ),
        ),
      ),
      traces: <AssistantTraceEvent>[repairTrace, ...repaired.traces],
      degraded: repaired.degraded,
      failureCode: repaired.failureCode,
    );
  }

  Future<String> _buildPhaseOneDirectAnswerRepairInstruction({
    required String recoveredMarkdown,
    required String latestUserQuery,
    required Map<String, dynamic> templateVariables,
  }) async {
    final templateVariablesView =
        AssistantPipelineTemplateVariablesView.fromMap(templateVariables);
    final anchors = _requiredTopicAnchors(templateVariablesView);
    final renderedAnchorReminder = anchors.isEmpty
        ? ''
        : await _renderPromptSnippet(
            'synthesis_anchor_reminder',
            variables: <String, dynamic>{'anchors': anchors.join('、')},
          );
    final anchorReminder = renderedAnchorReminder;
    final continuationReminder =
        templateVariablesView.hasContinuationCarryoverContext
        ? await _renderPromptSnippet(
            'continuation_reminder',
            variables: <String, dynamic>{
              'continuityMode': templateVariablesView.continuityMode.name,
            },
          )
        : '';
    final rendered = await _renderPromptSnippet(
      'phase_one_direct_answer_repair',
      variables: <String, dynamic>{
        'latestUserQuery': latestUserQuery,
        'recoveredMarkdown': recoveredMarkdown,
        'anchorReminder': anchorReminder,
        'continuationReminder': continuationReminder,
      },
    );
    final fallback = _buildPhaseOneDirectAnswerRepairFallback(
      latestUserQuery: latestUserQuery,
      recoveredMarkdown: recoveredMarkdown,
      anchorReminder: anchorReminder,
      continuationReminder: continuationReminder,
    );
    if (rendered.isEmpty) return fallback;
    if (rendered.contains('assistant_turn_repair|')) return rendered;
    return '$fallback\n$rendered';
  }

  String _buildSynthesisRepairFallback(String repairReason) {
    return 'assistant_turn_repair|phase=synthesis|reason=$repairReason|output=single_assistant_turn_json';
  }

  String _buildPhaseOneDirectAnswerRepairFallback({
    required String latestUserQuery,
    required String recoveredMarkdown,
    required String anchorReminder,
    required String continuationReminder,
  }) {
    final buffer = StringBuffer()
      ..writeln(
        'assistant_turn_repair|phase=phase_one_direct_answer|output=single_assistant_turn_json',
      )
      ..writeln('repair_mode=phase_one_direct_answer')
      ..writeln('latestUserQuery=$latestUserQuery')
      ..writeln('output=single_assistant_turn_json');
    if (anchorReminder.trim().isNotEmpty) {
      buffer.writeln(anchorReminder);
    }
    if (continuationReminder.trim().isNotEmpty) {
      buffer.writeln(continuationReminder);
    }
    buffer
      ..writeln('<draft_answer>')
      ..writeln(recoveredMarkdown)
      ..writeln('</draft_answer>');
    return buffer.toString().trimRight();
  }

  bool _hasContinuationCarryoverContext(
    AssistantPipelineTemplateVariablesView templateVariables,
  ) {
    return templateVariables.hasContinuationCarryoverContext;
  }

  bool _missingRequiredTopicAnchor(
    String projectedMarkdown, {
    AssistantPipelineTemplateVariablesView templateVariables =
        const AssistantPipelineTemplateVariablesView.empty(),
  }) {
    final anchors = _requiredTopicAnchors(templateVariables);
    if (anchors.isEmpty) {
      return false;
    }
    final normalizedMarkdown = _normalizeTopicAnchorText(projectedMarkdown);
    if (normalizedMarkdown.isEmpty) {
      return false;
    }
    return !anchors.any(
      (anchor) =>
          normalizedMarkdown.contains(_normalizeTopicAnchorText(anchor)),
    );
  }

  List<String> _requiredTopicAnchors(
    AssistantPipelineTemplateVariablesView templateVariables,
  ) {
    return templateVariables.requiredTopicAnchors;
  }

  String _normalizeTopicAnchorText(String raw) {
    final buffer = StringBuffer();
    for (final rune in raw.toLowerCase().runes) {
      final ch = String.fromCharCode(rune);
      if (ch.trim().isEmpty) continue;
      buffer.write(ch);
    }
    return buffer.toString();
  }

  /// 确保 rawText 是符合当前契约标识（[kAssistantTurnCurrentContractId]）的 JSON 信封。
  /// 若 rawText 无法通过当前契约校验，则返回 fail-closed 的降级信封。
  String _ensureAssistantTurnEnvelopeText(String rawText) {
    final parseResult = LlmResponseParser.parse(rawText);
    final parsed = parseResult.json;
    if (parsed != null) {
      final turn = tryParseAssistantTurnOutput(parsed);
      if (turn != null) {
        final normalizedTurn = AssistantDisplayTextResolver.normalizeTurn(turn);
        if (normalizedTurn.nextActionType == AssistantNextAction.answer &&
            !AssistantDisplayTextResolver.projectTurn(
              normalizedTurn,
            ).hasRenderableContent) {
          return _buildDegradedAssistantTurnEnvelopeText(
            failureCode: 'invalid_assistant_turn',
          );
        }
        return jsonEncode(normalizedTurn.toEnvelopeMap());
      }
    }
    return _buildDegradedAssistantTurnEnvelopeText(
      failureCode: 'invalid_assistant_turn',
    );
  }

  String _buildDegradedAssistantTurnEnvelopeText({
    required String failureCode,
  }) {
    final failureMessage = assistantPipelineDefaultFailureMessageForStep(
      ProcessStepId.unknown,
    );
    return jsonEncode(
      AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.abort,
        ),
        messageKind: AssistantMessageKind.fallback,
        userMarkdown: failureMessage,
        result: AssistantTurnResult(
          text: failureMessage,
          interpretation: failureCode,
        ),
        selfCheck: AssistantTurnSelfCheck(
          goalSatisfied: false,
          constraintSatisfied: false,
          safetyBoundarySatisfied: true,
          failedItems: <String>[failureCode],
        ),
        diagnostics: AssistantTurnDiagnostics(
          notes: <String>[failureCode, 'fail_closed'],
        ),
        modelSelfScore: const AssistantTurnModelSelfScore(
          score: 0,
          reason: 'invalid_model_output',
        ),
        slotState: const SlotStateSnapshot(),
        askUser: const AssistantTurnAskUser(),
      ).toEnvelopeMap(),
    );
  }

  String _buildStageFailureAssistantTurnEnvelopeText({
    required ProcessStepId stepId,
    required String failureCode,
    required String failureMessage,
  }) {
    final normalizedMessage = failureMessage.trim().isNotEmpty
        ? failureMessage.trim()
        : assistantPipelineDefaultFailureMessageForStep(stepId);
    final phaseId = stepId == ProcessStepId.understanding
        ? PlannerPhaseId.understanding
        : (stepId == ProcessStepId.answerOrganization
              ? PlannerPhaseId.answering
              : PlannerPhaseId.aggregating);
    final actionCode = stepId == ProcessStepId.understanding
        ? PlannerActionCode.frameProblem
        : (stepId == ProcessStepId.answerOrganization
              ? PlannerActionCode.composeAnswer
              : PlannerActionCode.assessEvidence);
    final reasonCode = stepId == ProcessStepId.understanding
        ? PlannerReasonCode.alignGoal
        : (stepId == ProcessStepId.answerOrganization
              ? PlannerReasonCode.prepareDelivery
              : PlannerReasonCode.needMoreEvidence);
    final answerProcessing = stepId == ProcessStepId.answerOrganization
        ? AssistantTurnAnswerProcessing(
            readinessSummary: normalizedMessage,
            retrieveMoreReason: normalizedMessage,
          )
        : const AssistantTurnAnswerProcessing();
    return jsonEncode(
      AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.abort,
        ),
        messageKind: AssistantMessageKind.fallback,
        userMarkdown: normalizedMessage,
        result: AssistantTurnResult(
          text: normalizedMessage,
          interpretation: failureCode,
          summary: normalizedMessage,
        ),
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        reasonShort: normalizedMessage,
        answerProcessing: answerProcessing,
        selfCheck: AssistantTurnSelfCheck(
          goalSatisfied: false,
          constraintSatisfied: false,
          safetyBoundarySatisfied: true,
          failedItems: <String>[failureCode],
        ),
        diagnostics: AssistantTurnDiagnostics(
          notes: <String>[failureCode, 'fail_closed', stepId.wireName],
        ),
        modelSelfScore: const AssistantTurnModelSelfScore(
          score: 0,
          reason: 'stage_failed',
        ),
        slotState: const SlotStateSnapshot(),
        askUser: const AssistantTurnAskUser(),
      ).toEnvelopeMap(),
    );
  }

  String _buildRecoveredAssistantTurnEnvelopeText({
    required String recoveredMarkdown,
    required String failureCode,
    required AssistantPipelineRecoveryPayloadBundle payloadBundle,
  }) {
    final plainText = AssistantDisplayTextResolver.stripMarkdown(
      recoveredMarkdown,
    );
    final normalizedPlain = plainText.isNotEmpty
        ? plainText
        : recoveredMarkdown;
    final reasonShort = _firstNonEmptyText(<String?>[
      payloadBundle.recovery.reasonShort,
      payloadBundle.fallback.reasonShort,
      assistantPipelineDefaultReasonShort(),
    ]);
    return jsonEncode(
      AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.answer,
        ),
        messageKind: AssistantMessageKind.answer,
        phaseId: PlannerPhaseId.answering,
        actionCode: PlannerActionCode.composeAnswer,
        reasonCode: PlannerReasonCode.evidenceReady,
        reasonShort: reasonShort,
        userMarkdown: recoveredMarkdown,
        result: AssistantTurnResult(
          text: normalizedPlain,
          summary: _firstNonEmptyText(<String?>[
            payloadBundle.recovery.resultSummary,
            payloadBundle.fallback.resultSummary,
            normalizedPlain,
          ]),
          interpretation: _firstNonEmptyText(<String?>[
            _normalizedRecoveredAnswerInterpretation(
              existingInterpretation:
                  payloadBundle.recovery.resultInterpretation,
            ),
            _normalizedRecoveredAnswerInterpretation(
              existingInterpretation:
                  payloadBundle.fallback.resultInterpretation,
            ),
          ]),
        ),
        understandingSnapshot: payloadBundle.recovery.understandingSnapshot,
        retrievalProcessing: payloadBundle.recovery.retrievalProcessing,
        answerProcessing: payloadBundle.recovery.answerProcessing,
        historicalThinkingSnapshot:
            payloadBundle.recovery.historicalThinkingSnapshot,
        selfCheck: const AssistantTurnSelfCheck(
          goalSatisfied: true,
          constraintSatisfied: true,
          safetyBoundarySatisfied: true,
        ),
        diagnostics: AssistantTurnDiagnostics(
          notes: <String>[failureCode, 'recovered_from_answer_delta'],
        ),
        modelSelfScore: const AssistantTurnModelSelfScore(
          score: 78,
          reason: 'recovered_from_streamed_answer',
        ),
        slotState: payloadBundle.recovery.slotState,
        askUser: const AssistantTurnAskUser(),
      ).toEnvelopeMap(),
    );
  }

  String _normalizedRecoveredAnswerInterpretation({
    required String existingInterpretation,
  }) {
    final normalized = existingInterpretation.trim().toLowerCase();
    return normalized == 'answer' ||
            normalized == 'bounded_answer' ||
            normalized == 'fallback'
        ? normalized
        : '';
  }

  String _recoverPhaseOneDirectAnswerEnvelopeText({
    required String rawText,
    required List<AssistantTraceEvent> traces,
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
  }) {
    final templateVariablesView =
        AssistantPipelineTemplateVariablesView.fromMap(templateVariables);
    final recoveredMarkdown = _recoverDisplayMarkdownFromInvalidSynthesis(
      primaryText: rawText,
      primaryTraces: traces,
      fallbackText: '',
      fallbackTraces: const <AssistantTraceEvent>[],
    );
    if (recoveredMarkdown.isEmpty ||
        AssistantContentFilters.isJsonEnvelope(recoveredMarkdown) ||
        AssistantContentFilters.isProgressPlaceholder(recoveredMarkdown) ||
        _containsXmlToolCallMarkup(recoveredMarkdown) ||
        _missingRequiredTopicAnchor(
          recoveredMarkdown,
          templateVariables: templateVariablesView,
        )) {
      return '';
    }
    final recoveryPayload = parseAnswerPayload(
      rawFinalText: rawText,
      traces: traces,
    );
    return _buildRecoveredAssistantTurnEnvelopeText(
      recoveredMarkdown: recoveredMarkdown,
      failureCode: 'phase_one_answer_recovery',
      payloadBundle: AssistantPipelineRecoveryPayloadBundle.fromWireMaps(
        recoveryPayload: recoveryPayload,
        fallbackPayload: const <String, dynamic>{},
      ),
    );
  }

  String _recoverDisplayMarkdownFromInvalidSynthesis({
    required String primaryText,
    required List<AssistantTraceEvent> primaryTraces,
    required String fallbackText,
    required List<AssistantTraceEvent> fallbackTraces,
  }) {
    final candidates = <String>[
      _recoverDisplayMarkdownCandidate(primaryText),
      _recoverDisplayMarkdownFromTraces(primaryTraces),
      if (fallbackText.trim().isNotEmpty)
        _recoverDisplayMarkdownCandidate(fallbackText),
      _recoverDisplayMarkdownFromTraces(fallbackTraces),
    ];
    for (final candidate in candidates) {
      final normalized = AssistantDisplayTextResolver.normalizeMarkdown(
        candidate,
      );
      if (normalized.isEmpty) continue;
      if (AssistantContentFilters.isJsonEnvelope(normalized) ||
          AssistantContentFilters.isProgressPlaceholder(normalized) ||
          _containsXmlToolCallMarkup(normalized) ||
          AssistantDisplayTextResolver.containsInternalProcessFragment(
            normalized,
          ) ||
          AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
            normalized,
          ) ||
          !_looksLikeRenderableAnswerText(normalized)) {
        continue;
      }
      return normalized;
    }
    return '';
  }

  String _recoverDisplayMarkdownCandidate(String rawText) {
    final trimmed = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
      rawText,
    ).trim();
    if (trimmed.isEmpty) return '';
    final parsed = LlmResponseParser.parse(trimmed);
    if (parsed.ok) {
      final payload = parsed.json;
      final turn = payload != null
          ? tryParseAssistantTurnOutput(payload)
          : null;
      if (turn != null) {
        final projection = AssistantDisplayTextResolver.projectTurn(turn);
        if (turn.nextActionType != AssistantNextAction.answer ||
            turn.messageKindType == AssistantMessageKind.progress ||
            !projection.hasRenderableContent ||
            AssistantDisplayTextResolver.containsInternalProcessFragment(
              projection.markdown,
            ) ||
            AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
              projection.markdown,
            )) {
          return '';
        }
        return projection.markdown;
      }
      final compatMarkdown = _recoverCompatDisplayMarkdown(payload);
      if (compatMarkdown.isNotEmpty) {
        return compatMarkdown;
      }
      return AssistantDisplayTextResolver.extractDisplayMarkdownFromStructuredText(
        trimmed,
      );
    }
    final sanitized = AssistantDisplayTextResolver.normalizeMarkdown(trimmed);
    if (sanitized.isEmpty) {
      return '';
    }
    if (AssistantDisplayTextResolver.containsInternalProcessFragment(
          sanitized,
        ) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          sanitized,
        )) {
      return '';
    }
    if (!_looksLikeRenderableAnswerText(sanitized)) {
      return '';
    }
    return sanitized;
  }

  String _recoverCompatDisplayMarkdown(Map<String, dynamic>? payload) {
    if (payload == null || payload.isEmpty) return '';
    final payloadView = AssistantAnswerPayloadReadView(payload);
    final nextAction = parseNextAction(payloadView.nextActionWireName);
    final messageKind = parseMessageKind(payloadView.messageKindTrimmed);
    final toolCalls = normalizeToolCalls(payload['toolCalls']);
    final result = payloadView.resultMap;
    final candidates = <String>[
      AssistantDisplayTextResolver.normalizeMarkdown(
        payloadView.userMarkdownTrimmed,
      ),
      AssistantDisplayTextResolver.normalizeMarkdown(
        payloadView.resultTextTrimmed,
      ),
      AssistantDisplayTextResolver.normalizeMarkdown(
        (result['summary'] as String?)?.trim() ?? '',
      ),
    ].where((item) => item.trim().isNotEmpty).toList(growable: false);
    if (candidates.isEmpty) return '';
    final candidate = candidates.first;
    final answerLike =
        nextAction == AssistantNextAction.answer ||
        messageKind == AssistantMessageKind.answer ||
        (payloadView.phaseIdTrimmed) ==
            AssistantPipelineDiagnosticsKeys.answeringPhaseId;
    final staleProgressAnswer =
        toolCalls.isEmpty &&
        messageKind == AssistantMessageKind.progress &&
        candidate.isNotEmpty &&
        (payloadView.phaseIdTrimmed ==
                AssistantPipelineDiagnosticsKeys.answeringPhaseId ||
            payloadView.resultTextTrimmed.isNotEmpty);
    if (!answerLike && !staleProgressAnswer) {
      return '';
    }
    if (AssistantDisplayTextResolver.containsInternalProcessFragment(
          candidate,
        ) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          candidate,
        )) {
      return '';
    }
    return _looksLikeRenderableAnswerText(candidate) ? candidate : '';
  }

  String _recoverDisplayMarkdownFromTraces(List<AssistantTraceEvent> traces) {
    if (traces.isEmpty) return '';
    final streamedAnswerBuffer = StringBuffer();
    for (final event in traces) {
      if (event.type != AssistantTraceEventType.answerDelta &&
          event.type != AssistantTraceEventType.streamDelta) {
        continue;
      }
      final data = event.data ?? const <String, dynamic>{};
      final delta = (data['delta'] as String?)?.trim();
      final chunk = (delta?.isNotEmpty == true ? delta! : event.message).trim();
      if (chunk.isEmpty) continue;
      streamedAnswerBuffer.write(chunk);
    }
    final streamedAnswer = _recoverDisplayMarkdownCandidate(
      streamedAnswerBuffer.toString(),
    );
    if (streamedAnswer.isNotEmpty) {
      return streamedAnswer;
    }
    for (final event in traces.reversed) {
      if (event.type != AssistantTraceEventType.assistantDelta) continue;
      final data = event.data ?? const <String, dynamic>{};
      final toolCalls = data['toolCalls'] as List? ?? const <Object?>[];
      if (toolCalls.isNotEmpty) continue;
      final raw = event.message.trim();
      if (raw.isEmpty) continue;
      final parsed = LlmResponseParser.parse(raw);
      if (parsed.ok) {
        final payload = parsed.json;
        final turn = payload != null
            ? tryParseAssistantTurnOutput(payload)
            : null;
        if (turn != null &&
            turn.nextActionType == AssistantNextAction.answer &&
            turn.messageKindType != AssistantMessageKind.progress) {
          final markdown = AssistantDisplayTextResolver.projectTurn(
            turn,
          ).markdown;
          if (markdown.isNotEmpty) return markdown;
        }
        final compat = _recoverCompatDisplayMarkdown(payload);
        if (compat.isNotEmpty) return compat;
      }
      final candidate = _recoverDisplayMarkdownCandidate(raw);
      if (candidate.isNotEmpty) {
        return candidate;
      }
    }
    return '';
  }

  bool _hasPhaseOneExecutionSignals(List<AssistantTraceEvent> traces) {
    for (final trace in traces) {
      switch (trace.type) {
        case AssistantTraceEventType.toolStart:
        case AssistantTraceEventType.toolResult:
        case AssistantTraceEventType.toolError:
        case AssistantTraceEventType.skillStart:
        case AssistantTraceEventType.skillResult:
        case AssistantTraceEventType.skillError:
        case AssistantTraceEventType.subagentStart:
        case AssistantTraceEventType.subagentResult:
        case AssistantTraceEventType.subagentError:
        case AssistantTraceEventType.searchQueryGenerated:
        case AssistantTraceEventType.searchStarted:
        case AssistantTraceEventType.searchCompleted:
          return true;
        default:
          break;
      }
      final stageType = parseAssistantTraceEventType(
        (trace.data?['stageType'] as String?)?.trim() ?? '',
      );
      if (stageType == AssistantTraceEventType.toolStart ||
          stageType == AssistantTraceEventType.toolResult ||
          stageType == AssistantTraceEventType.toolError ||
          stageType == AssistantTraceEventType.searchQueryGenerated ||
          stageType == AssistantTraceEventType.searchStarted ||
          stageType == AssistantTraceEventType.searchCompleted ||
          stageType == AssistantTraceEventType.subagentStart ||
          stageType == AssistantTraceEventType.subagentResult ||
          stageType == AssistantTraceEventType.subagentError) {
        return true;
      }
    }
    return false;
  }

  bool _looksLikeRenderableAnswerText(String text) {
    final normalized = text.trim();
    if (normalized.isEmpty) return false;
    if (normalized.length >= 24) return true;
    final hasStructuredMarkdown =
        normalized.contains('\n') ||
        normalized.contains('- ') ||
        normalized.contains('* ') ||
        normalized.contains('1.');
    if (hasStructuredMarkdown) return true;
    final sentenceLikeHits = _countSentenceTerminators(normalized);
    if (sentenceLikeHits >= 2) return true;
    final hasSentenceEnding = _containsSentenceTerminator(normalized);
    if (hasSentenceEnding && normalized.length >= 8) {
      return true;
    }
    return normalized.length >= 12 &&
        _containsCjkOrAsciiLetterOrDigit(normalized);
  }

  Future<List<AssistantSubagentRunRecord>> _executeSubagentPlans({
    required Map<String, dynamic> answerPayload,
    required AssistantRunRequest request,
    required String sessionId,
    required String runId,
    required String traceId,
    required Map<String, dynamic> templateContext,
    required Map<String, dynamic> templateVariables,
    required void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final apv = AssistantAnswerPayloadReadView(answerPayload);
    final rawPlans = apv.subagentPlanMaps;
    final plans = rawPlans
        .map((item) => SubagentPlan.fromJson(item))
        .where((item) => item.domainId.trim().isNotEmpty)
        .toList(growable: false);
    if (plans.isEmpty) return const <AssistantSubagentRunRecord>[];
    // Build a single subagent execution closure for parallel dispatch
    Future<AssistantSubagentRunRecord> runSingleSubagent(
      int index,
      SubagentPlan plan,
    ) async {
      final subagentId = plan.subagentId.isNotEmpty
          ? plan.subagentId
          : 'subagent_${index + 1}';
      final goal = plan.goal;
      final taskBrief = plan.taskBrief.trim().isNotEmpty
          ? plan.taskBrief.trim()
          : goal;
      final routeNarrative = plan.routeNarrative.trim();
      final localContextSeed = plan.localContextSeed.trim();
      final executionGoal = taskBrief.isNotEmpty ? taskBrief : goal;
      final subagentDomainId = plan.domainId;
      final planMode = plan.mode;
      final timeoutMs = plan.timeoutMs;
      var maxIterations = plan.maxIterations;
      var toolBudget = plan.toolBudget;
      final toolWhitelist = plan.toolWhitelist;
      // Load domain-specific skill instruction for this subagent (P1-2)
      Map<String, dynamic> subagentTemplateVars = templateVariables;
      var effectiveSubagentShell = const SkillExecutionShell();
      if (subagentDomainId.isNotEmpty) {
        final subagentSkillContext = await _executionPreparationResolver
            .resolveSkillContext(
              domainId: subagentDomainId,
              userQuery: executionGoal,
              preferExplicitDomain: true,
            );
        effectiveSubagentShell = _executionPreparationResolver
            .resolveExecutionShellForProblemClass(
              domainId: subagentDomainId,
              baseShell: subagentSkillContext.executionShell,
              problemClass: parseProblemClass(plan.problemClass),
              mode: planMode,
              secondarySkills: const <String>[],
              queryText: executionGoal,
            );
        effectiveSubagentShell = _applySubagentStrategyToShell(
          baseShell: effectiveSubagentShell,
          plan: plan,
        );
        subagentTemplateVars = <String, dynamic>{
          ...templateVariables,
          'domainId': subagentDomainId,
          'domainSkillInstruction': subagentSkillContext.instructionMarkdown,
          'domainSkillName': subagentSkillContext.skillName,
          'skillExecutionShell': effectiveSubagentShell.toJson(),
          'problemClass': effectiveSubagentShell.problemClass,
          'subagentPlan': plan.toJson(),
          'subagentTaskBrief': taskBrief,
          'subagentRouteNarrative': routeNarrative,
          'subagentLocalContextSeed': localContextSeed,
          'subagentRole': plan.role,
          'subagentNeedClarify': plan.needClarify,
          'subagentPendingClarifications': plan.pendingClarifications,
        };
        if (effectiveSubagentShell.maxIterations > 0 &&
            effectiveSubagentShell.maxIterations < maxIterations) {
          maxIterations = effectiveSubagentShell.maxIterations;
        }
        if (effectiveSubagentShell.toolBudget > 0 &&
            effectiveSubagentShell.toolBudget < toolBudget) {
          toolBudget = effectiveSubagentShell.toolBudget;
        }
      }
      final subagentTools = _resolveSubagentToolNames(
        toolWhitelist: toolWhitelist,
        toolBudget: toolBudget,
      );
      onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.subagentStart,
          message: 'subagent started: $subagentId',
          timestamp: DateTime.now(),
          runId: runId,
          traceId: traceId,
          data: <String, dynamic>{
            'subagentId': subagentId,
            'domainId': subagentDomainId,
            'goal': executionGoal,
            'mode': planMode,
            'problemClass': effectiveSubagentShell.problemClass,
            'shell': effectiveSubagentShell.toJson(),
            'stopPolicy': plan.stopPolicy,
            'searchIntensity': plan.searchIntensity,
            'providerPolicy': plan.providerPolicy,
            'freshnessHoursMax': plan.freshnessHoursMax,
            'answerThreshold': plan.answerThreshold,
            'toolWhitelist': subagentTools,
            'timeoutMs': timeoutMs,
          },
        ),
      );
      try {
        final subagentResult = await _runtime
            .run(
              messages: <Map<String, dynamic>>[
                <String, dynamic>{
                  'role': 'system',
                  'content': await _renderPromptSnippet(
                    'subagent_execution',
                    variables: <String, dynamic>{
                      'routeNarrative': routeNarrative,
                      'localContextSeed': localContextSeed,
                    },
                  ),
                },
                <String, dynamic>{'role': 'user', 'content': executionGoal},
              ],
              maxIterations: maxIterations,
              goal: executionGoal,
              availableToolNamesOverride: subagentTools,
              templateId: 'planner.global_plan',
              templateVersion: '',
              templateContext: templateContext,
              templateVariables: subagentTemplateVars,
              sessionId: sessionId,
              runId: runId,
              traceId: traceId,
              onTraceEvent: onTraceEvent,
            )
            .timeout(Duration(milliseconds: timeoutMs));
        final childAnswerPayload = parseAnswerPayload(
          rawFinalText: subagentResult.finalText,
          traces: subagentResult.traces,
        );
        final childAnswerView = AssistantAnswerPayloadReadView(
          childAnswerPayload,
        );
        final childToolResults = subagentResult.traces
            .where((event) => event.type == AssistantTraceEventType.toolResult)
            .map(AssistantToolResultRow.fromTraceEvent)
            .toList(growable: false);
        final childReferences = _buildUiReferences(
          childToolResults,
          isRealtimeLike: _isRealtimeLikeProblemClass(plan.problemClass),
        );
        final childReferenceMaps = childReferences
            .map((item) => item.toJson())
            .toList(growable: false);
        final childAcceptedEvidence = childReferenceMaps;
        final childRejectedEvidence = const <Map<String, dynamic>>[];
        final childMissingSlots =
            <String>[
                  ...childAnswerView.topLevelMissingSlots,
                  ...childAnswerView.slotStateMissingSlots,
                ]
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toSet()
                .toList(growable: false);
        final childNextAction = childAnswerView.nextActionWireName;
        final childFailureReason = childAnswerView.diagnosticsFailureReason;
        final subagentUsage = usage_stats.buildUsageStatsFromTraces(
          traces: subagentResult.traces,
          fallbackInputText: executionGoal,
          fallbackOutputText: subagentResult.finalText,
        );
        final run = AssistantSubagentRunRecord.success(
          subagentId: subagentId,
          domainId: subagentDomainId,
          goal: executionGoal,
          mode: planMode,
          problemClass: effectiveSubagentShell.problemClass,
          shell: effectiveSubagentShell.toJson(),
          stopPolicy: plan.stopPolicy,
          searchIntensity: plan.searchIntensity,
          providerPolicy: plan.providerPolicy,
          freshnessHoursMax: plan.freshnessHoursMax,
          answerThreshold: plan.answerThreshold,
          summary: subagentResult.finalText,
          userMarkdown: childAnswerView.userMarkdownTrimmed,
          result: childAnswerView.resultTyped.toJson(),
          answerReady:
              childAnswerView.userMarkdownTrimmed.isNotEmpty ||
              childAnswerView.hasTopLevelResultMap,
          references: childReferenceMaps,
          acceptedEvidence: childAcceptedEvidence,
          rejectedEvidence: childRejectedEvidence,
          nextAction: childNextAction,
          missingSlots: childMissingSlots,
          failureReason: childFailureReason,
          toolCallCount: subagentResult.traces
              .where((event) => event.type == AssistantTraceEventType.toolStart)
              .length,
          modelCallCount: subagentUsage.modelCallCount,
          totalTokens: subagentUsage.totalTokens,
          maxTokensPerCall: subagentUsage.maxTokensPerCall,
          tokenSource: subagentUsage.tokenSource,
          tokenSampleCount: subagentUsage.tokenSampleCount,
          inputTokens: subagentUsage.inputTokens,
          outputTokens: subagentUsage.outputTokens,
          usageLedger: subagentUsage.usageLedger,
        );
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentResult,
            message: 'subagent finished: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run.toJson(),
          ),
        );
        return run;
      } on TimeoutException {
        final run = AssistantSubagentRunRecord.timeout(
          subagentId: subagentId,
          domainId: subagentDomainId,
          goal: executionGoal,
          mode: planMode,
          problemClass: effectiveSubagentShell.problemClass,
          shell: effectiveSubagentShell.toJson(),
          stopPolicy: plan.stopPolicy,
          searchIntensity: plan.searchIntensity,
          providerPolicy: plan.providerPolicy,
          freshnessHoursMax: plan.freshnessHoursMax,
          answerThreshold: plan.answerThreshold,
          missingSlots: plan.pendingClarifications,
        );
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentError,
            message: 'subagent timeout: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run.toJson(),
          ),
        );
        return run;
      } catch (error) {
        final run = AssistantSubagentRunRecord.failure(
          subagentId: subagentId,
          domainId: subagentDomainId,
          goal: executionGoal,
          mode: planMode,
          problemClass: effectiveSubagentShell.problemClass,
          shell: effectiveSubagentShell.toJson(),
          stopPolicy: plan.stopPolicy,
          searchIntensity: plan.searchIntensity,
          providerPolicy: plan.providerPolicy,
          freshnessHoursMax: plan.freshnessHoursMax,
          answerThreshold: plan.answerThreshold,
          missingSlots: plan.pendingClarifications,
          failureReason: error.toString(),
          errorMessage: error.toString(),
        );
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentError,
            message: 'subagent failed: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run.toJson(),
          ),
        );
        return run;
      }
    }

    // Parallel dispatch (P2-1): run all subagents concurrently
    final futures = <Future<AssistantSubagentRunRecord>>[];
    if (plans.isEmpty) return const <AssistantSubagentRunRecord>[];
    for (var i = 0; i < plans.length; i++) {
      futures.add(runSingleSubagent(i, plans[i]));
    }
    return Future.wait(futures);
  }

  List<String> _resolveSubagentToolNames({
    required List<String> toolWhitelist,
    required int toolBudget,
  }) {
    final runtimeTools = _runtime.listAvailableToolNames();
    final scoped = toolWhitelist.isEmpty
        ? runtimeTools
        : runtimeTools.where((tool) => toolWhitelist.contains(tool)).toList();
    if (scoped.length <= toolBudget) return scoped;
    return scoped.take(toolBudget).toList(growable: false);
  }

  SkillExecutionShell _applySubagentStrategyToShell({
    required SkillExecutionShell baseShell,
    required SubagentPlan plan,
  }) {
    var next = baseShell.copyWith(
      providerPolicy: plan.providerPolicy.isNotEmpty
          ? plan.providerPolicy
          : baseShell.providerPolicy,
      freshnessHoursMax: plan.freshnessHoursMax > 0
          ? math.min(baseShell.freshnessHoursMax, plan.freshnessHoursMax)
          : baseShell.freshnessHoursMax,
    );
    switch (plan.searchIntensityType) {
      case SearchIntensity.low:
        next = next.copyWith(
          maxIterations: math.min(
            next.maxIterations,
            math.max(1, plan.maxIterations),
          ),
          toolBudget: math.min(next.toolBudget, math.max(1, plan.toolBudget)),
          variantBudget: math.min(next.variantBudget, 0),
          reflectionBudget: math.min(next.reflectionBudget, 0),
        );
        break;
      case SearchIntensity.high:
        next = next.copyWith(
          maxIterations: math.max(next.maxIterations, plan.maxIterations),
          toolBudget: math.max(next.toolBudget, plan.toolBudget),
          variantBudget: math.max(next.variantBudget, 1),
          reflectionBudget: math.max(next.reflectionBudget, 1),
        );
        break;
      case SearchIntensity.medium:
        next = next.copyWith(
          maxIterations: math.min(
            math.max(1, plan.maxIterations),
            math.max(next.maxIterations, plan.maxIterations),
          ),
          toolBudget: math.min(
            math.max(1, plan.toolBudget),
            math.max(next.toolBudget, plan.toolBudget),
          ),
        );
    }
    switch (plan.stopPolicyType) {
      case StopPolicy.fastExit:
        return next.copyWith(
          maxIterations: math.min(next.maxIterations, 2),
          toolBudget: math.min(next.toolBudget, 1),
          variantBudget: math.min(next.variantBudget, 0),
          reflectionBudget: math.min(next.reflectionBudget, 0),
        );
      case StopPolicy.exhaustive:
        return next.copyWith(
          maxIterations: math.max(next.maxIterations, 3),
          toolBudget: math.max(next.toolBudget, 2),
          variantBudget: math.max(next.variantBudget, 1),
          reflectionBudget: math.max(next.reflectionBudget, 1),
        );
      case StopPolicy.balanced:
        return next;
    }
  }

  bool _isRealtimeLikeProblemClass(String rawProblemClass) {
    return parseProblemClass(rawProblemClass) == ProblemClass.realtimeInfo;
  }

  AssistantRunResponse _buildBlockedResponse({
    required String runId,
    required String traceId,
    required ContextAssemblyResult contextAssembly,
  }) {
    final traceStart = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'agent loop blocked by domain preconditions',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      visibility: TraceVisibility.system,
      data: <String, dynamic>{
        'contextEnvelope': contextAssembly.contextEnvelope,
        'fillTasks': contextAssembly.fillTasks.map((e) => e.toJson()).toList(),
      },
    );
    final nextAction = contextAssembly.fillTasks
        .map((task) => '- ${_summarizeFillTask(task)}')
        .join('\n');
    final finalText = nextAction.isNotEmpty ? nextAction : 'missing_context';
    final traceEnd = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleEnd,
      message: 'agent loop finished (blocked_precondition)',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      visibility: TraceVisibility.system,
      data: const <String, dynamic>{'lifecycleOutcome': 'blocked'},
    );
    final boundaryOutcome = const AssistantBoundaryErrorMapper().blocked(
      boundary: 'assistant_turn',
      stage: 'context_precheck',
      failure: const RuntimeFailure(
        code: 'ASSISTANT.USER.missing_context',
        origin: RuntimeFailureOrigin.user,
        kind: RuntimeFailureKind.validation,
        nature: RuntimeFailureNature.requiresUserAction,
        location: RuntimeFailureLocation(
          businessObject: 'assistant_turn',
          functionModule: 'context_precheck',
        ),
        context: RuntimeFailureContext(),
      ),
    );
    return AssistantRunResponse(
      finalText: finalText,
      traces: <AssistantTraceEvent>[traceStart, traceEnd],
      runId: runId,
      traceId: traceId,
      degraded: true,
      errorCode: 'missing_context',
      structuredResponse: <String, dynamic>{
        'assistantBoundaryOutcome': boundaryOutcome.toJson(),
        'contextAssembly': contextAssembly.contextEnvelope,
        'domainPrecheck': <String, dynamic>{
          'canEnterDomain': false,
          'reason': 'missing_context',
        },
        'domainResults': const <Map<String, dynamic>>[],
        'synthesisReadiness': const <String, dynamic>{'ready': false},
        'fillTasks': <String, dynamic>{
          'contextFillTasks': contextAssembly.fillTasks
              .map((task) => task.toJson())
              .toList(growable: false),
          'replanTask': null,
        },
        'contextSlots': buildContextSlots(contextAssembly),
        'fillActions': contextAssembly.fillTasks
            .map((task) => task.toJson())
            .toList(growable: false),
        'missingCriticalSlots':
            (contextAssembly.contextEnvelope['missingSlots'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[],
        'answerEligibility': AnswerEligibility.blocked.wireName,
        'selfCheck': const <String, dynamic>{
          'passed': false,
          'failedChecks': <String>['missing_context'],
        },
        'diagnostics': const <String, dynamic>{
          'synthesisReason': 'blocked_precondition',
        },
        'nextActions': contextAssembly.fillTasks
            .map((task) => task.reason)
            .toList(growable: false),
        'experimentBucket': resolveExperimentBucket(
          const <String, dynamic>{},
          'control',
        ),
      },
    );
  }

  String _summarizeFillTask(ContextFillTask task) {
    final reason = task.reason.trim();
    if (reason.isNotEmpty) {
      return reason;
    }
    return task.targetSlot.wireName;
  }

  ProfileUpdateProposal? _buildProfileUpdateProposal({
    required AssistantRunRequest request,
  }) {
    final proposalRaw = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    ).value(AssistantPipelineStateKeys.profileUpdateProposal);
    if (proposalRaw is Map) {
      final parsed = ProfileUpdateProposal.fromJson(
        proposalRaw.cast<String, dynamic>(),
      );
      if (parsed.isValid) return parsed;
    }
    return null;
  }

  Future<Map<String, dynamic>> _buildStructuredResponse({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required SynthesisReadinessResult synthesisReadiness,
    required ReactRuntimeResult result,
    required AssistantPlanView planView,
    required List<SearchPlanItem> searchPlans,
    required List<SkillRun> skillRuns,
    required AggregationState aggregationState,
    required List<SubagentPlan> subagentPlan,
    required List<AssistantSubagentRunRecord> subagentRuns,
    required SkillSynthesisInput skillSynthesisInput,
    required SkillSynthesisOutput skillSynthesisOutput,
    required DialogueRoundScript dialogueRoundScript,
    required List<String> candidateDomains,
    required SkillExecutionShell skillExecutionShell,
    required String templateVersionUsed,
    required String domainCatalogVersion,
    required String sessionId,
    required Map<String, dynamic> retrievalPolicy,
    required AnswerBoundaryPolicy answerBoundaryPolicy,
    required SlotStateSnapshot previousSlotState,
    Map<String, dynamic> carriedUnderstandingSnapshot =
        const <String, dynamic>{},
    Map<String, dynamic> carriedRetrievalProcessing = const <String, dynamic>{},
    Map<String, dynamic> carriedHistoricalThinkingSnapshot =
        const <String, dynamic>{},
    String streamedRetrievalProcessingSummary = '',
    String streamedAnswerReadinessSummary = '',
    Map<String, dynamic> phaseOneRoutingDiagnostics = const <String, dynamic>{},
    DomainPolicyBundle? previousDomainPolicyBundle,
    ProcessStepId blockedProcessStepId = ProcessStepId.unknown,
    String blockedProcessMessage = '',
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  }) {
    final skillRoute = SkillRouteOutput(
      userQuery: skillSynthesisInput.userQuery,
      selectedTargets: skillSynthesisInput.selectedTargets
          .map(
            (item) => SkillRouteTarget(
              skillId: item.skillId,
              role: item.role,
              priority: item.priority,
              routeNarrative: item.reason,
            ),
          )
          .toList(growable: false),
      routeNarrative: skillSynthesisInput.routeNarrative,
      needClarify: skillSynthesisInput.pendingClarifications.isNotEmpty,
      pendingClarifications: skillSynthesisInput.pendingClarifications,
    );
    return buildStructuredResponsePayload(
      request: request,
      contextAssembly: contextAssembly,
      synthesisReadiness: synthesisReadiness,
      result: result,
      planView: planView,
      searchPlans: searchPlans,
      skillRuns: skillRuns,
      aggregationState: aggregationState,
      skillRoute: skillRoute,
      subagentPlan: subagentPlan,
      subagentRuns: subagentRuns,
      skillSynthesisInput: skillSynthesisInput,
      skillSynthesisOutput: skillSynthesisOutput,
      dialogueRoundScript: dialogueRoundScript,
      candidateDomains: candidateDomains,
      skillExecutionShell: skillExecutionShell,
      templateVersionUsed: templateVersionUsed,
      domainCatalogVersion: domainCatalogVersion,
      sessionId: sessionId,
      retrievalPolicy: retrievalPolicy,
      answerBoundaryPolicy: answerBoundaryPolicy,
      previousSlotState: previousSlotState,
      carriedUnderstandingSnapshot: carriedUnderstandingSnapshot,
      carriedRetrievalProcessing: carriedRetrievalProcessing,
      carriedHistoricalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
      streamedRetrievalProcessingSummary: streamedRetrievalProcessingSummary,
      streamedAnswerReadinessSummary: streamedAnswerReadinessSummary,
      phaseOneRoutingDiagnostics: phaseOneRoutingDiagnostics,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
      blockedProcessStepId: blockedProcessStepId,
      blockedProcessMessage: blockedProcessMessage,
      onTraceEvent: onTraceEvent,
      runId: runId,
      traceId: traceId,
    );
  }

  SearchIterationState _seedSearchIterationState({
    required AssistantRunRequest request,
    required List<SearchPlanItem> searchPlans,
  }) {
    return SearchIterationState(
      maxIterations: request.maxIterations,
      currentIteration: 1,
      rounds: searchPlans.isEmpty
          ? const <SearchIterationRound>[]
          : <SearchIterationRound>[
              SearchIterationRound(
                iteration: 1,
                triggerReason: 'initial_plan',
                plannerInputSummary: request.messages.isNotEmpty
                    ? request.messages.last.content.trim()
                    : '',
                plannerOutputSummary: _searchIterationPlannerOutputSummary(
                  searchPlans,
                ),
                searchPlans: searchPlans,
                acceptedEvidenceCount: 0,
                missingDimensions: const <String>[],
                convergenceStatus: SearchIterationConvergenceStatus.improving,
              ),
            ],
    );
  }

  String _searchIterationPlannerOutputSummary(
    List<SearchPlanItem> searchPlans,
  ) {
    if (searchPlans.isEmpty) {
      return '';
    }
    final labels = searchPlans
        .map((plan) => plan.effectiveLabel.trim())
        .where((item) => item.isNotEmpty)
        .take(3)
        .toList(growable: false);
    if (labels.isEmpty) {
      return '';
    }
    return labels.join('、');
  }

  SearchIterationState _searchIterationStateFromTemplateVariables(
    AssistantPipelineTemplateVariablesView templateVariables, {
    int fallbackMaxIterations = 0,
  }) {
    final base = templateVariables.searchIterationState;
    if (base.maxIterations > 0 ||
        base.currentIteration > 0 ||
        base.rounds.isNotEmpty) {
      return base;
    }
    return SearchIterationState(
      maxIterations: fallbackMaxIterations,
      currentIteration: fallbackMaxIterations > 0 ? 1 : 0,
      rounds: const <SearchIterationRound>[],
    );
  }

  SearchIterationState _buildSynthesisSearchIterationState({
    required AssistantPipelineTemplateVariablesView templateVariables,
    required List<AssistantTraceEvent> phaseOneTraces,
    required List<SearchPlanItem> fallbackSearchPlans,
    required int maxIterations,
    required int acceptedEvidenceCount,
    required List<String> missingDimensions,
    required bool answerReady,
  }) {
    final base = _searchIterationStateFromTemplateVariables(
      templateVariables,
      fallbackMaxIterations: maxIterations,
    );
    final traceRounds = phaseOneTraces
        .where(
          (event) => event.type == AssistantTraceEventType.searchQueryGenerated,
        )
        .map((event) {
          final data = event.data ?? const <String, dynamic>{};
          final rawTasks =
              (data['searchPlans'] as List?)?.whereType<Map>().toList(
                growable: false,
              ) ??
              const <Map>[];
          final searchPlans = SearchPlanItem.normalizeList(rawTasks);
          final iteration = ((data['iteration'] as num?)?.toInt() ?? 0) > 0
              ? (data['iteration'] as num).toInt()
              : 0;
          return SearchIterationRound(
            iteration: iteration,
            triggerReason:
                ((data['reason'] as String?)?.trim().isNotEmpty == true
                        ? (data['reason'] as String).trim()
                        : '')
                    .isNotEmpty
                ? (data['reason'] as String).trim()
                : 'initial_plan',
            plannerInputSummary: (data['query'] as String?)?.trim() ?? '',
            plannerOutputSummary: event.message.trim(),
            searchPlans: searchPlans,
            acceptedEvidenceCount: 0,
            missingDimensions: const <String>[],
            convergenceStatus: SearchIterationConvergenceStatus.unknown,
          );
        })
        .toList(growable: false);
    final rounds = traceRounds.isNotEmpty
        ? traceRounds
              .asMap()
              .entries
              .map((entry) {
                final round = entry.value;
                return SearchIterationRound(
                  iteration: round.iteration > 0
                      ? round.iteration
                      : entry.key + 1,
                  triggerReason: round.triggerReason,
                  plannerInputSummary: round.plannerInputSummary,
                  plannerOutputSummary: round.plannerOutputSummary,
                  searchPlans: round.searchPlans,
                  acceptedEvidenceCount: round.acceptedEvidenceCount,
                  missingDimensions: round.missingDimensions,
                  convergenceStatus: round.convergenceStatus,
                );
              })
              .toList(growable: false)
        : (base.rounds.isNotEmpty
              ? List<SearchIterationRound>.of(base.rounds)
              : (fallbackSearchPlans.isEmpty
                    ? <SearchIterationRound>[]
                    : <SearchIterationRound>[
                        SearchIterationRound(
                          iteration: 1,
                          triggerReason: 'initial_plan',
                          plannerInputSummary: '',
                          plannerOutputSummary:
                              _searchIterationPlannerOutputSummary(
                                fallbackSearchPlans,
                              ),
                          searchPlans: fallbackSearchPlans,
                          acceptedEvidenceCount: 0,
                          missingDimensions: const <String>[],
                          convergenceStatus:
                              SearchIterationConvergenceStatus.unknown,
                        ),
                      ]));
    final currentIteration = rounds.isNotEmpty
        ? rounds.last.iteration
        : (base.currentIteration > 0 ? base.currentIteration : 1);
    final effectiveMaxIterations = base.maxIterations > 0
        ? base.maxIterations
        : maxIterations;
    final convergenceStatus = answerReady
        ? SearchIterationConvergenceStatus.improving
        : (currentIteration >= effectiveMaxIterations
              ? SearchIterationConvergenceStatus.saturated
              : SearchIterationConvergenceStatus.flat);
    if (rounds.isNotEmpty) {
      final last = rounds.last;
      rounds[rounds.length - 1] = SearchIterationRound(
        iteration: last.iteration,
        triggerReason: last.triggerReason,
        plannerInputSummary: last.plannerInputSummary,
        plannerOutputSummary: last.plannerOutputSummary,
        searchPlans: last.searchPlans,
        acceptedEvidenceCount: acceptedEvidenceCount,
        missingDimensions: missingDimensions,
        convergenceStatus: convergenceStatus,
      );
    }
    return SearchIterationState(
      maxIterations: effectiveMaxIterations,
      currentIteration: currentIteration,
      rounds: rounds,
    );
  }

  ExecutionPreparationResolver get _executionPreparationResolver =>
      ExecutionPreparationResolver(
        domainRouter: _domainRouter,
        templateCatalogRuntime: _templateCatalogRuntime,
        skillLoader: _skillLoader,
        skillRouter: _skillRouter,
        toolMetadataRegistry: _toolMetadataRegistry,
      );

  PhaseOneDirectAnswerGate get _phaseOneDirectAnswerGate =>
      const PhaseOneDirectAnswerGate();

  bool _hasCapability(List<String> catalog, String capabilityId) {
    if (catalog.isEmpty) return true;
    return catalog.contains(capabilityId);
  }

  String _formatContextAnchor(Map<String, dynamic> scope) {
    final lines = <String>[];
    final pageType = (scope['pageType'] as String?)?.trim() ?? '';
    if (pageType.isNotEmpty) lines.add('- pageType: $pageType');
    final sessionId = (scope['sessionId'] as String?)?.trim() ?? '';
    if (sessionId.isNotEmpty) lines.add('- sessionId: $sessionId');
    final entityId = (scope['entityId'] as String?)?.trim() ?? '';
    if (entityId.isNotEmpty) lines.add('- entityId: $entityId');
    final tab = (scope['tab'] as String?)?.trim() ?? '';
    if (tab.isNotEmpty) lines.add('- tab: $tab');
    final privacyProfile = (scope['privacyProfile'] as String?)?.trim() ?? '';
    if (privacyProfile.isNotEmpty) {
      lines.add('- privacyProfile: $privacyProfile');
    }
    if (lines.isEmpty) return '- none';
    return lines.join('\n');
  }

  BootstrapPhase get _bootstrapPhase => BootstrapPhase(
    runtime: _runtime,
    sessionManager: _sessionManager,
    memoryRepository: _memoryRepository,
    contextOrchestrator: _contextOrchestrator,
    templateCatalogRuntime: _templateCatalogRuntime,
    domainRouter: _domainRouter,
    recallCoordinator: _recallCoordinator,
    toolMetadataRegistry: _toolMetadataRegistry,
  );

  UnderstandPhase get _understandPhase => UnderstandPhase(
    domainRouter: _domainRouter,
    dialogueStateRuntime: _dialogueStateRuntime,
    modeDecider: _modeDecider,
    runtime: _runtime,
    templateCatalogRuntime: _templateCatalogRuntime,
  );

  RetrievalDesignPhase get _retrievalDesignPhase => RetrievalDesignPhase(
    runtime: _runtime,
    domainRouter: _domainRouter,
    templateCatalogRuntime: _templateCatalogRuntime,
    toolMetadataRegistry: _toolMetadataRegistry,
    skillLoader: _skillLoader,
    skillRouter: _skillRouter,
  );

  FinalizeRunner buildFinalizeRunner() => FinalizeRunner(
    sessionManager: _sessionManager,
    memoryRepository: _memoryRepository,
    buildObservabilityPayload: const ObservabilityPayloadBuilder().call,
  );
}

class _CompatibilityBootstrapState {
  const _CompatibilityBootstrapState({
    required this.bootstrapContext,
    required this.contextAssembly,
  });

  final AssistantBootstrapContext bootstrapContext;
  final ContextAssemblyResult contextAssembly;
}

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/application/assistant_journey_projector.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/agent_run_observability.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_fill_contract.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/aggregation_gate.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/context/assembly/conversation_state_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/orchestration/answer_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/phase_one_direct_answer_gate.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/bootstrap_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/finalize_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/retrieval_design_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

// ─────────────────────────────────────────────────────────────────────────
// PROHIBITION: 禁止在此文件中增量堆新逻辑。
// 该文件为兼容桥，编排主逻辑应迁移到 orchestration/assistant_agent_loop.dart
// 与 orchestration/phases/。详见 assistant/docs/canonical_truth_sources.md。
// ─────────────────────────────────────────────────────────────────────────
class LocalPhaseExecutionOwner {
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
    AggregationGate? aggregationGate,
    BaselineKernel? baselineKernel,
    ConversationStateKernel? conversationStateKernel,
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
       _aggregationGate = aggregationGate ?? const AggregationGate(),
       _baselineKernel = baselineKernel ?? const BaselineKernel(),
       _answerBoundaryResolver =
           answerBoundaryResolver ?? const AnswerBoundaryResolver(),
       _conversationStateKernel =
           conversationStateKernel ?? const ConversationStateKernel();

  final ReactRuntime _runtime;
  final AssistantSessionManager _sessionManager;
  final AssistantMemoryRepository _memoryRepository;
  final ToolMetadataRegistry? _toolMetadataRegistry;
  final PersonalAssistantContextOrchestrator _contextOrchestrator;
  final DialogueStateRuntime _dialogueStateRuntime;
  final AssistantDomainRouter _domainRouter;
  final TemplateCatalogRuntime _templateCatalogRuntime;
  final PersonalAssistantSkillLoader _skillLoader;
  final PersonalAssistantSkillRouter _skillRouter;
  final RecallCoordinator _recallCoordinator;
  final ModeDecider _modeDecider;
  final AggregationGate _aggregationGate;
  final BaselineKernel _baselineKernel;
  final AnswerBoundaryResolver _answerBoundaryResolver;
  final ConversationStateKernel _conversationStateKernel;

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
      return AssistantRunResponse(
        finalText: '助手内部出现意外错误，请重试。',
        degraded: true,
        errorCode: 'internal_error',
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'agent_loop_uncaught: ${error.runtimeType}: $error',
            timestamp: DateTime.now(),
            data: <String, dynamic>{
              'errorType': error.runtimeType.toString(),
              'stackSnippet': stackTrace.toString().substring(
                0,
                math.min(400, stackTrace.toString().length),
              ),
            },
          ),
        ],
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
    final shortCircuitResponse =
        executionSnapshot['shortCircuitResponse'] as AssistantRunResponse?;
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

  Future<Map<String, dynamic>> executeBridgeFromState(
    AssistantRunRequest request, {
    required AgentExecutionState state,
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    final bridgedRequest = AssistantRunRequest.fromJson(<String, dynamic>{
      ...request.toJson(),
      'contextScopeHint': _buildCompatibilityContextScopeHint(
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

  Map<String, dynamic> _buildCompatibilityContextScopeHint({
    required AssistantRunRequest request,
    required AgentExecutionState state,
  }) {
    final continuationActive = _shouldCarryStructuredHistory(
      state.bootstrapContext?.contextContinuityPolicy ??
          const ContextContinuityPolicy(),
    );
    return <String, dynamic>{
      ..._sanitizeModelTemplateContext(
        request.contextScopeHint,
        continuationActive: continuationActive,
        previousRunArtifacts: state.previousRunArtifacts,
      ),
      if (state.bootstrapContext != null &&
          _hasStructuredContent(
            state.bootstrapContext!.previousUnderstandingSnapshot.toJson(),
          ))
        'previousUnderstandingSnapshot': state
            .bootstrapContext!
            .previousUnderstandingSnapshot
            .toJson(),
      if (state.bootstrapContext != null &&
          _hasStructuredContent(
            state.bootstrapContext!.previousAnswerProcessing.toJson(),
          ))
        'previousAnswerProcessing': state
            .bootstrapContext!
            .previousAnswerProcessing
            .toJson(),
      if (state.bootstrapContext != null &&
          _hasStructuredContent(
            state.bootstrapContext!.historicalThinkingSnapshot.toJson(),
          ))
        'historicalThinkingSnapshot': state
            .bootstrapContext!
            .historicalThinkingSnapshot
            .toJson(),
      if (state.bootstrapContext?.providerReasoningContinuation
              .trim()
              .isNotEmpty ==
          true)
        'providerReasoningContinuation': state
            .bootstrapContext!
            .providerReasoningContinuation
            .trim(),
      if (state.bootstrapContext != null)
        'precomputedBootstrap': <String, dynamic>{
          'sessionId': state.bootstrapContext!.sessionId,
          'latestUserQuery': state.bootstrapContext!.latestUserQuery,
          'historySummary': state.bootstrapContext!.historySummary,
          'recalledTexts': state.bootstrapContext!.recalledTexts,
          if (state.bootstrapContext!.previousIntentGraph != null)
            'previousIntentGraph': state.bootstrapContext!.previousIntentGraph!
                .toJson(),
          if (state.bootstrapContext!.previousAnswerSummary.isNotEmpty)
            'previousAnswerSummary':
                state.bootstrapContext!.previousAnswerSummary,
          if (_hasStructuredContent(
            state.bootstrapContext!.previousUnderstandingSnapshot.toJson(),
          ))
            'previousUnderstandingSnapshot': state
                .bootstrapContext!
                .previousUnderstandingSnapshot
                .toJson(),
          if (_hasStructuredContent(
            state.bootstrapContext!.previousAnswerProcessing.toJson(),
          ))
            'previousAnswerProcessing': state
                .bootstrapContext!
                .previousAnswerProcessing
                .toJson(),
          if (_hasStructuredContent(
            state.bootstrapContext!.historicalThinkingSnapshot.toJson(),
          ))
            'historicalThinkingSnapshot': state
                .bootstrapContext!
                .historicalThinkingSnapshot
                .toJson(),
          if (state.bootstrapContext!.providerReasoningContinuation
              .trim()
              .isNotEmpty)
            'providerReasoningContinuation': state
                .bootstrapContext!
                .providerReasoningContinuation
                .trim(),
          'contextContinuityPolicy': state
              .bootstrapContext!
              .contextContinuityPolicy
              .toJson(),
          'continuityOverrideSlots':
              state.bootstrapContext!.continuityOverrideSlots,
          'recallResult': state.bootstrapContext!.recallResult.toJson(),
          'forceRefreshCatalog': state.bootstrapContext!.forceRefreshCatalog,
          'domainCatalog': state.bootstrapContext!.domainCatalog,
          'domainCatalogVersion': state.bootstrapContext!.domainCatalogVersion,
          'fullSkillCatalog': state.bootstrapContext!.fullSkillCatalog,
          'skillCatalog': state.bootstrapContext!.skillCatalog,
          if (state.contextAssembly != null)
            'contextAssembly': state.contextAssembly!.toJson(),
          if (state.previousRunArtifacts != null)
            'previousRunArtifacts': state.previousRunArtifacts!.toJson(),
        },
      if (state.intentGraph != null)
        'precomputedIntentGraph': state.intentGraph!.toJson(),
      if (state.dialogueRoundScript != null ||
          state.executionPreparation != null)
        'precomputedUnderstand': <String, dynamic>{
          if (state.dialogueRoundScript != null)
            'dialogueRoundScript': state.dialogueRoundScript!.toJson(),
          if (state.executionPreparation != null)
            'domainId': state.executionPreparation!.domainId,
          if (state.executionPreparation != null)
            'modeDecision': state.executionPreparation!.modeDecision.toJson(),
        },
      if (state.executionPreparation != null)
        'precomputedExecutionPreparation': state.executionPreparation!.toJson(),
      if (state.executionPreparation != null)
        'precomputedRetrieval': <String, dynamic>{
          'skillName': state.executionPreparation!.skillName,
          'skillInstructionMarkdown':
              state.executionPreparation!.skillInstructionMarkdown,
          'skillPersona': state.executionPreparation!.skillPersona,
          'allowedToolNames': state.executionPreparation!.allowedToolNames,
          'executionShell': state.executionPreparation!.executionShell.toJson(),
          'plannerTemplateVersion':
              state.executionPreparation!.plannerTemplateVersion,
          'postcheckTemplateVersion':
              state.executionPreparation!.postcheckTemplateVersion,
          'synthTemplateVersion':
              state.executionPreparation!.synthTemplateVersion,
          'fusionSynthTemplateVersion':
              state.executionPreparation!.fusionSynthTemplateVersion,
          'previousSlotState': state.executionPreparation!.previousSlotState
              .toJson(),
          if (state.executionPreparation!.previousDomainPolicyBundle != null)
            'previousDomainPolicyBundle': state
                .executionPreparation!
                .previousDomainPolicyBundle!
                .toJson(),
        },
      if (state.queryTasks.isNotEmpty)
        'precomputedQueryTasks': state.queryTasks
            .map((item) => item.toJson())
            .toList(growable: false),
    };
  }

  bool _shouldCarryStructuredHistory(ContextContinuityPolicy policy) {
    switch (policy.continuityMode) {
      case ContextContinuityMode.sameTopic:
      case ContextContinuityMode.explicitFollowUp:
        return true;
      case ContextContinuityMode.freshTopic:
      case ContextContinuityMode.unknown:
        return false;
    }
  }

  List<AssistantRunMessage> _messagesForCurrentTurn(
    List<AssistantRunMessage> messages, {
    required bool continuationActive,
  }) {
    if (continuationActive) {
      return messages;
    }
    if (messages.isEmpty) {
      return const <AssistantRunMessage>[];
    }
    return <AssistantRunMessage>[messages.last];
  }

  Map<String, dynamic> _sanitizeModelTemplateContext(
    Map<String, dynamic> contextScopeHint, {
    required bool continuationActive,
    RunArtifacts? previousRunArtifacts,
  }) {
    if (contextScopeHint.isEmpty) {
      return continuationActive && previousRunArtifacts != null
          ? <String, dynamic>{'runArtifacts': previousRunArtifacts.toJson()}
          : const <String, dynamic>{};
    }
    final sanitized = Map<String, dynamic>.from(contextScopeHint);
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
    if (!continuationActive) {
      sanitized.remove('dialogueState');
      sanitized.remove('currentStateId');
    } else if (previousRunArtifacts != null) {
      sanitized['runArtifacts'] = previousRunArtifacts.toJson();
    }
    return sanitized;
  }

  Future<Map<String, dynamic>> executeBridge(
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
    final precomputedBootstrap = _recoverPrecomputedBootstrap(
      request.contextScopeHint,
    );
    final precomputedUnderstand = _recoverPrecomputedUnderstand(
      request.contextScopeHint,
    );
    final precomputedRetrieval = _recoverPrecomputedRetrieval(
      request.contextScopeHint,
    );
    final precomputedExecutionPreparation =
        _recoverPrecomputedExecutionPreparation(
          request.contextScopeHint,
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
    final continuationActive = _shouldCarryStructuredHistory(
      contextContinuityPolicy,
    );
    final templateContext = _sanitizeModelTemplateContext(
      request.contextScopeHint,
      continuationActive: continuationActive,
      previousRunArtifacts: ownerState.previousRunArtifacts,
    );
    final historySummary = bootstrapContext.historySummary;
    final recalledTexts = bootstrapContext.recalledTexts;
    final contextAssembly =
        ownerState.contextAssembly ?? const ContextAssemblyResult();
    final forceRefreshDynamicCatalog =
        bootstrapContext.forceRefreshCatalog ||
        request.contextScopeHint['forceRefreshCatalog'] == true;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshDynamicCatalog,
    );
    await _toolMetadataRegistry?.ensureLoaded();
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = bootstrapContext.domainCatalog;
    final domainCatalogVersion = bootstrapContext.domainCatalogVersion;
    final skillCatalog = bootstrapContext.skillCatalog;
    final intentGraph = ownerState.intentGraph;
    if (intentGraph == null) {
      throw StateError(
        'executeBridge missing intentGraph after owner resolution',
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
        : (intentGraph.primarySkill.trim().isNotEmpty
              ? intentGraph.primarySkill.trim()
              : _domainRouter.fallbackDomainId);
    final problemShape = intentGraph.problemShape.wireName.isNotEmpty
        ? intentGraph.problemShape.wireName
        : (intentGraph.secondarySkills.isNotEmpty
              ? 'multi_skill'
              : 'single_skill');
    final modeDecision = resolvedExecutionPreparation.modeDecision;
    final intentTraceEvent = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'intent_graph_resolved',
      timestamp: DateTime.now(),
      runId: effectiveRunId,
      traceId: effectiveTraceId,
      visibility: TraceVisibility.internal,
      data: <String, dynamic>{
        ...intentGraph.toJson(),
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
    final answerBoundaryPolicy = _answerBoundaryResolver.resolve(
      intentGraph: intentGraph,
      contextAssembly: contextAssembly,
      retrievalPolicy: retrievalPolicy,
      queryTasks: intentGraph.queryTasks,
    );
    final templateVariables = _buildTemplateVariables(
      request: request,
      contextAssembly: contextAssembly,
      domainId: domainId,
      domainSkillInstruction: skillContext.instructionMarkdown,
      domainSkillName: skillContext.skillName,
      availableToolNames: effectiveToolNames,
      dialogueRoundScript: dialogueRoundScript,
      skillPersona: skillPersona,
      skillCatalog: skillCatalog,
      skillExecutionShell: effectiveExecutionShell,
      previousSlotState: previousSlotState,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
      intentGraph: intentGraph,
      answerBoundaryPolicy: answerBoundaryPolicy,
      previousIntentGraph: precomputedBootstrap?.previousIntentGraph,
      previousAnswerSummary: precomputedBootstrap?.previousAnswerSummary ?? '',
      continuityPolicy: contextContinuityPolicy,
      continuityOverrideSlots:
          precomputedBootstrap?.continuityOverrideSlots ??
          const <String, dynamic>{},
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
      return <String, dynamic>{'shortCircuitResponse': blocked};
    }
    final modelMessages = _messagesForCurrentTurn(
      request.messages,
      continuationActive: continuationActive,
    );
    final messages = modelMessages
        .map((m) => <String, dynamic>{'role': m.role, 'content': m.content})
        .toList(growable: true);
    final dataLayerBuffer = StringBuffer();
    dataLayerBuffer.writeln('<dialogue_state>');
    dataLayerBuffer.writeln(
      jsonEncode(_dialogueScriptForModel(dialogueRoundScript)),
    );
    dataLayerBuffer.writeln('</dialogue_state>');
    dataLayerBuffer.writeln();
    dataLayerBuffer.writeln('<context_slots>');
    dataLayerBuffer.writeln(jsonEncode(contextAssembly.contextEnvelope));
    dataLayerBuffer.writeln('</context_slots>');
    if (previousSlotState.slotValues.isNotEmpty ||
        previousSlotState.missingSlots.isNotEmpty) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<slot_state_snapshot>');
      dataLayerBuffer.writeln(jsonEncode(previousSlotState.toJson()));
      dataLayerBuffer.writeln('</slot_state_snapshot>');
    }
    if (previousDomainPolicyBundle != null) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<domain_policy_bundle>');
      dataLayerBuffer.writeln(jsonEncode(previousDomainPolicyBundle.toJson()));
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
                !t.contains('"contractId"') &&
                !t.contains('"decision"') &&
                !t.contains('assistant_turn') &&
                !t.contains('queryTasks') &&
                !t.contains('tool_call') &&
                !t.contains('<tool_call>') &&
                !t.contains('provider') &&
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
      dataLayerBuffer.writeln('原始问题：${ri.originalQuery}');
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('上一次回答：');
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
        component: 'local_phase_execution_owner',
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
    final shellMaxIterations = math.max(
      1,
      effectiveExecutionShell.maxIterations,
    );
    final rewriteMaxIterations = request.shouldSkipSearch
        ? 1
        : math.min(request.maxIterations, shellMaxIterations);
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
    List<Map<String, dynamic>> collectToolResults(
      ReactRuntimeResult runtimeResult,
    ) {
      return runtimeResult.traces
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

    SynthesisReadinessResult computeSynthesisReadiness(
      ReactRuntimeResult runtimeResult,
      List<Map<String, dynamic>> toolResults,
    ) {
      final hasToolResult = toolResults.isNotEmpty;
      final blockingDimensions = _blockingEvidenceDimensions(
        queryTasks: intentGraph.queryTasks,
        toolResults: toolResults,
      );
      final evidenceEvaluation = _baselineKernel.evaluateEvidence(
        ledger: _baselineKernel.buildEvidenceLedger(
          domainId: domainId,
          toolResults: _toolResultsForEvidenceLedger(toolResults),
          slotState: const SlotStateSnapshot(),
          retrievalPolicy: retrievalPolicy,
        ),
        evidenceRequired: answerBoundaryPolicy.evidenceRequired,
        authorityRequired: answerBoundaryPolicy.authorityRequired,
        freshnessHoursMax: answerBoundaryPolicy.freshnessHoursMax,
        blockingDimensions: blockingDimensions,
      );
      return _contextOrchestrator.checkSynthesisReadiness(
        query: request.messages.isNotEmpty ? request.messages.last.content : '',
        finalText: runtimeResult.finalText,
        hasToolResult: hasToolResult,
        problemClass: intentGraph.problemClassWireName,
        contextAssembly: contextAssembly,
        intentGraph: intentGraph,
        queryTasks: intentGraph.queryTasks,
        boundaryPolicy: answerBoundaryPolicy,
        evidenceEvaluation: evidenceEvaluation,
      );
    }

    final toolResults = collectToolResults(result);
    final synthesisReadiness = computeSynthesisReadiness(result, toolResults);
    var mergedResult = result;
    if (!synthesisReadiness.ready && synthesisReadiness.gapFillTask != null) {
      final gap = synthesisReadiness.gapFillTask!;
      final retryMessages = <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{
          'role': 'system',
          'content':
              '合成前置条件未满足：${synthesisReadiness.reason}。\n'
              '请按以下补齐任务重新规划并执行检索后再回答：${jsonEncode(gap.toJson())}',
        },
      ];
      final retryResult = await _runtime.run(
        messages: retryMessages,
        maxIterations: math.min(request.maxIterations, shellMaxIterations),
        goal: latestUserQuery,
        availableToolNamesOverride: effectiveToolNames,
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
      final retryGapFillEvent = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'synthesis readiness failed, trigger gap fill retry',
        timestamp: DateTime.now(),
        runId: effectiveRunId,
        traceId: effectiveTraceId,
        visibility: TraceVisibility.internal,
        data: <String, dynamic>{
          'reason': synthesisReadiness.reason,
          'gapFillTask': gap.toJson(),
        },
      );
      onTraceEvent?.call(retryGapFillEvent);
      mergedResult = ReactRuntimeResult(
        finalText: retryResult.finalText,
        traces: <AssistantTraceEvent>[
          ...result.traces,
          retryGapFillEvent,
          ...retryResult.traces,
        ],
      );
    }
    final finalToolResults = identical(mergedResult, result)
        ? toolResults
        : collectToolResults(mergedResult);
    final finalSynthesisReadiness = identical(mergedResult, result)
        ? synthesisReadiness
        : computeSynthesisReadiness(mergedResult, finalToolResults);
    return <String, dynamic>{
      'runId': effectiveRunId,
      'traceId': effectiveTraceId,
      'runStartAt': runStartAt,
      'sessionId': sessionId,
      'latestUserQuery': latestUserQuery,
      'domainId': domainId,
      'contextAssembly': contextAssembly,
      'intentGraph': intentGraph,
      'dialogueRoundScript': dialogueRoundScript,
      'domainCatalog': domainCatalog,
      'domainCatalogVersion': domainCatalogVersion,
      'executionShell': effectiveExecutionShell,
      'previousSlotState': previousSlotState,
      'previousDomainPolicyBundle': previousDomainPolicyBundle,
      'retrievalPolicy': retrievalPolicy,
      'answerBoundaryPolicy': answerBoundaryPolicy,
      'templateVariables': templateVariables,
      'messages': messages,
      'synthTemplateVersion': synthTemplateVersion,
      'fusionSynthTemplateVersion': fusionSynthTemplateVersion,
      'phaseOneResult': mergedResult,
      'synthesisReadiness': finalSynthesisReadiness,
      'supplementalTraces': supplementalTraces,
    };
  }

  Future<AgentExecutionState> _resolveExecutionOwnerState({
    required AssistantRunRequest request,
    required _PrecomputedBootstrap? precomputedBootstrap,
    required _PrecomputedUnderstand? precomputedUnderstand,
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
        state.intentGraph != null || precomputedExecutionPreparation != null;
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
          onTraceEvent: onTraceEvent == null
              ? null
              : (event) {
                  if (event is AssistantTraceEvent) {
                    onTraceEvent(event);
                  }
                },
        ),
      );
      state = bootstrapOutput.state ?? state;
    }
    final hasIntentGraph = state.intentGraph != null;
    final hasExecutionDomainId =
        state.executionPreparation?.domainId.trim().isNotEmpty == true;
    if (!hasIntentGraph || !hasExecutionDomainId) {
      final understandOutput = await _understandPhase.run(
        PhaseInput(
          request: request,
          state: state,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent == null
              ? null
              : (event) {
                  if (event is AssistantTraceEvent) {
                    onTraceEvent(event);
                  }
                },
        ),
      );
      state = understandOutput.state ?? state;
    }
    final hasQueryTasks =
        state.queryTasks.isNotEmpty ||
        (state.intentGraph?.queryTasks.isNotEmpty ?? false);
    final hasExecutionDetails =
        state.executionPreparation?.hasExecutionDetails ?? false;
    final hasExplicitPreparedExecution =
        precomputedExecutionPreparation?.hasExecutionDetails ?? false;
    if (!hasExplicitPreparedExecution &&
        (!hasExecutionDetails || !hasQueryTasks)) {
      final retrievalOutput = await _retrievalDesignPhase.run(
        PhaseInput(
          request: request,
          state: state,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent == null
              ? null
              : (event) {
                  if (event is AssistantTraceEvent) {
                    onTraceEvent(event);
                  }
                },
        ),
      );
      state = retrievalOutput.state ?? state;
    }
    if (state.queryTasks.isEmpty &&
        state.intentGraph?.queryTasks.isNotEmpty == true) {
      state = state.copyWith(queryTasks: state.intentGraph!.queryTasks);
    }
    return state;
  }

  AgentExecutionState _buildPrecomputedExecutionState({
    required AssistantRunRequest request,
    required _PrecomputedBootstrap? precomputedBootstrap,
    required _PrecomputedUnderstand? precomputedUnderstand,
    required AssistantExecutionPreparation? precomputedExecutionPreparation,
  }) {
    final precomputedIntentGraph = _recoverPrecomputedIntentGraph(
      request.contextScopeHint,
    );
    final precomputedQueryTasks = _recoverPrecomputedQueryTasks(
      request.contextScopeHint,
      fallbackIntentGraph: precomputedIntentGraph,
    );
    final effectiveIntentGraph =
        precomputedIntentGraph != null &&
            precomputedIntentGraph.queryTasks.isEmpty &&
            precomputedQueryTasks.isNotEmpty
        ? IntentGraph.fromJson(<String, dynamic>{
            ...precomputedIntentGraph.toJson(),
            'queryTasks': QueryTask.toJsonList(precomputedQueryTasks),
          })
        : precomputedIntentGraph;
    return AgentExecutionState(
      bootstrapContext: precomputedBootstrap == null
          ? null
          : AssistantBootstrapContext(
              sessionId: precomputedBootstrap.sessionId,
              latestUserQuery: precomputedBootstrap.latestUserQuery,
              historySummary: precomputedBootstrap.historySummary,
              recalledTexts: precomputedBootstrap.recalledTexts,
              previousIntentGraph: precomputedBootstrap.previousIntentGraph,
              previousAnswerSummary: precomputedBootstrap.previousAnswerSummary,
              previousUnderstandingSnapshot:
                  precomputedBootstrap.previousUnderstandingSnapshot,
              previousAnswerProcessing:
                  precomputedBootstrap.previousAnswerProcessing,
              historicalThinkingSnapshot:
                  precomputedBootstrap.historicalThinkingSnapshot,
              providerReasoningContinuation:
                  precomputedBootstrap.providerReasoningContinuation,
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
          _recoverPreviousRunArtifacts(request.contextScopeHint),
      intentGraph: effectiveIntentGraph,
      queryTasks: precomputedQueryTasks,
      dialogueRoundScript: precomputedUnderstand?.dialogueRoundScript,
      executionPreparation: precomputedExecutionPreparation,
    );
  }

  IntentGraph? _recoverPrecomputedIntentGraph(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw =
        (contextScopeHint['precomputedIntentGraph'] as Map?)
            ?.cast<String, dynamic>() ??
        (contextScopeHint['intentGraph'] as Map?)?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return IntentGraph.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  List<QueryTask> _recoverPrecomputedQueryTasks(
    Map<String, dynamic> contextScopeHint, {
    IntentGraph? fallbackIntentGraph,
  }) {
    final recovered = QueryTask.normalizeList(
      contextScopeHint['precomputedQueryTasks'],
    );
    if (recovered.isNotEmpty) return recovered;
    return fallbackIntentGraph?.queryTasks ?? const <QueryTask>[];
  }

  Future<_CompatibilityBootstrapState> _buildCompatibilityBootstrapState(
    AssistantRunRequest request,
  ) async {
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
    final continuityPolicy = _contextOrchestrator.buildContinuityPolicy(
      query: latestUserQuery,
      sessionHistory: priorSessionHistory,
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
        ? _sessionManager.summarizeRecent(sessionId)
        : '';
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
      contextScopeHint: request.contextScopeHint,
      continuityPolicy: continuityPolicy,
    );
    final forceRefreshCatalog =
        request.contextScopeHint['forceRefreshCatalog'] == true;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await _toolMetadataRegistry?.ensureLoaded();
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = await _domainRouter.availableDomains(
      forceRefresh: forceRefreshCatalog,
      contextScopeHint: request.contextScopeHint,
    );
    final domainCatalogVersion = await _domainRouter.catalogVersion(
      forceRefresh: false,
      contextScopeHint: request.contextScopeHint,
    );
    final fullSkillCatalog = await _domainRouter.buildSkillCatalogPrompt(
      contextScopeHint: request.contextScopeHint,
    );
    final allManifests = await _domainRouter.availableSkillManifests(
      contextScopeHint: request.contextScopeHint,
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
        recalledTexts: recalledTexts,
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
    required Map<String, dynamic> executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return SynthesisRunner(
      buildDraft: synthesizeDraftBridge,
      materialize: SynthesisMaterializer(this).materialize,
    ).synthesize(
      request,
      executionSnapshot: executionSnapshot,
      onTraceEvent: onTraceEvent,
    );
  }

  Future<SynthesisDraft> synthesizeDraftBridge(
    AssistantRunRequest request, {
    required Map<String, dynamic> executionSnapshot,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final runId = (executionSnapshot['runId'] as String?) ?? '';
    final traceId = (executionSnapshot['traceId'] as String?) ?? '';
    final sessionId =
        (executionSnapshot['sessionId'] as String?) ??
        (request.sessionId ?? 'default');
    final latestUserQuery =
        (executionSnapshot['latestUserQuery'] as String?)?.trim() ?? '';
    final domainId = (executionSnapshot['domainId'] as String?)?.trim() ?? '';
    final contextAssembly =
        executionSnapshot['contextAssembly'] as ContextAssemblyResult;
    final intentGraph = executionSnapshot['intentGraph'] as IntentGraph;
    final dialogueRoundScript =
        executionSnapshot['dialogueRoundScript'] as DialogueRoundScript;
    final domainCatalog =
        ((executionSnapshot['domainCatalog'] as List?) ?? const <dynamic>[])
            .map((item) => item.toString())
            .toList(growable: false);
    final domainCatalogVersion =
        (executionSnapshot['domainCatalogVersion'] as String?) ?? '';
    final effectiveExecutionShell =
        executionSnapshot['executionShell'] as SkillExecutionShell;
    final previousSlotState =
        executionSnapshot['previousSlotState'] as SlotStateSnapshot;
    final previousDomainPolicyBundle =
        executionSnapshot['previousDomainPolicyBundle'] as DomainPolicyBundle?;
    final retrievalPolicy =
        (executionSnapshot['retrievalPolicy'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final answerBoundaryPolicy =
        executionSnapshot['answerBoundaryPolicy'] is Map
        ? AnswerBoundaryPolicy.fromJson(
            (executionSnapshot['answerBoundaryPolicy'] as Map)
                .cast<String, dynamic>(),
          )
        : _answerBoundaryResolver.resolve(
            intentGraph: intentGraph,
            contextAssembly: contextAssembly,
            retrievalPolicy: retrievalPolicy,
            queryTasks: intentGraph.queryTasks,
          );
    final templateVariables =
        (executionSnapshot['templateVariables'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final templateContext = _sanitizeModelTemplateContext(
      request.contextScopeHint,
      continuationActive: _hasContinuationCarryoverContext(templateVariables),
      previousRunArtifacts: _recoverPreviousRunArtifacts(
        request.contextScopeHint,
      ),
    );
    final messages =
        ((executionSnapshot['messages'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false);
    final synthTemplateVersion =
        (executionSnapshot['synthTemplateVersion'] as String?) ?? '';
    final phaseOneResult =
        executionSnapshot['phaseOneResult'] as ReactRuntimeResult;
    final synthesisReadiness =
        executionSnapshot['synthesisReadiness'] as SynthesisReadinessResult;
    final supplementalTraces =
        ((executionSnapshot['supplementalTraces'] as List?) ??
                const <dynamic>[])
            .whereType<AssistantTraceEvent>()
            .toList(growable: false);

    final domainResultsForSynthesis = _buildDomainResultsForSynthesis(
      phaseOneResult.traces,
    );
    final synthesisQueryTasks = QueryTask.toJsonList(intentGraph.queryTasks);
    final bootstrapPayload =
        (request.contextScopeHint['precomputedBootstrap'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final phaseOneText = phaseOneResult.finalText;
    final phaseOneParsedJson =
        LlmResponseParser.parse(phaseOneText).json ?? const <String, dynamic>{};
    final phaseOneAnswerPayload = _parseAnswerPayload(
      rawFinalText: phaseOneText,
      traces: phaseOneResult.traces,
    );
    final previousUnderstandingSnapshotForSynthesis =
        (bootstrapPayload['previousUnderstandingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        (request.contextScopeHint['previousUnderstandingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final previousAnswerProcessingForSynthesis =
        (bootstrapPayload['previousAnswerProcessing'] as Map?)
            ?.cast<String, dynamic>() ??
        (request.contextScopeHint['previousAnswerProcessing'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final historicalThinkingSnapshotForSynthesis =
        (bootstrapPayload['historicalThinkingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        (request.contextScopeHint['historicalThinkingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final understandingSnapshotForSynthesis =
        (phaseOneParsedJson['understandingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        previousUnderstandingSnapshotForSynthesis;
    final historicalThinkingSnapshotFromPhaseOne =
        (phaseOneParsedJson['historicalThinkingSnapshot'] as Map?)
            ?.cast<String, dynamic>() ??
        historicalThinkingSnapshotForSynthesis;
    final sharedContextForSynthesis = <String, dynamic>{
      'contextEnvelope': contextAssembly.contextEnvelope,
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
    final currentRuntimeStateForSynthesis = <String, dynamic>{
      'dialogueState': <String, dynamic>{
        'domainId': domainId,
        'problemClass': intentGraph.problemClassWireName,
        'answerShape': intentGraph.answerShape.wireName,
        'synthesisReady': synthesisReadiness.ready,
        'synthesisReason': synthesisReadiness.reason,
      },
      'slotStateSnapshot': previousSlotState.toJson(),
      'contextSlots': _buildContextSlots(contextAssembly),
      'domainPolicyBundle':
          previousDomainPolicyBundle?.toJson() ?? const <String, dynamic>{},
      'skillExecutionShell': effectiveExecutionShell.toJson(),
      'queryTasks': synthesisQueryTasks,
    };
    final dialogueContinuityForSynthesis = <String, dynamic>{
      'historySummary':
          (bootstrapPayload['historySummary'] as String?)?.trim() ?? '',
      'previousIntentGraph':
          (bootstrapPayload['previousIntentGraph'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'previousUnderstandingSnapshot':
          previousUnderstandingSnapshotForSynthesis,
      'previousAnswerProcessing': previousAnswerProcessingForSynthesis,
      'previousSlotState': previousSlotState.toJson(),
      'previousAnswerSummary':
          (bootstrapPayload['previousAnswerSummary'] as String?)?.trim() ?? '',
      'historicalThinkingSnapshot': historicalThinkingSnapshotForSynthesis,
      'continuityOverrideSlots':
          (bootstrapPayload['continuityOverrideSlots'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    };
    final evidenceContextForSynthesis = <String, dynamic>{
      'intentGraph': intentGraph.toJson(),
      'queryTasks': synthesisQueryTasks,
      'domainResults': domainResultsForSynthesis,
      'webEvidencePacks':
          domainResultsForSynthesis['webEvidencePacks'] ?? const <dynamic>[],
      'contextSlots': _buildContextSlots(contextAssembly),
      'entityAnchors': intentGraph.entityAnchors,
    };
    final synthesisTemplateVars = <String, dynamic>{
      ...templateVariables,
      'userGoal': intentGraph.userGoal.trim().isNotEmpty
          ? intentGraph.userGoal.trim()
          : latestUserQuery,
      'understandingSnapshot': jsonEncode(understandingSnapshotForSynthesis),
      'sharedContext': jsonEncode(sharedContextForSynthesis),
      'currentRuntimeState': jsonEncode(currentRuntimeStateForSynthesis),
      'dialogueContinuity': jsonEncode(dialogueContinuityForSynthesis),
      'evidenceContext': jsonEncode(evidenceContextForSynthesis),
      'intentGraphJson': jsonEncode(intentGraph.toJson()),
      'queryTasksJson': jsonEncode(synthesisQueryTasks),
      'entityAnchors': intentGraph.entityAnchors,
      'queryTasks': synthesisQueryTasks,
      'answerShape': intentGraph.answerShape.wireName,
    };
    final synthesisInput = <Map<String, dynamic>>[
      ...messages,
      <String, dynamic>{
        'role': 'system',
        'content': '领域执行结果摘要：${phaseOneResult.finalText}',
      },
      <String, dynamic>{'role': 'user', 'content': latestUserQuery},
    ];
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
    final explicitPhaseOneSkillRunPlans = _buildExplicitSkillRunPlans(
      answerPayload: phaseOneAnswerPayload,
      latestUserQuery: latestUserQuery,
      fallbackProblemClass: intentGraph.problemClassWireName,
      primaryDomainId: domainId,
    );
    final derivedPhaseOneSkillRunPlans = explicitPhaseOneSkillRunPlans.isEmpty
        ? _buildDerivedSkillRunPlansFromIntent(
            intentGraph: intentGraph,
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
    final phaseOneContinuationCarryover = _hasContinuationCarryoverContext(
      synthesisTemplateVars,
    );
    final allowPhaseOneContractRepair =
        !phaseOneExecutionSignalsPresent || phaseOneContinuationCarryover;
    if (explicitPhaseOneSkillRunPlans.isEmpty &&
        synthesisReadiness.ready &&
        allowPhaseOneContractRepair &&
        (rawDirectAnswerDecision.reason == 'phase_one_not_structured' ||
            rawDirectAnswerDecision.reason == 'phase_one_not_contract_turn')) {
      final recoveredPhaseOneEnvelopeText =
          _recoverPhaseOneDirectAnswerEnvelopeText(
            rawText: phaseOneText,
            traces: phaseOneResult.traces,
            templateVariables: synthesisTemplateVars,
          );
      if (recoveredPhaseOneEnvelopeText.isNotEmpty) {
        effectivePhaseOneText = recoveredPhaseOneEnvelopeText;
        effectivePhaseOneAnswerPayload = _parseAnswerPayload(
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
        (((effectivePhaseOneAnswerPayload['userMarkdown'] as String?)
                    ?.trim()
                    .isNotEmpty ==
                true) ||
            ((((effectivePhaseOneAnswerPayload['result'] as Map?)?['text']
                        as String?)
                    ?.trim()
                    .isNotEmpty ==
                true)));
    final shouldAttemptPhaseOneModelRepair =
        explicitPhaseOneSkillRunPlans.isEmpty &&
        synthesisReadiness.ready &&
        !directAnswerDecision.shouldSkipSynthesis &&
        phaseOneHasRenderableContent &&
        allowPhaseOneContractRepair &&
        (directAnswerDecision.reason == 'phase_one_not_structured' ||
            directAnswerDecision.reason == 'phase_one_not_contract_turn');
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
        effectivePhaseOneAnswerPayload = _parseAnswerPayload(
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
    var templateVersionUsed = synthTemplateVersion;
    var phaseOneRoute = 'formal_synthesis';
    ReactRuntimeResult mergedResult;
    late final Map<String, dynamic> answerPayloadBeforeSubagent;
    late final List<SubagentPlan> skillRunPlans;
    final phaseOneSkillRunPlans = explicitPhaseOneSkillRunPlans.isNotEmpty
        ? explicitPhaseOneSkillRunPlans
        : (directAnswerDecision.shouldSkipSynthesis
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
    } else if (directAnswerDecision.shouldSkipSynthesis) {
      phaseOneRoute = 'phase_one_direct_answer';
      templateVersionUsed = PhaseOneDirectAnswerGate.directTemplateVersion;
      final shortcutTrace = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'phase one answer ready, skip synthesis',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
        visibility: TraceVisibility.system,
        data: <String, dynamic>{
          'stage': 'phase_one_direct_answer',
          'reason': directAnswerDecision.reason,
        },
      );
      onTraceEvent?.call(shortcutTrace);
      mergedResult = ReactRuntimeResult(
        finalText: directAnswerDecision.normalizedEnvelopeText,
        traces: <AssistantTraceEvent>[
          ...effectivePhaseOneTraces,
          shortcutTrace,
        ],
        degraded: effectivePhaseOneDegraded,
        failureCode: effectivePhaseOneFailureCode,
      );
      answerPayloadBeforeSubagent = _parseAnswerPayload(
        rawFinalText: mergedResult.finalText,
        traces: mergedResult.traces,
      );
      skillRunPlans = const <SubagentPlan>[];
    } else {
      ReactRuntimeResult synthesisResult;
      final canStreamSynthesis = synthesisReadiness.ready;
      if (canStreamSynthesis) {
        final streamedText = await _runtime.streamSynthesis(
          messages: synthesisInput,
          goal: latestUserQuery,
          onDelta: (_) {},
          templateContext: templateContext,
          templateVariables: synthesisTemplateVars,
          templateId: 'synthesizer.final_answer',
          templateVersion: synthTemplateVersion,
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent,
        );
        if (streamedText.trim().isNotEmpty) {
          final synthesisInputText = synthesisInput
              .map((item) => (item['content'] ?? '').toString())
              .join('\n');
          final outputTokens = _estimateTokenCount(streamedText);
          final inputTokens = _estimateTokenCount(synthesisInputText);
          final synthesisTrace = AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'llm request synthesis stream',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            visibility: TraceVisibility.system,
            data: <String, dynamic>{
              'stage': 'synthesis_stream',
              'estimatedTokens': outputTokens,
              'usageEntries': <Map<String, dynamic>>[
                <String, dynamic>{
                  'provider': 'synthesis_stream',
                  'modelId': 'streaming_final_answer',
                  'modelRef': 'streaming_final_answer',
                  'streaming': true,
                  'source': 'estimated',
                  'inputTokens': inputTokens,
                  'outputTokens': outputTokens,
                  'totalTokens': inputTokens + outputTokens,
                  'latencyMs': 0,
                },
              ],
            },
          );
          onTraceEvent?.call(synthesisTrace);
          synthesisResult = ReactRuntimeResult(
            finalText: streamedText,
            traces: <AssistantTraceEvent>[synthesisTrace],
          );
        } else {
          synthesisResult = await _runtime.run(
            messages: synthesisInput,
            maxIterations: 1,
            goal: latestUserQuery,
            availableToolNamesOverride: const <String>[],
            templateId: 'synthesizer.final_answer',
            templateVersion: synthTemplateVersion,
            templateContext: templateContext,
            templateVariables: synthesisTemplateVars,
            sessionId: sessionId,
            runId: runId,
            traceId: traceId,
            onTraceEvent: onTraceEvent,
            callOptions: const LlmCallOptions.synthesis(),
            onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
          );
        }
      } else {
        synthesisResult = await _runtime.run(
          messages: synthesisInput,
          maxIterations: 1,
          goal: latestUserQuery,
          availableToolNamesOverride: const <String>[],
          templateId: 'synthesizer.final_answer',
          templateVersion: synthTemplateVersion,
          templateContext: templateContext,
          templateVariables: synthesisTemplateVars,
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          onTraceEvent: onTraceEvent,
          callOptions: const LlmCallOptions.synthesis(),
          onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
        );
      }
      synthesisResult = await _repairInvalidSynthesisResult(
        currentResult: synthesisResult,
        synthesisInput: synthesisInput,
        latestUserQuery: latestUserQuery,
        templateContext: templateContext,
        templateVariables: synthesisTemplateVars,
        templateId: 'synthesizer.final_answer',
        templateVersion: synthTemplateVersion,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
      );
      mergedResult = ReactRuntimeResult(
        finalText: _ensureAssistantTurnEnvelopeText(synthesisResult.finalText),
        traces: <AssistantTraceEvent>[
          ...phaseOneResult.traces,
          ...synthesisResult.traces,
        ],
        degraded: synthesisResult.degraded,
        failureCode: synthesisResult.failureCode,
      );
      answerPayloadBeforeSubagent = _parseAnswerPayload(
        rawFinalText: mergedResult.finalText,
        traces: mergedResult.traces,
      );
      if (((answerPayloadBeforeSubagent['subagentPlan'] as List?)?.isEmpty ??
              true) &&
          ((effectivePhaseOneAnswerPayload['subagentPlan'] as List?)
                  ?.isNotEmpty ??
              false)) {
        answerPayloadBeforeSubagent['subagentPlan'] =
            effectivePhaseOneAnswerPayload['subagentPlan'];
      }
      skillRunPlans = _buildSkillRunPlans(
        intentGraph: intentGraph,
        answerPayload: answerPayloadBeforeSubagent,
        latestUserQuery: latestUserQuery,
        primaryDomainId: domainId,
      );
    }
    final phaseOneRoutingDiagnostics = <String, dynamic>{
      'route': phaseOneRoute,
      'synthesisReadinessReady': synthesisReadiness.ready,
      'synthesisReadinessReason': synthesisReadiness.reason,
      'rawDirectAnswerReason': rawDirectAnswerDecision.reason,
      'directAnswerReason': directAnswerDecision.reason,
      'directAnswerShouldSkipSynthesis':
          directAnswerDecision.shouldSkipSynthesis,
      'phaseOneRecoveryApplied': phaseOneRecoveryApplied,
      'phaseOneModelRepairApplied': phaseOneModelRepairApplied,
      'phaseOneModelRepairAttempted': phaseOneModelRepairAttempted,
      'phaseOneModelRepairProducedText': phaseOneModelRepairProducedText,
      'phaseOneModelRepairFailureCode': phaseOneModelRepairFailureCode,
      'phaseOneParsedContractTurn': effectivePhaseOneTurn != null,
      'phaseOneNextAction':
          effectivePhaseOneTurn?.nextActionType.wireName ??
          (((effectivePhaseOneAnswerPayload['decision'] as Map?)?['nextAction']
                      as String?)
                  ?.trim() ??
              ''),
      'phaseOneMessageKind':
          effectivePhaseOneTurn?.messageKindType.wireName ??
          (effectivePhaseOneAnswerPayload['messageKind'] as String?)?.trim() ??
          '',
      'phaseOnePhaseId':
          effectivePhaseOneTurn?.phaseIdType.wireName ??
          (effectivePhaseOneAnswerPayload['phaseId'] as String?)?.trim() ??
          '',
      'phaseOneActionCode':
          effectivePhaseOneTurn?.actionCodeType.wireName ??
          (effectivePhaseOneAnswerPayload['actionCode'] as String?)?.trim() ??
          '',
      'phaseOneReasonCode':
          effectivePhaseOneTurn?.reasonCodeType.wireName ??
          (effectivePhaseOneAnswerPayload['reasonCode'] as String?)?.trim() ??
          '',
      'phaseOneHasRenderableContent': phaseOneHasRenderableContent,
      'phaseOneExplicitSkillRunPlanCount': explicitPhaseOneSkillRunPlans.length,
      'phaseOneDerivedSkillRunPlanCount': derivedPhaseOneSkillRunPlans.length,
      'phaseOneSkillRunPlanCount': phaseOneSkillRunPlans.length,
      'phaseOneSkillRunPlanSource': phaseOneSkillRunPlans.isNotEmpty
          ? (explicitPhaseOneSkillRunPlans.isNotEmpty
                ? 'phase_one'
                : 'intent_secondary_skills')
          : 'none',
      'phaseOneExecutionSignalsPresent': phaseOneExecutionSignalsPresent,
      'phaseOneContinuationCarryover': phaseOneContinuationCarryover,
      'allowPhaseOneContractRepair': allowPhaseOneContractRepair,
      'phaseOneSkillRunPlans': phaseOneSkillRunPlans
          .map((item) => item.toJson())
          .toList(growable: false),
      'templateVersionUsed': templateVersionUsed,
    };
    final primaryToolResults = mergedResult.traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(
          (event) => <String, dynamic>{
            'message': event.message,
            'data': event.data ?? const <String, dynamic>{},
            'toolCallId': event.toolCallId ?? '',
          },
        )
        .toList(growable: false);
    final primaryUiReferences = _buildUiReferences(
      primaryToolResults,
      isRealtimeLike: _isRealtimeLikeRequest(
        fallbackProblemClass: intentGraph.problemClassWireName,
        answerPayload: answerPayloadBeforeSubagent,
      ),
    );
    final primarySkillRun = _buildPrimarySkillRun(
      intentGraph: intentGraph,
      domainId: domainId,
      answerPayload: answerPayloadBeforeSubagent,
      result: mergedResult,
      executionShell: effectiveExecutionShell,
      references: primaryUiReferences,
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
      ...subagentRuns.map(_skillRunFromLegacySubagentRun),
    ];
    final aggregationState = _buildAggregationState(
      intentGraph: intentGraph,
      skillRuns: skillRuns,
      answerPayload: answerPayloadBeforeSubagent,
    );
    if (subagentRuns.isNotEmpty) {
      final runsForModel = _subagentRunsForModel(subagentRuns);
      final fusionTemplateVars = <String, dynamic>{
        ...synthesisTemplateVars,
        'skillRuns': jsonEncode(
          skillRuns.map((item) => item.toJson()).toList(growable: false),
        ),
        'aggregationState': jsonEncode(aggregationState.toJson()),
        'subagentRuns': jsonEncode(runsForModel),
      };
      templateVersionUsed = synthTemplateVersion;
      final subagentSynthesisInput = <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{
          'role': 'system',
          'content': '各子任务执行结果：${jsonEncode(runsForModel)}',
        },
        <String, dynamic>{
          'role': 'system',
          'content':
              '请基于以上子任务结果整合为最终答复。'
              '必须输出标准 JSON 格式：含 decision（nextAction/confidence/reason）、userMarkdown（用户可见 Markdown）、'
              'result、evidence、reasoningBasis、selfCheck、diagnostics。'
              'userMarkdown 不得包含任何 JSON 字段名。',
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
        onTraceEvent: onTraceEvent,
        callOptions: const LlmCallOptions.synthesis(),
        onDelta: _buildThinkingDeltaForwarder(onTraceEvent, runId, traceId),
      );
      subagentSynthesis = await _repairInvalidSynthesisResult(
        currentResult: subagentSynthesis,
        synthesisInput: subagentSynthesisInput,
        latestUserQuery: latestUserQuery,
        templateContext: templateContext,
        templateVariables: fusionTemplateVars,
        templateId: 'synthesizer.final_answer',
        templateVersion: synthTemplateVersion,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
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
      );
    }
    final responseTraces = <AssistantTraceEvent>[
      ...supplementalTraces,
      ...mergedResult.traces,
    ];
    final finalResult = ReactRuntimeResult(
      finalText: mergedResult.finalText,
      traces: responseTraces,
      degraded: mergedResult.degraded,
      failureCode: mergedResult.failureCode,
    );
    final finalResultTurn = _tryParseAssistantTurnFromRawText(
      finalResult.finalText,
    );
    final finalResultProjection = finalResultTurn != null
        ? AssistantDisplayTextResolver.projectTurn(finalResultTurn)
        : null;
    final finalResponseHasRenderableContent =
        finalResultProjection?.hasRenderableContent ?? false;
    final finalResponseIsFallback =
        finalResultTurn?.messageKindType == AssistantMessageKind.fallback ||
        finalResultTurn?.nextActionType == AssistantNextAction.abort;
    return SynthesisDraft(
      runId: runId,
      traceId: traceId,
      sessionId: sessionId,
      contextAssembly: contextAssembly,
      synthesisReadiness: synthesisReadiness,
      finalResult: finalResult,
      intentGraph: intentGraph,
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
      understandingSnapshot: understandingSnapshotForSynthesis,
      historicalThinkingSnapshot: historicalThinkingSnapshotFromPhaseOne,
      previousDomainPolicyBundle: previousDomainPolicyBundle,
      profileUpdateProposal: _buildProfileUpdateProposal(request: request),
      responseDegraded:
          (!finalResponseHasRenderableContent || finalResponseIsFallback) &&
          (finalResult.degraded || _hasDegradedTrace(finalResult.traces)),
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
      intentGraph: draft.intentGraph,
      skillRuns: draft.skillRuns,
      aggregationState: draft.aggregationState,
      subagentPlan: draft.subagentPlan,
      subagentRuns: draft.subagentRuns,
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
      carriedHistoricalThinkingSnapshot: draft.historicalThinkingSnapshot,
      previousDomainPolicyBundle: draft.previousDomainPolicyBundle,
      onTraceEvent: onTraceEvent,
      runId: draft.runId,
      traceId: draft.traceId,
    );
  }

  Future<AssistantRunResponse> finalizeBridge(
    AssistantRunRequest request, {
    required Map<String, dynamic> executionSnapshot,
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
    required Map<String, dynamic> templateVariables,
    required String templateId,
    required String templateVersion,
    required String sessionId,
    required String runId,
    required String traceId,
    required void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final repairReason = _synthesisRepairReason(
      currentResult.finalText,
      templateVariables: templateVariables,
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
          'content': _buildSynthesisRepairInstruction(
            repairReason: repairReason,
            templateVariables: templateVariables,
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
      templateVariables: templateVariables,
    )) {
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
            'content':
                '结构化 JSON 仍然无效。现在不要输出 JSON，不要输出工具调用，不要输出 XML。'
                '请直接返回给用户看的最终 Markdown 答案正文；'
                '若证据不足，就明确说明不足并给出当前最稳妥的建议。'
                '${_buildSynthesisAnchorReminder(templateVariables)}',
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
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
  }) {
    return _synthesisRepairReason(
          rawText,
          templateVariables: templateVariables,
        ) !=
        null;
  }

  String? _synthesisRepairReason(
    String rawText, {
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
  }) {
    final trimmed = rawText.trim();
    if (trimmed.isEmpty || trimmed.contains('没有生成可展示结果')) {
      return 'empty_or_missing_display';
    }
    if (_containsXmlToolCallMarkup(trimmed)) return 'xml_tool_markup';
    final parseResult = LlmResponseParser.parse(trimmed);
    if (!parseResult.ok) return 'unparseable_envelope';
    final parsed = parseResult.json!;
    final turn = tryParseAssistantTurnOutput(parsed);
    final decision =
        turn?.decision.toJson() ??
        (parsed['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextAction = parseNextAction(
      (decision['nextAction'] as String?)?.trim() ?? '',
    );
    final projectedMarkdown = turn != null
        ? AssistantDisplayTextResolver.projectTurn(turn).markdown
        : AssistantDisplayTextResolver.normalizeMarkdown(
            parseResult.userMarkdown,
          );
    if (nextAction != AssistantNextAction.answer) {
      return 'next_action_not_answer';
    }
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
      _xmlToolCallTagRe.hasMatch(text);

  String _buildSynthesisRepairInstruction({
    required String repairReason,
    required Map<String, dynamic> templateVariables,
  }) {
    final base =
        '上一次输出未通过最终成答契约校验（$repairReason）。'
        '请只做契约修复：'
        '禁止新增工具调用，禁止输出 XML 标签或解释性前后缀，'
        '仅返回单个 assistant_turn JSON，且字段必须与最终可展示结果一致。';
    return '$base${_buildSynthesisAnchorReminder(templateVariables)}';
  }

  String _buildSynthesisAnchorReminder(Map<String, dynamic> templateVariables) {
    final anchors = _requiredTopicAnchors(templateVariables);
    if (anchors.isEmpty) {
      return '';
    }
    return ' 这轮最终回答必须显式保留至少一个主题锚点：${anchors.join('、')}。'
        ' `userMarkdown`、`result.text` 与 `result.summary` 都不得把这些主题词丢成同域泛化表述。';
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
        'continuation': _hasContinuationCarryoverContext(templateVariables),
      },
    );
    onTraceEvent?.call(repairTrace);
    final repaired = await _runtime.run(
      messages: <Map<String, dynamic>>[
        ...messages,
        <String, dynamic>{
          'role': 'system',
          'content': _buildPhaseOneDirectAnswerRepairInstruction(
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
              templateVariables: templateVariables,
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
          templateVariables: templateVariables,
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
      ),
      traces: <AssistantTraceEvent>[repairTrace, ...repaired.traces],
      degraded: repaired.degraded,
      failureCode: repaired.failureCode,
    );
  }

  String _buildPhaseOneDirectAnswerRepairInstruction({
    required String recoveredMarkdown,
    required String latestUserQuery,
    required Map<String, dynamic> templateVariables,
  }) {
    final carryoverReminder = _buildContinuationCarryoverReminder(
      templateVariables,
    );
    return '上一轮 phase-one 输出已经包含可直接展示的答案，但没有按最终契约返回。'
        '现在只做 direct-answer 契约修复：'
        '禁止新增工具调用，禁止扩搜，禁止 ask_user，禁止输出 XML 标签或解释性前后缀，'
        '必须返回单个 assistant_turn JSON，且 decision.nextAction=answer、'
        'messageKind=answer、phaseId/actionCode/reasonCode=answering/compose_answer/evidence_ready。'
        ' 当前用户问题是：$latestUserQuery。'
        '${_buildSynthesisAnchorReminder(templateVariables)}'
        ' 如果现成正文里把主题锚点或显式约束说省了，只允许补回当前问题里的主题词、对象名或限制条件，'
        '这属于契约修复，不算改换主题。'
        '$carryoverReminder'
        '请基于下面这段现成答案正文做最小修复，不要改换主题：\n'
        '<draft_answer>\n$recoveredMarkdown\n</draft_answer>';
  }

  bool _hasContinuationCarryoverContext(
    Map<String, dynamic> templateVariables,
  ) {
    final continuityMode = parseContextContinuityMode(
      (templateVariables['continuityMode'] as String?)?.trim() ?? '',
    );
    if (continuityMode == ContextContinuityMode.unknown ||
        continuityMode == ContextContinuityMode.freshTopic) {
      return false;
    }
    final previousAnswerSummary =
        (templateVariables['previousAnswerSummary'] as String?)?.trim() ?? '';
    if (previousAnswerSummary.isNotEmpty) {
      return true;
    }
    final previousIntentGraphJson =
        (templateVariables['previousIntentGraphJson'] as String?)?.trim() ?? '';
    return previousIntentGraphJson.isNotEmpty;
  }

  String _buildContinuationCarryoverReminder(
    Map<String, dynamic> templateVariables,
  ) {
    if (!_hasContinuationCarryoverContext(templateVariables)) {
      return '';
    }
    final previousAnswerSummary =
        (templateVariables['previousAnswerSummary'] as String?)?.trim() ?? '';
    final continuityMode =
        (templateVariables['continuityMode'] as String?)?.trim() ?? '';
    final previousIntentGraphJson =
        (templateVariables['previousIntentGraphJson'] as String?)?.trim() ?? '';
    final overrideSlots = jsonEncode(
      (templateVariables['continuityOverrideSlots'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
    return ' 这是连续追问场景（continuityMode=$continuityMode）。'
        '最终回答必须把承接对象重新说全，不能只保留脱离上下文的指代。'
        '${previousAnswerSummary.isNotEmpty ? ' 上一轮回答摘要：$previousAnswerSummary。' : ''}'
        '${previousIntentGraphJson.isNotEmpty ? ' 上一轮意图骨架：$previousIntentGraphJson。' : ''}'
        '${overrideSlots != '{}' ? ' 本轮显式覆盖条件：$overrideSlots。' : ''}';
  }

  bool _missingRequiredTopicAnchor(
    String projectedMarkdown, {
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
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

  List<String> _requiredTopicAnchors(Map<String, dynamic> templateVariables) {
    final seen = <String>{};
    final anchors = <String>[];

    void collect(Iterable<dynamic> values) {
      for (final raw in values) {
        final value = raw.toString().trim();
        if (!_isMeaningfulTopicAnchor(value) || !seen.add(value)) {
          continue;
        }
        anchors.add(value);
      }
    }

    final directAnchors = templateVariables['entityAnchors'];
    if (directAnchors is Iterable) {
      collect(directAnchors);
    } else if (directAnchors is String && directAnchors.trim().isNotEmpty) {
      collect(directAnchors.split(','));
    }

    final queryTasks = templateVariables['queryTasks'];
    if (queryTasks is Iterable) {
      for (final item in queryTasks) {
        if (item is Map) {
          final taskAnchors = item['entityAnchors'];
          if (taskAnchors is Iterable) {
            collect(taskAnchors);
          }
        }
      }
    }

    return anchors;
  }

  bool _isMeaningfulTopicAnchor(String value) {
    final normalized = value.trim();
    if (normalized.length >= 2 &&
        RegExp(r'[\u4e00-\u9fff]').hasMatch(normalized)) {
      return true;
    }
    return normalized.length >= 3 &&
        RegExp(r'[A-Za-z0-9]').hasMatch(normalized);
  }

  String _normalizeTopicAnchorText(String raw) {
    return raw.toLowerCase().replaceAll(RegExp(r'\s+'), '');
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
    return jsonEncode(
      AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.abort,
        ),
        messageKind: AssistantMessageKind.fallback,
        userMarkdown: '',
        result: AssistantTurnResult(
          text: '模型输出无效，已停止本轮回答。',
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

  String _buildRecoveredAssistantTurnEnvelopeText({
    required String recoveredMarkdown,
    required String failureCode,
  }) {
    final plainText = _stripMarkdownForPlainText(recoveredMarkdown);
    final normalizedPlain = plainText.isNotEmpty
        ? plainText
        : recoveredMarkdown;
    return jsonEncode(
      AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.answer,
        ),
        messageKind: AssistantMessageKind.answer,
        userMarkdown: recoveredMarkdown,
        result: AssistantTurnResult(
          text: normalizedPlain,
          interpretation: 'recovered_from_$failureCode',
        ),
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
        slotState: const SlotStateSnapshot(),
        askUser: const AssistantTurnAskUser(),
      ).toEnvelopeMap(),
    );
  }

  String _recoverPhaseOneDirectAnswerEnvelopeText({
    required String rawText,
    required List<AssistantTraceEvent> traces,
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
  }) {
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
          templateVariables: templateVariables,
        )) {
      return '';
    }
    return _buildRecoveredAssistantTurnEnvelopeText(
      recoveredMarkdown: recoveredMarkdown,
      failureCode: 'phase_one_answer_recovery',
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
          !_looksLikeRecoverableAnswerText(normalized)) {
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
    if (!_looksLikeRecoverableAnswerText(sanitized)) {
      return '';
    }
    return sanitized;
  }

  String _recoverCompatDisplayMarkdown(Map<String, dynamic>? payload) {
    if (payload == null || payload.isEmpty) return '';
    final decision =
        (payload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextAction = parseNextAction(
      (decision['nextAction'] as String?)?.trim() ?? '',
    );
    final messageKind = parseMessageKind(
      (payload['messageKind'] as String?)?.trim() ?? '',
    );
    final toolCalls =
        (payload['toolCalls'] as List?)?.whereType<Object>().toList() ??
        const <Object>[];
    final result =
        (payload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final candidates = <String>[
      AssistantDisplayTextResolver.normalizeMarkdown(
        (payload['userMarkdown'] as String?) ?? '',
      ),
      AssistantDisplayTextResolver.normalizeMarkdown(
        (result['text'] as String?) ?? '',
      ),
      AssistantDisplayTextResolver.normalizeMarkdown(
        (result['summary'] as String?) ?? '',
      ),
    ].where((item) => item.trim().isNotEmpty).toList(growable: false);
    if (candidates.isEmpty) return '';
    final candidate = candidates.first;
    final answerLike =
        nextAction == AssistantNextAction.answer ||
        messageKind == AssistantMessageKind.answer ||
        ((payload['phaseId'] as String?)?.trim() ?? '') == 'answering';
    final staleProgressAnswer =
        toolCalls.isEmpty &&
        messageKind == AssistantMessageKind.progress &&
        candidate.isNotEmpty &&
        ((((payload['phaseId'] as String?)?.trim() ?? '') == 'answering') ||
            ((result['text'] as String?)?.trim().isNotEmpty == true));
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
    return _looksLikeRecoverableAnswerText(candidate) ? candidate : '';
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
      final toolCalls = data['toolCalls'] as List? ?? const <dynamic>[];
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
      final stage =
          (trace.data?['stage'] as String?)?.trim().toLowerCase() ?? '';
      if (stage.contains('tool') ||
          stage.contains('search') ||
          stage.contains('retrieval') ||
          stage.contains('subagent')) {
        return true;
      }
    }
    return false;
  }

  bool _looksLikeRecoverableAnswerText(String text) {
    final normalized = text.trim();
    if (normalized.isEmpty) return false;
    if (normalized.length >= 24) return true;
    final hasStructuredMarkdown =
        normalized.contains('\n') ||
        normalized.contains('- ') ||
        normalized.contains('* ') ||
        normalized.contains('1.');
    if (hasStructuredMarkdown) return true;
    final sentenceLikeHits = RegExp(
      r'[。！？；;.!?]',
    ).allMatches(normalized).length;
    if (sentenceLikeHits >= 2) return true;
    final hasSentenceEnding = RegExp(r'[。！？.!?]').hasMatch(normalized);
    if (hasSentenceEnding && normalized.length >= 8) {
      return true;
    }
    return normalized.length >= 12 &&
        RegExp(r'[\u4e00-\u9fffA-Za-z0-9]').hasMatch(normalized);
  }

  Future<List<Map<String, dynamic>>> _executeSubagentPlans({
    required Map<String, dynamic> answerPayload,
    required AssistantRunRequest request,
    required String sessionId,
    required String runId,
    required String traceId,
    required Map<String, dynamic> templateContext,
    required Map<String, dynamic> templateVariables,
    required void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final rawPlans =
        (answerPayload['subagentPlan'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final plans = rawPlans
        .map((item) => SubagentPlan.fromJson(item.cast<String, dynamic>()))
        .where((item) => item.goal.trim().isNotEmpty)
        .toList(growable: false);
    if (plans.isEmpty) return const <Map<String, dynamic>>[];
    // Build a single subagent execution closure for parallel dispatch
    Future<Map<String, dynamic>> runSingleSubagent(
      int index,
      SubagentPlan plan,
    ) async {
      final subagentId = plan.subagentId.isNotEmpty
          ? plan.subagentId
          : 'subagent_${index + 1}';
      final goal = plan.goal;
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
              userQuery: goal,
              preferExplicitDomain: true,
            );
        effectiveSubagentShell = _executionPreparationResolver
            .resolveExecutionShellForProblemClass(
              domainId: subagentDomainId,
              baseShell: subagentSkillContext.executionShell,
              rawProblemClass: plan.problemClass,
              mode: planMode,
              secondarySkills: const <String>[],
              queryText: goal,
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
            'goal': goal,
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
                const <String, dynamic>{
                  'role': 'system',
                  'content': '你是后台子代理。目标是完成分配任务并给出结构化结论，禁止输出与任务无关内容。',
                },
                <String, dynamic>{'role': 'user', 'content': goal},
              ],
              maxIterations: maxIterations,
              goal: goal,
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
        final childAnswerPayload = _parseAnswerPayload(
          rawFinalText: subagentResult.finalText,
          traces: subagentResult.traces,
        );
        final childToolResults = subagentResult.traces
            .where((event) => event.type == AssistantTraceEventType.toolResult)
            .map(
              (event) => <String, dynamic>{
                'message': event.message,
                'data': event.data ?? const <String, dynamic>{},
                'toolCallId': event.toolCallId ?? '',
              },
            )
            .toList(growable: false);
        final childReferences = _buildUiReferences(
          childToolResults,
          isRealtimeLike: _isRealtimeLikeProblemClass(plan.problemClass),
        );
        final subagentUsage = _buildUsageStatsFromTraces(
          traces: subagentResult.traces,
          fallbackInputText: goal,
          fallbackOutputText: subagentResult.finalText,
        );
        final run = <String, dynamic>{
          'version': 'subagent_result',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'success',
          'goal': goal,
          'mode': planMode,
          'problemClass': effectiveSubagentShell.problemClass,
          'shell': effectiveSubagentShell.toJson(),
          'stopPolicy': plan.stopPolicy,
          'searchIntensity': plan.searchIntensity,
          'providerPolicy': plan.providerPolicy,
          'freshnessHoursMax': plan.freshnessHoursMax,
          'answerThreshold': plan.answerThreshold,
          'summary': subagentResult.finalText,
          'userMarkdown': (childAnswerPayload['userMarkdown'] as String?) ?? '',
          'result':
              (childAnswerPayload['result'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          'answerReady':
              ((childAnswerPayload['userMarkdown'] as String?)
                      ?.trim()
                      .isNotEmpty ??
                  false) ||
              childAnswerPayload['result'] is Map,
          'references': childReferences,
          'toolCallCount': subagentResult.traces
              .where((event) => event.type == AssistantTraceEventType.toolStart)
              .length,
          'modelCallCount': subagentUsage['modelCallCount'],
          'totalTokens': subagentUsage['totalTokens'],
          'maxTokensPerCall': subagentUsage['maxTokensPerCall'],
          'tokenSource': subagentUsage['tokenSource'],
          'tokenSampleCount': subagentUsage['tokenSampleCount'],
        };
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentResult,
            message: 'subagent finished: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run,
          ),
        );
        return run;
      } on TimeoutException {
        final run = <String, dynamic>{
          'version': 'subagent_result',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'timeout',
          'goal': goal,
          'mode': planMode,
          'problemClass': effectiveSubagentShell.problemClass,
          'shell': effectiveSubagentShell.toJson(),
          'stopPolicy': plan.stopPolicy,
          'searchIntensity': plan.searchIntensity,
          'providerPolicy': plan.providerPolicy,
          'freshnessHoursMax': plan.freshnessHoursMax,
          'answerThreshold': plan.answerThreshold,
          'summary': '',
          'references': const <Map<String, dynamic>>[],
          'errorClass': 'timeout',
        };
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentError,
            message: 'subagent timeout: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run,
          ),
        );
        return run;
      } catch (error) {
        final run = <String, dynamic>{
          'version': 'subagent_result',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'failed',
          'goal': goal,
          'mode': planMode,
          'problemClass': effectiveSubagentShell.problemClass,
          'shell': effectiveSubagentShell.toJson(),
          'stopPolicy': plan.stopPolicy,
          'searchIntensity': plan.searchIntensity,
          'providerPolicy': plan.providerPolicy,
          'freshnessHoursMax': plan.freshnessHoursMax,
          'answerThreshold': plan.answerThreshold,
          'summary': '',
          'references': const <Map<String, dynamic>>[],
          'errorClass': 'execution_failed',
          'errorMessage': error.toString(),
        };
        onTraceEvent?.call(
          AssistantTraceEvent(
            type: AssistantTraceEventType.subagentError,
            message: 'subagent failed: $subagentId',
            timestamp: DateTime.now(),
            runId: runId,
            traceId: traceId,
            data: run,
          ),
        );
        return run;
      }
    }

    // Parallel dispatch (P2-1): run all subagents concurrently
    final futures = <Future<Map<String, dynamic>>>[];
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

  int _nonNegativeInt(Object? value, {required int fallback}) {
    if (value is int && value >= 0) return value;
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed >= 0) return parsed;
    return fallback;
  }

  double _normalizedThreshold(Object? value, {required double fallback}) {
    final parsed =
        (value as num?)?.toDouble() ??
        double.tryParse(value?.toString() ?? '') ??
        fallback;
    if (parsed.isNaN) return fallback;
    if (parsed < 0) return 0.0;
    if (parsed > 1) return 1.0;
    return parsed;
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

  List<PreferenceFact> _buildSessionPreferenceFacts({
    required AssistantRunRequest request,
    required Map<String, dynamic> answerPayload,
    required List<SkillRun> skillRuns,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final now = DateTime.now().toIso8601String();
    final facts = <PreferenceFact>[
      PreferenceFact(
        factId: 'session_problem_class_$now',
        scope: 'session',
        key: 'problemClass',
        value: skillRuns.isNotEmpty ? skillRuns.first.problemClass : '',
        source: 'local_phase_execution_owner',
        createdAt: now,
      ),
      PreferenceFact(
        factId: 'session_reference_count_$now',
        scope: 'session',
        key: 'referenceCount',
        value: uiReferences.length.toString(),
        source: 'local_phase_execution_owner',
        createdAt: now,
      ),
    ];
    final feedbackHint = (request.contextScopeHint['preferenceFeedback'] ?? '')
        .toString()
        .trim();
    if (feedbackHint.isNotEmpty) {
      facts.add(
        PreferenceFact(
          factId: 'session_feedback_$now',
          scope: 'session',
          key: 'feedbackHint',
          value: feedbackHint,
          source: 'context_scope_hint',
          createdAt: now,
        ),
      );
    }
    final followupPrompt =
        (answerPayload['followupPrompt'] as String?)?.trim() ?? '';
    if (followupPrompt.isNotEmpty) {
      facts.add(
        PreferenceFact(
          factId: 'session_followup_$now',
          scope: 'session',
          key: 'followupPrompt',
          value: followupPrompt,
          source: 'answer_payload',
          createdAt: now,
        ),
      );
    }
    return facts.where((item) => item.value.isNotEmpty).toList(growable: false);
  }

  List<PreferenceFact> _buildLongTermPreferenceFacts({
    required AssistantRunRequest request,
    required Map<String, dynamic> answerPayload,
    required List<PreferenceFact> sessionFacts,
  }) {
    final seedFacts =
        (request.contextScopeHint['longTermPreferenceFacts'] as List?)
            ?.whereType<Map>()
            .map(
              (item) => PreferenceFact.fromJson(item.cast<String, dynamic>()),
            )
            .toList(growable: false) ??
        const <PreferenceFact>[];
    final emergedTags =
        ((answerPayload['diagnostics'] as Map?)?['emergedTags'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (emergedTags.isEmpty) return seedFacts;
    final now = DateTime.now().toIso8601String();
    return <PreferenceFact>[
          ...seedFacts,
          ...emergedTags.map(
            (item) => PreferenceFact(
              factId: 'long_term_${item['tag'] ?? item['key'] ?? now}_$now',
              scope: 'long_term',
              key: (item['tag'] ?? item['key'] ?? '').toString(),
              value: (item['value'] ?? item['label'] ?? '').toString(),
              source: 'diagnostics.emergedTags',
              createdAt: now,
            ),
          ),
          ...sessionFacts
              .where((item) => item.key == 'feedbackHint')
              .map(
                (item) => PreferenceFact(
                  factId: 'long_term_feedback_${item.factId}',
                  scope: 'long_term',
                  key: item.key,
                  value: item.value,
                  source: item.source,
                  createdAt: item.createdAt,
                ),
              ),
        ]
        .where((item) => item.key.isNotEmpty && item.value.isNotEmpty)
        .toList(growable: false);
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
        .map((task) => '- ${_humanizeFillTask(task)}')
        .join('\n');
    final finalText =
        '为保证回答准确，我还缺少少量关键信息。\n'
        '请先补充：\n$nextAction';
    final traceEnd = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleEnd,
      message: 'agent loop finished (blocked_precondition)',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      visibility: TraceVisibility.system,
      data: const <String, dynamic>{'lifecycleOutcome': 'blocked'},
    );
    return AssistantRunResponse(
      finalText: finalText,
      traces: <AssistantTraceEvent>[traceStart, traceEnd],
      runId: runId,
      traceId: traceId,
      degraded: true,
      errorCode: 'missing_context',
      structuredResponse: <String, dynamic>{
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
          'gapFillTask': null,
        },
        'contextSlots': _buildContextSlots(contextAssembly),
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
        'experimentBucket': _resolveExperimentBucket(
          const <String, dynamic>{},
          'control',
        ),
      },
    );
  }

  String _humanizeFillTask(ContextFillTask task) {
    switch (task.targetSlot) {
      case ContextTargetSlot.gpsOrCityLocation:
        return '你想查询的城市或当前位置（例如：深圳）';
      case ContextTargetSlot.longtermMemory:
        return '相关历史背景（例如：你上次提到的时间点或事件）';
      case ContextTargetSlot.realtimeEvidence:
        return '实时检索依据（我需要先查到最新信息）';
      case ContextTargetSlot.answerSufficiency:
        return '关键补充信息（当前证据不足以直接下结论）';
      default:
        return task.reason.trim().isEmpty
            ? task.targetSlot.wireName
            : task.reason;
    }
  }

  ProfileUpdateProposal? _buildProfileUpdateProposal({
    required AssistantRunRequest request,
  }) {
    final proposalRaw = request.contextScopeHint['profileUpdateProposal'];
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
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required AggregationState aggregationState,
    required List<SubagentPlan> subagentPlan,
    required List<Map<String, dynamic>> subagentRuns,
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
    Map<String, dynamic> carriedHistoricalThinkingSnapshot =
        const <String, dynamic>{},
    Map<String, dynamic> phaseOneRoutingDiagnostics = const <String, dynamic>{},
    DomainPolicyBundle? previousDomainPolicyBundle,
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  }) async {
    final parsedAnswerPayload = _parseAnswerPayload(
      rawFinalText: result.finalText,
      traces: result.traces,
    );
    final toolResults = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(
          (event) => <String, dynamic>{
            'message': event.message,
            'data': event.data ?? const <String, dynamic>{},
            'toolCallId': event.toolCallId ?? '',
          },
        )
        .toList(growable: false);
    final toolErrors = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolError)
        .map(
          (event) => <String, dynamic>{
            'message': event.message,
            'data': event.data ?? const <String, dynamic>{},
            'toolCallId': event.toolCallId ?? '',
          },
        )
        .toList(growable: false);
    final profileSnapshot = request.userProfileSnapshot;
    final basicIdentity =
        (profileSnapshot['basicIdentity'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final ipResidenceProfile =
        (profileSnapshot['ipResidenceProfile'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content
        : '';
    final problemClass = skillExecutionShell.problemClass.trim().isNotEmpty
        ? skillExecutionShell.problemClass.trim()
        : (intentGraph.problemClassWireName.isNotEmpty
              ? intentGraph.problemClassWireName
              : ProblemClass.general.wireName);
    final slotSchema = _conversationStateKernel.defaultSlotSchema(
      domainId: dialogueRoundScript.domainId,
      problemClass: problemClass,
      dialogueRoundScript: dialogueRoundScript,
    );
    final initialStateDecision = _conversationStateKernel.evaluate(
      domainId: dialogueRoundScript.domainId,
      problemClass: problemClass,
      intentGraph: intentGraph,
      queryTasks: intentGraph.queryTasks,
      dialogueRoundScript: dialogueRoundScript,
      aggregationState: aggregationState,
      answerPayload: parsedAnswerPayload,
      previousSlotState: previousSlotState,
      evidenceEvaluation: const EvidenceEvaluationResult(),
      slotSchema: slotSchema,
    );
    final blockingDimensions = _blockingEvidenceDimensions(
      queryTasks: intentGraph.queryTasks,
      toolResults: toolResults,
    );
    final provisionalLedger = _baselineKernel.buildEvidenceLedger(
      domainId: dialogueRoundScript.domainId,
      toolResults: _toolResultsForEvidenceLedger(toolResults),
      slotState: initialStateDecision.slotState,
      retrievalPolicy: retrievalPolicy,
    );
    final provisionalEvidenceEvaluation = _baselineKernel.evaluateEvidence(
      ledger: provisionalLedger,
      evidenceRequired: answerBoundaryPolicy.evidenceRequired,
      authorityRequired: answerBoundaryPolicy.authorityRequired,
      freshnessHoursMax: answerBoundaryPolicy.freshnessHoursMax,
      blockingDimensions: blockingDimensions,
    );
    var stateDecision = _conversationStateKernel.evaluate(
      domainId: dialogueRoundScript.domainId,
      problemClass: problemClass,
      intentGraph: intentGraph,
      queryTasks: intentGraph.queryTasks,
      dialogueRoundScript: dialogueRoundScript,
      aggregationState: aggregationState,
      answerPayload: parsedAnswerPayload,
      previousSlotState: previousSlotState,
      evidenceEvaluation: provisionalEvidenceEvaluation,
      slotSchema: slotSchema,
    );
    final evidenceLedger = _baselineKernel.buildEvidenceLedger(
      domainId: dialogueRoundScript.domainId,
      toolResults: _toolResultsForEvidenceLedger(toolResults),
      slotState: stateDecision.slotState,
      retrievalPolicy: retrievalPolicy,
    );
    final evidenceEvaluation = _baselineKernel.evaluateEvidence(
      ledger: evidenceLedger,
      evidenceRequired: answerBoundaryPolicy.evidenceRequired,
      authorityRequired: answerBoundaryPolicy.authorityRequired,
      freshnessHoursMax: answerBoundaryPolicy.freshnessHoursMax,
      blockingDimensions: blockingDimensions,
    );
    stateDecision = _conversationStateKernel.evaluate(
      domainId: dialogueRoundScript.domainId,
      problemClass: problemClass,
      intentGraph: intentGraph,
      queryTasks: intentGraph.queryTasks,
      dialogueRoundScript: dialogueRoundScript,
      aggregationState: aggregationState,
      answerPayload: parsedAnswerPayload,
      previousSlotState: previousSlotState,
      evidenceEvaluation: evidenceEvaluation,
      slotSchema: slotSchema,
    );
    final effectiveSynthesisReadiness = _contextOrchestrator
        .checkSynthesisReadiness(
          query: latestUserQuery,
          finalText: result.finalText,
          hasToolResult: toolResults.isNotEmpty,
          problemClass: problemClass,
          contextAssembly: contextAssembly,
          intentGraph: intentGraph,
          queryTasks: intentGraph.queryTasks,
          boundaryPolicy: answerBoundaryPolicy,
          evidenceEvaluation: evidenceEvaluation,
        );
    final groundedSlotState = _contextOrchestrator.bindEvidenceToSlots(
      slotState: stateDecision.slotState,
      evidenceLedger: evidenceLedger,
    );
    final effectiveStateDecision = ConversationStateDecision(
      nextAction: stateDecision.nextActionType,
      finalAnswerMode: stateDecision.finalAnswerModeType,
      answerEligibility: stateDecision.answerEligibilityType,
      slotState: groundedSlotState,
      missingCriticalSlots: stateDecision.missingCriticalSlots,
      askUser: stateDecision.askUser,
      qualityGates: stateDecision.qualityGates,
      finalAnswerReady: stateDecision.finalAnswerReady,
    );
    final answerPayload = _applyConversationStateDecision(
      parsedAnswerPayload,
      effectiveStateDecision,
      evidenceEvaluation: evidenceEvaluation,
      synthesisReadiness: effectiveSynthesisReadiness,
    );
    final webEvidencePacks = _extractWebEvidencePacks(toolResults);
    final evidenceGatePassed =
        evidenceEvaluation.passed ||
        evidenceEvaluation.status == EvidenceStatus.bounded ||
        !evidenceEvaluation.evidenceRequired;
    final modelSelfScore = _asDouble(
      ((answerPayload['modelSelfScore'] as Map?)?['score']),
    );
    final parseStatus =
        (answerPayload['parseStatus'] as String?) ?? 'fallback_text';
    final decisionParseSuccess = parseStatus == 'assistant_turn_parsed';
    final heuristicFallbackUsed = _usedHeuristicFallback(result.traces);
    final messageKind = _resolveMessageKind(
      answerPayload: answerPayload,
      resultText: result.finalText,
    );
    final learningSatisfaction = modelSelfScore >= 85
        ? 'high'
        : (modelSelfScore >= 70 ? 'medium' : 'low');
    final isRealtimeLike = _isRealtimeLikeRequest(
      fallbackProblemClass: problemClass,
      answerPayload: answerPayload,
    );
    final uiReferences = evidenceLedger.isNotEmpty
        ? _buildUiReferencesFromLedger(
            evidenceLedger,
            toolResults: toolResults,
            domainId: dialogueRoundScript.domainId,
            isRealtimeLike: isRealtimeLike,
          )
        : _buildUiReferences(toolResults, isRealtimeLike: isRealtimeLike);
    final understandingSnapshot = _buildUnderstandingSnapshot(
      raw:
          (answerPayload['understandingSnapshot'] as Map?)
              ?.cast<String, dynamic>() ??
          carriedUnderstandingSnapshot,
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
    );
    final answerProcessingSnapshot = _buildAnswerProcessingSnapshot(
      raw:
          (answerPayload['answerProcessing'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      synthesisReadiness: effectiveSynthesisReadiness,
      stateDecision: effectiveStateDecision,
      evidenceEvaluation: evidenceEvaluation,
      evidenceLedger: evidenceLedger,
      answerPayload: answerPayload,
    );
    final historicalThinkingSnapshot = _buildHistoricalThinkingSnapshot(
      raw:
          (answerPayload['historicalThinkingSnapshot'] as Map?)
              ?.cast<String, dynamic>() ??
          carriedHistoricalThinkingSnapshot,
      understandingSnapshot: understandingSnapshot,
    );
    final directMarkdown = _extractUiMarkdown(answerPayload, result.finalText);
    final preferredMarkdown = directMarkdown.trim();
    final hasDirectMarkdown = preferredMarkdown.isNotEmpty;
    final answerEligible =
        effectiveStateDecision.nextActionType == AssistantNextAction.answer &&
        hasDirectMarkdown;
    final normalizedMarkdown = preferredMarkdown;
    final evidenceLinks = _buildInlineEvidenceLinks(
      answerPayload: answerPayload,
      uiReferences: uiReferences,
      evidenceLedger: evidenceLedger,
    );
    final answerEvidenceBindings = evidenceLinks
        .map(AnswerEvidenceBinding.fromJson)
        .toList(growable: false);
    final linkedMarkdown = _applyInlineEvidenceLinks(
      normalizedMarkdown,
      evidenceLinks,
    );
    final retrievalProcessingSnapshot = _buildRetrievalProcessingSnapshot(
      uiReferences: uiReferences,
      toolResults: toolResults,
      understandingSnapshot: understandingSnapshot,
      synthesisReadiness: effectiveSynthesisReadiness,
      finalAnswerReady: answerEligible,
    );
    final displayPlainText = _resolveDisplayPlainText(
      answerPayload: answerPayload,
      displayMarkdown: linkedMarkdown,
      machineEnvelope: result.finalText,
    );
    final renderMode = linkedMarkdown.trim().isNotEmpty
        ? 'md_json_dual'
        : 'fallback_text';
    final renderFallback = renderMode == 'fallback_text';
    final hasAnsweringTrace = result.traces.any(
      (trace) =>
          trace.type == AssistantTraceEventType.answerDelta ||
          trace.type == AssistantTraceEventType.streamDelta,
    );
    final synthesizedAnsweringTraces = <AssistantTraceEvent>[];
    if (linkedMarkdown.isNotEmpty && !hasAnsweringTrace) {
      for (final chunk in _chunkMarkdownForStreaming(linkedMarkdown)) {
        synthesizedAnsweringTraces.add(
          AssistantTraceEvent(
            type: AssistantTraceEventType.answerDelta,
            message: chunk,
            timestamp: DateTime.now(),
            runId: runId ?? '',
            traceId: traceId ?? '',
            data: <String, dynamic>{'delta': chunk, 'phase': 'answering'},
          ),
        );
      }
    }
    final domainPolicyBundle = _buildDomainPolicyBundle(
      domainId: dialogueRoundScript.domainId,
      previous: previousDomainPolicyBundle,
      skillExecutionShell: skillExecutionShell,
      slotSchema: slotSchema,
      dialogueRoundScript: dialogueRoundScript,
      retrievalPolicy: retrievalPolicy,
      evidenceEvaluation: evidenceEvaluation,
      stateDecision: effectiveStateDecision,
    );
    final effectiveAggregationState = AggregationState(
      allSkillsReady: aggregationState.allSkillsReady,
      blockingSkills: aggregationState.blockingSkills,
      blockedBy: aggregationState.blockedBy,
      canGivePartialAnswer: aggregationState.canGivePartialAnswer,
      needExpansion: aggregationState.needExpansion,
      expansionPlan: aggregationState.expansionPlan,
      finalAnswerReady: answerEligible,
      finalAnswerMode: effectiveStateDecision.finalAnswerModeType,
      clarificationNeeded:
          effectiveStateDecision.nextActionType ==
              AssistantNextAction.askUser ||
          effectiveStateDecision.finalAnswerModeType == FinalAnswerMode.clarify,
      answerOwner: aggregationState.answerOwner,
      clarificationSource:
          effectiveStateDecision.askUser.slotId.trim().isNotEmpty == true
          ? effectiveStateDecision.askUser.slotId.trim()
          : aggregationState.clarificationSource,
      dependencies: aggregationState.dependencies,
    );
    final effectiveToolMetadataRegistry =
        _toolMetadataRegistry ?? ToolMetadataRegistry();
    if (_toolMetadataRegistry == null) {
      await effectiveToolMetadataRegistry.ensureLoaded();
    }
    final effectiveJourneyTraces = <AssistantTraceEvent>[
      ...result.traces,
      ...synthesizedAnsweringTraces,
    ];
    final journey = _enrichJourneyWithStructuredSnapshots(
      AssistantJourneyProjector.replay(
        traces: effectiveJourneyTraces,
        toolMetadataRegistry: effectiveToolMetadataRegistry,
        aggregationState: effectiveAggregationState,
        conversationStateDecision: effectiveStateDecision,
      ),
      understandingSnapshot: understandingSnapshot,
      retrievalProcessing: retrievalProcessingSnapshot,
      answerProcessing: answerProcessingSnapshot,
      finalAnswerReady: answerEligible,
    );
    final effectiveSkillRuns = _finalizeSkillRuns(
      skillRuns: skillRuns,
      primaryDomainId: dialogueRoundScript.domainId,
      slotState: groundedSlotState,
      answerReady: answerEligible,
      stopReason: effectiveStateDecision.finalAnswerModeWireName,
      references: uiReferences,
      resultSummary: _extractUiSummary(answerPayload, displayPlainText),
    );
    final resolvedAnswerEligibility = answerEligible
        ? effectiveStateDecision.answerEligibilityWireName
        : AnswerEligibility.blocked.wireName;
    final answerOutcome = AnswerOutcomeSnapshot(
      slotState: groundedSlotState,
      evidenceLedger: evidenceLedger,
      answerEvidenceBindings: answerEvidenceBindings,
      evidenceEvaluation: evidenceEvaluation,
      aggregationState: effectiveAggregationState,
      synthesisReadiness: effectiveSynthesisReadiness,
      conversationStateDecision: effectiveStateDecision,
      domainPolicyBundle: domainPolicyBundle,
      journey: journey,
    );
    final providerReasoningContinuation = _extractProviderReasoningContinuation(
      result.traces,
    );
    final runArtifacts = RunArtifacts(
      machineEnvelope: result.finalText,
      displayMarkdown: linkedMarkdown.trim(),
      displayPlainText: displayPlainText,
      journey: journey,
      understandingSnapshot: understandingSnapshot,
      answerProcessing: answerProcessingSnapshot,
      historicalThinkingSnapshot: historicalThinkingSnapshot,
      retrievalProcessing: retrievalProcessingSnapshot,
      evidenceLedger: evidenceLedger,
      answerEvidenceBindings: answerEvidenceBindings,
      slotState: groundedSlotState,
      answerDecision: <String, dynamic>{
        ...((answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
        ...effectiveStateDecision.toDecisionMap(),
        'evidenceSummary': evidenceEvaluation.summary,
      },
      diagnostics: <String, dynamic>{
        'domainId': dialogueRoundScript.domainId,
        'renderMode': renderMode,
        'renderFallback': renderFallback,
        'answerEligibility': resolvedAnswerEligibility,
        'qualityGates': effectiveStateDecision.qualityGatesData,
        'evidenceEvaluation': evidenceEvaluation.toJson(),
        'answerBoundaryPolicy': answerBoundaryPolicy.toJson(),
        ...((answerPayload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
      },
      domainPolicyBundle: domainPolicyBundle,
    );
    final sessionPreferenceFacts = _buildSessionPreferenceFacts(
      request: request,
      answerPayload: answerPayload,
      skillRuns: effectiveSkillRuns,
      uiReferences: uiReferences,
    );
    final longTermPreferenceFacts = _buildLongTermPreferenceFacts(
      request: request,
      answerPayload: answerPayload,
      sessionFacts: sessionPreferenceFacts,
    );
    final enrichedAnswerPayload = <String, dynamic>{
      ...answerPayload,
      'intentGraph': intentGraph.toJson(),
      'messageKind': messageKind,
      'subagentPlan': subagentPlan
          .map((item) => item.toJson())
          .toList(growable: false),
      'skillRuns': effectiveSkillRuns
          .map((item) => item.toJson())
          .toList(growable: false),
      'aggregationState': effectiveAggregationState.toJson(),
      'evidenceEvaluation': evidenceEvaluation.toJson(),
      'slotState': groundedSlotState.toJson(),
      'missingContextSlots': effectiveStateDecision.missingCriticalSlots,
      'understandingSnapshot': understandingSnapshot.toJson(),
      'answerProcessing': answerProcessingSnapshot.toJson(),
      'historicalThinkingSnapshot': historicalThinkingSnapshot.toJson(),
      'retrievalProcessing': retrievalProcessingSnapshot.toJson(),
      'askUser':
          (answerPayload['askUser'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'decision': <String, dynamic>{
        ...effectiveStateDecision.toDecisionMap(),
        ...((answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
      },
      'journey': journey.toJson(),
      'sessionPreferenceFacts': sessionPreferenceFacts
          .map((item) => item.toJson())
          .toList(growable: false),
      'longTermPreferenceFacts': longTermPreferenceFacts
          .map((item) => item.toJson())
          .toList(growable: false),
    };
    if (synthesizedAnsweringTraces.isNotEmpty && onTraceEvent != null) {
      for (final trace in synthesizedAnsweringTraces) {
        onTraceEvent(trace);
      }
    }
    return <String, dynamic>{
      'domainId': dialogueRoundScript.domainId,
      'problemShape': intentGraph.problemShape,
      'primarySkill': intentGraph.primarySkill,
      'secondarySkills': intentGraph.secondarySkills,
      'intentGraph': intentGraph.toJson(),
      'candidateDomains': candidateDomains,
      'templateVersionUsed': templateVersionUsed,
      'phaseOneRoutingDiagnostics': phaseOneRoutingDiagnostics,
      'domainCatalogVersion': domainCatalogVersion,
      'effectiveSessionId': sessionId,
      'activeTopicTitle': _sessionManager.topicTitleOf(sessionId),
      'contextAssembly': contextAssembly.contextEnvelope,
      'answerOutcome': answerOutcome.toJson(),
      'domainPrecheck': <String, dynamic>{
        'canEnterDomain': contextAssembly.canEnterDomain,
        'fillTaskCount': contextAssembly.fillTasks.length,
      },
      'domainResults': <String, dynamic>{
        'toolResults': toolResults,
        'toolErrors': toolErrors,
      },
      'synthesisReadiness': <String, dynamic>{
        'ready': effectiveSynthesisReadiness.ready,
        'reason': effectiveSynthesisReadiness.reason,
      },
      'webEvidencePacks': webEvidencePacks,
      'webEvidenceGate': <String, dynamic>{
        'passed': evidenceGatePassed,
        'evaluation': evidenceEvaluation.toJson(),
        'thresholds': <String, dynamic>{
          'coverageMin': 0.7,
          'confidenceMin': 0.65,
          'freshnessHoursMax': answerBoundaryPolicy.freshnessHoursMax,
          'authorityRequired': answerBoundaryPolicy.authorityRequired,
        },
      },
      'fillTasks': <String, dynamic>{
        'contextFillTasks': contextAssembly.fillTasks
            .map((task) => task.toJson())
            .toList(growable: false),
        'gapFillTask': effectiveSynthesisReadiness.gapFillTask?.toJson(),
      },
      'contextSlots': _buildContextSlots(contextAssembly),
      'dialogueRuntime': dialogueRoundScript.toJson(),
      'roundTrace': _buildRoundTrace(
        request: request,
        result: result,
        dialogueRoundScript: dialogueRoundScript,
      ),
      'fillActions': <Map<String, dynamic>>[
        ...contextAssembly.fillTasks.map((task) => task.toJson()),
        if (effectiveSynthesisReadiness.gapFillTask != null)
          effectiveSynthesisReadiness.gapFillTask!.toJson(),
      ],
      'missingCriticalSlots': effectiveStateDecision.missingCriticalSlots,
      'answerEligibility': resolvedAnswerEligibility,
      'conversationStateDecision': effectiveStateDecision.toDecisionMap(),
      'finalAnswerMode': effectiveStateDecision.finalAnswerModeWireName,
      'nextActions': _buildNextActions(
        contextAssembly,
        effectiveSynthesisReadiness,
      ),
      'experimentBucket': _resolveExperimentBucket(
        request.contextScopeHint,
        'control',
      ),
      'userProfileSnapshot': profileSnapshot,
      'profileVersion': (profileSnapshot['profileVersion'] ?? '').toString(),
      'snapshotAt': DateTime.now().toIso8601String(),
      'confidenceByFacet':
          (profileSnapshot['confidenceByFacet'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'sourceRuns':
          (profileSnapshot['sourceRuns'] as List?)?.whereType<String>().toList(
            growable: false,
          ) ??
          const <String>[],
      'basicIdentity': basicIdentity,
      'ipResidenceProfile': ipResidenceProfile,
      'retrievalFeedback': <String, dynamic>{
        'hasToolResult': toolResults.isNotEmpty,
        'toolResultCount': toolResults.length,
        'toolErrorCount': toolErrors.length,
        // Layer 4: 传递搜索质量分和轮次历史，供反思重写和 gap 补查使用
        'qualityScore': () {
          for (final r in toolResults.reversed) {
            final data = r['data'];
            if (data is Map) {
              final qs = (data['qualityScore'] as num?)?.toDouble();
              if (qs != null) return qs;
            }
          }
          return 0.0;
        }(),
        'roundTraces': toolResults
            .where((r) => r['tool'] == 'web_search' || r['stepId'] != null)
            .map(
              (r) => <String, dynamic>{
                'stepId': r['stepId'] ?? '',
                'tool': r['tool'] ?? '',
                'success': r['success'] ?? false,
                'qualityScore':
                    (r['data'] is Map
                        ? (r['data']['qualityScore'] as num?)?.toDouble()
                        : null) ??
                    0.0,
                'authorityScore':
                    (r['data'] is Map
                        ? (r['data']['authorityScore'] as num?)?.toDouble()
                        : null) ??
                    0.0,
                'totalReferences':
                    (r['data'] is Map
                        ? (r['data']['totalReferences'] as int?)
                        : null) ??
                    0,
              },
            )
            .toList(growable: false),
        'eligible':
            toolResults.isNotEmpty &&
            toolResults.any((r) {
              if (r['success'] != true) return false;
              final qs =
                  (r['data'] is Map
                      ? (r['data']['qualityScore'] as num?)?.toDouble()
                      : null) ??
                  0.0;
              return qs >= 0.35;
            }),
        'gaps': toolResults.isEmpty
            ? <String>['no_search_result']
            : toolResults
                  .where((r) {
                    final qs =
                        (r['data'] is Map
                            ? (r['data']['qualityScore'] as num?)?.toDouble()
                            : null) ??
                        0.0;
                    return r['success'] != true || qs < 0.35;
                  })
                  .map((r) => 'low_quality_result:${r['stepId'] ?? ''}')
                  .toList(growable: false),
      },
      'learningSignals': <String, dynamic>{
        'profileTagDelta':
            ((answerPayload['diagnostics'] as Map?)?['emergedTags'] as List?)
                ?.whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList(growable: false) ??
            const <Map<String, dynamic>>[],
        'retrievalStrategyOutcome': 'not_generated',
        'answerFormatOutcome': 'not_generated',
        'satisfactionProxy': learningSatisfaction,
        'modelSelfScore': modelSelfScore,
      },
      'reasoningBasis':
          (answerPayload['reasoningBasis'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      'selfCheck': _mergeSelfCheck(
        answerPayload: answerPayload,
        answerEligible: answerEligible,
        synthesisReason: effectiveSynthesisReadiness.reason,
        evidenceGatePassed: evidenceGatePassed,
      ),
      'diagnostics': <String, dynamic>{
        ...((answerPayload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
        'synthesisReason': effectiveSynthesisReadiness.reason,
        'toolResultCount': toolResults.length,
        'toolErrorCount': toolErrors.length,
        'webEvidenceGatePassed': evidenceGatePassed,
        'qualityGates': effectiveStateDecision.qualityGatesData,
      },
      'understandingSnapshot': understandingSnapshot.toJson(),
      'answerProcessing': answerProcessingSnapshot.toJson(),
      'historicalThinkingSnapshot': historicalThinkingSnapshot.toJson(),
      'retrievalProcessing': retrievalProcessingSnapshot.toJson(),
      if (providerReasoningContinuation.isNotEmpty)
        'providerReasoningContinuation': providerReasoningContinuation,
      'answerPayload': enrichedAnswerPayload,
      'decision':
          enrichedAnswerPayload['decision'] ?? const <String, dynamic>{},
      'messageKind': messageKind,
      'toolObservations': <Map<String, dynamic>>[
        ...toolResults.map(
          (item) => <String, dynamic>{
            'ok': true,
            'message': item['message'] ?? '',
            'data': item['data'] ?? const <String, dynamic>{},
            'toolCallId': item['toolCallId'] ?? '',
          },
        ),
        ...toolErrors.map(
          (item) => <String, dynamic>{
            'ok': false,
            'message': item['message'] ?? '',
            'data': item['data'] ?? const <String, dynamic>{},
            'toolCallId': item['toolCallId'] ?? '',
          },
        ),
      ],
      'subagentPlan': subagentPlan
          .map((item) => item.toJson())
          .toList(growable: false),
      'subagentRuns': subagentRuns,
      'skillRuns': effectiveSkillRuns
          .map((item) => item.toJson())
          .toList(growable: false),
      'aggregationState': effectiveAggregationState.toJson(),
      'sessionPreferenceFacts': sessionPreferenceFacts
          .map((item) => item.toJson())
          .toList(growable: false),
      'longTermPreferenceFacts': longTermPreferenceFacts
          .map((item) => item.toJson())
          .toList(growable: false),
      'renderMode': renderMode,
      'qualityMetrics': <String, dynamic>{
        'decisionParseSuccess': decisionParseSuccess,
        'renderFallback': renderFallback,
        'heuristicFallbackUsed': heuristicFallbackUsed,
        'evidenceSufficient': evidenceGatePassed,
        'freshnessSatisfied':
            evidenceEvaluation.freshnessSatisfied ||
            !evidenceEvaluation.evidenceRequired,
        'criticalSlotsResolved':
            effectiveStateDecision.missingCriticalSlots.isEmpty,
      },
      'contractId': kAssistantTurnCurrentContractId,
      '_meta': EngineResponseMeta(
        contractId: kAssistantTurnCurrentContractId,
        domainId: dialogueRoundScript.domainId,
        stateId: dialogueRoundScript.currentStateId,
        detectedEvent: dialogueRoundScript.detectedEvent,
        latencyMs: DateTime.now()
            .difference(
              result.traces.isEmpty
                  ? DateTime.now()
                  : result.traces.first.timestamp,
            )
            .inMilliseconds,
      ).toJson(),
      'journey': journey.toJson(),
      'runArtifacts': runArtifacts.toJson(),
      'uiTimeline': <Map<String, dynamic>>[
        for (final run in subagentRuns)
          <String, dynamic>{
            'event': 'subagent_progress',
            'subagentId': (run['subagentId'] as String?) ?? '',
            'status': (run['status'] as String?) ?? 'unknown',
          },
      ],
      'uiReferences': uiReferences,
      'evidenceLedger': evidenceLedger
          .map((entry) => entry.toJson())
          .toList(growable: false),
      'domainPolicyBundle': domainPolicyBundle.toJson(),
      'uiActions': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'regenerate'},
        <String, dynamic>{'id': 'brief'},
        <String, dynamic>{'id': 'detailed'},
        <String, dynamic>{'id': 'switch_model'},
      ],
      'uiUsageStats': _buildUiUsageStats(
        traces: result.traces,
        request: request,
        subagentRuns: subagentRuns,
        outputText: result.finalText,
      ),
      'profileUpdateProposal': _buildProfileUpdateProposal(
        request: request,
      )?.toJson(),
    };
  }

  static final RegExp _xmlToolCallTagRe = RegExp(
    r'<tool_call>[\s\S]*?</tool_call>|'
    r'<function=[^>]+>[\s\S]*?</function>|'
    r'<tool_call>|</tool_call>|'
    r'<function=[^>]*>|</function>|'
    r'<parameter=[^>]*>[\s\S]*?</parameter>|'
    r'</?parameter[^>]*>',
  );

  Map<String, dynamic> _buildUiUsageStats({
    required List<AssistantTraceEvent> traces,
    required AssistantRunRequest request,
    required List<Map<String, dynamic>> subagentRuns,
    required String outputText,
  }) {
    final inputText = request.messages.map((item) => item.content).join('\n');
    final mainUsage = _buildUsageStatsFromTraces(
      traces: traces,
      fallbackInputText: inputText,
      fallbackOutputText: outputText,
    );
    final mainLedger =
        (mainUsage['usageLedger'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final mainCalls = (mainUsage['modelCallCount'] as num?)?.toInt() ?? 0;
    final mainTokens = (mainUsage['totalTokens'] as num?)?.toInt() ?? 0;
    final mainMaxTokens = (mainUsage['maxTokensPerCall'] as num?)?.toInt() ?? 0;
    final mainTokenSamples =
        (mainUsage['tokenSampleCount'] as num?)?.toInt() ?? 0;
    final mainInputTokens = (mainUsage['inputTokens'] as num?)?.toInt() ?? 0;
    final mainOutputTokens = (mainUsage['outputTokens'] as num?)?.toInt() ?? 0;

    var subagentCalls = 0;
    var subagentTokens = 0;
    var subagentMaxTokens = 0;
    var subagentTokenSamples = 0;
    var subagentInputTokens = 0;
    var subagentOutputTokens = 0;
    final usageLedger = <Map<String, dynamic>>[...mainLedger];
    for (final run in subagentRuns) {
      subagentCalls += _safeNonNegativeInt(run['modelCallCount']);
      subagentTokens += _safeNonNegativeInt(run['totalTokens']);
      final maxTokens = _safeNonNegativeInt(run['maxTokensPerCall']);
      if (maxTokens > subagentMaxTokens) subagentMaxTokens = maxTokens;
      subagentTokenSamples += _safeNonNegativeInt(run['tokenSampleCount']);
      subagentInputTokens += _safeNonNegativeInt(run['inputTokens']);
      subagentOutputTokens += _safeNonNegativeInt(run['outputTokens']);
      final subagentLedger =
          (run['usageLedger'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      usageLedger.addAll(subagentLedger);
    }

    final tokenSampleCount = mainTokenSamples + subagentTokenSamples;
    final modelCalls = math.max(1, mainCalls + subagentCalls);
    final totalTokens = mainTokens + subagentTokens;
    final maxTokens = math.max(mainMaxTokens, subagentMaxTokens);

    return <String, dynamic>{
      'modelCallCount': modelCalls,
      'totalTokens': totalTokens,
      'maxTokensPerCall': maxTokens,
      'inputTokens': mainInputTokens + subagentInputTokens,
      'outputTokens': mainOutputTokens + subagentOutputTokens,
      'tokenSource': tokenSampleCount > 0 ? 'trace_or_subagent' : 'estimated',
      'tokenSampleCount': tokenSampleCount,
      if (usageLedger.isNotEmpty) 'usageLedger': usageLedger,
    };
  }

  Map<String, dynamic> _buildUsageStatsFromTraces({
    required List<AssistantTraceEvent> traces,
    required String fallbackInputText,
    required String fallbackOutputText,
  }) {
    final usageLedger = <Map<String, dynamic>>[];
    for (final trace in traces) {
      final entries =
          (trace.data?['usageEntries'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (entries.isEmpty) continue;
      usageLedger.addAll(entries);
    }
    if (usageLedger.isNotEmpty) {
      var totalTokens = 0;
      var maxTokens = 0;
      var inputTokens = 0;
      var outputTokens = 0;
      final sources = <String>{};
      for (final entry in usageLedger) {
        final total = _safeNonNegativeInt(
          entry['totalTokens'] ?? entry['tokenUsage'],
        );
        final input = _safeNonNegativeInt(entry['inputTokens']);
        final output = _safeNonNegativeInt(entry['outputTokens']);
        totalTokens += total;
        inputTokens += input;
        outputTokens += output;
        if (total > maxTokens) maxTokens = total;
        final source = (entry['source'] as String?)?.trim() ?? '';
        if (source.isNotEmpty) {
          sources.add(source);
        }
      }
      return <String, dynamic>{
        'modelCallCount': usageLedger.length,
        'totalTokens': totalTokens,
        'maxTokensPerCall': maxTokens,
        'inputTokens': inputTokens,
        'outputTokens': outputTokens,
        'tokenSource': sources.isEmpty
            ? 'usage_ledger'
            : (sources.length == 1 ? sources.first : 'mixed_ledger'),
        'tokenSampleCount': usageLedger.length,
        'usageLedger': usageLedger,
      };
    }

    int totalTokensFromTrace = 0;
    int maxTokensFromTrace = 0;
    var tokenSampleCount = 0;

    void collectTokenValues(Object? node) {
      if (node is Map) {
        for (final entry in node.entries) {
          final key = entry.key.toString().toLowerCase();
          final value = entry.value;
          if (value is num &&
              (key.contains('token') ||
                  key.contains('input_tokens') ||
                  key.contains('output_tokens'))) {
            final token = value.toInt();
            if (token > 0) {
              tokenSampleCount += 1;
              totalTokensFromTrace += token;
              if (token > maxTokensFromTrace) maxTokensFromTrace = token;
            }
          } else {
            collectTokenValues(value);
          }
        }
      } else if (node is List) {
        for (final item in node) {
          collectTokenValues(item);
        }
      }
    }

    for (final trace in traces) {
      collectTokenValues(trace.data);
    }

    final estimatedInputTokens = _estimateTokenCount(fallbackInputText);
    final estimatedOutputTokens = _estimateTokenCount(fallbackOutputText);
    final estimatedTotalTokens = estimatedInputTokens + estimatedOutputTokens;
    final estimatedMaxTokens = math.max(
      estimatedInputTokens,
      estimatedOutputTokens,
    );

    final totalTokens = tokenSampleCount > 0
        ? totalTokensFromTrace
        : estimatedTotalTokens;
    final maxTokens = tokenSampleCount > 0
        ? maxTokensFromTrace
        : estimatedMaxTokens;
    final modelCalls = _countModelCallsFromTraces(traces);

    return <String, dynamic>{
      'modelCallCount': modelCalls,
      'totalTokens': totalTokens,
      'maxTokensPerCall': maxTokens,
      'tokenSource': tokenSampleCount > 0 ? 'trace' : 'estimated',
      'tokenSampleCount': tokenSampleCount,
    };
  }

  int _countModelCallsFromTraces(List<AssistantTraceEvent> traces) {
    final calls = traces
        .where(
          (trace) =>
              trace.type == AssistantTraceEventType.lifecycleStart &&
              (trace.message.startsWith('llm request iteration ') ||
                  trace.message.startsWith('llm request synthesis ')),
        )
        .length;
    return math.max(1, calls);
  }

  int _estimateTokenCount(String text) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return 0;
    return (trimmed.length / 4).ceil();
  }

  int _safeNonNegativeInt(Object? value) {
    if (value is num) return value.toInt() < 0 ? 0 : value.toInt();
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed == null || parsed < 0) return 0;
    return parsed;
  }

  List<Map<String, dynamic>> _buildUiReferences(
    List<Map<String, dynamic>> toolResults, {
    required bool isRealtimeLike,
  }) {
    final refs = <Map<String, dynamic>>[];
    final seen = <String>{};
    var totalSearched = 0;
    for (final item in toolResults) {
      final toolName = (item['toolName'] as String?)?.trim() ?? '';
      if (!_toolContributesUiReferences(
        toolName,
        allowLocationContext: isRealtimeLike,
      )) {
        continue;
      }
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      // Layer 5: 统计总搜索量
      final searchTotal = (data['totalReferences'] as int?) ?? 0;
      if (searchTotal > 0) totalSearched += searchTotal;
      final rawRefs =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((ref) => ref.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final authorityDomains =
          (data['authorityDomains'] as List?)?.cast<String>() ?? <String>[];
      for (final ref in rawRefs) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || seen.contains(url)) continue;
        final parsed = Uri.tryParse(url);
        final sourceLabel =
            (ref['source'] as String?)?.trim().isNotEmpty == true
            ? (ref['source'] as String).trim()
            : ((ref['sourceHost'] as String?)?.trim().isNotEmpty == true
                  ? (ref['sourceHost'] as String).trim()
                  : parsed?.host ?? '');
        final sourceHost =
            (ref['sourceHost'] as String?)?.trim().isNotEmpty == true
            ? (ref['sourceHost'] as String).trim()
            : parsed?.host ?? '';
        final title = (ref['title'] as String?)?.trim() ?? '';
        final snippet = (ref['snippet'] as String?)?.trim() ?? '';
        final sourceTier = (ref['sourceTier'] as String?)?.trim() ?? '';
        final authorityScore =
            (ref['authorityScore'] as num?)?.toDouble() ?? 0.0;
        final freshnessHours =
            (ref['freshnessHours'] as num?)?.toDouble() ?? 0.0;
        final isCited =
            authorityDomains.isNotEmpty &&
            authorityDomains.any(
              (d) => sourceHost == d || sourceHost.endsWith('.$d'),
            );
        if (isRealtimeLike &&
            !_isStrictRealtimeReference(
              title: title,
              source: sourceLabel,
              snippet: snippet,
              sourceTier: sourceTier,
              authorityScore: authorityScore,
              freshnessHours: freshnessHours,
              isAuthoritative: isCited,
            )) {
          continue;
        }
        final dedupeKey = '${sourceLabel.toLowerCase()}|${title.toLowerCase()}';
        if (seen.contains(dedupeKey)) continue;
        refs.add(<String, dynamic>{
          'title': title.isNotEmpty ? title : sourceLabel,
          'url': url,
          'source': sourceLabel,
          'provider': (ref['provider'] as String?)?.trim() ?? '',
          'snippet': snippet,
          'cited': isCited,
          'authorityScore': isCited ? 1.0 : 0.0,
        });
        seen.add(url);
        seen.add(dedupeKey);
      }
    }
    refs.sort((a, b) {
      final citedDelta =
          ((b['cited'] == true) ? 1 : 0) - ((a['cited'] == true) ? 1 : 0);
      if (citedDelta != 0) return citedDelta;
      final authorityDelta =
          (((b['authorityScore'] as num?)?.toDouble() ?? 0.0) * 100).round() -
          (((a['authorityScore'] as num?)?.toDouble() ?? 0.0) * 100).round();
      if (authorityDelta != 0) return authorityDelta;
      return 0;
    });
    final curatedRefs = isRealtimeLike
        ? refs
              .where((item) => item['cited'] == true)
              .take(4)
              .toList(growable: false)
        : refs.take(8).toList(growable: false);
    // Layer 5: 总搜索资料数注入到第一个参考资料的元数据中，供 UI 展示"共检索 N 篇资料，以下为参考来源"
    if (curatedRefs.isNotEmpty && totalSearched > 0) {
      curatedRefs.first['_totalSearched'] = totalSearched;
    }
    return curatedRefs;
  }

  List<Map<String, dynamic>> _buildInlineEvidenceLinks({
    required Map<String, dynamic> answerPayload,
    required List<Map<String, dynamic>> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    return _buildAnswerEvidenceBindings(
      answerPayload: answerPayload,
      uiReferences: uiReferences,
      evidenceLedger: evidenceLedger,
    ).map((item) => item.toJson()).toList(growable: false);
  }

  List<AnswerEvidenceBinding> _buildAnswerEvidenceBindings({
    required Map<String, dynamic> answerPayload,
    required List<Map<String, dynamic>> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    final bindings = <AnswerEvidenceBinding>[];
    final seenKeys = <String>{};
    final rawEvidence =
        (answerPayload['evidence'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    for (final item in rawEvidence) {
      final candidate = _normalizeInlineEvidenceBinding(
        item: item,
        uiReferences: uiReferences,
        evidenceLedger: evidenceLedger,
        index: bindings.length + 1,
      );
      if (candidate == null) continue;
      final dedupeKey = candidate.evidenceId.isNotEmpty
          ? candidate.evidenceId
          : candidate.url;
      if (dedupeKey.isEmpty || !seenKeys.add(dedupeKey)) continue;
      bindings.add(candidate);
      if (bindings.length >= 4) break;
    }
    if (bindings.isEmpty) {
      for (final entry in evidenceLedger.take(2)) {
        final dedupeKey = entry.evidenceId.isNotEmpty
            ? entry.evidenceId
            : entry.url;
        if (dedupeKey.isEmpty || !seenKeys.add(dedupeKey)) continue;
        bindings.add(
          _fallbackBindingFromEvidenceEntry(
            entry: entry,
            index: bindings.length + 1,
          ),
        );
      }
    }
    if (bindings.isEmpty) {
      for (final ref in uiReferences.take(2)) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || !seenKeys.add(url)) continue;
        bindings.add(
          _fallbackBindingFromReference(ref: ref, index: bindings.length + 1),
        );
      }
    }
    return bindings;
  }

  AnswerEvidenceBinding? _normalizeInlineEvidenceBinding({
    required Map<String, dynamic> item,
    required List<Map<String, dynamic>> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
    required int index,
  }) {
    final claim =
        ((item['text'] as String?)?.trim().isNotEmpty == true
            ? (item['text'] as String).trim()
            : (item['claim'] as String?)?.trim()) ??
        '';
    final directEvidenceId = (item['evidenceId'] as String?)?.trim() ?? '';
    final directUrl = SafeReferenceNormalizer.canonicalizeUrl(
      (item['url'] as String?)?.trim() ?? '',
    );
    final directTitle = (item['title'] as String?)?.trim() ?? '';
    final directSource = (item['source'] as String?)?.trim() ?? '';
    final directSnippet = (item['snippet'] as String?)?.trim() ?? '';
    final matchedEvidence = _matchEvidenceEntryForBinding(
      claim: claim,
      title: directTitle,
      snippet: directSnippet,
      directUrl: directUrl,
      directEvidenceId: directEvidenceId,
      evidenceLedger: evidenceLedger,
    );
    Map<String, dynamic> matchedReference = const <String, dynamic>{};
    if (directUrl.isEmpty && matchedEvidence == null) {
      matchedReference = _matchReferenceForEvidence(
        claim: claim,
        title: directTitle,
        snippet: directSnippet,
        uiReferences: uiReferences,
      );
    }
    final url = directUrl.isNotEmpty
        ? directUrl
        : (matchedEvidence?.url.isNotEmpty == true
              ? matchedEvidence!.url
              : SafeReferenceNormalizer.canonicalizeUrl(
                  (matchedReference['url'] as String?)?.trim() ?? '',
                ));
    if (url.isEmpty) return null;
    final normalizedReference = SafeReferenceNormalizer.normalize(<
      String,
      dynamic
    >{
      'url': url,
      'title': directTitle.isNotEmpty
          ? directTitle
          : (matchedEvidence?.title.isNotEmpty == true
                ? matchedEvidence!.title
                : ((matchedReference['title'] as String?)?.trim().isNotEmpty ==
                          true
                      ? (matchedReference['title'] as String).trim()
                      : url)),
      'source': matchedEvidence?.source.isNotEmpty == true
          ? matchedEvidence!.source
          : (directSource.isNotEmpty
                ? directSource
                : (matchedEvidence?.sourceHost.isNotEmpty == true
                      ? matchedEvidence!.sourceHost
                      : (matchedReference['source'] as String?)?.trim() ?? '')),
      'snippet': directSnippet.isNotEmpty
          ? directSnippet
          : (matchedEvidence?.snippet.isNotEmpty == true
                ? matchedEvidence!.snippet
                : (matchedReference['snippet'] as String?)?.trim() ?? ''),
    });
    if (normalizedReference == null) return null;
    final source = matchedEvidence?.source.isNotEmpty == true
        ? matchedEvidence!.source
        : (directSource.isNotEmpty
              ? directSource
              : (matchedEvidence?.sourceHost.isNotEmpty == true
                    ? matchedEvidence!.sourceHost
                    : (normalizedReference['source'] as String?)?.trim() ??
                          ''));
    final snippet = (normalizedReference['snippet'] as String?)?.trim() ?? '';
    return AnswerEvidenceBinding(
      bindingId:
          'answer_evidence_${index}_${matchedEvidence?.evidenceId.isNotEmpty == true ? matchedEvidence!.evidenceId : url.hashCode}',
      label: '来源$index',
      claim: claim,
      evidenceId: matchedEvidence?.evidenceId ?? '',
      url: url,
      title: (normalizedReference['title'] as String?)?.trim() ?? url,
      source: source,
      snippet: snippet,
    );
  }

  AnswerEvidenceBinding _fallbackBindingFromEvidenceEntry({
    required EvidenceLedgerEntry entry,
    required int index,
  }) {
    return AnswerEvidenceBinding(
      bindingId:
          'answer_evidence_${index}_${entry.evidenceId.isNotEmpty ? entry.evidenceId : entry.url.hashCode}',
      label: '来源$index',
      claim: entry.title,
      evidenceId: entry.evidenceId,
      url: entry.url,
      title: entry.title.isNotEmpty ? entry.title : entry.url,
      source: entry.source.isNotEmpty ? entry.source : entry.sourceHost,
      snippet: entry.snippet,
    );
  }

  AnswerEvidenceBinding _fallbackBindingFromReference({
    required Map<String, dynamic> ref,
    required int index,
  }) {
    final normalized = SafeReferenceNormalizer.normalize(ref) ?? ref;
    final url = SafeReferenceNormalizer.canonicalizeUrl(
      (normalized['url'] as String?)?.trim() ?? '',
    );
    final title = (normalized['title'] as String?)?.trim().isNotEmpty == true
        ? (normalized['title'] as String).trim()
        : url;
    return AnswerEvidenceBinding(
      bindingId: 'answer_evidence_${index}_${url.hashCode}',
      label: '来源$index',
      claim: title,
      evidenceId: (ref['evidenceId'] as String?)?.trim() ?? '',
      url: url,
      title: title,
      source: (ref['source'] as String?)?.trim() ?? '',
      snippet: (ref['snippet'] as String?)?.trim() ?? '',
    );
  }

  EvidenceLedgerEntry? _matchEvidenceEntryForBinding({
    required String claim,
    required String title,
    required String snippet,
    required String directUrl,
    required String directEvidenceId,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    for (final entry in evidenceLedger) {
      if (directEvidenceId.isNotEmpty && entry.evidenceId == directEvidenceId) {
        return entry;
      }
      if (directUrl.isNotEmpty &&
          SafeReferenceNormalizer.canonicalizeUrl(entry.url) == directUrl) {
        return entry;
      }
    }
    final scoreTarget = '$claim $title $snippet'.toLowerCase();
    EvidenceLedgerEntry? best;
    var bestScore = 0;
    for (final entry in evidenceLedger) {
      final haystack =
          '${entry.title} ${entry.snippet} ${entry.source} ${entry.sourceHost} ${entry.url}'
              .toLowerCase();
      var score = 0;
      if (claim.isNotEmpty && haystack.contains(claim.toLowerCase())) {
        score += claim.length + 6;
      }
      if (title.isNotEmpty && haystack.contains(title.toLowerCase())) {
        score += title.length + 4;
      }
      for (final token in _evidenceScoreTokens(scoreTarget)) {
        if (haystack.contains(token)) score += token.length;
      }
      if (score > bestScore) {
        bestScore = score;
        best = entry;
      }
    }
    return bestScore > 0 ? best : null;
  }

  Map<String, dynamic> _matchReferenceForEvidence({
    required String claim,
    required String title,
    required String snippet,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final scoreTarget = '$claim $title $snippet'.toLowerCase();
    Map<String, dynamic> best = const <String, dynamic>{};
    var bestScore = 0;
    for (final ref in uiReferences) {
      final refText =
          '${(ref['title'] ?? '').toString()} ${(ref['snippet'] ?? '').toString()} ${(ref['source'] ?? '').toString()}'
              .toLowerCase();
      var score = 0;
      for (final token in _evidenceScoreTokens(scoreTarget)) {
        if (refText.contains(token)) score += token.length;
      }
      if (score > bestScore) {
        bestScore = score;
        best = ref;
      }
    }
    return best;
  }

  String _applyInlineEvidenceLinks(
    String markdown,
    List<Map<String, dynamic>> evidenceLinks,
  ) {
    final trimmed = markdown.trimRight();
    if (trimmed.isEmpty || evidenceLinks.isEmpty) return trimmed;
    final lines = trimmed.split('\n');
    final candidateIndices = <int>[];
    for (var i = 0; i < lines.length; i++) {
      if (_isEvidenceCandidateLine(lines[i])) {
        candidateIndices.add(i);
      }
    }
    if (candidateIndices.isEmpty) return trimmed;
    final usedIndices = <int>{};
    for (final link in evidenceLinks) {
      final targetIndex = _pickEvidenceTargetLine(
        lines: lines,
        candidates: candidateIndices,
        usedIndices: usedIndices,
        link: link,
      );
      if (targetIndex < 0) continue;
      final url = (link['url'] as String?)?.trim() ?? '';
      final label = (link['label'] as String?)?.trim() ?? '来源';
      if (url.isEmpty || lines[targetIndex].contains('($url)')) continue;
      lines[targetIndex] = '${lines[targetIndex].trimRight()} [$label]($url)';
      usedIndices.add(targetIndex);
    }
    return lines.join('\n');
  }

  int _pickEvidenceTargetLine({
    required List<String> lines,
    required List<int> candidates,
    required Set<int> usedIndices,
    required Map<String, dynamic> link,
  }) {
    var bestIndex = -1;
    var bestScore = -1;
    for (final index in candidates) {
      if (usedIndices.contains(index)) continue;
      final score = _scoreLineForEvidence(lines[index], link);
      if (score > bestScore) {
        bestScore = score;
        bestIndex = index;
      }
    }
    if (bestIndex >= 0 && bestScore > 0) return bestIndex;
    for (final index in candidates) {
      if (!usedIndices.contains(index)) return index;
    }
    return -1;
  }

  int _scoreLineForEvidence(String line, Map<String, dynamic> link) {
    final haystack = line.toLowerCase();
    var score = 0;
    final claim = ((link['claim'] as String?)?.trim() ?? '').toLowerCase();
    if (claim.isNotEmpty && haystack.contains(claim)) {
      score += claim.length + 4;
    }
    final title = ((link['title'] as String?)?.trim() ?? '').toLowerCase();
    if (title.isNotEmpty && haystack.contains(title)) {
      score += title.length + 2;
    }
    for (final token in _evidenceScoreTokens('$claim $title')) {
      if (haystack.contains(token)) score += token.length;
    }
    return score;
  }

  Iterable<String> _evidenceScoreTokens(String raw) {
    return RegExp(r'[\u4e00-\u9fa5A-Za-z0-9]{2,}')
        .allMatches(raw)
        .map((m) => m.group(0)!.toLowerCase())
        .where((token) => token.length >= 2)
        .take(8);
  }

  bool _isEvidenceCandidateLine(String line) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) return false;
    if (trimmed.startsWith('#') ||
        trimmed.startsWith('```') ||
        trimmed.startsWith('|') ||
        trimmed.startsWith('>')) {
      return false;
    }
    return true;
  }

  bool _isStrictRealtimeReference({
    required String title,
    required String source,
    required String snippet,
    required String sourceTier,
    required double authorityScore,
    required double freshnessHours,
    required bool isAuthoritative,
  }) {
    if (isAuthoritative) return true;
    if (authorityScore >= 0.8) return true;
    if (freshnessHours > 0 && freshnessHours <= 24) return true;
    final sourceTierType = parseEvidenceSourceTier(sourceTier);
    if (sourceTierType == EvidenceSourceTier.authority ||
        sourceTierType == EvidenceSourceTier.page) {
      return freshnessHours <= 0 || freshnessHours <= 72;
    }
    return false;
  }

  /// 将 LLM 最终文本解析为结构化的 answerPayload Map。
  ///
  /// LLM JSON → [tryParseAssistantTurnOutput()] 类型化对象 → answerPayload Map。
  /// 字段名字符串只在 [tryParseAssistantTurnOutput()] 内出现（见 02-dart-coding §5.1）。
  Map<String, dynamic> _parseAnswerPayload({
    required String rawFinalText,
    required List<AssistantTraceEvent> traces,
  }) {
    final parseResult = LlmResponseParser.parse(rawFinalText);
    final parsed = parseResult.json ?? <String, dynamic>{};
    // 解析为类型化对象，字段名字符串集中在 tryParseAssistantTurnOutput() 内
    final turn = tryParseAssistantTurnOutput(parsed);
    final toolCallsFromTrace = traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map(
          (event) => <String, dynamic>{
            'toolName': _traceToolName(event),
            'arguments': event.data ?? const <String, dynamic>{},
            'toolCallId': event.toolCallId ?? '',
          },
        )
        .toList(growable: false);
    final existingToolCalls = _normalizeToolCalls(
      turn != null ? turn.toolCalls : (parsed['toolCalls']),
    );
    final normalizedToolCalls = existingToolCalls.isNotEmpty
        ? existingToolCalls
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false)
        : toolCallsFromTrace;
    final resultPayload = turn != null
        ? (turn.resultData.isNotEmpty
              ? Map<String, dynamic>.from(turn.resultData)
              : <String, dynamic>{'text': rawFinalText})
        : ((parsed['result'] as Map?)?.cast<String, dynamic>() ??
              <String, dynamic>{'text': rawFinalText});
    // 将 nextAction 注入到 result，供下游 _extractUiMarkdown 使用
    if (turn != null && turn.nextAction.isNotEmpty) {
      resultPayload['nextAction'] = turn.nextAction;
    }
    final parseStatus = parsed.isEmpty
        ? 'fallback_text'
        : (turn != null ? 'assistant_turn_parsed' : 'json_parsed');
    return <String, dynamic>{
      'result': resultPayload,
      'evidence': turn != null
          ? turn.evidence.map((item) => item.toJson()).toList(growable: false)
          : _normalizeMapList(parsed['evidence'], textKey: 'text'),
      'reasoningBasis': turn != null
          ? turn.reasoningBasis
                .map((item) => item.toJson())
                .toList(growable: false)
          : _normalizeMapList(parsed['reasoningBasis'], textKey: 'text'),
      'selfCheck': turn != null
          ? turn.selfCheck.toJson()
          : _normalizeMap(parsed['selfCheck']),
      'diagnostics': turn != null
          ? turn.diagnostics.toJson()
          : _normalizeMap(parsed['diagnostics']),
      'modelSelfScore': turn != null
          ? _normalizeModelSelfScore(turn.modelSelfScore.toJson())
          : _normalizeModelSelfScore(parsed['modelSelfScore']),
      'toolCalls': normalizedToolCalls,
      'userMarkdown': turn?.userMarkdown ?? '',
      'decision': turn?.decision.toJson() ?? const <String, dynamic>{},
      'messageKind': turn?.messageKind.wireName ?? '',
      'slotState': turn?.slotState.toJson() ?? const <String, dynamic>{},
      'askUser': turn?.askUser.toJson() ?? const <String, dynamic>{},
      'understandingSnapshot':
          turn?.understandingSnapshot.toJson() ??
          _normalizeMap(parsed['understandingSnapshot']),
      'answerProcessing':
          turn?.answerProcessing.toJson() ??
          _normalizeMap(parsed['answerProcessing']),
      'historicalThinkingSnapshot':
          turn?.historicalThinkingSnapshot.toJson() ??
          _normalizeMap(parsed['historicalThinkingSnapshot']),
      'subagentPlan': turn != null
          ? turn.subagentPlan
                .map((item) => item.toJson())
                .toList(growable: false)
          : _normalizeMapList(parsed['subagentPlan'], textKey: 'goal'),
      'intentGraph':
          turn?.intentGraph?.toJson() ?? _normalizeMap(parsed['intentGraph']),
      'skillRuns': turn != null
          ? turn.skillRuns.map((item) => item.toJson()).toList(growable: false)
          : _normalizeMapList(parsed['skillRuns'], textKey: 'goal'),
      'aggregationState':
          turn?.aggregationState?.toJson() ??
          _normalizeMap(parsed['aggregationState']),
      'journey': turn?.journey.toJson() ?? _normalizeMap(parsed['journey']),
      'toolPlan': turn != null
          ? turn.toolPlan.map((item) => item.toJson()).toList(growable: false)
          : _normalizeMapList(parsed['toolPlan'], textKey: 'toolName'),
      'missingContextSlots':
          turn?.missingContextSlots ??
          _normalizeStringList(parsed['missingContextSlots']),
      'fillGuidance': turn != null
          ? turn.fillGuidance
                .map((item) => item.toJson())
                .toList(growable: false)
          : _normalizeMapList(parsed['fillGuidance'], textKey: 'guidance'),
      'followupPrompt': turn?.followupPrompt ?? '',
      'actionHints':
          turn?.result.actionHints ??
          _normalizeStringList(
            (((parsed['result'] as Map?)?.cast<String, dynamic>()) ??
                const <String, dynamic>{})['actionHints'],
          ),
      'sessionPreferenceFacts': turn != null
          ? turn.sessionPreferenceFacts
                .map((item) => item.toJson())
                .toList(growable: false)
          : _normalizeMapList(parsed['sessionPreferenceFacts'], textKey: 'key'),
      'longTermPreferenceFacts': turn != null
          ? turn.longTermPreferenceFacts
                .map((item) => item.toJson())
                .toList(growable: false)
          : _normalizeMapList(
              parsed['longTermPreferenceFacts'],
              textKey: 'key',
            ),
      'parseStatus': parseStatus,
    };
  }

  RunArtifactsUnderstandingSnapshot _buildUnderstandingSnapshot({
    required Map<String, dynamic> raw,
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsUnderstandingSnapshot.fromJson(raw)
        : const RunArtifactsUnderstandingSnapshot();
    final queryGroups = parsed.queryGroups.isNotEmpty
        ? parsed.queryGroups
        : _buildUnderstandingQueryGroups(intentGraph.queryTasks);
    final concernPoints = parsed.concernPoints.isNotEmpty
        ? parsed.concernPoints
        : <String>[
                ...intentGraph.hardConstraints,
                ...intentGraph.softConstraints,
              ]
              .where((item) => item.trim().isNotEmpty)
              .take(4)
              .toList(growable: false);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: parsed.intentSummary.isNotEmpty
          ? parsed.intentSummary
          : _firstNonEmptyText(<String?>[
              intentGraph.userGoal,
              intentGraph.userJobToBeDone,
              intentGraph.targetObject,
              latestUserQuery,
            ]),
      concernPoints: concernPoints,
      emotionSignal: parsed.emotionSignal,
      queryDesignSummary: parsed.queryDesignSummary.isNotEmpty
          ? parsed.queryDesignSummary
          : _buildUserFacingQueryDesignSummary(intentGraph.queryTasks),
      queryGroups: queryGroups,
      assumptions: parsed.assumptions,
      mismatchSignal: parsed.mismatchSignal,
      carryForwardFacts: parsed.carryForwardFacts,
      discardedAssumptions: parsed.discardedAssumptions,
    );
  }

  List<RunArtifactsUnderstandingQueryGroup> _buildUnderstandingQueryGroups(
    List<QueryTask> queryTasks,
  ) {
    final grouped = <String, List<String>>{};
    final labels = <String, String>{};
    for (final task in queryTasks) {
      final dimension = task.dimensionLabel.trim().isNotEmpty
          ? task.dimensionLabel.trim()
          : (task.label.trim().isNotEmpty ? task.label.trim() : '综合');
      final query = task.query.trim();
      if (query.isEmpty) continue;
      grouped.putIfAbsent(dimension, () => <String>[]).add(query);
      labels[dimension] = task.label.trim();
    }
    return grouped.entries
        .map(
          (entry) => RunArtifactsUnderstandingQueryGroup(
            dimension: entry.key,
            queries: entry.value.toSet().toList(growable: false),
            why: labels[entry.key]?.trim() ?? '',
          ),
        )
        .toList(growable: false);
  }

  String _buildUserFacingQueryDesignSummary(List<QueryTask> queryTasks) {
    if (queryTasks.isEmpty) {
      return '';
    }
    final lines = <String>[_queryTaskLeadLine(queryTasks.length)];
    final seen = <String>{};
    for (final task in queryTasks) {
      final line = _queryTaskDisplayLine(task);
      if (line.isEmpty || !seen.add(line)) {
        continue;
      }
      lines.add(line);
    }
    return lines.join('\n').trim();
  }

  String _queryTaskLeadLine(int taskCount) {
    return taskCount >= 2 ? '我会先把会影响判断的几个方面拆开确认：' : '我先确认最影响判断的这一项：';
  }

  String _queryTaskDisplayLine(QueryTask task) {
    final query = task.query.trim();
    if (query.isEmpty) {
      return '';
    }
    final objectLabel = _queryTaskObjectLabel(task, query: query);
    final displayLabel = _queryTaskDisplayLabel(task, query: query);
    final prefixParts = <String>[
      if (objectLabel.isNotEmpty) objectLabel,
      if (displayLabel.isNotEmpty) displayLabel,
    ];
    final prefix = prefixParts.join(' · ');
    if (prefix.isNotEmpty) {
      return '- $prefix';
    }
    return '- $query';
  }

  String _queryTaskObjectLabel(QueryTask task, {required String query}) {
    final anchors = task.entityAnchors
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (anchors.isEmpty) {
      return '';
    }
    final joined = anchors.join(' / ');
    return _normalizedCompactQueryToken(joined) ==
            _normalizedCompactQueryToken(query)
        ? ''
        : joined;
  }

  String _queryTaskDisplayLabel(QueryTask task, {required String query}) {
    final label = task.label.trim();
    if (label.isNotEmpty &&
        _normalizedCompactQueryToken(label) !=
            _normalizedCompactQueryToken(query)) {
      return label;
    }
    final dimension = task.dimensionLabel.trim();
    if (dimension.isNotEmpty &&
        _normalizedCompactQueryToken(dimension) !=
            _normalizedCompactQueryToken(query)) {
      return dimension;
    }
    return '';
  }

  String _normalizedCompactQueryToken(String raw) {
    return raw.trim().toLowerCase().replaceAll(
      RegExp(r'[\s:：|｜/、,，。！？!?._-]+'),
      '',
    );
  }

  RunArtifactsAnswerProcessing _buildAnswerProcessingSnapshot({
    required Map<String, dynamic> raw,
    required SynthesisReadinessResult synthesisReadiness,
    required ConversationStateDecision stateDecision,
    required EvidenceEvaluationResult evidenceEvaluation,
    required List<EvidenceLedgerEntry> evidenceLedger,
    required Map<String, dynamic> answerPayload,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsAnswerProcessing.fromJson(raw)
        : const RunArtifactsAnswerProcessing();
    final keyFacts = parsed.keyFacts.isNotEmpty
        ? parsed.keyFacts
        : _buildAnswerKeyFacts(
            answerPayload: answerPayload,
            evidenceLedger: evidenceLedger,
          );
    final missingDimensions = parsed.missingDimensions.isNotEmpty
        ? parsed.missingDimensions
        : stateDecision.missingCriticalSlots
              .where((item) => item.trim().isNotEmpty)
              .take(4)
              .toList(growable: false);
    final retrieveMoreReason = parsed.retrieveMoreReason.isNotEmpty
        ? parsed.retrieveMoreReason
        : (stateDecision.finalAnswerReady
              ? ''
              : _firstNonEmptyText(<String?>[
                  synthesisReadiness.reason,
                  evidenceEvaluation.summary,
                ]));
    return RunArtifactsAnswerProcessing(
      readinessSummary: parsed.readinessSummary.isNotEmpty
          ? parsed.readinessSummary
          : (stateDecision.finalAnswerReady
                ? _defaultAnswerReadinessSummary(
                    keyFacts: keyFacts,
                    answerPayload: answerPayload,
                  )
                : _firstNonEmptyText(<String?>[
                    synthesisReadiness.reason,
                    evidenceEvaluation.summary,
                    '仍有维度待补充',
                  ])),
      keyFacts: keyFacts,
      missingDimensions: missingDimensions,
      retrieveMoreReason: retrieveMoreReason,
    );
  }

  String _defaultAnswerReadinessSummary({
    required List<String> keyFacts,
    required Map<String, dynamic> answerPayload,
  }) {
    if (keyFacts.isNotEmpty) {
      return '我已经把能直接回答这个问题的关键信息收拢好了。';
    }
    final resultData =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final resultSummary = (resultData['summary'] as String?)?.trim() ?? '';
    if (resultSummary.isNotEmpty &&
        !AssistantDisplayTextResolver.containsInternalProcessFragment(
          resultSummary,
        )) {
      return resultSummary;
    }
    return '我已经把现在最关键的判断依据收拢好了。';
  }

  List<String> _buildAnswerKeyFacts({
    required Map<String, dynamic> answerPayload,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    final fromPayload =
        ((answerPayload['evidence'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .map(
              (item) => (item['claim'] as String?)?.trim().isNotEmpty == true
                  ? (item['claim'] as String).trim()
                  : (item['text'] as String?)?.trim() ?? '',
            )
            .where((item) => item.isNotEmpty)
            .take(4)
            .toList(growable: false);
    if (fromPayload.isNotEmpty) return fromPayload;
    return evidenceLedger
        .map(
          (entry) => entry.snippet.trim().isNotEmpty
              ? entry.snippet.trim()
              : entry.title.trim(),
        )
        .where((item) => item.isNotEmpty)
        .take(4)
        .toList(growable: false);
  }

  RunArtifactsHistoricalThinkingSnapshot _buildHistoricalThinkingSnapshot({
    required Map<String, dynamic> raw,
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsHistoricalThinkingSnapshot.fromJson(raw)
        : const RunArtifactsHistoricalThinkingSnapshot();
    return RunArtifactsHistoricalThinkingSnapshot(
      continuityMode: parsed.continuityMode,
      mismatchSignal: parsed.mismatchSignal.isNotEmpty
          ? parsed.mismatchSignal
          : understandingSnapshot.mismatchSignal,
      carryForwardFacts: parsed.carryForwardFacts.isNotEmpty
          ? parsed.carryForwardFacts
          : understandingSnapshot.carryForwardFacts,
      discardedAssumptions: parsed.discardedAssumptions.isNotEmpty
          ? parsed.discardedAssumptions
          : understandingSnapshot.discardedAssumptions,
    );
  }

  RetrievalProcessingSnapshot _buildRetrievalProcessingSnapshot({
    required List<Map<String, dynamic>> uiReferences,
    required List<Map<String, dynamic>> toolResults,
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required SynthesisReadinessResult synthesisReadiness,
    required bool finalAnswerReady,
  }) {
    final acceptedReferences = uiReferences
        .map(
          (item) => RetrievalProcessingReference(
            title: (item['title'] as String?)?.trim() ?? '',
            url: (item['url'] as String?)?.trim() ?? '',
            source: (item['source'] as String?)?.trim() ?? '',
            snippet: (item['snippet'] as String?)?.trim() ?? '',
          ),
        )
        .where(
          (item) =>
              item.title.isNotEmpty ||
              item.url.isNotEmpty ||
              item.source.isNotEmpty,
        )
        .toList(growable: false);
    final processedDocumentCount = _resolveProcessedDocumentCount(
      uiReferences: uiReferences,
      toolResults: toolResults,
      acceptedDocumentCount: acceptedReferences.length,
    );
    return RetrievalProcessingSnapshot(
      processedDocumentCount: processedDocumentCount,
      acceptedDocumentCount: acceptedReferences.length,
      processingSummary: understandingSnapshot.queryDesignSummary.trim(),
      expansionReason: finalAnswerReady
          ? ''
          : _firstNonEmptyText(<String?>[synthesisReadiness.reason]),
      acceptedReferences: acceptedReferences,
    );
  }

  int _resolveProcessedDocumentCount({
    required List<Map<String, dynamic>> uiReferences,
    required List<Map<String, dynamic>> toolResults,
    required int acceptedDocumentCount,
  }) {
    var maxProcessed = acceptedDocumentCount;
    for (final item in uiReferences) {
      final total = (item['_totalSearched'] as num?)?.toInt() ?? 0;
      if (total > maxProcessed) {
        maxProcessed = total;
      }
    }
    var summedToolTotal = 0;
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      summedToolTotal += (data['totalReferences'] as num?)?.toInt() ?? 0;
    }
    if (summedToolTotal > maxProcessed) {
      maxProcessed = summedToolTotal;
    }
    return maxProcessed;
  }

  AssistantJourney _enrichJourneyWithStructuredSnapshots(
    AssistantJourney journey, {
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required RetrievalProcessingSnapshot retrievalProcessing,
    required RunArtifactsAnswerProcessing answerProcessing,
    required bool finalAnswerReady,
  }) {
    final entries = List<AssistantJourneyEntry>.of(journey.entries);
    var changed = false;

    if (!_hasVisibleJourneyEntry(entries, JourneyStageId.analyze)) {
      final headline = _buildUnderstandingJourneyHeadline(
        understandingSnapshot,
      );
      final detail = _buildUnderstandingJourneyDetail(understandingSnapshot);
      if (headline.isNotEmpty || detail.isNotEmpty) {
        entries.add(
          AssistantJourneyEntry(
            entryId: 'journey.analyze.snapshot',
            stageId: JourneyStageId.analyze,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: -10,
            headline: headline,
            detail: detail,
            provenance: const AssistantJourneyProvenance(source: 'snapshot'),
          ),
        );
        changed = true;
      }
    }

    if (!_hasVisibleJourneyEntry(entries, JourneyStageId.answer) &&
        finalAnswerReady) {
      final headline = answerProcessing.readinessSummary.trim();
      final detail = answerProcessing.keyFacts.take(2).join('；').trim();
      if (headline.isNotEmpty || detail.isNotEmpty) {
        entries.add(
          AssistantJourneyEntry(
            entryId: 'journey.answer.snapshot',
            stageId: JourneyStageId.answer,
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: 9990,
            headline: headline,
            detail: detail,
            provenance: const AssistantJourneyProvenance(source: 'snapshot'),
          ),
        );
        changed = true;
      }
    }

    if (!_hasVisibleJourneyEntry(entries, JourneyStageId.search) &&
        (retrievalProcessing.processingSummary.trim().isNotEmpty ||
            retrievalProcessing.acceptedReferences.isNotEmpty)) {
      final detail = _firstNonEmptyText(<String?>[
        understandingSnapshot.queryDesignSummary,
        retrievalProcessing.processingSummary,
      ]);
      entries.add(
        AssistantJourneyEntry(
          entryId: 'journey.search.snapshot',
          stageId: JourneyStageId.search,
          kind: retrievalProcessing.acceptedReferences.isNotEmpty
              ? JourneyEntryKind.referenceBundle
              : JourneyEntryKind.narrative,
          status: finalAnswerReady
              ? JourneyStageStatus.completed
              : JourneyStageStatus.active,
          order: 100,
          headline: '',
          detail: detail,
          references: retrievalProcessing.acceptedReferences
              .map(
                (item) => AssistantJourneyReference(
                  title: item.title.trim(),
                  url: item.url.trim(),
                  source: item.source.trim(),
                ),
              )
              .where(
                (item) =>
                    item.title.isNotEmpty &&
                    (item.url.isNotEmpty || item.source.isNotEmpty),
              )
              .toList(growable: false),
          provenance: const AssistantJourneyProvenance(source: 'snapshot'),
        ),
      );
      changed = true;
    }

    if (!changed) {
      return journey;
    }
    entries.sort((a, b) => a.order.compareTo(b.order));
    return AssistantJourney(
      stages: journey.stages,
      entries: entries,
      summary: journey.summary,
      referenceSummary: journey.referenceSummary,
      readiness: journey.readiness,
    );
  }

  bool _hasVisibleJourneyEntry(
    List<AssistantJourneyEntry> entries,
    JourneyStageId stageId,
  ) {
    for (final entry in entries) {
      final displayStageId = entry.stageId == JourneyStageId.verify
          ? JourneyStageId.search
          : entry.stageId;
      if (displayStageId != stageId) continue;
      if (_hasUserVisibleJourneyNarrative(entry, stageId: stageId)) {
        return true;
      }
      if (entry.references.isNotEmpty && stageId != JourneyStageId.search) {
        return true;
      }
    }
    return false;
  }

  String _buildUnderstandingJourneyHeadline(
    RunArtifactsUnderstandingSnapshot snapshot,
  ) {
    final intent = snapshot.intentSummary.trim();
    final concern = snapshot.concernPoints
        .where((item) => item.trim().isNotEmpty)
        .take(2)
        .join('、');
    final emotion = snapshot.emotionSignal.trim();
    if (intent.isEmpty && concern.isEmpty && emotion.isEmpty) {
      return '';
    }
    final buffer = StringBuffer('先确认');
    if (intent.isNotEmpty) {
      buffer.write('你想了解的是$intent');
    } else {
      buffer.write('当前问题的核心目标');
    }
    if (concern.isNotEmpty) {
      buffer.write('，重点看$concern');
    }
    if (emotion.isNotEmpty) {
      buffer.write('，也考虑到你当前$emotion');
    }
    buffer.write('。');
    return buffer.toString();
  }

  String _buildUnderstandingJourneyDetail(
    RunArtifactsUnderstandingSnapshot snapshot,
  ) {
    final lines = <String>[];
    final concern = snapshot.concernPoints
        .where((item) => item.trim().isNotEmpty)
        .take(3)
        .toList(growable: false);
    if (concern.isNotEmpty) {
      lines.add('你现在更在意的是${concern.join('、')}。');
    }
    final emotion = snapshot.emotionSignal.trim();
    if (emotion.isNotEmpty) {
      lines.add('我也留意到你现在$emotion。');
    }
    final focusGroups = snapshot.queryGroups
        .map(
          (group) => group.why.trim().isNotEmpty
              ? group.why.trim()
              : group.dimension.trim(),
        )
        .where((item) => item.isNotEmpty)
        .take(3)
        .toList(growable: false);
    if (focusGroups.isNotEmpty) {
      lines.add('我会先拆开确认${focusGroups.join('、')}，再判断能不能直接给你结论。');
    }
    return lines.join('\n').trim();
  }

  bool _hasUserVisibleJourneyNarrative(
    AssistantJourneyEntry entry, {
    required JourneyStageId stageId,
  }) {
    final candidates = <String>[entry.headline, entry.detail];
    for (final candidate in candidates) {
      final sanitized = _sanitizeJourneyCandidate(candidate);
      if (sanitized.isEmpty ||
          _isLowSignalJourneyNarrative(stageId, sanitized)) {
        continue;
      }
      return true;
    }
    return false;
  }

  String _sanitizeJourneyCandidate(String raw) {
    final normalized =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          AssistantDisplayTextResolver.stripRomanizedQueryLeakSentences(raw),
        ).trim();
    if (normalized.isEmpty) {
      return '';
    }
    if (RegExp(r'\{\{[^{}]+\}\}').hasMatch(normalized)) {
      return '';
    }
    if (AssistantContentFilters.isJsonEnvelope(normalized) ||
        AssistantContentFilters.isDegradedText(normalized) ||
        AssistantDisplayTextResolver.containsInternalPlannerNarrationFragment(
          normalized,
        ) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          normalized,
        ) ||
        AssistantDisplayTextResolver.containsTechnicalFailureFragment(
          normalized,
        ) ||
        normalized.toLowerCase().contains('token')) {
      return '';
    }
    return normalized;
  }

  bool _isLowSignalJourneyNarrative(JourneyStageId stageId, String text) {
    final normalized = text.trim();
    switch (stageId) {
      case JourneyStageId.analyze:
        return RegExp(r'^正在获取.+位置').hasMatch(normalized);
      case JourneyStageId.search:
        return normalized == '已完成资料筛选并进入成答' ||
            normalized == '已完成当前轮资料筛选' ||
            RegExp(r'^正在(?:交叉核对|搜索|查询|检索).+').hasMatch(normalized) ||
            RegExp(r'^已找到\s*\d+\s*篇相关资料$').hasMatch(normalized) ||
            RegExp(r'^已经有一批能支撑判断的信息了.+').hasMatch(normalized);
      case JourneyStageId.answer:
        return normalized == '已满足成答条件' ||
            RegExp(r'^我开始整理.+关键信息').hasMatch(normalized);
      default:
        return false;
    }
  }

  String _firstNonEmptyText(Iterable<String?> candidates) {
    for (final candidate in candidates) {
      final normalized = candidate?.trim() ?? '';
      if (normalized.isNotEmpty) {
        return normalized;
      }
    }
    return '';
  }

  String _extractProviderReasoningContinuation(
    List<AssistantTraceEvent> traces,
  ) {
    for (final trace in traces.reversed) {
      final data = trace.data;
      if (data == null) continue;
      final continuation =
          (data['providerReasoningContinuation'] as String?)?.trim() ?? '';
      if (continuation.isNotEmpty) {
        return continuation;
      }
    }
    return '';
  }

  List<SubagentPlan> _buildSkillRunPlans({
    required IntentGraph intentGraph,
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final explicitPlans = _buildExplicitSkillRunPlans(
      answerPayload: answerPayload,
      latestUserQuery: latestUserQuery,
      fallbackProblemClass: intentGraph.problemClassWireName,
      primaryDomainId: primaryDomainId,
    );
    if (explicitPlans.isNotEmpty) {
      return explicitPlans;
    }
    return _buildDerivedSkillRunPlansFromIntent(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
      primaryDomainId: primaryDomainId,
    );
  }

  List<SubagentPlan> _buildExplicitSkillRunPlans({
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String fallbackProblemClass,
    required String primaryDomainId,
  }) {
    final existingPlans =
        (answerPayload['subagentPlan'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (existingPlans.isEmpty) return const <SubagentPlan>[];
    return existingPlans
        .where(
          (item) =>
              ((item['domainId'] as String?)?.trim() ?? '').isNotEmpty &&
              ((item['domainId'] as String?)?.trim() ?? '') != primaryDomainId,
        )
        .map(
          (item) => _normalizeSubagentPlan(
            plan: item,
            latestUserQuery: latestUserQuery,
            fallbackProblemClass: fallbackProblemClass,
          ),
        )
        .toList(growable: false);
  }

  List<SubagentPlan> _buildDerivedSkillRunPlansFromIntent({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    return intentGraph.secondarySkills
        .where(
          (item) => item.trim().isNotEmpty && item.trim() != primaryDomainId,
        )
        .map(
          (skillId) => _normalizeSubagentPlan(
            plan: <String, dynamic>{
              'subagentId': 'skill_${skillId}_1',
              'domainId': skillId,
              'problemClass': intentGraph.problemClassWireName.isNotEmpty
                  ? intentGraph.problemClassWireName
                  : ProblemClass.general.wireName,
              'mode': 'qa',
              'goal': '围绕用户问题补充 $skillId 视角的关键信息：$latestUserQuery',
              'maxIterations': 2,
              'toolBudget': 2,
              'stopPolicy': StopPolicy.balanced.wireName,
              'searchIntensity':
                  intentGraph.problemClassType == ProblemClass.realtimeInfo
                  ? SearchIntensity.low.wireName
                  : SearchIntensity.medium.wireName,
            },
            latestUserQuery: latestUserQuery,
            fallbackProblemClass: intentGraph.problemClassWireName,
          ),
        )
        .toList(growable: false);
  }

  SubagentPlan _normalizeSubagentPlan({
    required Map<String, dynamic> plan,
    required String latestUserQuery,
    required String fallbackProblemClass,
  }) {
    final domainId = (plan['domainId'] as String?)?.trim() ?? '';
    final goal = (plan['goal'] as String?)?.trim() ?? '';
    final mode = (plan['mode'] as String?)?.trim() ?? 'qa';
    final rawProblemClass =
        (plan['problemClass'] as String?)?.trim() ?? fallbackProblemClass;
    return SubagentPlan.fromJson(<String, dynamic>{
      ...plan,
      'domainId': domainId,
      'goal': goal,
      'mode': mode,
      'problemClass': _normalizeProblemClassForQuery(
        raw: rawProblemClass,
        primarySkill: domainId,
        mode: mode,
        secondarySkills: const <String>[],
        queryText: goal.isNotEmpty ? goal : latestUserQuery,
      ),
      'stopPolicy': (plan['stopPolicy'] as String?)?.trim() ?? 'balanced',
      'searchIntensity':
          (plan['searchIntensity'] as String?)?.trim() ?? 'medium',
      'providerPolicy': (plan['providerPolicy'] as String?)?.trim() ?? '',
      'freshnessHoursMax': _nonNegativeInt(
        plan['freshnessHoursMax'],
        fallback: 0,
      ),
      'answerThreshold': _normalizedThreshold(
        plan['answerThreshold'],
        fallback: 0.0,
      ),
      'dependencies': _normalizeStringList(plan['dependencies']),
    });
  }

  SkillRun _buildPrimarySkillRun({
    required IntentGraph intentGraph,
    required String domainId,
    required Map<String, dynamic> answerPayload,
    required ReactRuntimeResult result,
    required SkillExecutionShell executionShell,
    required List<Map<String, dynamic>> references,
  }) {
    return SkillRun(
      runId: 'skill_primary_$domainId',
      domainId: domainId,
      goal: intentGraph.userGoal,
      problemClass: executionShell.problemClass,
      shell: executionShell.toJson(),
      slotState:
          (answerPayload['slotState'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      answerReady:
          (answerPayload['userMarkdown'] as String?)?.trim().isNotEmpty ==
              true ||
          (answerPayload['result'] as Map?) != null,
      stopReason: (answerPayload['messageKind'] as String?)?.trim() ?? '',
      references: references,
      resultSummary: _extractUiSummary(
        answerPayload,
        _resolveDisplayPlainText(
          answerPayload: answerPayload,
          displayMarkdown: _extractUiMarkdown(answerPayload, result.finalText),
          machineEnvelope: result.finalText,
        ),
      ),
    );
  }

  SkillRun _skillRunFromLegacySubagentRun(Map<String, dynamic> run) {
    final domainId = (run['domainId'] as String?)?.trim() ?? '';
    final status = (run['status'] as String?)?.trim() ?? 'unknown';
    final goal = (run['goal'] as String?)?.trim() ?? '';
    return SkillRun(
      runId: (run['subagentId'] as String?)?.trim() ?? 'skill_$domainId',
      domainId: domainId,
      goal: goal,
      problemClass: _normalizeProblemClassForQuery(
        raw: (run['problemClass'] as String?)?.trim() ?? '',
        primarySkill: domainId,
        mode: (run['mode'] as String?)?.trim() ?? 'qa',
        secondarySkills: const <String>[],
        queryText: goal,
      ),
      shell:
          (run['shell'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      answerReady: run['answerReady'] == true || status == 'success',
      stopReason: status,
      references:
          (run['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      resultSummary: (run['summary'] as String?)?.trim() ?? '',
    );
  }

  AggregationState _buildAggregationState({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    return _aggregationGate.evaluate(
      intentGraph: intentGraph,
      skillRuns: skillRuns,
      answerPayload: answerPayload,
    );
  }

  String _resolveMessageKind({
    required Map<String, dynamic> answerPayload,
    required String resultText,
  }) {
    final decision = AssistantTurnDecision.fromMaps(
      structured: <String, dynamic>{
        'messageKind': answerPayload['messageKind'],
      },
      answerPayload: answerPayload,
    );
    if (decision.messageKind != AssistantMessageKind.unknown) {
      return decision.messageKind.name;
    }
    switch (decision.nextAction) {
      case AssistantNextAction.toolCall:
        return 'progress';
      case AssistantNextAction.askUser:
        return 'ask_user';
      case AssistantNextAction.retry:
      case AssistantNextAction.abort:
        return 'fallback';
      case AssistantNextAction.answer:
        return 'answer';
      case AssistantNextAction.unknown:
        break;
    }
    if (AssistantContentFilters.isJsonEnvelope(resultText)) return 'fallback';
    if (AssistantContentFilters.isProgressPlaceholder(resultText)) {
      return 'progress';
    }
    return 'answer';
  }

  List<Map> _normalizeToolCalls(dynamic value) {
    if (value is List) {
      return value.whereType<Map>().toList(growable: false);
    }
    if (value is Map) return <Map>[value];
    return const <Map>[];
  }

  Map<String, dynamic> _normalizeMap(dynamic value) {
    if (value is Map) {
      return value.cast<String, dynamic>();
    }
    if (value is String && value.trim().isNotEmpty) {
      return <String, dynamic>{'text': value.trim()};
    }
    return const <String, dynamic>{};
  }

  /// 供模型消费的对话脚本，移除版本追踪字段，避免干扰指令理解。
  Map<String, dynamic> _dialogueScriptForModel(DialogueRoundScript script) {
    final json = Map<String, dynamic>.from(script.toJson());
    json.remove('routingCatalogVersion');
    json.remove('eventCatalogVersion');
    return json;
  }

  /// 供模型消费的子任务结果，移除版本追踪字段。
  List<Map<String, dynamic>> _subagentRunsForModel(
    List<Map<String, dynamic>> runs,
  ) {
    return runs
        .map((r) {
          return <String, dynamic>{
            'subagentId': (r['subagentId'] ?? '').toString(),
            'domainId': (r['domainId'] ?? '').toString(),
            'status': (r['status'] ?? '').toString(),
            'goal': (r['goal'] ?? '').toString(),
            'problemClass': (r['problemClass'] ?? '').toString(),
            'userMarkdown': (r['userMarkdown'] ?? '').toString(),
            'result':
                (r['result'] as Map?)?.cast<String, dynamic>() ??
                const <String, dynamic>{},
            'summary': (r['summary'] ?? '').toString(),
            'references':
                (r['references'] as List?)
                    ?.whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList(growable: false) ??
                const <Map<String, dynamic>>[],
          };
        })
        .toList(growable: false);
  }

  Map<String, dynamic> _normalizeModelSelfScore(dynamic value) {
    final mapped = _normalizeMap(value);
    if (mapped.isNotEmpty) return mapped;
    return const <String, dynamic>{'score': 0, 'reason': 'not_provided'};
  }

  List<String> _normalizeStringList(dynamic value) {
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

  List<Map<String, dynamic>> _normalizeMapList(
    dynamic value, {
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

  // JSON 解析已统一委托给 LlmResponseParser，不再在此文件内重复实现。

  Map<String, dynamic> _mergeSelfCheck({
    required Map<String, dynamic> answerPayload,
    required bool answerEligible,
    required String synthesisReason,
    required bool evidenceGatePassed,
  }) {
    final base =
        (answerPayload['selfCheck'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{};
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

  String _extractUiSummary(
    Map<String, dynamic> answerPayload,
    String fallback,
  ) {
    final turn = tryParseAssistantTurnOutput(answerPayload);
    final interpretation =
        turn?.interpretation ??
        (((answerPayload['result'] as Map?)?['interpretation'] as String?)
                ?.trim() ??
            '');
    if (interpretation.isNotEmpty) return interpretation;
    final text =
        turn?.resultText ??
        (((answerPayload['result'] as Map?)?['text'] as String?)?.trim() ?? '');
    if (text.isNotEmpty) return text;
    return fallback;
  }

  bool _isRealtimeLikeRequest({
    required String fallbackProblemClass,
    required Map<String, dynamic> answerPayload,
  }) {
    final payloadProblemClass =
        (answerPayload['problemClass'] as String?)?.trim().toLowerCase() ??
        (((answerPayload['decision'] as Map?)?['problemClass'] as String?)
                ?.trim()
                .toLowerCase() ??
            '');
    if (payloadProblemClass.isNotEmpty) {
      return parseProblemClass(payloadProblemClass) ==
          ProblemClass.realtimeInfo;
    }
    return parseProblemClass(fallbackProblemClass) == ProblemClass.realtimeInfo;
  }

  bool _toolContributesUiReferences(
    String toolName, {
    required bool allowLocationContext,
  }) {
    final normalized = toolName.trim();
    if (normalized.isEmpty) return false;
    final registry = _toolMetadataRegistry;
    return registry?.contributesUiReferences(
          normalized,
          allowLocationContext: allowLocationContext,
        ) ??
        false;
  }

  String _traceToolName(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    return (data['toolName'] as String?)?.trim() ?? '';
  }

  /// 从 finalText（可能是 JSON envelope）提取用于 session/记忆存储的纯文本。
  /// 委托给 [LlmResponseParser] 统一解析，避免 JSON 原文污染摘要和历史。
  String _extractDisplayTextForStorage(String finalText) {
    final t = finalText.trim();
    if (t.isEmpty) return '';
    if (!t.startsWith('{') &&
        !t.startsWith('```') &&
        !t.startsWith('<think>')) {
      return t;
    }
    final result = LlmResponseParser.parse(t);
    if (!result.ok) return '';
    return result.userMarkdown;
  }

  String _resolveDisplayPlainText({
    required Map<String, dynamic> answerPayload,
    required String displayMarkdown,
    required String machineEnvelope,
  }) {
    final result =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final directText = _sanitizeDisplayPlainCandidate(
      (result['text'] as String?)?.trim() ?? '',
    );
    if (directText.isNotEmpty) {
      return directText;
    }
    final summaryText = _sanitizeDisplayPlainCandidate(
      (result['summary'] as String?)?.trim() ?? '',
    );
    if (summaryText.isNotEmpty) {
      return summaryText;
    }
    final markdownSource = displayMarkdown.trim().isNotEmpty
        ? displayMarkdown
        : _extractDisplayTextForStorage(machineEnvelope);
    final plainFromMarkdown = _sanitizeDisplayPlainCandidate(
      _stripMarkdownForPlainText(markdownSource),
    );
    if (plainFromMarkdown.isNotEmpty) return plainFromMarkdown;
    final fallback = _sanitizeDisplayPlainCandidate(
      OpenAiCompatibleLlmProvider.stripXmlToolCalls(machineEnvelope),
    ).trim();
    if (fallback.isNotEmpty) {
      return fallback;
    }
    return '';
  }

  String _sanitizeDisplayPlainCandidate(String raw) {
    final text =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(raw);
    if (text.isEmpty) return '';
    if (AssistantContentFilters.isProgressPlaceholder(text) ||
        AssistantContentFilters.isJsonEnvelope(text)) {
      return '';
    }
    if (text.contains('assistant_turn') ||
        text.contains('contractId') ||
        text.contains('tool_call') ||
        text.contains('<tool_call>')) {
      return '';
    }
    return text;
  }

  String _stripMarkdownForPlainText(String markdown) {
    final raw = markdown.trim();
    if (raw.isEmpty) return '';
    var text = raw
        .replaceAllMapped(
          RegExp(r'\[([^\]]+)\]\(([^)]+)\)'),
          (match) => match.group(1) ?? '',
        )
        .replaceAllMapped(RegExp(r'`([^`]+)`'), (match) => match.group(1) ?? '')
        .replaceAll(RegExp(r'^#{1,6}\s*', multiLine: true), '')
        .replaceAll(RegExp(r'^\s*[-*+]\s+', multiLine: true), '')
        .replaceAll(RegExp(r'^\s*\d+\.\s+', multiLine: true), '')
        .replaceAll('**', '')
        .replaceAll('__', '')
        .replaceAll('*', '')
        .replaceAll('_', '')
        .replaceAll('```', '')
        .replaceAll('|', ' ')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n');
    final lines = text
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList(growable: false);
    text = lines.join('\n');
    return text.trim();
  }

  String _extractUiMarkdown(
    Map<String, dynamic> answerPayload,
    String fallback,
  ) {
    // nextAction != 'answer' 表示中间状态（进度占位），不应作为最终展示内容输出。
    // nextAction 来自 _parseAnswerPayload 注入到 result 中的值，属于受控 Map。
    final resultMap =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextAction = (resultMap['nextAction'] as String?)?.trim() ?? '';
    if (nextAction.isNotEmpty && nextAction != 'answer') return '';

    // 优先级 1：userMarkdown（契约标准字段，已通过 AssistantTurnOutput 类型化解析）
    final userMd = AssistantDisplayTextResolver.normalizeMarkdown(
      (answerPayload['userMarkdown'] as String?)?.trim() ?? '',
    );
    if (_isRenderableAssistantAnswerText(userMd)) {
      return userMd;
    }
    // 优先级 2：fallback（finalText），过滤 JSON 原文和进度文本
    final fb = AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
      fallback,
    );
    if (!_isRenderableAssistantAnswerText(fb)) {
      return '';
    }
    return fb;
  }

  bool _isRenderableAssistantAnswerText(String text) {
    final normalized = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
      text,
    ).trim();
    if (normalized.isEmpty) return false;
    if (AssistantContentFilters.isNotDisplayable(normalized)) return false;
    if (normalized.contains('assistant_turn') ||
        normalized.contains('contractId') ||
        normalized.contains('queryTasks') ||
        normalized.contains('tool_call')) {
      return false;
    }
    return true;
  }

  List<String> _chunkMarkdownForStreaming(String markdown) {
    final paragraphs = markdown.split(RegExp(r'\n\n'));
    final chunks = <String>[];
    for (int pi = 0; pi < paragraphs.length; pi++) {
      final paragraph = paragraphs[pi];
      if (paragraph.isEmpty) continue;
      final suffix = pi < paragraphs.length - 1 ? '\n\n' : '';
      if (paragraph.length <= 120) {
        chunks.add('$paragraph$suffix');
      } else {
        final sentences = paragraph.split(RegExp(r'(?<=[。！？；\n])'));
        final buffer = StringBuffer();
        for (final sentence in sentences) {
          buffer.write(sentence);
          if (buffer.length >= 80) {
            chunks.add(buffer.toString());
            buffer.clear();
          }
        }
        if (buffer.isNotEmpty) {
          chunks.add('${buffer.toString()}$suffix');
        } else if (suffix.isNotEmpty && chunks.isNotEmpty) {
          chunks[chunks.length - 1] = '${chunks.last}$suffix';
        }
      }
    }
    return chunks;
  }

  List<String> _buildNextActions(
    ContextAssemblyResult contextAssembly,
    SynthesisReadinessResult synthesisReadiness,
  ) {
    final out = <String>[];
    for (final task in contextAssembly.fillTasks) {
      out.add(task.reason);
    }
    if (!synthesisReadiness.ready && synthesisReadiness.gapFillTask != null) {
      out.add(synthesisReadiness.reason);
    }
    return out;
  }

  String _resolveExperimentBucket(Map<String, dynamic> hint, String fallback) {
    final raw = (hint['experimentBucket'] as String?)?.trim() ?? '';
    if (raw.isNotEmpty) return raw;
    return fallback;
  }

  Map<String, dynamic> _buildObservabilityPayload({
    required AssistantRunResponse response,
    required AssistantRunRequest request,
  }) {
    final structured = response.structuredResponse;
    final domainResults =
        (structured['domainResults'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final payload = AgentRunObservabilityPayload(
      kind: 'agent_run',
      templateId: 'synthesizer.final_answer',
      templateVersion:
          (structured['templateVersionUsed'] as String?)?.trim().isNotEmpty ==
              true
          ? (structured['templateVersionUsed'] as String).trim()
          : 'latest',
      structuredResponse: <String, dynamic>{
        'contextAssembly':
            structured['contextAssembly'] ?? const <String, dynamic>{},
        'domainPrecheck':
            structured['domainPrecheck'] ?? const <String, dynamic>{},
        'synthesisReadiness':
            structured['synthesisReadiness'] ?? const <String, dynamic>{},
        'contextSlots':
            structured['contextSlots'] ?? const <Map<String, dynamic>>[],
        'dialogueRuntime':
            structured['dialogueRuntime'] ?? const <String, dynamic>{},
        'roundTrace': structured['roundTrace'] ?? const <String, dynamic>{},
        'fillActions':
            structured['fillActions'] ?? const <Map<String, dynamic>>[],
        'missingCriticalSlots':
            structured['missingCriticalSlots'] ?? const <String>[],
        'answerEligibility': structured['answerEligibility'] ?? 'unknown',
        'selfCheck': structured['selfCheck'] ?? const <String, dynamic>{},
        'diagnostics': structured['diagnostics'] ?? const <String, dynamic>{},
        'webEvidencePacks':
            structured['webEvidencePacks'] ?? const <Map<String, dynamic>>[],
        'webEvidenceGate':
            structured['webEvidenceGate'] ?? const <String, dynamic>{},
      },
      domainRouting: <String, dynamic>{
        'catalogVersion': (structured['domainCatalogVersion'] as String?) ?? '',
        'candidateDomains':
            (structured['candidateDomains'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[],
        'domainScores': const <String, double>{},
        'selectedDomains': <String>[
          ((structured['dialogueRuntime'] as Map?)?['domainId'] as String?) ??
              'fallback_general_search',
        ],
        'fallbackTriggered':
            (((structured['dialogueRuntime'] as Map?)?['domainId']
                    as String?) ??
                '') ==
            'fallback_general_search',
        'fallbackReason': '',
      },
      retrievalRounds: <String, dynamic>{
        'retrievalRound': 1,
        'queryId': response.runId ?? '',
        'topicId': request.messages.isNotEmpty
            ? request.messages.last.content
            : '',
        'singleTopic': true,
        'providerHint': '',
        'scopeExpansionPolicy': '',
        'usedHistoricalStrategy': false,
      },
      gapFillChain: <String, dynamic>{
        'triggerReason':
            ((structured['synthesisReadiness'] as Map?)?['reason'] ?? '')
                .toString(),
        'contextFillTaskCount':
            ((structured['fillTasks'] as Map?)?['contextFillTasks'] as List?)
                ?.length ??
            0,
        'hasGapFillTask':
            ((structured['fillTasks'] as Map?)?['gapFillTask']) != null,
      },
      webPipeline: <String, dynamic>{
        'evidencePackCount':
            ((structured['webEvidencePacks'] as List?)?.length ?? 0),
        'gatePassed':
            ((structured['webEvidenceGate'] as Map?)?['passed']) == true,
      },
      profileProposalLifecycle: <String, dynamic>{
        'proposalId': response.profileUpdateProposal?.proposalId ?? '',
        'proposalStatus': response.profileUpdateProposal == null
            ? 'none'
            : 'created',
        'statusChangedAt': DateTime.now().toIso8601String(),
        'changedBy': 'assistant',
        'idempotencyKey': response.profileUpdateProposal?.proposalId ?? '',
      },
      userProfile: <String, dynamic>{
        'profileVersion': (structured['profileVersion'] ?? '').toString(),
        'profileReadAt': DateTime.now().toIso8601String(),
        'profileUpdateProposalId':
            response.profileUpdateProposal?.proposalId ?? '',
        'profileUpdateConfirmedByUser': false,
      },
      learningTrack: <String, dynamic>{
        'profileTagDelta':
            ((structured['learningSignals'] as Map?)?['profileTagDelta']) ??
            const <Map<String, dynamic>>[],
        'satisfactionProxy':
            ((structured['learningSignals'] as Map?)?['satisfactionProxy'] ??
                    'unknown')
                .toString(),
        'strategySelectionReason':
            ((structured['learningSignals']
                        as Map?)?['strategySelectionReason'] ??
                    '')
                .toString(),
      },
      sensitiveBoundary: _redactSensitiveProfile(structured: structured),
      resultSummary: <String, dynamic>{
        'toolResultCount':
            ((domainResults['toolResults'] as List?)?.length ?? 0),
        'toolErrorCount': ((domainResults['toolErrors'] as List?)?.length ?? 0),
        'degraded': response.degraded,
      },
      qualityMetrics: structured['qualityMetrics'] ?? const <String, dynamic>{},
    );
    return payload.toJson();
  }

  bool _usedHeuristicFallback(List<AssistantTraceEvent> traces) {
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

  bool _hasDegradedTrace(List<AssistantTraceEvent> traces) {
    for (final event in traces) {
      if (event.type != AssistantTraceEventType.assistantDelta) continue;
      final data = event.data ?? const <String, dynamic>{};
      if (data['degraded'] == true) return true;
    }
    return false;
  }

  List<Map<String, dynamic>> _extractWebEvidencePacks(
    List<Map<String, dynamic>> toolResults,
  ) {
    final packs = <Map<String, dynamic>>[];
    for (final item in toolResults) {
      final data = (item['data'] as Map?)?.cast<String, dynamic>();
      if (data == null) continue;
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
        // Layer 5: 新增 qualityScore 和 freshScore，供 synthesizer 参考资料展示使用
        'qualityScore': _asDouble(data['qualityScore']),
        'freshScore': _asDouble(data['freshScore']),
        'facts': data['facts'] ?? const <Map<String, dynamic>>[],
      });
    }
    return packs;
  }

  /// 从 assets 加载对应领域的 retrieval_policy.json。
  /// 若文件不存在或解析失败，返回空 Map，调用方使用默认值。
  Future<Map<String, dynamic>> _loadRetrievalPolicy(String domainId) async {
    if (domainId.isEmpty) return const <String, dynamic>{};
    const basePath = 'assets/assistant/skills';
    final path = '$basePath/$domainId/config/retrieval_policy.json';
    try {
      final raw = await rootBundle.loadString(path);
      final decoded = jsonDecode(raw);
      if (decoded is Map) return decoded.cast<String, dynamic>();
    } catch (_) {
      // Asset missing or malformed — caller falls back to defaults.
    }
    return const <String, dynamic>{};
  }

  _PrecomputedBootstrap? _recoverPrecomputedBootstrap(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw = (contextScopeHint['precomputedBootstrap'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return _PrecomputedBootstrap(
        sessionId: (raw['sessionId'] as String?)?.trim() ?? 'default',
        latestUserQuery: (raw['latestUserQuery'] as String?)?.trim() ?? '',
        historySummary: (raw['historySummary'] as String?) ?? '',
        recalledTexts:
            (raw['recalledTexts'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        previousIntentGraph: raw['previousIntentGraph'] is Map
            ? IntentGraph.fromJson(
                (raw['previousIntentGraph'] as Map).cast<String, dynamic>(),
              )
            : null,
        previousAnswerSummary:
            (raw['previousAnswerSummary'] as String?)?.trim() ?? '',
        previousUnderstandingSnapshot:
            raw['previousUnderstandingSnapshot'] is Map
            ? RunArtifactsUnderstandingSnapshot.fromJson(
                (raw['previousUnderstandingSnapshot'] as Map)
                    .cast<String, dynamic>(),
              )
            : const RunArtifactsUnderstandingSnapshot(),
        previousAnswerProcessing: raw['previousAnswerProcessing'] is Map
            ? RunArtifactsAnswerProcessing.fromJson(
                (raw['previousAnswerProcessing'] as Map)
                    .cast<String, dynamic>(),
              )
            : const RunArtifactsAnswerProcessing(),
        historicalThinkingSnapshot: raw['historicalThinkingSnapshot'] is Map
            ? RunArtifactsHistoricalThinkingSnapshot.fromJson(
                (raw['historicalThinkingSnapshot'] as Map)
                    .cast<String, dynamic>(),
              )
            : const RunArtifactsHistoricalThinkingSnapshot(),
        providerReasoningContinuation:
            (raw['providerReasoningContinuation'] as String?)?.trim() ?? '',
        continuityPolicy: raw['contextContinuityPolicy'] is Map
            ? ContextContinuityPolicy.fromJson(
                (raw['contextContinuityPolicy'] as Map).cast<String, dynamic>(),
              )
            : const ContextContinuityPolicy(),
        continuityOverrideSlots:
            (raw['continuityOverrideSlots'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
        recallResult: raw['recallResult'] is Map
            ? RecallResult.fromJson(
                (raw['recallResult'] as Map).cast<String, dynamic>(),
              )
            : const RecallResult(topK: <RecallCandidate>[]),
        forceRefreshCatalog: raw['forceRefreshCatalog'] == true,
        domainCatalog:
            (raw['domainCatalog'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        domainCatalogVersion:
            (raw['domainCatalogVersion'] as String?)?.trim() ?? '',
        fullSkillCatalog: (raw['fullSkillCatalog'] as String?) ?? '',
        skillCatalog: (raw['skillCatalog'] as String?) ?? '',
        contextAssembly: raw['contextAssembly'] is Map
            ? ContextAssemblyResult.fromJson(
                (raw['contextAssembly'] as Map).cast<String, dynamic>(),
              )
            : null,
        previousRunArtifacts: raw['previousRunArtifacts'] is Map
            ? parseRunArtifacts(
                (raw['previousRunArtifacts'] as Map).cast<String, dynamic>(),
              )
            : null,
      );
    } catch (_) {
      return null;
    }
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

  _PrecomputedUnderstand? _recoverPrecomputedUnderstand(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw = (contextScopeHint['precomputedUnderstand'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      final modeRaw =
          (raw['modeDecision'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      return _PrecomputedUnderstand(
        domainId: (raw['domainId'] as String?)?.trim() ?? '',
        dialogueRoundScript: raw['dialogueRoundScript'] is Map
            ? _dialogueRoundScriptFromJson(
                (raw['dialogueRoundScript'] as Map).cast<String, dynamic>(),
              )
            : null,
        modeDecision: ModeDecision.fromJson(modeRaw),
      );
    } catch (_) {
      return null;
    }
  }

  _PrecomputedRetrieval? _recoverPrecomputedRetrieval(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw = (contextScopeHint['precomputedRetrieval'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return _PrecomputedRetrieval(
        skillName: (raw['skillName'] as String?)?.trim() ?? '',
        skillInstructionMarkdown:
            (raw['skillInstructionMarkdown'] as String?) ?? '',
        skillPersona: (raw['skillPersona'] as String?) ?? '',
        allowedToolNames:
            (raw['allowedToolNames'] as List?)
                ?.map((item) => item.toString().trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        executionShell: raw['executionShell'] is Map
            ? SkillExecutionShell.fromJson(
                (raw['executionShell'] as Map).cast<String, dynamic>(),
              )
            : const SkillExecutionShell(),
        plannerTemplateVersion:
            (raw['plannerTemplateVersion'] as String?)?.trim() ?? '',
        postcheckTemplateVersion:
            (raw['postcheckTemplateVersion'] as String?)?.trim() ?? '',
        synthTemplateVersion:
            (raw['synthTemplateVersion'] as String?)?.trim() ?? '',
        fusionSynthTemplateVersion:
            (raw['fusionSynthTemplateVersion'] as String?)?.trim() ?? '',
        previousSlotState: raw['previousSlotState'] is Map
            ? SlotStateSnapshot.fromJson(
                (raw['previousSlotState'] as Map).cast<String, dynamic>(),
              )
            : const SlotStateSnapshot(),
        previousDomainPolicyBundle: raw['previousDomainPolicyBundle'] is Map
            ? DomainPolicyBundle.fromJson(
                (raw['previousDomainPolicyBundle'] as Map)
                    .cast<String, dynamic>(),
              )
            : null,
      );
    } catch (_) {
      return null;
    }
  }

  AssistantExecutionPreparation? _recoverPrecomputedExecutionPreparation(
    Map<String, dynamic> contextScopeHint, {
    _PrecomputedUnderstand? precomputedUnderstand,
    _PrecomputedRetrieval? precomputedRetrieval,
  }) {
    final raw = (contextScopeHint['precomputedExecutionPreparation'] as Map?)
        ?.cast<String, dynamic>();
    if (raw != null && raw.isNotEmpty) {
      try {
        return AssistantExecutionPreparation.fromJson(raw);
      } catch (_) {
        // Fall through to compatibility recovery.
      }
    }
    if (precomputedUnderstand == null && precomputedRetrieval == null) {
      return null;
    }
    return AssistantExecutionPreparation(
      domainId: precomputedUnderstand?.domainId ?? '',
      modeDecision:
          precomputedUnderstand?.modeDecision ??
          const ModeDecision(
            mode: AgentMode.singleAgent,
            reason: 'default_single',
          ),
      skillName: precomputedRetrieval?.skillName ?? '',
      skillInstructionMarkdown:
          precomputedRetrieval?.skillInstructionMarkdown ?? '',
      skillPersona: precomputedRetrieval?.skillPersona ?? '',
      allowedToolNames:
          precomputedRetrieval?.allowedToolNames ?? const <String>[],
      executionShell:
          precomputedRetrieval?.executionShell ?? const SkillExecutionShell(),
      plannerTemplateVersion:
          precomputedRetrieval?.plannerTemplateVersion ?? '',
      postcheckTemplateVersion:
          precomputedRetrieval?.postcheckTemplateVersion ?? '',
      synthTemplateVersion: precomputedRetrieval?.synthTemplateVersion ?? '',
      fusionSynthTemplateVersion:
          precomputedRetrieval?.fusionSynthTemplateVersion ?? '',
      previousSlotState:
          precomputedRetrieval?.previousSlotState ?? const SlotStateSnapshot(),
      previousDomainPolicyBundle:
          precomputedRetrieval?.previousDomainPolicyBundle,
    );
  }

  DialogueRoundScript _dialogueRoundScriptFromJson(Map<String, dynamic> json) {
    final dto = DialogueRoundScriptDto.fromJson(json);
    return DialogueRoundScript(
      domainId: dto.domainId,
      enabled: dto.enabled,
      currentStateId: dto.currentStateId,
      detectedEvent: dto.detectedEvent,
      suggestedNextStateId: dto.suggestedNextStateId,
      nextStateCandidates: dto.nextStateCandidates,
      requiredFieldsForNextState: dto.requiredFieldsForNextState,
      totalSubTotalRequired: dto.totalSubTotalRequired,
      optionalEnrichment: dto.optionalEnrichment,
      maxQuestionsPerTurn: dto.maxQuestionsPerTurn,
      hardFailCodes: dto.hardFailCodes,
      passCriteriaRound: dto.passCriteriaRound,
      statePromptExcerpt: dto.statePromptExcerpt,
      stateMachineExcerpt: dto.stateMachineExcerpt,
      routingCatalogVersion: dto.routingCatalogVersion,
      eventCatalogVersion: dto.eventCatalogVersion,
    );
  }

  RunArtifacts? _recoverPreviousRunArtifacts(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw = (contextScopeHint['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return parseRunArtifacts(raw);
    } catch (_) {
      return null;
    }
  }

  List<Map<String, dynamic>> _toolResultsForEvidenceLedger(
    List<Map<String, dynamic>> toolResults,
  ) {
    return toolResults
        .map((item) {
          final data =
              (item['data'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
          return <String, dynamic>{
            'toolName': (data['toolName'] as String?)?.trim().isNotEmpty == true
                ? (data['toolName'] as String).trim()
                : (item['toolName'] as String?)?.trim() ?? '',
            'data': data,
          };
        })
        .toList(growable: false);
  }

  List<String> _blockingEvidenceDimensions({
    required List<QueryTask> queryTasks,
    required List<Map<String, dynamic>> toolResults,
  }) {
    final dimensions = <String>{};
    for (final item in toolResults) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final explicitBlocking =
          (data['blockingDimensions'] as List?)
              ?.whereType<String>()
              .map(
                (value) =>
                    parseQueryTaskDimension(value.trim()) !=
                        QueryTaskDimension.unknown
                    ? parseQueryTaskDimension(value.trim()).wireName
                    : value.trim(),
              )
              .where((value) => value.isNotEmpty) ??
          const Iterable<String>.empty();
      dimensions.addAll(explicitBlocking);
    }
    if (dimensions.isNotEmpty) {
      return dimensions.toList(growable: false);
    }
    return AnswerBoundaryResolver.normalizedTaskDimensions(queryTasks);
  }

  Map<String, dynamic> _applyConversationStateDecision(
    Map<String, dynamic> answerPayload,
    ConversationStateDecision decision, {
    required EvidenceEvaluationResult evidenceEvaluation,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    final turn = tryParseAssistantTurnOutput(answerPayload);
    final diagnostics =
        (answerPayload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final existingDecision =
        turn?.decision.toJson() ??
        (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final existingAskUser =
        turn?.askUser.toJson() ??
        (answerPayload['askUser'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final sanitizedAskUser = _sanitizeAskUserPayload(
      existingAskUser: existingAskUser,
      decision: decision,
    );
    final userMarkdown =
        turn?.userMarkdown.trim() ??
        (answerPayload['userMarkdown'] as String?)?.trim() ??
        '';
    final resultText =
        turn?.resultText ??
        ((answerPayload['result'] as Map?)?['text'] as String?)?.trim() ??
        '';
    final hasRenderableAnswer =
        _isRenderableAssistantAnswerText(userMarkdown) ||
        _isRenderableAssistantAnswerText(resultText);
    final messageKind = decision.nextActionType == AssistantNextAction.askUser
        ? AssistantMessageKind.askUser.wireName
        : (decision.nextActionType == AssistantNextAction.answer &&
                  hasRenderableAnswer
              ? AssistantMessageKind.answer.wireName
              : AssistantMessageKind.fallback.wireName);
    return <String, dynamic>{
      ...answerPayload,
      'messageKind': messageKind,
      'slotState': _slotStatePayloadFromSnapshot(decision.slotState),
      'missingContextSlots': decision.missingCriticalSlots,
      'askUser': sanitizedAskUser,
      'followupPrompt': '',
      'actionHints': const <String>[],
      'decision': <String, dynamic>{
        ...existingDecision,
        ...decision.toDecisionMap(),
        'synthesisReady': synthesisReadiness.ready,
        'synthesisReason': synthesisReadiness.reason,
        'evidenceSummary': evidenceEvaluation.summary,
      },
      'diagnostics': <String, dynamic>{
        ...diagnostics,
        'qualityGates': decision.qualityGatesData,
        'evidenceSummary': evidenceEvaluation.summary,
        'evidencePassed': evidenceEvaluation.passed,
        'finalAnswerMode': decision.finalAnswerModeWireName,
        'answerEligibility': decision.answerEligibilityWireName,
        'synthesisReady': synthesisReadiness.ready,
        'synthesisReason': synthesisReadiness.reason,
      },
    };
  }

  Map<String, dynamic> _sanitizeAskUserPayload({
    required Map<String, dynamic> existingAskUser,
    required ConversationStateDecision decision,
  }) {
    final prompt =
        (existingAskUser['prompt'] as String?)?.trim().isNotEmpty == true
        ? (existingAskUser['prompt'] as String).trim()
        : decision.askUser.prompt.trim();
    final slotId =
        (existingAskUser['slotId'] as String?)?.trim().isNotEmpty == true
        ? (existingAskUser['slotId'] as String).trim()
        : decision.askUser.slotId.trim();
    final suggestions =
        (existingAskUser['suggestions'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        decision.askUser.suggestions;
    final required =
        existingAskUser['required'] == true || decision.askUser.required;
    return <String, dynamic>{
      'slotId': slotId,
      'prompt': prompt,
      'required': required,
      'suggestions': suggestions,
    };
  }

  Map<String, dynamic> _slotStatePayloadFromSnapshot(
    SlotStateSnapshot slotState,
  ) => slotState.toJson();

  List<Map<String, dynamic>> _buildUiReferencesFromLedger(
    List<EvidenceLedgerEntry> ledger, {
    required List<Map<String, dynamic>> toolResults,
    required String domainId,
    required bool isRealtimeLike,
  }) {
    if (ledger.isEmpty) {
      return _buildUiReferences(toolResults, isRealtimeLike: isRealtimeLike);
    }
    final refs = <Map<String, dynamic>>[];
    final seen = <String>{};
    final totalSearched = toolResults.fold<int>(0, (sum, item) {
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      return sum + ((data['totalReferences'] as num?)?.toInt() ?? 0);
    });
    for (final entry in ledger) {
      final source = entry.source.isNotEmpty
          ? entry.source
          : (entry.sourceHost.isNotEmpty ? entry.sourceHost : entry.url);
      final dedupeKey = '${source.toLowerCase()}|${entry.title.toLowerCase()}';
      if (!seen.add(entry.url) || !seen.add(dedupeKey)) continue;
      refs.add(<String, dynamic>{
        'evidenceId': entry.evidenceId,
        'title': entry.title.isNotEmpty ? entry.title : source,
        'url': entry.url,
        'source': source,
        'provider': entry.queryTaskId,
        'snippet': entry.snippet,
        'cited':
            entry.sourceTierType == EvidenceSourceTier.authority ||
            entry.authorityScore >= 0.8,
        'authorityScore': entry.authorityScore,
        'dimension': entry.effectiveDimensionLabel,
        'queryTaskId': entry.queryTaskId,
      });
    }
    refs.sort((a, b) {
      final citedDelta =
          ((b['cited'] == true) ? 1 : 0) - ((a['cited'] == true) ? 1 : 0);
      if (citedDelta != 0) return citedDelta;
      final authorityDelta =
          (((b['authorityScore'] as num?)?.toDouble() ?? 0.0) * 100).round() -
          (((a['authorityScore'] as num?)?.toDouble() ?? 0.0) * 100).round();
      if (authorityDelta != 0) return authorityDelta;
      return 0;
    });
    final curated = isRealtimeLike
        ? refs
              .where((item) => item['cited'] == true)
              .take(4)
              .toList(growable: false)
        : refs.take(8).toList(growable: false);
    if (curated.isNotEmpty && totalSearched > 0) {
      curated.first['_totalSearched'] = totalSearched;
    }
    return curated;
  }

  DomainPolicyBundle _buildDomainPolicyBundle({
    required String domainId,
    required SkillExecutionShell skillExecutionShell,
    required SlotSchema slotSchema,
    required DialogueRoundScript dialogueRoundScript,
    required Map<String, dynamic> retrievalPolicy,
    required EvidenceEvaluationResult evidenceEvaluation,
    required ConversationStateDecision stateDecision,
    DomainPolicyBundle? previous,
  }) {
    return DomainPolicyBundle(
      domainId: domainId,
      executionPolicy: <String, dynamic>{
        ...?previous?.executionPolicy,
        'problemClass': skillExecutionShell.problemClass,
        'maxIterations': skillExecutionShell.maxIterations,
        'toolBudget': skillExecutionShell.toolBudget,
        'variantBudget': skillExecutionShell.variantBudget,
        'reflectionBudget': skillExecutionShell.reflectionBudget,
        'providerPolicy': skillExecutionShell.providerPolicy,
        'preferredProviders': skillExecutionShell.preferredProviders,
        'freshnessHoursMax': skillExecutionShell.freshnessHoursMax,
        'finalAnswerMode': stateDecision.finalAnswerModeWireName,
        'nextAction': stateDecision.nextActionWireName,
      },
      slotSchema: <String, dynamic>{
        ...?previous?.slotSchema,
        ...slotSchema.toSchemaMap(),
      },
      dialoguePolicy: <String, dynamic>{
        ...?previous?.dialoguePolicy,
        'currentStateId': dialogueRoundScript.currentStateId,
        'suggestedNextStateId': dialogueRoundScript.suggestedNextStateId,
        'detectedEvent': dialogueRoundScript.detectedEvent,
        'requiredFieldsForNextState':
            dialogueRoundScript.requiredFieldsForNextState,
        'missingCriticalSlots': stateDecision.missingCriticalSlots,
        'askUser': stateDecision.askUserData,
      },
      authorityPolicy: <String, dynamic>{
        ...?previous?.authorityPolicy,
        'authorityRequired': retrievalPolicy['authorityRequired'] == true,
        'authoritySatisfied': evidenceEvaluation.authoritySatisfied,
        'freshnessSatisfied': evidenceEvaluation.freshnessSatisfied,
      },
      retrievalPolicy: <String, dynamic>{
        ...?previous?.retrievalPolicy,
        ...retrievalPolicy,
        'coveredDimensions': evidenceEvaluation.coveredDimensions,
        'missingDimensions': evidenceEvaluation.missingDimensions,
        'coveredQueryTaskIds': evidenceEvaluation.coveredQueryTaskIds,
      },
      answerPolicy: <String, dynamic>{
        ...?previous?.answerPolicy,
        'answerEligibility': stateDecision.answerEligibilityWireName,
        'finalAnswerMode': stateDecision.finalAnswerModeWireName,
        'qualityGates': stateDecision.qualityGatesData,
      },
      narrativePolicy: <String, dynamic>{
        ...?previous?.narrativePolicy,
        'style': 'user_facing',
        'referencesMode': 'inline_links',
        'fallbackReasoning': evidenceEvaluation.summary,
      },
    );
  }

  List<SkillRun> _finalizeSkillRuns({
    required List<SkillRun> skillRuns,
    required String primaryDomainId,
    required SlotStateSnapshot slotState,
    required bool answerReady,
    required String stopReason,
    required List<Map<String, dynamic>> references,
    required String resultSummary,
  }) {
    return skillRuns
        .map((item) {
          if (item.domainId != primaryDomainId) return item;
          return SkillRun(
            runId: item.runId,
            domainId: item.domainId,
            goal: item.goal,
            problemClass: item.problemClass,
            shell: item.shell,
            slotState: _slotStatePayloadFromSnapshot(slotState),
            answerReady: answerReady,
            stopReason: stopReason,
            references: references,
            resultSummary: resultSummary,
          );
        })
        .toList(growable: false);
  }

  double _asDouble(Object? raw) {
    if (raw is num) return raw.toDouble();
    return double.tryParse(raw?.toString() ?? '') ?? 0;
  }

  List<Map<String, dynamic>> _buildContextSlots(
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

  /// Uses the LLM to semantically compress a session transcript.
  /// Returns the compressed summary, or rethrows on failure (caller handles fallback).
  /// Builds domain results payload from traces for synthesizer injection.
  Map<String, dynamic> _buildDomainResultsForSynthesis(
    List<AssistantTraceEvent> traces,
  ) {
    final toolResults = traces
        .where((e) => e.type == AssistantTraceEventType.toolResult)
        .map(
          (e) => <String, dynamic>{
            'message': e.message,
            'data': e.data ?? const <String, dynamic>{},
            'toolCallId': e.toolCallId ?? '',
          },
        )
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
    final webEvidencePacks = _extractWebEvidencePacks(toolResults);
    return <String, dynamic>{
      'toolResults': toolResults,
      'toolErrors': toolErrors,
      'toolResultCount': toolResults.length,
      'toolErrorCount': toolErrors.length,
      'webEvidencePacks': webEvidencePacks,
    };
  }

  Map<String, dynamic> _buildTemplateVariables({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required String domainId,
    required String domainSkillInstruction,
    required String domainSkillName,
    required List<String> availableToolNames,
    required DialogueRoundScript dialogueRoundScript,
    String skillPersona = '',
    String skillCatalog = '',
    required SkillExecutionShell skillExecutionShell,
    SlotStateSnapshot previousSlotState = const SlotStateSnapshot(),
    DomainPolicyBundle? previousDomainPolicyBundle,
    IntentGraph? intentGraph,
    AnswerBoundaryPolicy answerBoundaryPolicy = const AnswerBoundaryPolicy(),
    IntentGraph? previousIntentGraph,
    String previousAnswerSummary = '',
    ContextContinuityPolicy continuityPolicy = const ContextContinuityPolicy(),
    Map<String, dynamic> continuityOverrideSlots = const <String, dynamic>{},
  }) {
    final query = request.messages.isEmpty ? '' : request.messages.last.content;
    final toolGuidelines =
        _toolMetadataRegistry?.invocationGuidelinesForTools(
          availableToolNames,
        ) ??
        const <Map<String, dynamic>>[];
    return <String, dynamic>{
      'userQuery': query,
      'deviceProfile': request.deviceProfile,
      'deviceModel': request.deviceModel,
      'deviceOs': request.deviceOs,
      'gpsLocation': request.gpsLocation,
      'userProfileSnapshot': request.userProfileSnapshot,
      'historicalRetrievalFeedback':
          (request.contextScopeHint['historicalRetrievalFeedback'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'domainLearningSignals':
          (request.contextScopeHint['domainLearningSignals'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      'domainId': domainId,
      'domainSkillName': domainSkillName,
      'domainSkillInstruction': domainSkillInstruction,
      'contextEnvelope': contextAssembly.contextEnvelope,
      'availableTools': availableToolNames,
      'toolInvocationGuidelines': toolGuidelines,
      'dialogueRoundScript': _dialogueScriptForModel(dialogueRoundScript),
      'slotStateSnapshot': previousSlotState.toJson(),
      'domainPolicyBundle':
          previousDomainPolicyBundle?.toJson() ?? const <String, dynamic>{},
      'answerBoundaryPolicy': answerBoundaryPolicy.toJson(),
      'allowBoundedAnswer': answerBoundaryPolicy.allowBoundedAnswer,
      if (previousIntentGraph != null)
        'previousIntentGraphJson': jsonEncode(previousIntentGraph.toJson()),
      'previousAnswerSummary': previousAnswerSummary,
      'continuityMode': continuityPolicy.continuityMode.wireName,
      'continuityPolicy': continuityPolicy.toJson(),
      'continuityOverrideSlots': continuityOverrideSlots,
      'skillPersona': skillPersona,
      'skillCatalog': skillCatalog,
      'skillExecutionShell': <String, dynamic>{
        ...skillExecutionShell.toJson(),
        if (intentGraph?.queryTasks != null &&
            intentGraph!.queryTasks.isNotEmpty)
          'preComputedQueryTasks': intentGraph.queryTasks
              .map((t) => t.toJson())
              .toList(growable: false),
      },
      'problemClass': skillExecutionShell.problemClass,
      'traceId': '',
    };
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

  Map<String, dynamic> _buildRoundTrace({
    required AssistantRunRequest request,
    required ReactRuntimeResult result,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final toolStarts = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map(
          (event) => <String, dynamic>{
            'toolName': _traceToolName(event),
            'toolCallId': event.toolCallId ?? '',
            'arguments': event.data ?? const <String, dynamic>{},
          },
        )
        .toList(growable: false);
    final toolResults = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .length;
    final toolErrors = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolError)
        .length;
    return <String, dynamic>{
      'domainId': dialogueRoundScript.domainId,
      'stateId': dialogueRoundScript.currentStateId,
      'event': dialogueRoundScript.detectedEvent,
      'suggestedNextStateId': dialogueRoundScript.suggestedNextStateId,
      'nextStateCandidates': dialogueRoundScript.nextStateCandidates,
      'requiredFieldsForNextState':
          dialogueRoundScript.requiredFieldsForNextState,
      'totalSubTotalRequired': dialogueRoundScript.totalSubTotalRequired,
      'query': request.messages.isNotEmpty ? request.messages.last.content : '',
      'assistantResponse': result.finalText,
      'toolCalls': toolStarts,
      'toolResultCount': toolResults,
      'toolErrorCount': toolErrors,
      'timestamp': DateTime.now().toIso8601String(),
    };
  }

  /// Returns [fallbackDomainId]. In the LLM-first architecture the model
  /// autonomously selects the domain via the planner prompt; pre-classification
  /// is no longer needed. Kept for backward compatibility with UI callers.
  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) async {
    await _domainRouter.ensureLoaded();
    return _domainRouter.fallbackDomainId;
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

  Map<String, dynamic> _redactSensitiveProfile({
    required Map<String, dynamic> structured,
  }) {
    final basicIdentity =
        (structured['basicIdentity'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final ipResidence =
        (structured['ipResidenceProfile'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return <String, dynamic>{
      'birthDateSolar': _maskDate(
        (basicIdentity['birthDateSolar'] ?? '').toString(),
      ),
      'birthDateLunar': _maskDate(
        (basicIdentity['birthDateLunar'] ?? '').toString(),
      ),
      'ageRange': _ageRangeLabel((basicIdentity['age'] as num?)?.toInt()),
      'ipResidenceProfile': <String, dynamic>{
        'home': _maskResidence(ipResidence['home']),
        'office': _maskResidence(ipResidence['office']),
        'study': _maskResidence(ipResidence['study']),
      },
      'retentionPolicy': 'sensitive_fields_30d_masked',
      'deleteMark': false,
    };
  }

  String _ageRangeLabel(int? age) {
    if (age == null || age <= 0) return '';
    if (age < 18) return '<18';
    if (age <= 24) return '18-24';
    if (age <= 34) return '25-34';
    if (age <= 44) return '35-44';
    if (age <= 54) return '45-54';
    return '55+';
  }

  String _maskDate(String raw) {
    if (raw.isEmpty) return '';
    if (raw.length <= 4) return '****';
    return '${raw.substring(0, 4)}-**-**';
  }

  String _maskResidence(dynamic value) {
    final text = (value ?? '').toString().trim();
    if (text.isEmpty) return '';
    if (text.length <= 2) return '${text.substring(0, 1)}*';
    return '${text.substring(0, 2)}**';
  }

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

  Future<List<Map<String, dynamic>>> listSessions() async {
    await _sessionManager.load();
    _sessionManager.ensureAssistantActiveSession();
    return _sessionManager.listSessionDescriptors();
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    await _sessionManager.load();
    final messages = _sessionManager.sessions[sessionId];
    if (messages == null) return null;
    return <String, dynamic>{
      'sessionId': sessionId,
      'messages': messages,
      'summary': _sessionManager.summarizeRecent(sessionId),
      'topicTitle': _sessionManager.topicTitleOf(sessionId),
      'sessionPreferenceFacts': _sessionManager
          .sessionPreferenceFactsOf(sessionId)
          .map((item) => item.toJson())
          .toList(growable: false),
      'longTermPreferenceFacts': _sessionManager
          .longTermPreferenceFactsOf(sessionId)
          .map((item) => item.toJson())
          .toList(growable: false),
    };
  }

  Future<void> switchSession(String sessionId) async {
    await _sessionManager.load();
    _sessionManager.switchAssistantSession(sessionId);
    await _sessionManager.save();
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
    answerBoundaryResolver: _answerBoundaryResolver,
  );

  FinalizeRunner buildFinalizeRunner() => FinalizeRunner(
    sessionManager: _sessionManager,
    memoryRepository: _memoryRepository,
    buildObservabilityPayload: ({required response, required request}) =>
        _buildObservabilityPayload(response: response, request: request),
  );
}

class _PrecomputedBootstrap {
  const _PrecomputedBootstrap({
    required this.sessionId,
    required this.latestUserQuery,
    required this.historySummary,
    required this.recalledTexts,
    this.previousIntentGraph,
    this.previousAnswerSummary = '',
    this.previousUnderstandingSnapshot =
        const RunArtifactsUnderstandingSnapshot(),
    this.previousAnswerProcessing = const RunArtifactsAnswerProcessing(),
    this.historicalThinkingSnapshot =
        const RunArtifactsHistoricalThinkingSnapshot(),
    this.providerReasoningContinuation = '',
    required this.continuityPolicy,
    this.continuityOverrideSlots = const <String, dynamic>{},
    required this.recallResult,
    required this.forceRefreshCatalog,
    required this.domainCatalog,
    required this.domainCatalogVersion,
    required this.fullSkillCatalog,
    required this.skillCatalog,
    this.contextAssembly,
    this.previousRunArtifacts,
  });

  final String sessionId;
  final String latestUserQuery;
  final String historySummary;
  final List<String> recalledTexts;
  final IntentGraph? previousIntentGraph;
  final String previousAnswerSummary;
  final RunArtifactsUnderstandingSnapshot previousUnderstandingSnapshot;
  final RunArtifactsAnswerProcessing previousAnswerProcessing;
  final RunArtifactsHistoricalThinkingSnapshot historicalThinkingSnapshot;
  final String providerReasoningContinuation;
  final ContextContinuityPolicy continuityPolicy;
  final Map<String, dynamic> continuityOverrideSlots;
  final RecallResult recallResult;
  final bool forceRefreshCatalog;
  final List<String> domainCatalog;
  final String domainCatalogVersion;
  final String fullSkillCatalog;
  final String skillCatalog;
  final ContextAssemblyResult? contextAssembly;
  final RunArtifacts? previousRunArtifacts;
}

class _PrecomputedUnderstand {
  const _PrecomputedUnderstand({
    required this.domainId,
    required this.modeDecision,
    this.dialogueRoundScript,
  });

  final String domainId;
  final ModeDecision modeDecision;
  final DialogueRoundScript? dialogueRoundScript;
}

class _PrecomputedRetrieval {
  const _PrecomputedRetrieval({
    required this.skillName,
    required this.skillInstructionMarkdown,
    required this.skillPersona,
    required this.allowedToolNames,
    required this.executionShell,
    required this.plannerTemplateVersion,
    required this.postcheckTemplateVersion,
    required this.synthTemplateVersion,
    required this.fusionSynthTemplateVersion,
    required this.previousSlotState,
    this.previousDomainPolicyBundle,
  });

  final String skillName;
  final String skillInstructionMarkdown;
  final String skillPersona;
  final List<String> allowedToolNames;
  final SkillExecutionShell executionShell;
  final String plannerTemplateVersion;
  final String postcheckTemplateVersion;
  final String synthTemplateVersion;
  final String fusionSynthTemplateVersion;
  final SlotStateSnapshot previousSlotState;
  final DomainPolicyBundle? previousDomainPolicyBundle;
}

class _CompatibilityBootstrapState {
  const _CompatibilityBootstrapState({
    required this.bootstrapContext,
    required this.contextAssembly,
  });

  final AssistantBootstrapContext bootstrapContext;
  final ContextAssemblyResult contextAssembly;
}

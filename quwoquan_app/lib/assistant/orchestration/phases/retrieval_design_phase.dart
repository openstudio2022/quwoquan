import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/retrieval_tool_selection_policy.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/task_scheduler.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

/// Retrieval design: normalize planned TaskGraph for execution.
class RetrievalDesignPhase implements Phase {
  const RetrievalDesignPhase({
    this.runtime,
    this.domainRouter,
    this.templateCatalogRuntime,
    this.toolMetadataRegistry,
    this.skillLoader,
    this.skillRouter,
  });

  final ReactRuntime? runtime;
  final AssistantDomainRouter? domainRouter;
  final TemplateCatalogRuntime? templateCatalogRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final PersonalAssistantSkillLoader? skillLoader;
  final PersonalAssistantSkillRouter? skillRouter;

  @override
  String get phaseId => 'retrieval_design';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final availableToolNames =
        runtime?.listAvailableToolNames() ?? const <String>[];
    final bootstrapContext = input.state.bootstrapContext;
    final forceRefreshCatalog = bootstrapContext?.forceRefreshCatalog ?? false;
    final dialogueRoundScript = input.state.dialogueRoundScript;
    final understandingResult = input.state.understandingResult;
    if (latestUserQuery.isEmpty || understandingResult.intents.isEmpty) {
      return PhaseOutput(state: input.state);
    }
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await toolMetadataRegistry?.ensureLoaded();
    final taskGraph = input.state.taskGraph.tasks.isNotEmpty
        ? input.state.taskGraph
        : _fallbackTaskGraph(
            understandingResult: understandingResult,
            latestUserQuery: latestUserQuery,
          );
    final updatedUnderstandingSnapshot = _updatedUnderstandingSnapshot(
      current: input.state.understandingSnapshot,
    );
    final domainId =
        input.state.executionPreparation?.domainId.isNotEmpty == true
        ? input.state.executionPreparation!.domainId
        : _domainIdForTypedUnderstanding(understandingResult);
    final modeDecision = const ModeDecider().decide(
      understandingResult: understandingResult,
      taskGraph: taskGraph,
    );
    final updatedPreparation = await _executionPreparationResolver.resolveTyped(
      domainId: domainId,
      base:
          input.state.executionPreparation ??
          AssistantExecutionPreparation(
            domainId: domainId,
            modeDecision: modeDecision,
          ),
      userQuery: latestUserQuery,
      understandingResult: understandingResult,
      taskGraph: taskGraph,
      request: request,
      dialogueRoundScript: dialogueRoundScript,
      previousRunArtifacts: input.state.previousRunArtifacts,
      runtimeToolNames: availableToolNames,
    );
    final updatedOrchestratorState = const TaskScheduler()
        .schedule(taskGraph)
        .copyWithInteractionDirective(
          input.state.orchestratorState.interactionDirective,
        );

    if (taskGraph.tasks.isNotEmpty) {
      final traceToolName = _preferredRetrievalToolName(
        updatedPreparation.allowedToolNames.isNotEmpty
            ? updatedPreparation.allowedToolNames
            : (runtime?.listAvailableToolNames() ?? const <String>[]),
        searchPlans: searchPlansFromTaskGraph(taskGraph),
      );
      final retrievalDesignNarrative =
          updatedUnderstandingSnapshot.retrievalDesignNarrative
              .trim()
              .isNotEmpty
          ? updatedUnderstandingSnapshot.retrievalDesignNarrative.trim()
          : (updatedUnderstandingSnapshot.intentSummary.trim() !=
                    updatedUnderstandingSnapshot.userFacingSummary.trim()
                ? updatedUnderstandingSnapshot.intentSummary.trim()
                : '');
      input.onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchQueryGenerated,
          message: retrievalDesignNarrative,
          timestamp: DateTime.now(),
          runId: input.runId,
          traceId: input.traceId,
          data: <String, dynamic>{
            'toolName': traceToolName.isNotEmpty
                ? traceToolName
                : AssistantToolNames.search,
            'taskGraph': taskGraph.toJson(),
            'query': latestUserQuery,
          },
        ),
      );
    }
    return PhaseOutput(
      state: input.state.copyWith(
        taskGraph: taskGraph,
        orchestratorState: updatedOrchestratorState,
        understandingSnapshot: updatedUnderstandingSnapshot,
        executionPreparation: updatedPreparation,
      ),
    );
  }

  RunArtifactsUnderstandingSnapshot _updatedUnderstandingSnapshot({
    required RunArtifactsUnderstandingSnapshot current,
  }) {
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: current.intentSummary,
      userFacingSummary: current.userFacingSummary,
      retrievalDesignNarrative: current.retrievalDesignNarrative,
      concernPoints: current.concernPoints,
      emotionSignal: current.emotionSignal,
      resolutionItems: current.resolutionItems,
      assumptions: current.assumptions,
      mismatchSignal: current.mismatchSignal,
      carryForwardFacts: current.carryForwardFacts,
      discardedAssumptions: current.discardedAssumptions,
    );
  }

  TaskGraph _fallbackTaskGraph({
    required UnderstandingResult understandingResult,
    required String latestUserQuery,
  }) {
    if (understandingResult.intents.isEmpty) {
      return const TaskGraph();
    }
    final primaryIntent = understandingResult.intents.first;
    final searchPlans = primaryIntent.requiresEvidence
        ? <SearchPlanItem>[
            SearchPlanItem(
              id: 'fallback_retrieval',
              query: primaryIntent.goal.trim().isNotEmpty
                  ? primaryIntent.goal.trim()
                  : latestUserQuery,
              dimension: SearchPlanDimension.latestSignal,
              freshnessNeed: FreshnessNeed.realtime,
            ),
          ]
        : const <SearchPlanItem>[];
    final selectedToolName = _preferredRetrievalToolName(
      runtime?.listAvailableToolNames() ??
          const <String>[
            AssistantToolNames.appSearch,
            AssistantToolNames.search,
            AssistantToolNames.webSearch,
          ],
      searchPlans: searchPlans,
    );
    return TaskGraph(
      tasks: <TaskNode>[
        TaskNode(
          taskId: 'task_retrieval',
          intentId: primaryIntent.intentId,
          toolName: selectedToolName,
          toolArgs: TaskToolArgs(<String, Object?>{
            'query': primaryIntent.goal.trim().isNotEmpty
                ? primaryIntent.goal.trim()
                : latestUserQuery,
          }),
        ),
      ],
    );
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

  String _preferredRetrievalToolName(
    List<String> toolNames, {
    Iterable<SearchPlanItem> searchPlans = const <SearchPlanItem>[],
  }) {
    return const RetrievalToolSelectionPolicy().select(
      availableToolNames: toolNames,
      searchPlans: searchPlans,
    );
  }

  AssistantDomainRouter get _domainRouter =>
      domainRouter ?? AssistantDomainRouter();

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

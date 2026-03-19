import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

/// Retrieval design: produce QueryTask list, multi-lane retrieval plan.
class RetrievalDesignPhase implements Phase {
  const RetrievalDesignPhase({
    this.kernel = const BaselineKernel(),
    this.runtime,
    this.domainRouter,
    this.templateCatalogRuntime,
    this.toolMetadataRegistry,
    this.skillLoader,
    this.skillRouter,
    this.answerBoundaryResolver = const AnswerBoundaryResolver(),
  });

  final BaselineKernel kernel;
  final ReactRuntime? runtime;
  final AssistantDomainRouter? domainRouter;
  final TemplateCatalogRuntime? templateCatalogRuntime;
  final ToolMetadataRegistry? toolMetadataRegistry;
  final PersonalAssistantSkillLoader? skillLoader;
  final PersonalAssistantSkillRouter? skillRouter;
  final AnswerBoundaryResolver answerBoundaryResolver;

  @override
  String get phaseId => 'retrieval_design';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = input.request is AssistantRunRequest
        ? input.request as AssistantRunRequest
        : AssistantRunRequest.fromJson((input.request as dynamic).toJson());
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final bootstrapContext = input.state.bootstrapContext;
    final intentGraph = input.state.intentGraph;
    final forceRefreshCatalog = bootstrapContext?.forceRefreshCatalog ?? false;
    final dialogueRoundScript = input.state.dialogueRoundScript;
    if (latestUserQuery.isEmpty || intentGraph == null) {
      return PhaseOutput(state: input.state);
    }
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await toolMetadataRegistry?.ensureLoaded();

    final authorityDomains = intentGraph.authorityDomains;
    final freshnessHoursMax = intentGraph.freshnessHoursMax;
    final seededTasks = intentGraph.queryTasks;
    final contextEnvelope =
        input.state.contextAssembly?.contextEnvelope ??
        const <String, dynamic>{};
    final needsQueryPlan = answerBoundaryResolver.requiresQueryTaskDesign(
      intentGraph: intentGraph,
      contextEnvelope: contextEnvelope,
    );
    final plannedTasks = seededTasks.isNotEmpty
        ? seededTasks
        : !needsQueryPlan
        ? const <QueryTask>[]
        : _resolveQueryTasksWithoutModel(
            latestUserQuery: latestUserQuery,
            intentGraph: intentGraph,
            availableTools: (() {
              final toolNames = runtime?.listAvailableToolNames() ?? const <String>[];
              return toolNames.isNotEmpty
                  ? toolNames
                  : const <String>['web_search'];
            })(),
          );
    final continuitySlotState = _recoverPreviousSlotState(
      fallbackDomainId: intentGraph.primarySkill.trim(),
      runArtifacts: input.state.previousRunArtifacts,
    );
    final continuityAnchors = _seedEntityAnchorsFromContext(
      intentGraph: intentGraph,
      previousSlotState: continuitySlotState,
      continuityOverrideSlots:
          bootstrapContext?.continuityOverrideSlots ??
          const <String, dynamic>{},
    );

    final queryTasks = plannedTasks
        .map(
          (task) => task.copyWith(
            entityAnchors: task.entityAnchors.isNotEmpty
                ? task.entityAnchors
                : continuityAnchors,
            negativeKeywords: task.negativeKeywords.isNotEmpty
                ? task.negativeKeywords
                : intentGraph.negativeKeywords,
            authorityDomains: task.authorityDomains.isNotEmpty
                ? task.authorityDomains
                : authorityDomains,
            freshnessHoursMax: task.freshnessHoursMax > 0
                ? task.freshnessHoursMax
                : freshnessHoursMax,
            answerShape: task.answerShape != AnswerShape.unspecified
                ? task.answerShape
                : intentGraph.answerShape,
            freshnessNeed: task.freshnessNeed != FreshnessNeed.unspecified
                ? task.freshnessNeed
                : intentGraph.freshnessNeed,
          ),
        )
        .toList(growable: false);
    final updatedIntentGraph = IntentGraph.fromJson(<String, dynamic>{
      ...intentGraph.toJson(),
      'queryTasks': QueryTask.toJsonList(queryTasks),
      'authorityDomains': authorityDomains,
      'freshnessHoursMax': freshnessHoursMax,
    });
    final domainId =
        input.state.executionPreparation?.domainId.isNotEmpty == true
        ? input.state.executionPreparation!.domainId
        : updatedIntentGraph.primarySkill.trim();
    final updatedPreparation = await _executionPreparationResolver.resolve(
      domainId: domainId,
      base:
          input.state.executionPreparation ??
          AssistantExecutionPreparation(
            domainId: domainId,
            modeDecision: const ModeDecision(
              mode: AgentMode.singleAgent,
              reason: 'default_single',
            ),
          ),
      userQuery: latestUserQuery,
      intentGraph: updatedIntentGraph,
      request: request,
      dialogueRoundScript: dialogueRoundScript,
      previousRunArtifacts: input.state.previousRunArtifacts,
      runtimeToolNames: runtime?.listAvailableToolNames() ?? const <String>[],
    );

    if (queryTasks.isNotEmpty) {
      input.onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchQueryGenerated,
          message: '我先按最影响结论的几路信息分开核对。',
          timestamp: DateTime.now(),
          runId: input.runId,
          traceId: input.traceId,
          data: <String, dynamic>{
            'toolName': 'web_search',
            'queryTasks': QueryTask.toJsonList(queryTasks),
            'query': latestUserQuery,
            'problemClass': updatedIntentGraph.problemClassWireName,
            'queryNormalization': updatedIntentGraph.queryNormalization
                .toJson(),
            'entityAnchors': updatedIntentGraph.entityAnchors,
          },
        ),
      );
    }

    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: updatedIntentGraph,
        queryTasks: queryTasks,
        executionPreparation: updatedPreparation,
      ),
    );
  }

  List<QueryTask> _resolveQueryTasksWithoutModel({
    required String latestUserQuery,
    required IntentGraph intentGraph,
    required List<String> availableTools,
  }) {
    final plan = kernel.buildRetrievalPlan(
      latestUserQuery,
      availableTools,
      intentPayload: <String, dynamic>{
        'primaryDomainId': intentGraph.primarySkill.trim(),
        'secondaryDomains': intentGraph.secondarySkills,
        'problemClass': intentGraph.problemClassWireName,
        'inferredMotive': intentGraph.inferredMotive,
        'targetObject': intentGraph.targetObject,
        'userJobToBeDone': intentGraph.userJobToBeDone,
        'hardConstraints': intentGraph.hardConstraints,
        'softConstraints': intentGraph.softConstraints,
        'excludedScopes': intentGraph.excludedScopes,
        'freshnessNeed': intentGraph.freshnessNeedWireName,
        'answerShape': intentGraph.answerShapeWireName,
        'requiresExternalEvidence': intentGraph.requiresExternalEvidence,
        'entityAnchors': intentGraph.entityAnchors,
        'negativeKeywords': intentGraph.negativeKeywords,
        'queryNormalization': intentGraph.queryNormalization.toJson(),
        'queryTasks': QueryTask.toJsonList(intentGraph.queryTasks),
      },
    );
    return plan?.queryTasks ?? const <QueryTask>[];
  }

  SkillExecutionShell inputSkillExecutionShell(IntentGraph intentGraph) {
    return SkillExecutionShell(
      problemClass: intentGraph.problemClassWireName,
      authorityDomains: intentGraph.authorityDomains,
      freshnessHoursMax: intentGraph.freshnessHoursMax > 0
          ? intentGraph.freshnessHoursMax
          : 72,
    );
  }

  List<String> _seedEntityAnchorsFromContext({
    required IntentGraph intentGraph,
    required SlotStateSnapshot previousSlotState,
    required Map<String, dynamic> continuityOverrideSlots,
  }) {
    final anchors = <String>{
      ...intentGraph.entityAnchors
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty),
    };
    for (final value in continuityOverrideSlots.values) {
      final normalized = _normalizedAnchorValue(value);
      if (normalized.isNotEmpty) {
        anchors.add(normalized);
      }
    }
    for (final snapshot in previousSlotState.slotValues.values) {
      final normalized = _normalizedAnchorValue(snapshot.value);
      if (normalized.isNotEmpty) {
        anchors.add(normalized);
      }
    }
    return anchors.toList(growable: false);
  }

  String _normalizedAnchorValue(Object? value) {
    final candidate = value?.toString().trim() ?? '';
    if (candidate.isEmpty) return '';
    if (candidate.length > 48) return '';
    return candidate;
  }

  SlotStateSnapshot _recoverPreviousSlotState({
    required String fallbackDomainId,
    RunArtifacts? runArtifacts,
  }) {
    final fromArtifacts = runArtifacts?.slotState;
    if (fromArtifacts != null &&
        (fromArtifacts.slotValues.isNotEmpty ||
            fromArtifacts.missingSlots.isNotEmpty)) {
      return fromArtifacts;
    }
    return SlotStateSnapshot(domainId: fallbackDomainId);
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

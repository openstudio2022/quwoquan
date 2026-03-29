import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
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
    final designSummary = input.state.understandingSnapshot.queryDesignSummary
        .trim();

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
              final toolNames =
                  runtime?.listAvailableToolNames() ?? const <String>[];
              return toolNames.isNotEmpty
                  ? toolNames
                  : const <String>['search', 'web_search'];
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

    final queryTasks = _normalizeDomainQueryTasks(
      queryTasks: plannedTasks
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
          .toList(growable: false),
    );
    final updatedUnderstandingSnapshot = _updatedUnderstandingSnapshot(
      current: input.state.understandingSnapshot,
      queryTasks: queryTasks,
    );
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
      final traceToolName = _preferredRetrievalToolName(
        updatedPreparation.allowedToolNames.isNotEmpty
            ? updatedPreparation.allowedToolNames
            : (runtime?.listAvailableToolNames() ?? const <String>[]),
      );
      input.onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchQueryGenerated,
          message: '我先按最影响结论的几路信息分开核对。',
          timestamp: DateTime.now(),
          runId: input.runId,
          traceId: input.traceId,
          data: <String, dynamic>{
            'toolName': traceToolName.isNotEmpty ? traceToolName : 'search',
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
    final detail = queryTasks
        .map((task) {
          final label = task.effectiveLabel.trim().isNotEmpty
              ? task.effectiveLabel.trim()
              : task.query.trim();
          final query = task.query.trim();
          if (label.isEmpty) return '';
          if (query.isEmpty || query == label) return label;
          return '$label：$query';
        })
        .where((item) => item.isNotEmpty)
        .take(4)
        .join('\n');
    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: updatedIntentGraph,
        queryTasks: queryTasks,
        understandingSnapshot: updatedUnderstandingSnapshot,
        executionPreparation: updatedPreparation,
      ),
    );
  }

  RunArtifactsUnderstandingSnapshot _updatedUnderstandingSnapshot({
    required RunArtifactsUnderstandingSnapshot current,
    required List<QueryTask> queryTasks,
  }) {
    final queryDesignSummary = current.queryDesignSummary.trim().isNotEmpty
        ? current.queryDesignSummary.trim()
        : _buildQueryDesignSummary(queryTasks);
    final queryGroups = current.queryGroups.isNotEmpty
        ? current.queryGroups
        : _buildQueryGroups(queryTasks);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: current.intentSummary,
      userFacingSummary: current.userFacingSummary,
      concernPoints: current.concernPoints,
      emotionSignal: current.emotionSignal,
      queryDesignSummary: queryDesignSummary,
      queryGroups: queryGroups,
      assumptions: current.assumptions,
      mismatchSignal: current.mismatchSignal,
      carryForwardFacts: current.carryForwardFacts,
      discardedAssumptions: current.discardedAssumptions,
    );
  }

  String _buildQueryDesignSummary(List<QueryTask> queryTasks) {
    if (queryTasks.isEmpty) {
      return '';
    }
    final labels = queryTasks
        .map((task) => task.effectiveLabel.trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .take(3)
        .toList(growable: false);
    if (labels.isEmpty) {
      return '我把要核对的信息拆成几条检索线索了。';
    }
    if (labels.length == 1) {
      return '我先确认${labels.first}这一路信息。';
    }
    return '我会先按${labels.join('、')}这几路信息分开核对。';
  }

  List<RunArtifactsUnderstandingQueryGroup> _buildQueryGroups(
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

  List<QueryTask> _normalizeDomainQueryTasks({
    required List<QueryTask> queryTasks,
  }) {
    return QueryTask.normalizeList(QueryTask.toJsonList(queryTasks));
  }

  String _preferredRetrievalToolName(List<String> toolNames) {
    if (toolNames.contains('search')) {
      return 'search';
    }
    if (toolNames.contains('web_search')) {
      return 'web_search';
    }
    return '';
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

import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/slot_value_codec.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/understanding_user_facing_summary.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

/// Retrieval design: normalize planned QueryTask list for execution.
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
    final bootstrapContext = input.state.bootstrapContext;
    final intentGraph = input.state.intentGraph;
    final forceRefreshCatalog = bootstrapContext?.forceRefreshCatalog ?? false;
    final dialogueRoundScript = input.state.dialogueRoundScript;
    if (latestUserQuery.isEmpty || intentGraph == null) {
      return PhaseOutput(state: input.state);
    }
    final temporalizedIntentGraph = intentGraph;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    await toolMetadataRegistry?.ensureLoaded();

    final authorityDomains = temporalizedIntentGraph.authorityDomains;
    final freshnessHoursMax = temporalizedIntentGraph.freshnessHoursMax;
    final seededTasks = temporalizedIntentGraph.queryTasks;
    final continuitySlotState = _recoverPreviousSlotState(
      fallbackDomainId: temporalizedIntentGraph.primarySkill.trim(),
      runArtifacts: input.state.previousRunArtifacts,
    );
    final continuityAnchors = _seedEntityAnchorsFromContext(
      intentGraph: temporalizedIntentGraph,
      previousSlotState: continuitySlotState,
      continuityOverrideSlots:
          bootstrapContext?.continuityOverrideSlots ??
          const <String, dynamic>{},
    );
    final resolvedEntityAnchors = mergeGeoAnchors(
      continuityAnchors,
      temporalizedIntentGraph.resolvedGeoScope,
    );

    final queryTasks = _normalizeDomainQueryTasks(
      queryTasks: seededTasks
          .map(
            (task) => task.copyWith(
              query: applyResolvedGeoToQuery(
                task.query,
                temporalizedIntentGraph.resolvedGeoScope,
              ),
              entityAnchors: task.entityAnchors.isNotEmpty
                  ? mergeGeoAnchors(
                      task.entityAnchors,
                      temporalizedIntentGraph.resolvedGeoScope,
                    )
                  : resolvedEntityAnchors,
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
    final updatedIntentGraph = IntentGraph.fromJson(<String, dynamic>{
      ...temporalizedIntentGraph.toJson(),
      'entityAnchors': resolvedEntityAnchors,
      'queryTasks': QueryTask.toJsonList(queryTasks),
      'authorityDomains': authorityDomains,
      'freshnessHoursMax': freshnessHoursMax,
    });
    final resolvedIntentGraph = updatedIntentGraph;
    final resolvedQueryTasks = updatedIntentGraph.queryTasks;
    final updatedUnderstandingSnapshot = _updatedUnderstandingSnapshot(
      current: input.state.understandingSnapshot,
      queryTasks: resolvedQueryTasks,
    );
    final domainId =
        input.state.executionPreparation?.domainId.isNotEmpty == true
        ? input.state.executionPreparation!.domainId
        : resolvedIntentGraph.primarySkill.trim();
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
      intentGraph: resolvedIntentGraph,
      request: request,
      dialogueRoundScript: dialogueRoundScript,
      previousRunArtifacts: input.state.previousRunArtifacts,
      runtimeToolNames: runtime?.listAvailableToolNames() ?? const <String>[],
    );

    if (resolvedQueryTasks.isNotEmpty) {
      final traceToolName = _preferredRetrievalToolName(
        updatedPreparation.allowedToolNames.isNotEmpty
            ? updatedPreparation.allowedToolNames
            : (runtime?.listAvailableToolNames() ?? const <String>[]),
      );
      input.onTraceEvent?.call(
        AssistantTraceEvent(
          type: AssistantTraceEventType.searchQueryGenerated,
          message: updatedUnderstandingSnapshot.queryDesignSummary.trim(),
          timestamp: DateTime.now(),
          runId: input.runId,
          traceId: input.traceId,
          data: <String, dynamic>{
            'toolName': traceToolName.isNotEmpty ? traceToolName : 'search',
            'queryTasks': QueryTask.toJsonList(resolvedQueryTasks),
            'query': latestUserQuery,
            'problemClass': resolvedIntentGraph.problemClassWireName,
            'queryNormalization': resolvedIntentGraph.queryNormalization
                .toJson(),
            'entityAnchors': resolvedIntentGraph.entityAnchors,
          },
        ),
      );
    }
    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: resolvedIntentGraph,
        queryTasks: resolvedQueryTasks,
        understandingSnapshot: updatedUnderstandingSnapshot,
        executionPreparation: updatedPreparation,
      ),
    );
  }

  RunArtifactsUnderstandingSnapshot _updatedUnderstandingSnapshot({
    required RunArtifactsUnderstandingSnapshot current,
    required List<QueryTask> queryTasks,
  }) {
    final canonicalQueryGroups = _buildQueryGroups(queryTasks);
    final queryGroups = canonicalQueryGroups.isNotEmpty
        ? canonicalQueryGroups
        : current.queryGroups;
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: current.intentSummary,
      userFacingSummary: current.userFacingSummary,
      concernPoints: current.concernPoints,
      emotionSignal: current.emotionSignal,
      queryDesignSummary: current.queryDesignSummary.trim(),
      queryGroups: queryGroups,
      resolutionItems: current.resolutionItems,
      assumptions: current.assumptions,
      mismatchSignal: current.mismatchSignal,
      carryForwardFacts: current.carryForwardFacts,
      discardedAssumptions: current.discardedAssumptions,
    );
  }

  List<RunArtifactsUnderstandingQueryGroup> _buildQueryGroups(
    List<QueryTask> queryTasks,
  ) {
    final grouped = <String, List<String>>{};
    final reasons = <String, String>{};
    for (final task in queryTasks) {
      final dimension = task.dimensionLabel.trim().isNotEmpty
          ? task.dimensionLabel.trim()
          : (deriveQueryTaskFocusLabel(task).trim().isNotEmpty
                ? deriveQueryTaskFocusLabel(task).trim()
                : '综合');
      final query = task.query.trim();
      if (query.isEmpty) {
        continue;
      }
      grouped.putIfAbsent(dimension, () => <String>[]).add(query);
      final reason = deriveQueryTaskFocusReason(task).trim();
      if (reason.isNotEmpty) {
        reasons[dimension] = reason;
      }
    }
    return grouped.entries
        .map(
          (entry) => RunArtifactsUnderstandingQueryGroup(
            dimension: entry.key,
            queries: entry.value.toSet().take(2).toList(growable: false),
            why: reasons[entry.key]?.trim() ?? '',
          ),
        )
        .toList(growable: false);
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
      final normalized = _normalizedAnchorValue(
        SlotValueCodec.displayForSlotMerge(snapshot.value),
      );
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

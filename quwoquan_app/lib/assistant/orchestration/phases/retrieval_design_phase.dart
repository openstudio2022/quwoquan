import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/execution_preparation_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/model_output_extractors.dart';
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
    final modelDesignedTasks = seededTasks.isNotEmpty
        ? seededTasks
        : !needsQueryPlan
        ? const <QueryTask>[]
        : await _resolveQueryTasksWithModel(
            request: request,
            latestUserQuery: latestUserQuery,
            intentGraph: intentGraph,
            contextEnvelope: contextEnvelope,
            bootstrapContext: bootstrapContext,
            previousRunArtifacts: input.state.previousRunArtifacts,
            sessionId:
                bootstrapContext?.sessionId ?? request.sessionId ?? 'default',
            runId: input.runId,
            traceId: input.traceId,
            onTraceEvent: input.onTraceEvent,
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

    final queryTasks = modelDesignedTasks
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

  Future<List<QueryTask>> _resolveQueryTasksWithModel({
    required AssistantRunRequest request,
    required String latestUserQuery,
    required IntentGraph intentGraph,
    required Map<String, dynamic> contextEnvelope,
    required AssistantBootstrapContext? bootstrapContext,
    required RunArtifacts? previousRunArtifacts,
    required String sessionId,
    required String runId,
    required String traceId,
    void Function(dynamic event)? onTraceEvent,
  }) async {
    final runtime = this.runtime;
    if (runtime == null) return const <QueryTask>[];
    final templateVersion = _templateCatalogRuntime.latestVersionFor(
      'planner.retrieval_design',
      fallback: '',
    );
    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        <String, dynamic>{'role': 'user', 'content': latestUserQuery},
      ],
      maxIterations: 1,
      goal: '为当前问题设计最小但足够的一轮检索计划',
      availableToolNamesOverride: const <String>[],
      templateId: 'planner.retrieval_design',
      templateVersion: templateVersion,
      templateContext: request.contextScopeHint,
      templateVariables: <String, dynamic>{
        'currentQuery': latestUserQuery,
        'intentGraphJson': jsonEncode(intentGraph.toJson()),
        'contextEnvelopeJson': jsonEncode(contextEnvelope),
        'contextSlotsJson': jsonEncode(intentGraph.contextSlots),
        'continuityPolicyJson': jsonEncode(
          bootstrapContext?.contextContinuityPolicy.toJson() ??
              const <String, dynamic>{},
        ),
        'continuityOverrideSlotsJson': jsonEncode(
          bootstrapContext?.continuityOverrideSlots ??
              const <String, dynamic>{},
        ),
        'previousIntentGraphJson': jsonEncode(
          bootstrapContext?.previousIntentGraph?.toJson() ??
              const <String, dynamic>{},
        ),
        'previousAnswerSummary': bootstrapContext?.previousAnswerSummary ?? '',
        'previousSlotStateJson': jsonEncode(
          previousRunArtifacts?.slotState.toJson() ?? const <String, dynamic>{},
        ),
        'previousDomainPolicyBundleJson': jsonEncode(
          previousRunArtifacts?.domainPolicyBundle?.toJson() ??
              const <String, dynamic>{},
        ),
        'availableTools': jsonEncode(runtime.listAvailableToolNames()),
        'toolMetadata': jsonEncode(
          toolMetadataRegistry?.invocationGuidelinesForTools(
                runtime.listAvailableToolNames(),
              ) ??
              const <Map<String, dynamic>>[],
        ),
        'skillExecutionShell': jsonEncode(
          inputSkillExecutionShell(intentGraph).toJson(),
        ),
      },
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent == null
          ? null
          : (event) => onTraceEvent(
              event.copyWith(visibility: TraceVisibility.internal),
            ),
      callOptions: const LlmCallOptions(
        temperature: 0.15,
        maxTokens: 1200,
        forceJsonObject: true,
        timeoutSeconds: 20,
      ),
    );
    final parsed =
        LlmResponseParser.parse(result.finalText).json ?? <String, dynamic>{};
    final turn = tryParseAssistantTurnOutput(parsed);
    final extractedIntentGraph = extractIntentGraphFromModelPayload(
      parsed,
      parsedTurn: turn,
    );
    final tasks = extractQueryTasksFromModelPayload(
      parsed,
      parsedTurn: turn,
      extractedIntentGraph: extractedIntentGraph,
    );
    if (tasks.isNotEmpty) return tasks;
    return const <QueryTask>[];
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

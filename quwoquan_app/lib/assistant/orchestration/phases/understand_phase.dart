// ASSISTANT_WEAK_TYPE: LLM_RAW | EXTENSION_MAP — 理解阶段模板变量与 answer 轨 Map；稳定字段走 codegen/View。

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/context/assembly/answer_boundary_resolver.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/process_timeline_emitter.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/model_output_extractors.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/conversation_spine.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/baseline_kernel.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';

const RelativeTimeResolver _relativeTimeResolver = RelativeTimeResolver();
final RegExp _relativeTemporalTokenRe = RegExp(
  r'(昨天|昨日|明天|后天|今天|周[一二三四五六日天]|上周[一二三四五六日天]|下周[一二三四五六日天]|最近)',
);
final RegExp _relativeDayTokenRe = RegExp(r'(昨天|昨日|明天|后天|今天)');

/// Understand: intent graph, domain selection, dialogue round script.
class UnderstandPhase implements Phase {
  UnderstandPhase({
    this.domainRouter,
    this.dialogueStateRuntime,
    this.modeDecider = const ModeDecider(),
    this.kernel = const BaselineKernel(),
    this.answerBoundaryResolver = const AnswerBoundaryResolver(),
    this.runtime,
    this.templateCatalogRuntime,
  });

  final AssistantDomainRouter? domainRouter;
  final DialogueStateRuntime? dialogueStateRuntime;
  final ModeDecider modeDecider;
  final BaselineKernel kernel;
  final AnswerBoundaryResolver answerBoundaryResolver;
  final ReactRuntime? runtime;
  final TemplateCatalogRuntime? templateCatalogRuntime;

  @override
  String get phaseId => 'understand';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final bootstrapContext = input.state.bootstrapContext;
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final temporalReference = _relativeTimeResolver.resolveReferenceContext(
      referenceNowIso:
          (request.contextScopeHint['referenceNowIso'] as String?)?.trim() ??
          '',
      timezone: (request.contextScopeHint['timezone'] as String?)?.trim() ?? '',
    );
    final inlinePlanningOwnsUnderstanding =
        request.contextScopeHint['inlinePlanningOwnsUnderstanding'] == true;
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

    final hintedIntentRaw =
        (request.contextScopeHint['precomputedIntentGraph'] as Map?)
            ?.cast<String, Object?>() ??
        (request.contextScopeHint['intentGraph'] as Map?)
            ?.cast<String, Object?>() ??
        const <String, Object?>{};
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
        final geoResolvedIntent = await _resolveIntentGraphGeoContext(
          request: request,
          bootstrapContext: bootstrapContext,
          contextAssembly: input.state.contextAssembly,
          intentGraph: normalizedIntent,
          latestUserQuery: latestUserQuery,
        );
        final plannedIntent = _withPlannedQueryTasks(
          latestUserQuery: latestUserQuery,
          intentGraph: geoResolvedIntent,
          contextEnvelope:
              input.state.contextAssembly?.contextEnvelope ??
              const <String, Object?>{},
          availableTools:
              runtime?.listAvailableToolNames() ??
              const <String>['search', 'web_search'],
          referenceNowIso: temporalReference.referenceNowIso,
          timezone: temporalReference.timezone,
        );
        final domainId = plannedIntent.primarySkill.trim().isNotEmpty
            ? plannedIntent.primarySkill.trim()
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
          intentGraph: plannedIntent,
          recallResult: bootstrapContext?.recallResult,
        );
        final understandingSnapshot = _normalizeUnderstandingSnapshot(
          snapshot: _fallbackUnderstandingSnapshot(
            intentGraph: plannedIntent,
            latestUserQuery: latestUserQuery,
          ),
          intentGraph: plannedIntent,
          latestUserQuery: latestUserQuery,
          availableGeoContext:
              input.state.contextAssembly?.availableGeoContext ??
              const AvailableGeoContext(),
          previousIntentGraph: bootstrapContext?.previousIntentGraph,
        );
        _emitUnderstandingSnapshot(
          input: input,
          snapshot: understandingSnapshot,
        );
        return PhaseOutput(
          state: input.state.copyWith(
            intentGraph: plannedIntent,
            understandingSnapshot: understandingSnapshot,
            queryTasks: plannedIntent.queryTasks,
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

    if (!inlinePlanningOwnsUnderstanding) {
      final modelUnderstanding = await _resolveIntentGraphWithModel(
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
        final geoResolvedIntent = await _resolveIntentGraphGeoContext(
          request: request,
          bootstrapContext: bootstrapContext,
          contextAssembly: input.state.contextAssembly,
          intentGraph: normalizedIntent,
          latestUserQuery: latestUserQuery,
        );
        final plannedIntent = _withPlannedQueryTasks(
          latestUserQuery: latestUserQuery,
          intentGraph: geoResolvedIntent,
          contextEnvelope:
              input.state.contextAssembly?.contextEnvelope ??
              const <String, Object?>{},
          availableTools:
              runtime?.listAvailableToolNames() ??
              const <String>['search', 'web_search'],
          referenceNowIso: temporalReference.referenceNowIso,
          timezone: temporalReference.timezone,
        );
        final domainId = plannedIntent.primarySkill.trim().isNotEmpty
            ? plannedIntent.primarySkill.trim()
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
          intentGraph: plannedIntent,
          recallResult: bootstrapContext?.recallResult,
        );
        final understandingSnapshot = _normalizeUnderstandingSnapshot(
          snapshot: modelUnderstanding.understandingSnapshot,
          intentGraph: plannedIntent,
          latestUserQuery: latestUserQuery,
          availableGeoContext:
              input.state.contextAssembly?.availableGeoContext ??
              const AvailableGeoContext(),
          previousIntentGraph: bootstrapContext?.previousIntentGraph,
        );
        _emitUnderstandingSnapshot(
          input: input,
          snapshot: understandingSnapshot,
        );
        return PhaseOutput(
          state: input.state.copyWith(
            intentGraph: plannedIntent,
            understandingSnapshot: understandingSnapshot,
            queryTasks: plannedIntent.queryTasks,
            dialogueRoundScript: dialogueRoundScript,
            executionPreparation: AssistantExecutionPreparation(
              domainId: domainId,
              modeDecision: modeDecision,
            ),
          ),
        );
      }
    }

    final intentGraph = _buildFallbackIntentGraph(
      request: request,
      bootstrapContext: bootstrapContext,
      latestUserQuery: latestUserQuery,
      fallbackDomainId: _domainRouter.fallbackDomainId,
      recallResult: bootstrapContext?.recallResult,
      previousRunArtifacts: input.state.previousRunArtifacts,
    );
    final geoResolvedIntent = await _resolveIntentGraphGeoContext(
      request: request,
      bootstrapContext: bootstrapContext,
      contextAssembly: input.state.contextAssembly,
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
    );
    final plannedIntent = _withPlannedQueryTasks(
      latestUserQuery: latestUserQuery,
      intentGraph: geoResolvedIntent,
      contextEnvelope:
          input.state.contextAssembly?.contextEnvelope ??
          const <String, Object?>{},
      availableTools:
          runtime?.listAvailableToolNames() ??
          const <String>['search', 'web_search'],
      referenceNowIso: temporalReference.referenceNowIso,
      timezone: temporalReference.timezone,
    );
    final domainId = plannedIntent.primarySkill.trim().isNotEmpty
        ? plannedIntent.primarySkill.trim()
        : _domainRouter.fallbackDomainId;
    final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: domainId,
      userQuery: latestUserQuery,
      contextScopeHint: mergedScopeHint,
      forceRefreshCatalog: bootstrapContext?.forceRefreshCatalog ?? false,
    );
    final modeDecision = modeDecider.decide(
      intentGraph: plannedIntent,
      recallResult: bootstrapContext?.recallResult,
    );
    final understandingSnapshot = _normalizeUnderstandingSnapshot(
      snapshot: _fallbackUnderstandingSnapshot(
        intentGraph: plannedIntent,
        latestUserQuery: latestUserQuery,
      ),
      intentGraph: plannedIntent,
      latestUserQuery: latestUserQuery,
      availableGeoContext:
          input.state.contextAssembly?.availableGeoContext ??
          const AvailableGeoContext(),
      previousIntentGraph: bootstrapContext?.previousIntentGraph,
    );
    _emitUnderstandingSnapshot(input: input, snapshot: understandingSnapshot);

    return PhaseOutput(
      state: input.state.copyWith(
        intentGraph: plannedIntent,
        understandingSnapshot: understandingSnapshot,
        queryTasks: plannedIntent.queryTasks,
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
      resolvedGeoScope: hasResolvedGeoScope(intentGraph.resolvedGeoScope)
          ? intentGraph.resolvedGeoScope
          : (continuationActive && previousIntentGraph != null
                ? previousIntentGraph.resolvedGeoScope
                : const ResolvedGeoScope()),
    );
  }

  IntentGraph _withPlannedQueryTasks({
    required String latestUserQuery,
    required IntentGraph intentGraph,
    required Map<String, dynamic> contextEnvelope,
    required List<String> availableTools,
    required String referenceNowIso,
    required String timezone,
  }) {
    final temporalizedIntent = _applyResolvedGeoNormalization(
      intentGraph: _applyRelativeTimeNormalization(
        intentGraph: intentGraph,
        latestUserQuery: latestUserQuery,
        referenceNowIso: referenceNowIso,
        timezone: timezone,
      ),
    );
    if (temporalizedIntent.queryTasks.isNotEmpty) {
      return temporalizedIntent;
    }
    final needsQueryPlan = answerBoundaryResolver.requiresQueryTaskDesign(
      intentGraph: temporalizedIntent,
      contextEnvelope: contextEnvelope,
    );
    if (!needsQueryPlan) {
      return temporalizedIntent;
    }
    final plan = kernel.buildRetrievalPlan(
      latestUserQuery,
      availableTools.isNotEmpty
          ? availableTools
          : const <String>['search', 'web_search'],
      intentPayload: <String, dynamic>{
        'primaryDomainId': temporalizedIntent.primarySkill.trim(),
        'secondaryDomains': temporalizedIntent.secondarySkills,
        'problemClass': temporalizedIntent.problemClassWireName,
        'inferredMotive': temporalizedIntent.inferredMotive,
        'targetObject': temporalizedIntent.targetObject,
        'userJobToBeDone': temporalizedIntent.userJobToBeDone,
        'hardConstraints': temporalizedIntent.hardConstraints,
        'softConstraints': temporalizedIntent.softConstraints,
        'excludedScopes': temporalizedIntent.excludedScopes,
        'freshnessNeed': temporalizedIntent.freshnessNeedWireName,
        'answerShape': temporalizedIntent.answerShapeWireName,
        'requiresExternalEvidence': temporalizedIntent.requiresExternalEvidence,
        'entityAnchors': temporalizedIntent.entityAnchors,
        'negativeKeywords': temporalizedIntent.negativeKeywords,
        'queryNormalization': temporalizedIntent.queryNormalization.toJson(),
        'resolvedGeoScope': temporalizedIntent.resolvedGeoScope.toJson(),
      },
    );
    final queryTasks = QueryTask.normalizeList(
      QueryTask.toJsonList(plan?.queryTasks ?? const <QueryTask>[]),
    );
    if (queryTasks.isEmpty) {
      return temporalizedIntent;
    }
    return _applyResolvedGeoNormalization(
      intentGraph: _applyRelativeTimeNormalization(
        latestUserQuery: latestUserQuery,
        referenceNowIso: referenceNowIso,
        timezone: timezone,
        intentGraph: IntentGraph(
          userGoal: temporalizedIntent.userGoal,
          problemShape: temporalizedIntent.problemShape,
          primarySkill: temporalizedIntent.primarySkill,
          problemClass: temporalizedIntent.problemClass,
          inferredMotive: temporalizedIntent.inferredMotive,
          secondarySkills: temporalizedIntent.secondarySkills,
          targetObject: temporalizedIntent.targetObject,
          userJobToBeDone: temporalizedIntent.userJobToBeDone,
          hardConstraints: temporalizedIntent.hardConstraints,
          softConstraints: temporalizedIntent.softConstraints,
          excludedScopes: temporalizedIntent.excludedScopes,
          freshnessNeed: temporalizedIntent.freshnessNeed,
          answerShape: temporalizedIntent.answerShape,
          mustVerifyClaims: temporalizedIntent.mustVerifyClaims,
          requiresExternalEvidence: temporalizedIntent.requiresExternalEvidence,
          entityAnchors: temporalizedIntent.entityAnchors,
          negativeKeywords: temporalizedIntent.negativeKeywords,
          queryNormalization: temporalizedIntent.queryNormalization,
          queryTasks: queryTasks,
          searchIterationState: temporalizedIntent.searchIterationState,
          contextSlots: temporalizedIntent.contextSlots,
          globalConstraints: temporalizedIntent.globalConstraints,
          clarificationNeeded: temporalizedIntent.clarificationNeeded,
          recallResult: temporalizedIntent.recallResult,
          authorityDomains: temporalizedIntent.authorityDomains,
          freshnessHoursMax: temporalizedIntent.freshnessHoursMax,
          resolvedGeoScope: temporalizedIntent.resolvedGeoScope,
        ),
      ),
    );
  }

  IntentGraph _applyRelativeTimeNormalization({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    required String referenceNowIso,
    required String timezone,
  }) {
    return _relativeTimeResolver.applyToIntentGraph(
      intentGraph: intentGraph,
      latestUserQuery: latestUserQuery,
      referenceNowIso: referenceNowIso,
      timezone: timezone,
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
    final recentDialogueRounds = bootstrapContext?.recentDialogueRounds ??
        coerceRecentDialogueRounds(
          request.contextScopeHint['recentDialogueRounds'],
        );
    final recentDialogueRoundsLimit =
        bootstrapContext?.recentDialogueRoundsLimit ??
        resolveRecentDialogueRoundsLimit(request.contextScopeHint);
    final conversationSpineJson = jsonEncode(
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
          'allowedChoices': const <String>['tool_call', 'ask_user', 'answer'],
          'continuationActive': _isContinuationContext(bootstrapContext),
        },
      ),
    );
    final sharedContextJson = jsonEncode(
      _plannerSharedContextPayload(
        bootstrapContext: bootstrapContext,
        contextAssembly: contextAssembly,
        request: request,
        previousRunArtifacts: previousRunArtifacts,
        temporalReference: temporalReference,
      ),
    );
    final currentRuntimeStateJson = jsonEncode(
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
      referenceNowIso: temporalReference.referenceNowIso,
      timezone: temporalReference.timezone,
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
      'conversationSpine': conversationSpineJson,
      'skillCatalog': bootstrapContext?.skillCatalog ?? '',
      'sharedContext': sharedContextJson,
      'currentRuntimeState': currentRuntimeStateJson,
      'dialogueContinuity': dialogueContinuityJson,
      'recentDialogueRounds': jsonEncode(recentDialogueRounds),
      'searchIterationState': jsonEncode(searchIterationState.toJson()),
      'temporalReference': jsonEncode(<String, dynamic>{
        'referenceNowIso': temporalReference.referenceNowIso,
        'timezone': temporalReference.timezone,
      }),
      'recentDialogueRoundsLimit': recentDialogueRoundsLimit,
    };
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
    final intentGraph = extractIntentGraphFromModelPayload(
      parsed,
      parsedTurn: turn,
    );
    if (intentGraph == null) return null;
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
      concernPoints: parsedSnapshot.concernPoints,
      emotionSignal: parsedSnapshot.emotionSignal,
      resolutionItems: parsedSnapshot.resolutionItems,
      assumptions: parsedSnapshot.assumptions,
      mismatchSignal: parsedSnapshot.mismatchSignal,
      carryForwardFacts: parsedSnapshot.carryForwardFacts,
      discardedAssumptions: parsedSnapshot.discardedAssumptions,
    );
    return _ResolvedUnderstanding(
      intentGraph: intentGraph,
      understandingSnapshot: _normalizeUnderstandingSnapshot(
        snapshot: stabilizedSnapshot,
        intentGraph: intentGraph,
        latestUserQuery: latestUserQuery,
        availableGeoContext:
            contextAssembly?.availableGeoContext ?? const AvailableGeoContext(),
        previousIntentGraph: bootstrapContext?.previousIntentGraph,
      ),
    );
  }

  RunArtifactsUnderstandingSnapshot _fallbackUnderstandingSnapshot({
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) {
    final fallbackIntentSummary = intentGraph.userGoal.trim().isNotEmpty
        ? intentGraph.userGoal.trim()
        : latestUserQuery;
    final concernPoints = <String>[
      ...intentGraph.hardConstraints.map((item) => item.trim()),
      ...intentGraph.softConstraints.map((item) => item.trim()),
    ].where((item) => item.isNotEmpty).take(3).toList(growable: false);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: fallbackIntentSummary,
      userFacingSummary: fallbackIntentSummary,
      concernPoints: concernPoints,
      emotionSignal: 'neutral',
    );
  }

  String _currentCountryDefault(String countryLabel, String resolvedText) {
    final normalizedCountry = countryLabel.trim();
    final normalizedResolvedText = resolvedText.trim();
    if (normalizedCountry.isEmpty) {
      return normalizedResolvedText;
    }
    if (normalizedResolvedText.contains(normalizedCountry)) {
      return normalizedResolvedText;
    }
    if (normalizedResolvedText.isEmpty) {
      return normalizedCountry;
    }
    return '$normalizedCountry $normalizedResolvedText';
  }

  RunArtifactsUnderstandingSnapshot _normalizeUnderstandingSnapshot({
    required RunArtifactsUnderstandingSnapshot snapshot,
    required IntentGraph intentGraph,
    required String latestUserQuery,
    AvailableGeoContext? availableGeoContext,
    IntentGraph? previousIntentGraph,
  }) {
    final normalizedResolutionItems = _normalizeResolutionItems(
      snapshot: snapshot,
      intentGraph: intentGraph,
      availableGeoContext: availableGeoContext ?? const AvailableGeoContext(),
      previousIntentGraph: previousIntentGraph,
    );
    final normalizedIntent = _normalizeUnderstandingSummaryWithTemporalAnchor(
      base: snapshot.intentSummary.trim().isNotEmpty
          ? snapshot.intentSummary.trim()
          : (intentGraph.userGoal.trim().isNotEmpty
                ? intentGraph.userGoal.trim()
                : latestUserQuery),
      intentGraph: intentGraph,
    );
    final normalizedConcernPoints = snapshot.concernPoints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .take(3)
        .toList(growable: false);
    final normalizedUserFacingSummary =
        _normalizeUnderstandingSummaryWithTemporalAnchor(
          base: snapshot.userFacingSummary.trim().isNotEmpty
              ? snapshot.userFacingSummary.trim()
              : normalizedIntent,
          intentGraph: intentGraph,
        );
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: normalizedIntent,
      userFacingSummary: normalizedUserFacingSummary,
      concernPoints: normalizedConcernPoints,
      emotionSignal: snapshot.emotionSignal,
      resolutionItems: normalizedResolutionItems,
      assumptions: snapshot.assumptions,
      mismatchSignal: snapshot.mismatchSignal,
      carryForwardFacts: snapshot.carryForwardFacts,
      discardedAssumptions: snapshot.discardedAssumptions,
    );
  }

  String _normalizeUnderstandingSummaryWithTemporalAnchor({
    required String base,
    required IntentGraph intentGraph,
  }) {
    final trimmed = base.trim();
    if (trimmed.isEmpty) {
      return '';
    }
    if (!_relativeTemporalTokenRe.hasMatch(trimmed)) {
      return _canonicalizeExplicitDateAnchors(trimmed);
    }
    final queryNormalization = intentGraph.queryNormalization;
    final fallbackDate = _firstUnderstandingExplicitDate(intentGraph);
    final rewritten = _relativeTimeResolver
        .resolve(
          query: trimmed,
          referenceNowIso: queryNormalization.referenceNowIso,
          timezone: queryNormalization.timezone,
          timeScope: queryNormalization.timeScope,
          timeRangeStart: queryNormalization.timeRangeStart,
          timeRangeEnd: queryNormalization.timeRangeEnd,
          timePoint: queryNormalization.timePoint.isNotEmpty
              ? queryNormalization.timePoint
              : fallbackDate,
        )
        .rewrittenQuery
        .trim();
    if (rewritten.isNotEmpty &&
        rewritten != trimmed &&
        !_relativeDayTokenRe.hasMatch(rewritten)) {
      return _canonicalizeExplicitDateAnchors(rewritten);
    }
    if (fallbackDate.isNotEmpty && _relativeDayTokenRe.hasMatch(trimmed)) {
      return _canonicalizeExplicitDateAnchors(
        trimmed.replaceAllMapped(_relativeDayTokenRe, (_) => fallbackDate),
      );
    }
    return _canonicalizeExplicitDateAnchors(
      rewritten.isNotEmpty ? rewritten : trimmed,
    );
  }

  String _firstUnderstandingExplicitDate(IntentGraph intentGraph) {
    final queryNormalization = intentGraph.queryNormalization;
    final normalizedCandidates = <String>[
      queryNormalization.timePoint.trim(),
      queryNormalization.timeRangeStart.trim(),
      queryNormalization.timeRangeEnd.trim(),
    ].where((item) => item.isNotEmpty);
    if (normalizedCandidates.isNotEmpty) {
      return _canonicalDateToken(normalizedCandidates.first);
    }
    for (final task in intentGraph.queryTasks) {
      if (task.timePoint.trim().isNotEmpty) {
        return _canonicalDateToken(task.timePoint.trim());
      }
      final match = RegExp(
        r'(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})',
      ).firstMatch(task.query);
      if (match != null) {
        return _canonicalDateToken(match.group(0)?.trim() ?? '');
      }
    }
    return '';
  }

  static final RegExp _explicitDateTokenRe = RegExp(
    r'(\d{4})[-年/](\d{1,2})(?:[-月/])(\d{1,2})(?:日)?',
  );

  String _canonicalizeExplicitDateAnchors(String text) {
    return text.replaceAllMapped(_explicitDateTokenRe, (match) {
      final year = match.group(1) ?? '';
      final month = int.tryParse(match.group(2) ?? '')?.toString() ?? '';
      final day = int.tryParse(match.group(3) ?? '')?.toString() ?? '';
      if (year.isEmpty || month.isEmpty || day.isEmpty) {
        return match.group(0) ?? '';
      }
      return '$year年${month}月${day}日';
    });
  }

  String _canonicalDateToken(String value) =>
      _canonicalizeExplicitDateAnchors(value.trim());

  List<RunArtifactsUnderstandingResolutionItem> _normalizeResolutionItems({
    required RunArtifactsUnderstandingSnapshot snapshot,
    required IntentGraph intentGraph,
    required AvailableGeoContext availableGeoContext,
    required IntentGraph? previousIntentGraph,
  }) {
    final explicitItems = snapshot.resolutionItems
        .where(
          (item) =>
              item.detail.trim().isNotEmpty ||
              item.resolvedValue.trim().isNotEmpty ||
              item.title.trim().isNotEmpty,
        )
        .toList(growable: true);
    if (explicitItems.isNotEmpty) {
      return explicitItems.toList(growable: false);
    }
    final derivedItems = <RunArtifactsUnderstandingResolutionItem>[
      ...() sync* {
        final geoItem = _buildGeoResolutionItem(
          resolvedGeoScope: intentGraph.resolvedGeoScope,
          availableGeoContext: availableGeoContext,
          previousIntentGraph: previousIntentGraph,
        );
        if (geoItem != null) {
          yield geoItem;
        } else {
          final clarificationItem = _buildGeoClarificationItem(
            intentGraph: intentGraph,
          );
          if (clarificationItem != null) {
            yield clarificationItem;
          }
        }
      }(),
      ...() sync* {
        final temporalItem = _buildTemporalResolutionItem(
          queryNormalization: intentGraph.queryNormalization,
        );
        if (temporalItem != null) {
          yield temporalItem;
        }
      }(),
    ];
    for (final derived in derivedItems) {
      final alreadyPresent = explicitItems.any(
        (item) =>
            item.kind.trim() == derived.kind.trim() &&
            item.resolvedValue.trim() == derived.resolvedValue.trim(),
      );
      if (!alreadyPresent) {
        explicitItems.add(derived);
      }
    }
    return explicitItems.toList(growable: false);
  }

  RunArtifactsUnderstandingResolutionItem? _buildGeoResolutionItem({
    required ResolvedGeoScope resolvedGeoScope,
    required AvailableGeoContext availableGeoContext,
    required IntentGraph? previousIntentGraph,
  }) {
    if (!hasResolvedGeoScope(resolvedGeoScope)) {
      return null;
    }
    final resolvedText = resolvedGeoScope.resolvedText.trim().isNotEmpty
        ? resolvedGeoScope.resolvedText.trim()
        : (resolvedGeoScope.marketLabel.trim().isNotEmpty
              ? resolvedGeoScope.marketLabel.trim()
              : resolvedGeoScope.cityLabel.trim());
    if (resolvedText.isEmpty) {
      return null;
    }
    final source = resolvedGeoScope.source.trim();
    if (source == 'followup_carried') {
      return RunArtifactsUnderstandingResolutionItem(
        kind: 'followup_carry',
        title: '沿用上一轮地理范围',
        detail: '这轮没有改地点或市场，我继续按$resolvedText理解并检索。',
        source: 'followup_carried',
        originalValue: previousIntentGraph?.resolvedGeoScope.resolvedText ?? '',
        resolvedValue: resolvedText,
        defaultApplied: resolvedGeoScope.defaultApplied,
        visibleInUnderstanding: true,
      );
    }
    if (source == 'user_explicit') {
      final title = resolvedGeoScope.geoKind.trim() == 'market'
          ? '已识别明确市场'
          : '已识别明确地点';
      return RunArtifactsUnderstandingResolutionItem(
        kind: 'geo_explicit',
        title: title,
        detail: '你明确提到了$resolvedText，我会按这个范围检索。',
        source: 'user_explicit',
        originalValue: resolvedText,
        resolvedValue: resolvedText,
        defaultApplied: false,
        visibleInUnderstanding: true,
      );
    }
    if (resolvedGeoScope.defaultApplied) {
      if (resolvedGeoScope.geoKind.trim() == 'market') {
        final countryLabel = availableGeoContext.countryLabel.trim().isNotEmpty
            ? availableGeoContext.countryLabel.trim()
            : resolvedGeoScope.countryLabel.trim();
        return RunArtifactsUnderstandingResolutionItem(
          kind: 'market_default',
          title: '已采用默认市场',
          detail: countryLabel.isNotEmpty
              ? '你没有指定市场，我先按${_currentCountryDefault(countryLabel, resolvedText)}理解并检索。'
              : '你没有指定市场，我先按$resolvedText理解并检索。',
          source: source.isNotEmpty ? source : 'available_geo_default',
          originalValue: '',
          resolvedValue: resolvedText,
          defaultApplied: true,
          visibleInUnderstanding: true,
        );
      }
      final title = resolvedGeoScope.geoKind.trim() == 'city'
          ? '已采用默认城市'
          : '已采用默认地区';
      final detail = resolvedGeoScope.geoKind.trim() == 'city'
          ? '你没有指定城市，我先按$resolvedText理解并检索。'
          : '你没有指定地点，我先按$resolvedText这个范围理解并检索。';
      return RunArtifactsUnderstandingResolutionItem(
        kind: 'geo_default',
        title: title,
        detail: detail,
        source: source.isNotEmpty ? source : 'available_geo_default',
        originalValue: '',
        resolvedValue: resolvedText,
        defaultApplied: true,
        visibleInUnderstanding: true,
      );
    }
    return null;
  }

  RunArtifactsUnderstandingResolutionItem? _buildTemporalResolutionItem({
    required QueryNormalization queryNormalization,
  }) {
    for (final hint in queryNormalization.resolvedTemporalHints) {
      final parts = hint.split('->');
      if (parts.length != 2) {
        continue;
      }
      final originalValue = parts.first.trim();
      final resolvedValue = parts.last.trim();
      if (originalValue.isEmpty ||
          resolvedValue.isEmpty ||
          resolvedValue.startsWith('scope:')) {
        continue;
      }
      final detail = resolvedValue.contains('..')
          ? '你说$originalValue，我会按${resolvedValue.replaceAll('..', ' 至 ')}这个时间范围检索。'
          : '你说$originalValue，我会按$resolvedValue这个日期检索。';
      return RunArtifactsUnderstandingResolutionItem(
        kind: 'temporal_resolution',
        title: '已固定查询时间',
        detail: detail,
        source: 'query_normalization',
        originalValue: originalValue,
        resolvedValue: resolvedValue,
        defaultApplied: false,
        visibleInUnderstanding: true,
      );
    }
    return null;
  }

  RunArtifactsUnderstandingResolutionItem? _buildGeoClarificationItem({
    required IntentGraph intentGraph,
  }) {
    final reason =
        (intentGraph.contextSlots['geoClarificationReason'] as String?)
            ?.trim() ??
        '';
    if (!intentGraph.clarificationNeeded || reason.isEmpty) {
      return null;
    }
    final target = reason.contains('market') ? '市场范围' : '地点范围';
    return RunArtifactsUnderstandingResolutionItem(
      kind: 'clarification_needed',
      title: '需要补充地理范围',
      detail: '这个问题需要先确认$target，我再继续检索，避免搜到错城市或错市场。',
      source: 'query_normalization',
      originalValue: '',
      resolvedValue: '',
      defaultApplied: false,
      visibleInUnderstanding: true,
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
      'contextEnvelope': inputSafeContextEnvelope(
        bootstrapContext,
        request,
        contextAssembly,
        previousRunArtifacts,
      ),
      'recentDialogueRounds':
          bootstrapContext?.recentDialogueRounds ??
          coerceRecentDialogueRounds(
            request.contextScopeHint['recentDialogueRounds'],
          ),
      'temporalReference': <String, dynamic>{
        'referenceNowIso': temporalReference.referenceNowIso,
        'timezone': temporalReference.timezone,
        'calendarContext': calendarContext,
      },
      'userProfileSnapshot': request.userProfileSnapshot,
      'historicalRetrievalFeedback':
          (request.contextScopeHint['historicalRetrievalFeedback'] as Map?)
              ?.cast<String, Object?>() ??
          const <String, Object?>{},
      'domainLearningSignals':
          (request.contextScopeHint['domainLearningSignals'] as Map?)
              ?.cast<String, Object?>() ??
          const <String, Object?>{},
    };
  }

  Map<String, dynamic> _plannerCurrentRuntimeStatePayload({
    required AssistantBootstrapContext? bootstrapContext,
    required AssistantRunRequest request,
    required RunArtifacts? previousRunArtifacts,
    required String continuityMode,
    required String problemClass,
    required TemporalReferenceContext temporalReference,
    required SearchIterationState searchIterationState,
  }) {
    final continuationActive = _isContinuationContext(bootstrapContext);
    final previousIntentGraph = continuationActive
        ? bootstrapContext?.previousIntentGraph
        : null;
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
        'searchIterationState': searchIterationState.toJson(),
      },
      'slotStateSnapshot': continuationActive
          ? previousRunArtifacts?.slotState.toJson() ??
                const <String, Object?>{}
          : const <String, Object?>{},
      'contextSlots': continuationActive
          ? previousIntentGraph?.contextSlots ?? const <String, Object?>{}
          : const <String, Object?>{},
      'domainPolicyBundle': continuationActive
          ? previousRunArtifacts?.domainPolicyBundle?.toJson() ??
                const <String, Object?>{}
          : const <String, Object?>{},
      'skillExecutionShell': const SkillExecutionShell().toJson(),
    };
  }

  SearchIterationState _plannerSearchIterationState({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
  }) {
    final scopedStateRaw =
        (request.contextScopeHint['searchIterationState'] as Map?)
            ?.cast<String, Object?>();
    if (scopedStateRaw != null && scopedStateRaw.isNotEmpty) {
      return SearchIterationState.fromJson(scopedStateRaw);
    }
    final previousState =
        bootstrapContext?.previousIntentGraph?.searchIterationState ??
        const SearchIterationState();
    if (previousState.currentIteration > 0 ||
        previousState.maxIterations > 0 ||
        previousState.rounds.isNotEmpty) {
      return SearchIterationState(
        maxIterations: previousState.maxIterations > 0
            ? previousState.maxIterations
            : request.maxIterations,
        currentIteration: previousState.currentIteration > 0
            ? previousState.currentIteration
            : 1,
        rounds: previousState.rounds,
      );
    }
    return SearchIterationState(
      maxIterations: request.maxIterations,
      currentIteration: 1,
      rounds: const <SearchIterationRound>[],
    );
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
    return <String, dynamic>{
      'continuityMode': continuityMode,
      'problemClassHint': problemClass,
      'recentDialogueRounds':
          bootstrapContext?.recentDialogueRounds ??
          coerceRecentDialogueRounds(
            request.contextScopeHint['recentDialogueRounds'],
          ),
      'historySummary': allowHistorySummary
          ? bootstrapContext?.historySummary ?? ''
          : '',
      'previousIntentGraph':
          continuationActive && bootstrapContext?.previousIntentGraph != null
          ? bootstrapContext!.previousIntentGraph!.toJson()
          : const <String, Object?>{},
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

  String _buildIntentPlanningContext({
    required String continuityMode,
    required String problemClass,
  }) {
    return [
      '请先把 conversation_spine 当作当前轮唯一主线，再参考 shared_context / current_runtime_state / dialogue_continuity。',
      if (continuityMode.isNotEmpty) '连续性判断：$continuityMode',
      if (problemClass.isNotEmpty) '已知问题类型提示：$problemClass',
      '如果问题带时间约束，请直接把明确时间表达写进 queryTasks.query，不要把时间语义留给运行时再改写。',
      '如果本轮是在纠正上一轮理解，优先修正旧假设。',
      '请直接输出 assistant_turn JSON，并把结构化意图完整放入 intentGraph。',
    ].join('\n');
  }

  Future<IntentGraph> _resolveIntentGraphGeoContext({
    required AssistantRunRequest request,
    required AssistantBootstrapContext? bootstrapContext,
    required ContextAssemblyResult? contextAssembly,
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) async {
    final domainId = intentGraph.primarySkill.trim().isNotEmpty
        ? intentGraph.primarySkill.trim()
        : _domainRouter.fallbackDomainId;
    final retrievalPolicy = await _loadDomainRetrievalPolicy(domainId);
    final defaultGeoPolicy = parseDefaultGeoPolicy(retrievalPolicy);
    final availableGeoContext =
        contextAssembly != null &&
            hasAvailableGeoContext(contextAssembly.availableGeoContext)
        ? contextAssembly.availableGeoContext
        : buildAvailableGeoContext(
            gpsLocation: request.gpsLocation,
            scopeHint: request.contextScopeHint,
          );
    final previousGeoScope = _isContinuationContext(bootstrapContext)
        ? bootstrapContext?.previousIntentGraph?.resolvedGeoScope ??
              const ResolvedGeoScope()
        : const ResolvedGeoScope();
    final resolvedGeoScope = resolveGeoScope(
      userQuery: latestUserQuery,
      domainId: domainId,
      availableGeoContext: availableGeoContext,
      current: intentGraph.resolvedGeoScope,
      previous: previousGeoScope,
      geoPolicy: defaultGeoPolicy,
    );
    final needsGeoClarification =
        !hasResolvedGeoScope(resolvedGeoScope) &&
        defaultGeoPolicy.fallbackAllowed &&
        defaultGeoPolicy.defaultGeoScope.trim().isNotEmpty &&
        defaultGeoPolicy.defaultGeoScope.trim().toLowerCase() != 'none';
    return _applyResolvedGeoNormalization(
      intentGraph: IntentGraph.fromJson(<String, dynamic>{
        ...intentGraph.toJson(),
        'resolvedGeoScope': resolvedGeoScope.toJson(),
        'clarificationNeeded':
            intentGraph.clarificationNeeded || needsGeoClarification,
        'contextSlots': <String, dynamic>{
          ...intentGraph.contextSlots,
          if (hasAvailableGeoContext(availableGeoContext))
            'availableGeoContext': availableGeoContext.toJson(),
          if (hasResolvedGeoScope(resolvedGeoScope))
            'resolvedGeoScope': resolvedGeoScope.toJson(),
          if (needsGeoClarification)
            'geoClarificationReason':
                'missing_geo_context_for_${defaultGeoPolicy.defaultGeoScope}',
        },
      }),
    );
  }

  IntentGraph _applyResolvedGeoNormalization({
    required IntentGraph intentGraph,
  }) {
    if (!hasResolvedGeoScope(intentGraph.resolvedGeoScope)) {
      return intentGraph;
    }
    final mergedEntityAnchors = mergeGeoAnchors(
      intentGraph.entityAnchors,
      intentGraph.resolvedGeoScope,
    );
    final queryNormalization = QueryNormalization(
      normalizedQuery: intentGraph.queryNormalization.normalizedQuery,
      rewrittenQuery: applyResolvedGeoToQuery(
        intentGraph.queryNormalization.rewrittenQuery.trim().isNotEmpty
            ? intentGraph.queryNormalization.rewrittenQuery
            : intentGraph.queryNormalization.normalizedQuery,
        intentGraph.resolvedGeoScope,
      ),
      issues: intentGraph.queryNormalization.issues,
      language: intentGraph.queryNormalization.language,
      hints: intentGraph.queryNormalization.hints,
      referenceNowIso: intentGraph.queryNormalization.referenceNowIso,
      timezone: intentGraph.queryNormalization.timezone,
      resolvedTemporalHints:
          intentGraph.queryNormalization.resolvedTemporalHints,
      timeScope: intentGraph.queryNormalization.timeScope,
      timeRangeStart: intentGraph.queryNormalization.timeRangeStart,
      timeRangeEnd: intentGraph.queryNormalization.timeRangeEnd,
      timePoint: intentGraph.queryNormalization.timePoint,
    );
    final queryTasks = intentGraph.queryTasks
        .map(
          (task) => task.copyWith(
            query: applyResolvedGeoToQuery(
              task.query,
              intentGraph.resolvedGeoScope,
            ),
            entityAnchors: mergeGeoAnchors(
              task.entityAnchors.isNotEmpty
                  ? task.entityAnchors
                  : mergedEntityAnchors,
              intentGraph.resolvedGeoScope,
            ),
          ),
        )
        .toList(growable: false);
    return IntentGraph(
      userGoal: intentGraph.userGoal,
      problemShape: intentGraph.problemShape,
      primarySkill: intentGraph.primarySkill,
      problemClass: intentGraph.problemClass,
      inferredMotive: intentGraph.inferredMotive,
      secondarySkills: intentGraph.secondarySkills,
      targetObject: intentGraph.targetObject,
      userJobToBeDone: intentGraph.userJobToBeDone,
      hardConstraints: intentGraph.hardConstraints,
      softConstraints: intentGraph.softConstraints,
      excludedScopes: intentGraph.excludedScopes,
      freshnessNeed: intentGraph.freshnessNeed,
      answerShape: intentGraph.answerShape,
      mustVerifyClaims: intentGraph.mustVerifyClaims,
      requiresExternalEvidence: intentGraph.requiresExternalEvidence,
      entityAnchors: mergedEntityAnchors,
      negativeKeywords: intentGraph.negativeKeywords,
      queryNormalization: queryNormalization,
      queryTasks: queryTasks,
      searchIterationState: intentGraph.searchIterationState,
      contextSlots: intentGraph.contextSlots,
      globalConstraints: intentGraph.globalConstraints,
      clarificationNeeded: intentGraph.clarificationNeeded,
      recallResult: intentGraph.recallResult,
      authorityDomains: intentGraph.authorityDomains,
      freshnessHoursMax: intentGraph.freshnessHoursMax,
      resolvedGeoScope: intentGraph.resolvedGeoScope,
    );
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
    final limit = bootstrapContext?.recentDialogueRoundsLimit ??
        resolveRecentDialogueRoundsLimit(request.contextScopeHint);
    final policy = bootstrapContext?.contextContinuityPolicy ??
        const ContextContinuityPolicy();
    final isolatePlannerTurn = !policy.explicitContinuation &&
        (policy.continuityMode == ContextContinuityMode.freshTopic ||
            policy.continuityMode == ContextContinuityMode.unknown);
    final effectiveLimit = isolatePlannerTurn ? 0 : limit;
    return trimMessagesToRecentRounds(
      request.messages,
      limit: effectiveLimit,
    );
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
    final recalledPrimarySkill =
        recallResult?.topK
            .map((item) => item.domainId.trim())
            .firstWhere(
              (item) => item.isNotEmpty && item != fallbackDomainId,
              orElse: () => '',
            ) ??
        '';
    final primarySkill =
        continuationActive &&
            previousIntentGraph?.primarySkill.trim().isNotEmpty == true
        ? previousIntentGraph!.primarySkill.trim()
        : (recalledPrimarySkill.isNotEmpty
              ? recalledPrimarySkill
              : fallbackDomainId);
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
        current: previousIntentGraph?.contextSlots ?? const <String, Object?>{},
        bootstrapContext: bootstrapContext,
        previousIntentGraph: previousIntentGraph,
        previousRunArtifacts: previousRunArtifacts,
        continuationActive: continuationActive,
      ),
      globalConstraints: _mergeGlobalConstraints(
        current:
            previousIntentGraph?.globalConstraints ?? const <String, Object?>{},
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
      resolvedGeoScope: continuationActive && previousIntentGraph != null
          ? previousIntentGraph.resolvedGeoScope
          : const ResolvedGeoScope(),
    );
  }

  bool _isContinuationContext(AssistantBootstrapContext? bootstrapContext) {
    final continuityMode =
        bootstrapContext?.contextContinuityPolicy.continuityMode ??
        ContextContinuityMode.unknown;
    return continuityMode != ContextContinuityMode.unknown &&
        continuityMode != ContextContinuityMode.freshTopic;
  }

  Future<Map<String, dynamic>> _loadDomainRetrievalPolicy(
    String domainId,
  ) async {
    final normalized = domainId.trim();
    if (normalized.isEmpty) {
      return const <String, Object?>{};
    }
    final path =
        'assets/assistant/skills/$normalized/config/retrieval_policy.json';
    try {
      final content = await rootBundle.loadString(path);
      final decoded = jsonDecode(content);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      if (decoded is Map) {
        return decoded.cast<String, Object?>();
      }
    } catch (_) {
      final file = File(path);
      if (await file.exists()) {
        try {
          final decoded = jsonDecode(await file.readAsString());
          if (decoded is Map<String, dynamic>) {
            return decoded;
          }
          if (decoded is Map) {
            return decoded.cast<String, Object?>();
          }
        } catch (_) {
          return const <String, Object?>{};
        }
      }
    }
    return const <String, Object?>{};
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
    final previousNormalization =
        bootstrapContext?.previousIntentGraph?.queryNormalization ??
        const QueryNormalization();
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
      referenceNowIso: queryNormalization.referenceNowIso.trim().isNotEmpty
          ? queryNormalization.referenceNowIso.trim()
          : previousNormalization.referenceNowIso.trim(),
      timezone: queryNormalization.timezone.trim().isNotEmpty
          ? queryNormalization.timezone.trim()
          : previousNormalization.timezone.trim(),
      resolvedTemporalHints:
          queryNormalization.resolvedTemporalHints.isNotEmpty
          ? queryNormalization.resolvedTemporalHints
          : previousNormalization.resolvedTemporalHints,
      timeScope: queryNormalization.timeScope.trim().isNotEmpty
          ? queryNormalization.timeScope.trim()
          : previousNormalization.timeScope.trim(),
      timeRangeStart: queryNormalization.timeRangeStart.trim().isNotEmpty
          ? queryNormalization.timeRangeStart.trim()
          : previousNormalization.timeRangeStart.trim(),
      timeRangeEnd: queryNormalization.timeRangeEnd.trim().isNotEmpty
          ? queryNormalization.timeRangeEnd.trim()
          : previousNormalization.timeRangeEnd.trim(),
      timePoint: queryNormalization.timePoint.trim().isNotEmpty
          ? queryNormalization.timePoint.trim()
          : previousNormalization.timePoint.trim(),
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

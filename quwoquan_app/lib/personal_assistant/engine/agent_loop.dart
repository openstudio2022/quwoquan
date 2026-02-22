import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/personal_assistant/engine/context_orchestrator.dart';
import 'package:quwoquan_app/personal_assistant/engine/dialogue_state_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/domain_router.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/template_catalog_runtime.dart';
import 'package:quwoquan_app/personal_assistant/tools/metadata/tool_metadata_registry.dart';

class PersonalAssistantAgentLoop {
  PersonalAssistantAgentLoop(
    this._runtime, {
    required AssistantSessionManager sessionManager,
    required AssistantMemoryRepository memoryRepository,
    ToolMetadataRegistry? toolMetadataRegistry,
  }) : _sessionManager = sessionManager,
       _memoryRepository = memoryRepository,
       _toolMetadataRegistry = toolMetadataRegistry;

  final ReactRuntime _runtime;
  final AssistantSessionManager _sessionManager;
  final AssistantMemoryRepository _memoryRepository;
  final ToolMetadataRegistry? _toolMetadataRegistry;
  final PersonalAssistantContextOrchestrator _contextOrchestrator =
      const PersonalAssistantContextOrchestrator();
  final DialogueStateRuntime _dialogueStateRuntime = DialogueStateRuntime();
  final AssistantDomainRouter _domainRouter = AssistantDomainRouter();
  final TemplateCatalogRuntime _templateCatalogRuntime = TemplateCatalogRuntime();

  Future<AssistantRunResponse> run(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final runId =
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final traceId = request.traceId ?? runId;
    final sessionId = request.sessionId ?? 'default';
    await _sessionManager.load();
    for (final msg in request.messages) {
      _sessionManager.appendMessage(
        sessionId: sessionId,
        role: msg.role,
        content: msg.content,
      );
    }
    final enableChatRecent = _hasCapability(
      request.capabilityCatalog,
      AssistentCapabilityCatalog.chatRecent,
    );
    final enableChatLongterm = _hasCapability(
      request.capabilityCatalog,
      AssistentCapabilityCatalog.chatLongterm,
    );
    final historySummary = enableChatRecent
        ? _sessionManager.summarizeRecent(sessionId)
        : '';
    final recall = enableChatLongterm
        ? await _memoryRepository.recallByText(
            query: request.messages.isNotEmpty
                ? request.messages.last.content
                : '',
            limit: 3,
          )
        : const [];
    final recalledTexts = recall
        .map((item) => item.text.toString())
        .toList(growable: false);
    final contextAssembly = _contextOrchestrator.assemble(
      query: request.messages.isNotEmpty ? request.messages.last.content : '',
      historySummary: historySummary,
      recalledTexts: recalledTexts,
      deviceProfile: request.deviceProfile,
      deviceModel: request.deviceModel,
      deviceOs: request.deviceOs,
      gpsLocation: request.gpsLocation,
      contextScopeHint: request.contextScopeHint,
    );
    final forceRefreshDynamicCatalog =
        request.contextScopeHint['forceRefreshCatalog'] == true;
    await _templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshDynamicCatalog,
    );
    await _toolMetadataRegistry?.ensureLoaded();
    final domainId = await _resolveDomainId(
      request,
      forceRefreshCatalog: forceRefreshDynamicCatalog,
    );
    final domainCatalog = await _domainRouter.availableDomains(
      forceRefresh: forceRefreshDynamicCatalog,
      contextScopeHint: request.contextScopeHint,
    );
    final domainCatalogVersion = await _domainRouter.catalogVersion(
      forceRefresh: false,
      contextScopeHint: request.contextScopeHint,
    );
    final plannerTemplateVersion = _templateCatalogRuntime.latestVersionFor(
      'planner.global_plan',
      fallback: '',
    );
    final postcheckTemplateVersion = _templateCatalogRuntime.latestVersionFor(
      'planner.postcondition_check',
      fallback: plannerTemplateVersion,
    );
    final synthTemplateVersion = _templateCatalogRuntime.latestVersionFor(
      'synthesizer.final_answer',
      fallback: plannerTemplateVersion,
    );
    final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: domainId,
      userQuery: request.messages.isNotEmpty ? request.messages.last.content : '',
      contextScopeHint: request.contextScopeHint,
      forceRefreshCatalog: forceRefreshDynamicCatalog,
    );
    final runtimeToolNames = _runtime.listAvailableToolNames();
    final effectiveToolNames = _resolveAvailableTools(
      domainId: domainId,
      runtimeToolNames: runtimeToolNames,
    );
    final templateVariables = _buildTemplateVariables(
      request: request,
      contextAssembly: contextAssembly,
      domainId: domainId,
      availableToolNames: effectiveToolNames,
      dialogueRoundScript: dialogueRoundScript,
    );
    if (!contextAssembly.canEnterDomain) {
      final blocked = _buildBlockedResponse(
        runId: runId,
        traceId: traceId,
        contextAssembly: contextAssembly,
      );
      for (final event in blocked.traces) {
        onTraceEvent?.call(event);
      }
      await AssistantAgentLoopDevLogger.instance.writeRun(
        request: request,
        response: blocked,
        sessionId: sessionId,
        runId: runId,
      );
      return blocked;
    }
    final messages = request.messages
        .map((m) => <String, String>{'role': m.role, 'content': m.content})
        .toList(growable: true);
    messages.insert(0, <String, String>{
      'role': 'system',
      'content':
          '上下文组装结果（ContextEnvelope，仅按需使用）:\n${jsonEncode(contextAssembly.contextEnvelope)}',
    });
    if (historySummary.isNotEmpty) {
      messages.insert(0, <String, String>{
        'role': 'system',
        'content': '会话历史摘要:\n$historySummary',
      });
    }
    if (recall.isNotEmpty) {
      messages.insert(0, <String, String>{
        'role': 'system',
        'content': '记忆检索:\n${recall.map((e) => e.text).join('\n')}',
      });
    }
    if (request.capabilityCatalog.isNotEmpty) {
      messages.insert(0, <String, String>{
        'role': 'system',
        'content':
            '可查询能力目录（按需调用，不要全量扩查）:\n${AssistentCapabilityCatalog.toPromptText(request.capabilityCatalog)}',
      });
    }
    if (request.contextScopeHint.isNotEmpty) {
      final anchorText = _formatContextAnchor(request.contextScopeHint);
      messages.insert(0, <String, String>{
        'role': 'system',
        'content': '最小上下文锚点（仅用于决定是否扩展范围）:\n$anchorText',
      });
    }
    messages.insert(0, <String, String>{
      'role': 'system',
      'content':
          '当前轮次状态机脚本（必须遵循）：\n${jsonEncode(dialogueRoundScript.toJson())}',
    });
    final runStartAt = DateTime.now();
    await _safeWriteLogEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: AppPerfProbe.snapshot(
        event: 'operation',
        route: '/assistant/run',
        operation: 'agent_run_start',
      ),
      summaryPayload: <String, dynamic>{
        'event': 'operation',
        'operation': 'agent_run_start',
      },
    );
    final result = await _runtime.run(
      messages: messages,
      maxIterations: request.maxIterations,
      goal: request.messages.isNotEmpty ? request.messages.last.content : '',
      availableToolNamesOverride: effectiveToolNames,
      templateId: 'planner.global_plan',
      templateVersion: plannerTemplateVersion,
      templateContext: request.contextScopeHint,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
    final hasToolResult = result.traces.any(
      (event) => event.type == AssistantTraceEventType.toolResult,
    );
    final synthesisReadiness = _contextOrchestrator.checkSynthesisReadiness(
      query: request.messages.isNotEmpty ? request.messages.last.content : '',
      finalText: result.finalText,
      hasToolResult: hasToolResult,
      contextAssembly: contextAssembly,
    );
    var mergedResult = result;
    if (!synthesisReadiness.ready && synthesisReadiness.gapFillTask != null) {
      final gap = synthesisReadiness.gapFillTask!;
      final retryMessages = <Map<String, String>>[
        ...messages,
        <String, String>{
          'role': 'system',
          'content':
              'SynthesisReadinessCheck 未通过：${synthesisReadiness.reason}。\n'
              '请按以下补齐任务重新规划并执行检索后再回答：${jsonEncode(gap.toJson())}',
        },
      ];
      final retryResult = await _runtime.run(
        messages: retryMessages,
        maxIterations: request.maxIterations,
        goal: request.messages.isNotEmpty ? request.messages.last.content : '',
        availableToolNamesOverride: effectiveToolNames,
        templateId: 'planner.postcondition_check',
        templateVersion: postcheckTemplateVersion,
        templateContext: request.contextScopeHint,
        templateVariables: templateVariables,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
      );
      final retryGapFillEvent = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'synthesis readiness failed, trigger gap fill retry',
        timestamp: DateTime.now(),
        runId: runId,
        traceId: traceId,
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
    final synthesisInput = <Map<String, String>>[
      ...messages,
      <String, String>{
        'role': 'system',
        'content': '领域执行结果摘要：${mergedResult.finalText}',
      },
      <String, String>{
        'role': 'user',
        'content': request.messages.isNotEmpty ? request.messages.last.content : '',
      },
    ];
    final synthesisResult = await _runtime.run(
      messages: synthesisInput,
      maxIterations: 1,
      goal: request.messages.isNotEmpty ? request.messages.last.content : '',
      availableToolNamesOverride: effectiveToolNames,
      templateId: 'synthesizer.final_answer',
      templateVersion: synthTemplateVersion,
      templateContext: request.contextScopeHint,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
    mergedResult = ReactRuntimeResult(
      finalText: synthesisResult.finalText.trim().isEmpty
          ? mergedResult.finalText
          : synthesisResult.finalText,
      traces: <AssistantTraceEvent>[
        ...mergedResult.traces,
        ...synthesisResult.traces,
      ],
    );
    final runLatencyMs = DateTime.now().difference(runStartAt).inMilliseconds;
    _sessionManager.appendMessage(
      sessionId: sessionId,
      role: 'assistant',
      content: mergedResult.finalText,
    );
    await _sessionManager.save();
    await _memoryRepository.rememberText(
      id: '${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
      text: mergedResult.finalText,
      metadata: <String, dynamic>{
        'sessionId': sessionId,
        'userId': request.userId ?? '',
        'deviceProfile': request.deviceProfile,
        'deviceModel': request.deviceModel,
        'deviceOs': request.deviceOs,
      },
    );
    final response = AssistantRunResponse(
      finalText: mergedResult.finalText,
      traces: mergedResult.traces,
      runId: runId,
      traceId: traceId,
      structuredResponse: _buildStructuredResponse(
        request: request,
        contextAssembly: contextAssembly,
        synthesisReadiness: synthesisReadiness,
        result: mergedResult,
        dialogueRoundScript: dialogueRoundScript,
        candidateDomains: domainCatalog,
        templateVersionUsed: synthTemplateVersion,
        domainCatalogVersion: domainCatalogVersion,
      ),
      profileUpdateProposal: _buildProfileUpdateProposal(request: request),
    );
    await AssistantAgentLoopDevLogger.instance.writeRun(
      request: request,
      response: response,
      sessionId: sessionId,
      runId: runId,
    );
    await _safeWriteLogEvent(
      logType: AppLogType.agentRun,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: _buildObservabilityPayload(response: response, request: request),
      summaryPayload: <String, dynamic>{
        'kind': 'agent_run',
        'runId': runId,
        'traceId': traceId,
        'degraded': response.degraded,
      },
      hasError: response.degraded,
    );
    await _safeWriteLogEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: AppPerfProbe.snapshot(
        event: 'operation',
        route: '/assistant/run',
        operation: 'agent_run_end',
        latencyMs: runLatencyMs,
      ),
      summaryPayload: <String, dynamic>{
        'event': 'operation',
        'operation': 'agent_run_end',
        'latencyMs': runLatencyMs,
      },
    );
    return response;
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
      data: <String, dynamic>{
        'contextEnvelope': contextAssembly.contextEnvelope,
        'fillTasks': contextAssembly.fillTasks.map((e) => e.toJson()).toList(),
      },
    );
    final nextAction = contextAssembly.fillTasks
        .map((task) => '- ${task.targetSlot}: ${task.reason}')
        .join('\n');
    final finalText =
        '为保证答案质量，当前问题需要先补齐上下文后再执行垂类任务。\n'
        '请先补齐以下信息：\n$nextAction';
    final traceEnd = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleEnd,
      message: 'agent loop finished (blocked_precondition)',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
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
        'answerEligibility': 'blocked',
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

  Map<String, dynamic> _buildStructuredResponse({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required SynthesisReadinessResult synthesisReadiness,
    required ReactRuntimeResult result,
    required DialogueRoundScript dialogueRoundScript,
    required List<String> candidateDomains,
    required String templateVersionUsed,
    required String domainCatalogVersion,
  }) {
    final answerPayload = _parseAnswerPayload(
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
    final webEvidencePacks = _extractWebEvidencePacks(toolResults);
    final evidenceGatePassed = _webEvidenceGatePassed(webEvidencePacks);
    final answerEligible = synthesisReadiness.ready && evidenceGatePassed;
    final modelSelfScore = _asDouble(
      ((answerPayload['modelSelfScore'] as Map?)?['score']),
    );
    final learningSatisfaction = modelSelfScore >= 85
        ? 'high'
        : (modelSelfScore >= 70 ? 'medium' : 'low');
    return <String, dynamic>{
      'domainId': dialogueRoundScript.domainId,
      'candidateDomains': candidateDomains,
      'templateVersionUsed': templateVersionUsed,
      'domainCatalogVersion': domainCatalogVersion,
      'contextAssembly': contextAssembly.contextEnvelope,
      'domainPrecheck': <String, dynamic>{
        'canEnterDomain': contextAssembly.canEnterDomain,
        'fillTaskCount': contextAssembly.fillTasks.length,
      },
      'domainResults': <String, dynamic>{
        'toolResults': toolResults,
        'toolErrors': toolErrors,
      },
      'synthesisReadiness': <String, dynamic>{
        'ready': synthesisReadiness.ready,
        'reason': synthesisReadiness.reason,
      },
      'webEvidencePacks': webEvidencePacks,
      'webEvidenceGate': <String, dynamic>{
        'passed': evidenceGatePassed,
        'thresholds': const <String, dynamic>{
          'coverageMin': 0.7,
          'confidenceMin': 0.65,
          'freshnessHoursMax': 72,
        },
      },
      'fillTasks': <String, dynamic>{
        'contextFillTasks': contextAssembly.fillTasks
            .map((task) => task.toJson())
            .toList(growable: false),
        'gapFillTask': synthesisReadiness.gapFillTask?.toJson(),
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
        if (synthesisReadiness.gapFillTask != null)
          synthesisReadiness.gapFillTask!.toJson(),
      ],
      'missingCriticalSlots':
          (contextAssembly.contextEnvelope['missingSlots'] as List?)
              ?.whereType<String>()
              .toList(growable: false) ??
          const <String>[],
      'answerEligibility': answerEligible ? 'eligible' : 'blocked',
      'nextActions': _buildNextActions(contextAssembly, synthesisReadiness),
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
        synthesisReason: synthesisReadiness.reason,
        evidenceGatePassed: evidenceGatePassed,
      ),
      'diagnostics': <String, dynamic>{
        ...((answerPayload['diagnostics'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
        'synthesisReason': synthesisReadiness.reason,
        'toolResultCount': toolResults.length,
        'toolErrorCount': toolErrors.length,
        'webEvidenceGatePassed': evidenceGatePassed,
      },
      'answerPayload': answerPayload,
      'uiAnswer': <String, dynamic>{
        'summaryText': _extractUiSummary(answerPayload, result.finalText),
        'markdownText': _extractUiMarkdown(answerPayload, result.finalText),
        'actionHints':
            ((answerPayload['result'] as Map?)?['actionHints'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[],
        'followupPrompt': (answerPayload['followupPrompt'] as String?) ?? '',
        'selfScore': modelSelfScore,
      },
      'uiTimeline': _buildUiTimeline(
        traces: result.traces,
        request: request,
        toolResults: toolResults,
      ),
      'uiReferences': _buildUiReferences(toolResults),
      'uiActions': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'regenerate'},
        <String, dynamic>{'id': 'brief'},
        <String, dynamic>{'id': 'detailed'},
        <String, dynamic>{'id': 'switch_model'},
      ],
      'profileUpdateProposal': _buildProfileUpdateProposal(
        request: request,
      )?.toJson(),
    };
  }

  List<Map<String, dynamic>> _buildUiTimeline({
    required List<AssistantTraceEvent> traces,
    required AssistantRunRequest request,
    required List<Map<String, dynamic>> toolResults,
  }) {
    final timeline = <Map<String, dynamic>>[
      <String, dynamic>{
        'event': 'thinking',
      },
    ];
    final userQuery = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final plannedKeywords = userQuery
        .split(RegExp(r'[\s,，。；;]+'))
        .where((item) => item.trim().isNotEmpty)
        .take(4)
        .map((item) => item.trim())
        .toList(growable: false);
    if (plannedKeywords.isNotEmpty) {
      timeline.add(<String, dynamic>{
        'event': 'keyword_search',
        'keywords': plannedKeywords,
      });
    }
    var referenceCount = 0;
    for (final refs in _buildUiReferences(toolResults)) {
      referenceCount += 1;
      timeline.add(<String, dynamic>{
        'event': 'reference_increment',
        'count': referenceCount,
        'title': refs['title'] ?? '',
      });
    }
    final roundTrace = traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .length;
    timeline.add(<String, dynamic>{
      'event': 'reference_ready',
      'count': referenceCount,
      'rounds': roundTrace,
    });
    return timeline;
  }

  List<Map<String, dynamic>> _buildUiReferences(
    List<Map<String, dynamic>> toolResults,
  ) {
    final refs = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final item in toolResults) {
      final data = (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final rawRefs = (data['references'] as List?)
              ?.whereType<Map>()
              .map((ref) => ref.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final ref in rawRefs) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || seen.contains(url)) continue;
        final parsed = Uri.tryParse(url);
        final source = parsed?.host ?? (ref['source'] as String?) ?? '';
        refs.add(<String, dynamic>{
          'title': (ref['title'] as String?)?.trim().isNotEmpty == true
              ? (ref['title'] as String).trim()
              : source,
          'url': url,
          'source': source,
          'provider': (ref['provider'] as String?)?.trim() ?? '',
          'snippet': (ref['snippet'] as String?)?.trim() ?? '',
        });
        seen.add(url);
      }
    }
    return refs;
  }

  Map<String, dynamic> _parseAnswerPayload({
    required String rawFinalText,
    required List<AssistantTraceEvent> traces,
  }) {
    final parsed = _decodeJsonObject(rawFinalText) ?? <String, dynamic>{};
    final toolCallsFromTrace = traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map((event) => <String, dynamic>{
              'toolName': event.message.replaceFirst('calling ', '').trim(),
              'arguments': event.data ?? const <String, dynamic>{},
              'toolCallId': event.toolCallId ?? '',
            })
        .toList(growable: false);
    final existingToolCalls = _normalizeToolCalls(parsed['toolCalls']);
    final normalizedToolCalls = existingToolCalls.isNotEmpty
        ? existingToolCalls
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false)
        : toolCallsFromTrace;
    return <String, dynamic>{
      'result': (parsed['result'] as Map?)?.cast<String, dynamic>() ??
          <String, dynamic>{'text': rawFinalText},
      'evidence': _normalizeMapList(parsed['evidence'], textKey: 'text'),
      'reasoningBasis': _normalizeMapList(
        parsed['reasoningBasis'],
        textKey: 'text',
      ),
      'selfCheck': _normalizeMap(parsed['selfCheck']),
      'diagnostics': _normalizeMap(parsed['diagnostics']),
      'modelSelfScore': _normalizeModelSelfScore(parsed['modelSelfScore']),
      'toolCalls': normalizedToolCalls,
      'userFacingMarkdown': (parsed['userFacingMarkdown'] as String?) ?? '',
      'missingContextSlots': _normalizeStringList(parsed['missingContextSlots']),
      'fillGuidance': _normalizeMapList(
        parsed['fillGuidance'],
        textKey: 'guidance',
      ),
      'followupPrompt': (parsed['followupPrompt'] as String?) ?? '',
      'parseStatus': parsed.isEmpty ? 'fallback_text' : 'json_parsed',
    };
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

  Map<String, dynamic>? _decodeJsonObject(String rawText) {
    final text = rawText.trim();
    if (text.isEmpty) return null;
    final cleaned = text
        .replaceAll(RegExp(r'^```json\s*', multiLine: false), '')
        .replaceAll(RegExp(r'^```\s*', multiLine: false), '')
        .replaceAll(RegExp(r'```$'), '')
        .trim();
    final direct = _tryDecodeMap(cleaned);
    if (direct != null) return direct;
    final start = cleaned.indexOf('{');
    final end = cleaned.lastIndexOf('}');
    if (start >= 0 && end > start) {
      final sliced = cleaned.substring(start, end + 1);
      return _tryDecodeMap(sliced);
    }
    return null;
  }

  Map<String, dynamic>? _tryDecodeMap(String text) {
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) {
        return decoded.cast<String, dynamic>();
      }
    } catch (_) {
      return null;
    }
    return null;
  }

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

  String _extractUiSummary(Map<String, dynamic> answerPayload, String fallback) {
    final result = (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final interpretation = (result['interpretation'] as String?)?.trim() ?? '';
    if (interpretation.isNotEmpty) return interpretation;
    final text = (result['text'] as String?)?.trim() ?? '';
    if (text.isNotEmpty) return text;
    return fallback;
  }

  String _extractUiMarkdown(Map<String, dynamic> answerPayload, String fallback) {
    final markdown = (answerPayload['userFacingMarkdown'] as String?)?.trim() ?? '';
    if (markdown.isNotEmpty) return markdown;
    return fallback;
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
    return <String, dynamic>{
      'kind': 'agent_run',
      'templateId': 'synthesizer.final_answer',
      'templateVersion':
          (structured['templateVersionUsed'] as String?)?.trim().isNotEmpty ==
              true
          ? (structured['templateVersionUsed'] as String).trim()
          : 'latest',
      'structuredResponse': <String, dynamic>{
        'contextAssembly':
            structured['contextAssembly'] ?? const <String, dynamic>{},
        'domainPrecheck':
            structured['domainPrecheck'] ?? const <String, dynamic>{},
        'synthesisReadiness':
            structured['synthesisReadiness'] ?? const <String, dynamic>{},
        'contextSlots': structured['contextSlots'] ?? const <Map<String, dynamic>>[],
        'dialogueRuntime':
            structured['dialogueRuntime'] ?? const <String, dynamic>{},
        'roundTrace': structured['roundTrace'] ?? const <String, dynamic>{},
        'fillActions': structured['fillActions'] ?? const <Map<String, dynamic>>[],
        'missingCriticalSlots':
            structured['missingCriticalSlots'] ?? const <String>[],
        'answerEligibility': structured['answerEligibility'] ?? 'unknown',
        'selfCheck': structured['selfCheck'] ?? const <String, dynamic>{},
        'diagnostics': structured['diagnostics'] ?? const <String, dynamic>{},
        'webEvidencePacks':
            structured['webEvidencePacks'] ?? const <Map<String, dynamic>>[],
        'webEvidenceGate':
            structured['webEvidenceGate'] ?? const <String, dynamic>{},
        'answerPayload':
            structured['answerPayload'] ?? const <String, dynamic>{},
        'uiAnswer': structured['uiAnswer'] ?? const <String, dynamic>{},
      },
      'domainRouting': <String, dynamic>{
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
            (((structured['dialogueRuntime'] as Map?)?['domainId'] as String?) ??
                    '') ==
                'fallback_general_search',
        'fallbackReason': '',
      },
      'retrievalRounds': <String, dynamic>{
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
      'gapFillChain': <String, dynamic>{
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
      'webPipeline': <String, dynamic>{
        'evidencePackCount':
            ((structured['webEvidencePacks'] as List?)?.length ?? 0),
        'gatePassed':
            ((structured['webEvidenceGate'] as Map?)?['passed']) == true,
      },
      'profileProposalLifecycle': <String, dynamic>{
        'proposalId': response.profileUpdateProposal?.proposalId ?? '',
        'proposalStatus': response.profileUpdateProposal == null
            ? 'none'
            : 'created',
        'statusChangedAt': DateTime.now().toIso8601String(),
        'changedBy': 'assistant',
        'idempotencyKey': response.profileUpdateProposal?.proposalId ?? '',
      },
      'userProfile': <String, dynamic>{
        'profileVersion': (structured['profileVersion'] ?? '').toString(),
        'profileReadAt': DateTime.now().toIso8601String(),
        'profileUpdateProposalId':
            response.profileUpdateProposal?.proposalId ?? '',
        'profileUpdateConfirmedByUser': false,
      },
      'learningTrack': <String, dynamic>{
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
      'sensitiveBoundary': _redactSensitiveProfile(structured: structured),
      'resultSummary': <String, dynamic>{
        'toolResultCount':
            ((domainResults['toolResults'] as List?)?.length ?? 0),
        'toolErrorCount': ((domainResults['toolErrors'] as List?)?.length ?? 0),
        'degraded': response.degraded,
      },
    };
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
        'facts': data['facts'] ?? const <Map<String, dynamic>>[],
      });
    }
    return packs;
  }

  bool _webEvidenceGatePassed(List<Map<String, dynamic>> packs) {
    if (packs.isEmpty) return true;
    for (final pack in packs) {
      final coverage = _asDouble(pack['coverage']);
      final confidence = _asDouble(pack['confidence']);
      final freshnessHours = _asDouble(pack['freshnessHours']);
      if (coverage < 0.7 || confidence < 0.65 || freshnessHours > 72) {
        return false;
      }
    }
    return true;
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
    return sourceStatus.entries.map((entry) {
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
    }).toList(growable: false);
  }

  Map<String, dynamic> _buildTemplateVariables({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required String domainId,
    required List<String> availableToolNames,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final query = request.messages.isEmpty ? '' : request.messages.last.content;
    final toolGuidelines =
        _toolMetadataRegistry?.invocationGuidelinesForTools(availableToolNames) ??
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
      'contextEnvelope': contextAssembly.contextEnvelope,
      'availableTools': availableToolNames,
      'toolInvocationGuidelines': toolGuidelines,
      'dialogueRoundScript': dialogueRoundScript.toJson(),
    };
  }

  Map<String, dynamic> _buildRoundTrace({
    required AssistantRunRequest request,
    required ReactRuntimeResult result,
    required DialogueRoundScript dialogueRoundScript,
  }) {
    final toolStarts = result.traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map((event) => <String, dynamic>{
              'toolName': event.message.replaceFirst('calling ', '').trim(),
              'toolCallId': event.toolCallId ?? '',
              'arguments': event.data ?? const <String, dynamic>{},
            })
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
      'requiredFieldsForNextState': dialogueRoundScript.requiredFieldsForNextState,
      'totalSubTotalRequired': dialogueRoundScript.totalSubTotalRequired,
      'query': request.messages.isNotEmpty ? request.messages.last.content : '',
      'assistantResponse': result.finalText,
      'toolCalls': toolStarts,
      'toolResultCount': toolResults,
      'toolErrorCount': toolErrors,
      'timestamp': DateTime.now().toIso8601String(),
    };
  }

  /// 供 UI 在发起请求前预分类，便于远端优先使用正确领域，避免气运/时运等被误路由到闲聊或待办。
  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) async {
    return _domainRouter.classify(
      query: query,
      contextScopeHint: contextScopeHint,
      forceRefresh: false,
    );
  }

  Future<String> _resolveDomainId(
    AssistantRunRequest request, {
    required bool forceRefreshCatalog,
  }) async {
    final domainId = (request.contextScopeHint['domainId'] as String?)?.trim();
    if (domainId != null && domainId.isNotEmpty) return domainId;
    final query = request.messages.isNotEmpty ? request.messages.last.content : '';
    return _domainRouter.classify(
      query: query,
      contextScopeHint: request.contextScopeHint,
      forceRefresh: forceRefreshCatalog,
    );
  }

  List<String> _resolveAvailableTools({
    required String domainId,
    required List<String> runtimeToolNames,
  }) {
    final resolved = _toolMetadataRegistry?.availableToolsForDomain(
      domainId: domainId,
      fallbackNames: runtimeToolNames,
    );
    return resolved ?? runtimeToolNames;
  }

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
    return _sessionManager.sessions.entries
        .map(
          (e) => <String, dynamic>{
            'sessionId': e.key,
            'messageCount': e.value.length,
            'lastMessage': e.value.isEmpty
                ? ''
                : (e.value.last['content'] ?? ''),
          },
        )
        .toList(growable: false);
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    await _sessionManager.load();
    final messages = _sessionManager.sessions[sessionId];
    if (messages == null) return null;
    return <String, dynamic>{
      'sessionId': sessionId,
      'messages': messages,
      'summary': _sessionManager.summarizeRecent(sessionId),
    };
  }
}

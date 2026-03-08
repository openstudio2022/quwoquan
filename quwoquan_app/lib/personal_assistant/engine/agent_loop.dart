import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/agent_run_observability.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/personal_assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';
import 'package:quwoquan_app/personal_assistant/engine/context_orchestrator.dart';
import 'package:quwoquan_app/personal_assistant/engine/dialogue_state_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/domain_router.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_response_parser.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_loader.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_router.dart';
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
  final TemplateCatalogRuntime _templateCatalogRuntime =
      TemplateCatalogRuntime();
  final PersonalAssistantSkillLoader _skillLoader =
      const PersonalAssistantSkillLoader();
  final PersonalAssistantSkillRouter _skillRouter =
      const PersonalAssistantSkillRouter();

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
    final requestedSessionId = request.sessionId ?? 'default';
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content
        : '';
    await _sessionManager.load();
    final sessionId = requestedSessionId == 'assistant'
        ? _sessionManager.resolveAssistantSessionForQuery(latestUserQuery)
        : requestedSessionId;
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
        ? await _sessionManager.summarizeRecentAsync(
            sessionId,
            summarizer: (transcript) => _summarizeWithLlm(
              transcript: transcript,
              sessionId: sessionId,
              runId: runId,
              traceId: traceId,
            ),
          )
        : '';
    final recall = enableChatLongterm
        ? await _memoryRepository.recallByText(query: latestUserQuery, limit: 3)
        : const [];
    final recalledTexts = recall
        .map((item) => item.text.toString())
        .toList(growable: false);
    final contextAssembly = _contextOrchestrator.assemble(
      query: latestUserQuery,
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
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = await _domainRouter.availableDomains(
      forceRefresh: forceRefreshDynamicCatalog,
      contextScopeHint: request.contextScopeHint,
    );
    final domainCatalogVersion = await _domainRouter.catalogVersion(
      forceRefresh: false,
      contextScopeHint: request.contextScopeHint,
    );
    final skillCatalog = await _domainRouter.buildSkillCatalogPrompt(
      contextScopeHint: request.contextScopeHint,
    );
    final intentGraph = await _resolveIntentGraph(
      request: request,
      contextAssembly: contextAssembly,
      historySummary: historySummary,
      forceRefreshCatalog: forceRefreshDynamicCatalog,
      skillCatalog: skillCatalog,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
    final domainId =
        intentGraph.primarySkill.trim().isNotEmpty
            ? intentGraph.primarySkill.trim()
            : await _resolveDomainId(
                request,
                forceRefreshCatalog: forceRefreshDynamicCatalog,
              );
    final problemShape = intentGraph.problemShape.trim().isNotEmpty
        ? intentGraph.problemShape.trim()
        : (intentGraph.secondarySkills.isNotEmpty
              ? 'multi_skill'
              : 'single_skill');
    final intentTraceEvent = AssistantTraceEvent(
      type: AssistantTraceEventType.lifecycleStart,
      message: 'intent_graph_resolved',
      timestamp: DateTime.now(),
      runId: runId,
      traceId: traceId,
      data: intentGraph.toJson(),
    );
    onTraceEvent?.call(intentTraceEvent);
    // 先构建对话轮次脚本，以便 phase-aware 加载根据当前状态选择参考资料
    final dialogueRoundScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: domainId,
      userQuery: latestUserQuery,
      contextScopeHint: request.contextScopeHint,
      forceRefreshCatalog: forceRefreshDynamicCatalog,
    );
    final skillContext = await _resolveSkillContext(
      domainId: domainId,
      userQuery: latestUserQuery,
      dialogueRoundScript: dialogueRoundScript,
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
    final fusionSynthTemplateVersion = _templateCatalogRuntime.latestVersionFor(
      'synthesizer.multi_skill_fusion',
      fallback: synthTemplateVersion,
    );
    final runtimeToolNames = _runtime.listAvailableToolNames();
    final effectiveToolNames = _resolveAvailableTools(
      domainId: domainId,
      runtimeToolNames: runtimeToolNames,
    );
    final skillPersona = await _loadSkillPersona(domainId);
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
      skillExecutionShell: skillContext.executionShell,
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
    // 使用 List<Map<String, dynamic>> 以支持 tool_calls / tool_call_id 等非 String 字段。
    // 严禁改回 List<Map<String, String>>，否则 react_runtime 向其添加 tool 消息时会发生运行时类型错误。
    final messages = request.messages
        .map((m) => <String, dynamic>{'role': m.role, 'content': m.content})
        .toList(growable: true);
    // v2: 指令与数据分离——合并所有上下文数据为单条 system 消息，
    // 保持 prompt 栈（identity/safety/task/contract/persona/tool_policy）纯净。
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
    if (historySummary.isNotEmpty) {
      dataLayerBuffer.writeln();
      dataLayerBuffer.writeln('<session_history>');
      dataLayerBuffer.writeln(historySummary);
      dataLayerBuffer.writeln('</session_history>');
    }
    if (recall.isNotEmpty) {
      final cleanRecall = recall
          .map((e) => e.text.toString().trim())
          .where(
            (t) =>
                t.isNotEmpty &&
                !t.contains('"contractVersion"') &&
                !t.contains('"decision"') &&
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
        AssistentCapabilityCatalog.toPromptText(request.capabilityCatalog),
      );
      dataLayerBuffer.writeln('</capability_catalog>');
    }
    if (request.contextScopeHint.isNotEmpty) {
      final anchorText = _formatContextAnchor(request.contextScopeHint);
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
        runId: runId,
        traceId: traceId,
        component: 'agent_loop',
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
    // Rewrite modes (except deepThink) skip tool execution — the model
    // already has the previous answer as context and only needs to rephrase.
    final rewriteToolNames = request.shouldSkipSearch
        ? const <String>[]
        : effectiveToolNames;
    final shellMaxIterations = math.max(
      1,
      skillContext.executionShell.maxIterations,
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
      templateContext: request.contextScopeHint,
      templateVariables: templateVariables,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
      onDelta: onTraceEvent != null ? (_) {} : null,
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
        templateId: 'planner.postcondition_check',
        templateVersion: postcheckTemplateVersion,
        templateContext: request.contextScopeHint,
        templateVariables: templateVariables,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
        onDelta: onTraceEvent != null ? (_) {} : null,
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
    // Build synthesis-specific template variables with actual tool results injected
    final domainResultsForSynthesis = _buildDomainResultsForSynthesis(
      mergedResult.traces,
    );
    final synthesisTemplateVars = <String, dynamic>{
      ...templateVariables,
      'domainResults': jsonEncode(domainResultsForSynthesis),
      'contextSlots': jsonEncode(_buildContextSlots(contextAssembly)),
      'webEvidencePacks': jsonEncode(
        domainResultsForSynthesis['webEvidencePacks'] ?? const <dynamic>[],
      ),
      'userProfileSnapshot': jsonEncode(request.userProfileSnapshot),
    };
    final synthesisInput = <Map<String, dynamic>>[
      ...messages,
      <String, dynamic>{
        'role': 'system',
        'content': '领域执行结果摘要：${mergedResult.finalText}',
      },
      <String, dynamic>{'role': 'user', 'content': latestUserQuery},
    ];
    // Attempt SSE streaming for real-time typewriter effect (P4-1)
    final streamedText = await _runtime.streamSynthesis(
      messages: synthesisInput,
      goal: latestUserQuery,
      onDelta: (_) {},
      templateContext: request.contextScopeHint,
      templateVariables: synthesisTemplateVars,
      templateId: 'synthesizer.final_answer',
      templateVersion: synthTemplateVersion,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
    final ReactRuntimeResult synthesisResult;
    if (streamedText.trim().isNotEmpty) {
      synthesisResult = ReactRuntimeResult(
        finalText: streamedText,
        traces: const <AssistantTraceEvent>[],
      );
    } else {
      synthesisResult = await _runtime.run(
        messages: synthesisInput,
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: 'synthesizer.final_answer',
        templateVersion: synthTemplateVersion,
        templateContext: request.contextScopeHint,
        templateVariables: synthesisTemplateVars,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
        callOptions: const LlmCallOptions.synthesis(),
        onDelta: onTraceEvent != null ? (_) {} : null,
      );
    }
    final synthesisText = synthesisResult.finalText.trim();
    final phaseOneText = mergedResult.finalText;
    // 合成结果为空或是 react_runtime 兜底文案时，保留 Phase 1 的结果。
    // 避免好的 Phase 1 回答被无内容的合成兜底覆盖。
    final useSynthesis =
        synthesisText.isNotEmpty && !synthesisText.contains('没有生成可展示结果');
    mergedResult = ReactRuntimeResult(
      finalText: useSynthesis ? synthesisResult.finalText : phaseOneText,
      traces: <AssistantTraceEvent>[
        ...mergedResult.traces,
        ...synthesisResult.traces,
      ],
    );
    mergedResult = ReactRuntimeResult(
      finalText: _ensureAssistantTurnEnvelopeText(
        _guardSynthesisNextAction(mergedResult.finalText),
      ),
      traces: mergedResult.traces,
    );
    final answerPayloadBeforeSubagent = _parseAnswerPayload(
      rawFinalText: mergedResult.finalText,
      traces: mergedResult.traces,
    );
    final primarySkillRun = _buildPrimarySkillRun(
      intentGraph: intentGraph,
      domainId: domainId,
      answerPayload: answerPayloadBeforeSubagent,
      result: mergedResult,
      executionShell: skillContext.executionShell,
    );
    final skillRunPlans = _buildSkillRunPlans(
      intentGraph: intentGraph,
      answerPayload: answerPayloadBeforeSubagent,
      latestUserQuery: latestUserQuery,
      primaryDomainId: domainId,
    );
    final subagentRuns = await _executeSubagentPlans(
      answerPayload: <String, dynamic>{
        ...answerPayloadBeforeSubagent,
        'subagentPlan': skillRunPlans,
      },
      request: request,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      templateContext: request.contextScopeHint,
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
      // For multi-skill fusion synthesis, also inject subagent results into template vars
      final fusionTemplateVars = <String, dynamic>{
        ...synthesisTemplateVars,
        'skillRuns': jsonEncode(
          skillRuns.map((item) => item.toJson()).toList(growable: false),
        ),
        'subagentRuns': jsonEncode(runsForModel),
      };
      final fusionSynthesisTemplateId = subagentRuns.length > 1
          ? 'synthesizer.multi_skill_fusion'
          : 'synthesizer.final_answer';
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
      final subagentSynthesis = await _runtime.run(
        messages: subagentSynthesisInput,
        maxIterations: 1,
        goal: latestUserQuery,
        availableToolNamesOverride: const <String>[],
        templateId: fusionSynthesisTemplateId,
        templateVersion:
            fusionSynthesisTemplateId == 'synthesizer.multi_skill_fusion'
            ? fusionSynthTemplateVersion
            : synthTemplateVersion,
        templateContext: request.contextScopeHint,
        templateVariables: fusionTemplateVars,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
        callOptions: const LlmCallOptions.synthesis(),
        onDelta: onTraceEvent != null ? (_) {} : null,
      );
      mergedResult = ReactRuntimeResult(
        finalText: _ensureAssistantTurnEnvelopeText(
          subagentSynthesis.finalText.trim().isEmpty
              ? mergedResult.finalText
              : subagentSynthesis.finalText,
        ),
        traces: <AssistantTraceEvent>[
          ...mergedResult.traces,
          ...subagentSynthesis.traces,
        ],
      );
    }
    final runLatencyMs = DateTime.now().difference(runStartAt).inMilliseconds;
    // 使用结构化信号（mergedResult.degraded）判断是否是降级内容，
    // 不再依赖中文文案前缀匹配。AssistantContentFilters.isDegradedText 作为
    // 历史兼容兜底（覆盖极少数 finalText 未经 _ensureAssistantTurnEnvelopeText 的场景）。
    final isDegradedReply =
        mergedResult.degraded ||
        AssistantContentFilters.isDegradedText(mergedResult.finalText);
    // 提取用于存储的纯文本摘要（优先 userMarkdown，避免 JSON 进入记忆/摘要）
    final displayTextForStorage = _extractDisplayTextForStorage(
      mergedResult.finalText,
    );
    _sessionManager.updateSessionTopicSummary(
      sessionId: sessionId,
      latestUserQuery: latestUserQuery,
      latestAssistantReply: displayTextForStorage.isNotEmpty
          ? displayTextForStorage
          : mergedResult.finalText,
    );
    await _sessionManager.save();
    // 只存纯文本到记忆，绝不存含 contractVersion 的原始 JSON。
    // displayTextForStorage 为空（JSON 里无 userMarkdown）时，不存记忆，避免垃圾污染。
    final memoryText = displayTextForStorage;
    if (memoryText.isNotEmpty) {
      await _memoryRepository.rememberText(
        id: '${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: memoryText,
        metadata: <String, dynamic>{
          'sessionId': sessionId,
          'userId': request.userId ?? '',
          'deviceProfile': request.deviceProfile,
          'deviceModel': request.deviceModel,
          'deviceOs': request.deviceOs,
        },
      );
    }
    final response = AssistantRunResponse(
      finalText: mergedResult.finalText,
      traces: mergedResult.traces,
      runId: runId,
      traceId: traceId,
      degraded: _hasDegradedTrace(mergedResult.traces),
      structuredResponse: await _buildStructuredResponse(
        request: request,
        contextAssembly: contextAssembly,
        synthesisReadiness: synthesisReadiness,
        result: mergedResult,
        intentGraph: intentGraph,
        skillRuns: skillRuns,
        aggregationState: aggregationState,
        subagentRuns: subagentRuns,
        dialogueRoundScript: dialogueRoundScript,
        candidateDomains: domainCatalog,
        templateVersionUsed: synthTemplateVersion,
        domainCatalogVersion: domainCatalogVersion,
        sessionId: sessionId,
        onTraceEvent: onTraceEvent,
        runId: runId,
        traceId: traceId,
      ),
      profileUpdateProposal: _buildProfileUpdateProposal(request: request),
    );
    if (!isDegradedReply && displayTextForStorage.isNotEmpty) {
      _sessionManager.appendMessage(
        sessionId: sessionId,
        role: 'assistant',
        content: displayTextForStorage,
        metadata: <String, dynamic>{
          'uiProcessTimelineV2':
              (response.structuredResponse['uiProcessTimelineV2'] as List?) ??
              const <dynamic>[],
          'uiUsageStatsV1':
              (response.structuredResponse['uiUsageStatsV1'] as Map?) ??
              const <String, dynamic>{},
          'intentGraph':
              (response.structuredResponse['intentGraph'] as Map?) ??
              const <String, dynamic>{},
          'skillRuns':
              (response.structuredResponse['skillRuns'] as List?) ??
              const <dynamic>[],
          'aggregationState':
              (response.structuredResponse['aggregationState'] as Map?) ??
              const <String, dynamic>{},
        },
      );
    }
    await _persistLearningTags(
      response: response,
      sessionId: sessionId,
      userId: request.userId ?? '',
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

  Future<void> _persistLearningTags({
    required AssistantRunResponse response,
    required String sessionId,
    required String userId,
  }) async {
    try {
      final structured = response.structuredResponse;
      final learningTrack =
          (structured['learningTrack'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final tags =
          (learningTrack['profileTagDelta'] as List?)
              ?.whereType<Map>()
              .map((t) => t.cast<String, dynamic>())
              .where((t) => (t['tag'] ?? '').toString().isNotEmpty)
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (tags.isEmpty) return;

      final tagSummary = tags
          .map((t) => '${t['tag']}: ${t['value'] ?? t['confidence'] ?? ''}')
          .join('; ');
      await _memoryRepository.rememberText(
        id: 'learning_${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: '用户画像标签: $tagSummary',
        metadata: <String, dynamic>{
          'type': 'learning_tag',
          'sessionId': sessionId,
          'userId': userId,
          'tags': tags,
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    } catch (_) {
      // Non-critical: silently ignore persistence failures
    }
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

  /// Guards the synthesis output to ensure nextAction is always 'answer'.
  /// This prevents the synthesizer from accidentally triggering further tool calls.
  String _guardSynthesisNextAction(String rawText) {
    final result = LlmResponseParser.parse(rawText);
    if (!result.ok) return rawText;
    final parsed = result.json!;
    final turn = AssistantTurnOutput.tryParse(parsed);
    if (turn != null) {
      if (turn.nextAction == 'answer') return rawText;
      final updated = <String, dynamic>{
        ...turn.toEnvelopeMap(),
        'decision': <String, dynamic>{...turn.decision, 'nextAction': 'answer'},
      };
      return jsonEncode(updated);
    }
    // 非契约格式：尝试直接修正 decision.nextAction
    final decision =
        (parsed['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if ((decision['nextAction'] as String?)?.trim() == 'answer') return rawText;
    final updated = <String, dynamic>{
      ...parsed,
      'decision': <String, dynamic>{...decision, 'nextAction': 'answer'},
    };
    return jsonEncode(updated);
  }

  /// 确保 rawText 是符合当前契约版本（[kAssistantTurnCurrentVersion]）的 JSON 信封。
  /// 若 rawText 已是已知版本的契约 JSON，直接升级 contractVersion 值后返回；
  /// 否则构建 fallback 信封。
  String _ensureAssistantTurnEnvelopeText(String rawText) {
    final parseResult = LlmResponseParser.parse(rawText);
    final parsed = parseResult.json;
    if (parsed != null) {
      final turn = AssistantTurnOutput.tryParse(parsed);
      if (turn != null) {
        // 已是已知契约格式，确保 contractVersion 为当前版本后返回
        return jsonEncode(turn.toEnvelopeMap());
      }
    }
    // fallback 路径：构建最小合规信封
    final fallbackText = rawText.trim().isEmpty ? '' : rawText.trim();
    final resultFromParsed =
        (parsed?['result'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{'text': fallbackText, 'interpretation': fallbackText};
    final rawToolCalls =
        (parsed?['toolCalls'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final hasToolCalls = rawToolCalls.isNotEmpty;
    final nextAction = hasToolCalls ? 'tool_call' : 'answer';
    final toolPlan = rawToolCalls
        .map(
          (item) => <String, dynamic>{
            'tool': (item['toolName'] ?? item['name'] ?? '').toString(),
            'arguments':
                (item['arguments'] as Map?)?.cast<String, dynamic>() ??
                const <String, dynamic>{},
          },
        )
        .toList(growable: false);
    // fallback 路径下 userMarkdown 必须留空：
    //   - hasToolCalls=true 时，rawText 往往是计划描述/进度文本，不是最终答案
    //   - hasToolCalls=false 时，rawText 可能是进度文本（如"正在查询..."），
    //     写入 userMarkdown 会被 _extractUiMarkdown 的 isProgressPlaceholder 过滤
    //     但会误导 chunk 发送。统一留空，让 _extractUiMarkdown 从 result.text 提取。
    final fallback = AssistantTurnOutput(
      contractVersion: kAssistantTurnCurrentVersion,
      decision: <String, dynamic>{'nextAction': nextAction},
      messageKind: nextAction == 'tool_call' ? 'progress' : 'answer',
      userMarkdown: '',
      result: resultFromParsed,
      toolCalls: rawToolCalls,
      toolPlan: toolPlan,
      reasoningBasis:
          (parsed?['reasoningBasis'] as List?)
              ?.whereType<Map>()
              .map((m) => m.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      selfCheck:
          (parsed?['selfCheck'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      diagnostics:
          (parsed?['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      modelSelfScore:
          (parsed?['modelSelfScore'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
    return jsonEncode(fallback.toEnvelopeMap());
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
        .map((item) => item.cast<String, dynamic>())
        .where((item) => ((item['goal'] as String?)?.trim() ?? '').isNotEmpty)
        .toList(growable: false);
    if (plans.isEmpty) return const <Map<String, dynamic>>[];
    // Build a single subagent execution closure for parallel dispatch
    Future<Map<String, dynamic>> runSingleSubagent(
      int index,
      Map<String, dynamic> plan,
    ) async {
      final subagentId =
          ((plan['subagentId'] as String?)?.trim().isNotEmpty == true)
          ? (plan['subagentId'] as String).trim()
          : 'subagent_${index + 1}';
      final goal = (plan['goal'] as String?)?.trim() ?? '';
      final subagentDomainId = (plan['domainId'] as String?)?.trim() ?? '';
      final timeoutMs = _positiveInt(plan['timeoutMs'], fallback: 12000);
      var maxIterations = _positiveInt(plan['maxIterations'], fallback: 2);
      final toolBudget = _positiveInt(plan['toolBudget'], fallback: 2);
      final toolWhitelist =
          (plan['toolWhitelist'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      final subagentTools = _resolveSubagentToolNames(
        toolWhitelist: toolWhitelist,
        toolBudget: toolBudget,
      );
      // Load domain-specific skill instruction for this subagent (P1-2)
      Map<String, dynamic> subagentTemplateVars = templateVariables;
      if (subagentDomainId.isNotEmpty) {
        final subagentSkillContext = await _resolveSkillContext(
          domainId: subagentDomainId,
          userQuery: goal,
        );
        final subagentShell = subagentSkillContext.executionShell;
        subagentTemplateVars = <String, dynamic>{
          ...templateVariables,
          'domainId': subagentDomainId,
          'domainSkillInstruction': subagentSkillContext.instructionMarkdown,
          'domainSkillName': subagentSkillContext.skillName,
          'skillExecutionShell': subagentShell.toJson(),
        };
        if (subagentShell.maxIterations > 0 &&
            subagentShell.maxIterations < maxIterations) {
          maxIterations = subagentShell.maxIterations;
        }
      }
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
        final run = <String, dynamic>{
          'version': 'subagent_result_v1',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'success',
          'goal': goal,
          'summary': subagentResult.finalText,
          'toolCallCount': subagentResult.traces
              .where((event) => event.type == AssistantTraceEventType.toolStart)
              .length,
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
          'version': 'subagent_result_v1',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'timeout',
          'goal': goal,
          'summary': '',
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
          'version': 'subagent_result_v1',
          'subagentId': subagentId,
          'domainId': subagentDomainId,
          'status': 'failed',
          'goal': goal,
          'summary': '',
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

  int _positiveInt(Object? value, {required int fallback}) {
    if (value is int && value > 0) return value;
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed != null && parsed > 0) return parsed;
    return fallback;
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

  String _humanizeFillTask(ContextFillTask task) {
    switch (task.targetSlot) {
      case 'gps_or_city_location':
        return '你想查询的城市或当前位置（例如：深圳）';
      case 'longterm_memory':
        return '相关历史背景（例如：你上次提到的时间点或事件）';
      case 'realtime_evidence':
        return '实时检索依据（我需要先查到最新信息）';
      case 'answer_sufficiency':
        return '关键补充信息（当前证据不足以直接下结论）';
      default:
        return task.reason.trim().isEmpty ? task.targetSlot : task.reason;
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
    required List<Map<String, dynamic>> subagentRuns,
    required DialogueRoundScript dialogueRoundScript,
    required List<String> candidateDomains,
    required String templateVersionUsed,
    required String domainCatalogVersion,
    required String sessionId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  }) async {
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
    final retrievalPolicy = await _loadRetrievalPolicy(
      dialogueRoundScript.domainId,
    );
    final freshnessHoursMax =
        (retrievalPolicy['defaultFreshnessHoursMax'] as num?)?.toInt() ?? 72;
    final authorityRequired =
        (retrievalPolicy['authorityRequired'] as bool?) ?? false;
    final evidenceGatePassed = _webEvidenceGatePassed(
      webEvidencePacks,
      freshnessHoursMax: freshnessHoursMax,
      authorityRequired: authorityRequired,
    );
    final answerEligible = synthesisReadiness.ready && evidenceGatePassed;
    final modelSelfScore = _asDouble(
      ((answerPayload['modelSelfScore'] as Map?)?['score']),
    );
    final parseStatus =
        (answerPayload['parseStatus'] as String?) ?? 'fallback_text';
    final decisionParseSuccess = parseStatus == 'assistant_turn_v4_parsed';
    final heuristicFallbackUsed = _usedHeuristicFallback(result.traces);
    final messageKind = _resolveMessageKind(
      answerPayload: answerPayload,
      resultText: result.finalText,
    );
    final learningSatisfaction = modelSelfScore >= 85
        ? 'high'
        : (modelSelfScore >= 70 ? 'medium' : 'low');
    final uiReferences = _buildUiReferences(toolResults);
    final processSummaryV1 = _resolveProcessSummary(
      answerPayload: answerPayload,
      domainId: dialogueRoundScript.domainId,
      request: request,
      uiReferences: uiReferences,
      toolErrors: toolErrors,
      result: result,
    );
    final processReferenceCountV1 = _resolveProcessReferenceCount(
      answerPayload: answerPayload,
      uiReferences: uiReferences,
    );
    final directMarkdown = _extractUiMarkdown(answerPayload, result.finalText);
    final normalizedMarkdown = directMarkdown.trim().isNotEmpty
        ? directMarkdown
        : _buildFallbackMarkdown(
            answerPayload: answerPayload,
            domainId: dialogueRoundScript.domainId,
            request: request,
            uiReferences: uiReferences,
            toolErrors: toolErrors,
            result: result,
            synthesisReadiness: synthesisReadiness,
          );
    final renderMode = normalizedMarkdown.trim().isNotEmpty
        ? 'md_json_dual'
        : 'fallback_text';
    final renderFallback = renderMode == 'fallback_text';
    final uiProcessContentBlocks = _buildUiProcessContentBlocks(
      processSummary: processSummaryV1,
      uiReferences: uiReferences,
    );
    final userEvents = _buildUserEvents(
      intentGraph: intentGraph,
      skillRuns: skillRuns,
      aggregationState: aggregationState,
      processSummary: processSummaryV1,
      uiReferences: uiReferences,
    );
    final uiProcessTimelineV2 = _buildUiProcessTimelineV2(
      userEvents: userEvents,
      uiReferences: uiReferences,
    );
    final enrichedAnswerPayload = <String, dynamic>{
      ...answerPayload,
      'intentGraph': intentGraph.toJson(),
      'skillRuns': skillRuns.map((item) => item.toJson()).toList(growable: false),
      'aggregationState': aggregationState.toJson(),
      'userEvents': userEvents.map((item) => item.toJson()).toList(growable: false),
      'uiProcessTimelineV2': uiProcessTimelineV2,
    };
    if (normalizedMarkdown.isNotEmpty && onTraceEvent != null) {
      onTraceEvent(
        AssistantTraceEvent(
          type: AssistantTraceEventType.thinkingProgress,
          message: '正在组织回答...',
          timestamp: DateTime.now(),
          runId: runId ?? '',
          traceId: traceId ?? '',
          data: const <String, dynamic>{
            'phase': 'answering',
            'extracted': true,
          },
        ),
      );
      for (final chunk in _chunkMarkdownForStreaming(normalizedMarkdown)) {
        onTraceEvent(
          AssistantTraceEvent(
            type: AssistantTraceEventType.answerDelta,
            message: chunk,
            timestamp: DateTime.now(),
            runId: runId ?? '',
            traceId: traceId ?? '',
            data: const <String, dynamic>{'stage': 'synthesis'},
          ),
        );
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
      'domainCatalogVersion': domainCatalogVersion,
      'effectiveSessionId': sessionId,
      'activeTopicTitle': _sessionManager.topicTitleOf(sessionId),
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
        'thresholds': <String, dynamic>{
          'coverageMin': 0.7,
          'confidenceMin': 0.65,
          'freshnessHoursMax': freshnessHoursMax,
          'authorityRequired': authorityRequired,
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
      'answerPayload': enrichedAnswerPayload,
      'decisionJson': enrichedAnswerPayload['decision'] ?? const <String, dynamic>{},
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
      'subagentRuns': subagentRuns,
      'skillRuns': skillRuns.map((item) => item.toJson()).toList(growable: false),
      'aggregationState': aggregationState.toJson(),
      'userEvents': userEvents.map((item) => item.toJson()).toList(growable: false),
      'renderMode': renderMode,
      'qualityMetrics': <String, dynamic>{
        'decisionParseSuccess': decisionParseSuccess,
        'renderFallback': renderFallback,
        'heuristicFallbackUsed': heuristicFallbackUsed,
      },
      'contractVersion': kAssistantTurnCurrentVersion,
      '_meta': EngineResponseMeta(
        contractVersion: kAssistantTurnCurrentVersion,
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
      'uiAnswer': <String, dynamic>{
        'summaryText': _extractUiSummary(answerPayload, result.finalText),
        'markdownText': normalizedMarkdown,
        'actionHints':
            ((answerPayload['result'] as Map?)?['actionHints'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[],
        'followupPrompt': (answerPayload['followupPrompt'] as String?) ?? '',
        'selfScore': modelSelfScore,
      },
      'processSummaryV1': processSummaryV1,
      'processReferenceCountV1': processReferenceCountV1,
      'uiProcessTimelineV2': uiProcessTimelineV2,
      'uiPhaseTimelineV1': _buildUiPhaseTimelineV1(
        traces: result.traces,
        toolResults: toolResults,
        subagentRuns: subagentRuns,
      ),
      'uiTimeline': <Map<String, dynamic>>[
        for (final run in subagentRuns)
          <String, dynamic>{
            'event': 'subagent_progress',
            'subagentId': (run['subagentId'] as String?) ?? '',
            'status': (run['status'] as String?) ?? 'unknown',
          },
      ],
      'uiReferences': uiReferences,
      'uiProcessContentBlocks': uiProcessContentBlocks,
      'uiActions': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'regenerate'},
        <String, dynamic>{'id': 'brief'},
        <String, dynamic>{'id': 'detailed'},
        <String, dynamic>{'id': 'switch_model'},
      ],
      'uiUsageStatsV1': _buildUiUsageStatsV1(
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

  List<Map<String, dynamic>> _buildUiPhaseTimelineV1({
    required List<AssistantTraceEvent> traces,
    required List<Map<String, dynamic>> toolResults,
    required List<Map<String, dynamic>> subagentRuns,
  }) {
    final phases = <Map<String, dynamic>>[];
    Map<String, dynamic>? understandingPhase;
    Map<String, dynamic>? searchingPhase;
    Map<String, dynamic>? analyzingPhase;
    int retryCount = 0;

    void ensureUnderstandingPhase() {
      understandingPhase ??= <String, dynamic>{
        'phaseId': 'phase_understanding_1',
        'phaseType': 'understanding',
        'status': 'running',
        'title': '理解问题',
        'summary': '正在分析您的问题...',
        'details': <String>[],
        'references': <Map<String, dynamic>>[],
      };
      if (!phases.contains(understandingPhase)) phases.add(understandingPhase!);
    }

    void ensureSearchingPhase() {
      searchingPhase ??= <String, dynamic>{
        'phaseId': 'phase_searching_1',
        'phaseType': 'tool:web_search',
        'status': 'running',
        'title': '搜索资料',
        'summary': '正在搜索相关资料',
        'details': <String>[],
        'references': <Map<String, dynamic>>[],
      };
      if (!phases.contains(searchingPhase)) phases.add(searchingPhase!);
    }

    void ensureAnalyzingPhase() {
      analyzingPhase ??= <String, dynamic>{
        'phaseId': 'phase_analyzing_1',
        'phaseType': 'analyzing',
        'status': 'running',
        'title': '分析整理',
        'summary': '正在分析获取到的信息...',
        'details': <String>[],
        'references': <Map<String, dynamic>>[],
      };
      if (!phases.contains(analyzingPhase)) phases.add(analyzingPhase!);
    }

    void appendDetail(Map<String, dynamic> phase, String detail) {
      final text = _sanitizeUiDetail(detail);
      if (text.isEmpty) return;
      final details = (phase['details'] as List).cast<String>();
      if (details.isNotEmpty && details.last == text) return;
      details.add(text);
    }

    bool hasToolResults = false;

    for (final trace in traces) {
      final data = trace.data ?? const <String, dynamic>{};
      if (trace.type == AssistantTraceEventType.toolStart) {
        final toolName =
            (data['tool'] ?? data['toolName'] ?? data['name'] ?? '')
                .toString()
                .trim()
                .toLowerCase();
        if (toolName.contains('search') || toolName.contains('retrieval')) {
          ensureSearchingPhase();
          final args =
              (data['arguments'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
          final query =
              ((data['query'] ?? args['query'] ?? data['keyword']) as Object?)
                  ?.toString()
                  .trim() ??
              '';
          if (query.isNotEmpty) {
            appendDetail(searchingPhase!, '检索查询：$query');
          }
        } else if (toolName.contains('fetch')) {
          ensureSearchingPhase();
          final url = (data['url'] as String?)?.trim() ?? '';
          if (url.isNotEmpty) {
            appendDetail(searchingPhase!, '深度阅读：$url');
          }
        }
      } else if (trace.type == AssistantTraceEventType.assistantDelta) {
        final plannedQueries =
            (data['searchQueries'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[];
        if (plannedQueries.isNotEmpty) {
          ensureSearchingPhase();
          for (final query in plannedQueries.take(3)) {
            appendDetail(searchingPhase!, '检索查询：$query');
          }
        } else if (!hasToolResults) {
          ensureUnderstandingPhase();
          final detail = _sanitizeUiDetail(trace.message);
          if (detail.isNotEmpty) {
            appendDetail(understandingPhase!, detail);
          }
        } else {
          ensureAnalyzingPhase();
          final detail = _sanitizeUiDetail(trace.message);
          if (detail.isNotEmpty) {
            appendDetail(analyzingPhase!, detail);
          }
        }
      } else if (trace.type == AssistantTraceEventType.thinkingProgress) {
        final phase = (data['phase'] as String?) ?? 'understanding';
        final detail = _sanitizeUiDetail(trace.message);
        if (phase == 'analyzing') {
          ensureAnalyzingPhase();
          if (detail.isNotEmpty) appendDetail(analyzingPhase!, detail);
        } else {
          ensureUnderstandingPhase();
          if (detail.isNotEmpty) appendDetail(understandingPhase!, detail);
        }
      } else if (trace.type == AssistantTraceEventType.toolResult) {
        hasToolResults = true;
        if (data['isAssessment'] == true) {
          // Merge assessment into searching phase instead of creating separate phases
          retryCount++;
          ensureSearchingPhase();
          if (retryCount <= 1) {
            appendDetail(searchingPhase!, '正在验证搜索结果...');
          } else {
            appendDetail(searchingPhase!, '尝试其他搜索途径（第 $retryCount 次）');
          }
        } else {
          final refs =
              (data['references'] as List?)
                  ?.whereType<Map>()
                  .map((item) => item.cast<String, dynamic>())
                  .toList(growable: false) ??
              const <Map<String, dynamic>>[];
          if (refs.isNotEmpty) {
            ensureSearchingPhase();
            final current = (searchingPhase!['references'] as List)
                .cast<Map<String, dynamic>>();
            final seen = current
                .map((item) => (item['url'] as String?) ?? '')
                .where((item) => item.isNotEmpty)
                .toSet();
            for (final ref in refs) {
              final url = (ref['url'] as String?)?.trim() ?? '';
              if (url.isEmpty || seen.contains(url)) continue;
              current.add(<String, dynamic>{
                'title': (ref['title'] ?? '').toString(),
                'url': url,
                'source': (ref['source'] ?? '').toString(),
                'provider': (ref['provider'] ?? '').toString(),
                'snippet': (ref['snippet'] ?? '').toString(),
              });
              seen.add(url);
            }
            searchingPhase!['summary'] = '已找到 ${current.length} 篇相关资料';
          }
        }
      } else if (trace.type == AssistantTraceEventType.subagentResult) {
        ensureAnalyzingPhase();
        appendDetail(analyzingPhase!, trace.message);
      } else if (trace.type == AssistantTraceEventType.replanTriggered ||
          (trace.type == AssistantTraceEventType.lifecycleStart &&
              trace.message.toLowerCase().contains('replanning'))) {
        // Merge replan into searching phase instead of creating separate phases
        ensureSearchingPhase();
        appendDetail(searchingPhase!, '扩大搜索范围...');
      }
    }

    if (understandingPhase != null) {
      understandingPhase!['status'] = 'completed';
      if ((understandingPhase!['details'] as List).isEmpty) {
        (understandingPhase!['details'] as List).add('已完成问题分析');
      }
    }
    if (searchingPhase != null) {
      searchingPhase!['status'] = 'completed';
      final refs = (searchingPhase!['references'] as List);
      if (refs.isEmpty && retryCount > 0) {
        searchingPhase!['summary'] = '搜索完成（部分来源暂时不可用）';
      }
    }
    if (analyzingPhase != null) {
      analyzingPhase!['status'] = 'completed';
    }
    if (subagentRuns.isNotEmpty && analyzingPhase != null) {
      analyzingPhase!['summary'] = '已完成 ${subagentRuns.length} 个子任务';
    }
    phases.add(<String, dynamic>{
      'phaseId': 'phase_answering_final',
      'phaseType': 'answering',
      'status': 'completed',
      'title': '组织回答',
      'summary': '回答已生成',
      'details': <String>[],
      'references': <Map<String, dynamic>>[],
    });
    return phases;
  }

  static final RegExp _xmlToolCallTagRe = RegExp(
    r'<tool_call>[\s\S]*?</tool_call>|'
    r'<function=[^>]+>[\s\S]*?</function>|'
    r'<tool_call>|</tool_call>|'
    r'<function=[^>]*>|</function>|'
    r'<parameter=[^>]*>[\s\S]*?</parameter>|'
    r'</?parameter[^>]*>',
  );

  String _sanitizeUiDetail(String raw) {
    String text = raw.trim();
    if (text.isEmpty) return '';
    if (text.contains('"contractVersion"')) return '';
    // Filter internal dispatch messages
    if (text.startsWith('calling ') && text.length < 40) return '';
    if (text.startsWith('{') && text.contains('"tool_calls"')) return '';
    // Strip XML tool-call markup that some models emit
    if (text.contains('<tool_call>') || text.contains('<function=')) {
      text = text.replaceAll(_xmlToolCallTagRe, '').trim();
      if (text.isEmpty) return '';
    }
    if (text.length <= 120) return text;
    return '${text.substring(0, 120)}...';
  }

  Map<String, dynamic> _buildUiUsageStatsV1({
    required List<AssistantTraceEvent> traces,
    required AssistantRunRequest request,
    required List<Map<String, dynamic>> subagentRuns,
    required String outputText,
  }) {
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

    final inputText = request.messages.map((item) => item.content).join('\n');
    final estimatedTotalTokens = ((inputText.length + outputText.length) / 4)
        .ceil();
    final estimatedMaxTokens = (outputText.length / 4).ceil();
    final totalTokens = tokenSampleCount > 0
        ? totalTokensFromTrace
        : estimatedTotalTokens;
    final maxTokens = tokenSampleCount > 0
        ? maxTokensFromTrace
        : estimatedMaxTokens;
    final iterationCalls = traces
        .where(
          (trace) =>
              trace.type == AssistantTraceEventType.lifecycleStart &&
              trace.message.startsWith('llm request iteration '),
        )
        .length;
    final modelCalls = math.max(
      1,
      iterationCalls > 0 ? iterationCalls : (1 + subagentRuns.length),
    );

    return <String, dynamic>{
      'modelCallCount': modelCalls,
      'totalTokens': totalTokens,
      'maxTokensPerCall': maxTokens,
      'tokenSource': tokenSampleCount > 0 ? 'trace' : 'estimated',
    };
  }

  List<Map<String, dynamic>> _buildUiReferences(
    List<Map<String, dynamic>> toolResults,
  ) {
    final refs = <Map<String, dynamic>>[];
    final seen = <String>{};
    var totalSearched = 0;
    for (final item in toolResults) {
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
        final source = parsed?.host ?? (ref['source'] as String?) ?? '';
        // Layer 5: 标记权威来源
        final isCited =
            authorityDomains.isNotEmpty &&
            authorityDomains.any((d) => source == d || source.endsWith('.$d'));
        refs.add(<String, dynamic>{
          'title': (ref['title'] as String?)?.trim().isNotEmpty == true
              ? (ref['title'] as String).trim()
              : source,
          'url': url,
          'source': source,
          'provider': (ref['provider'] as String?)?.trim() ?? '',
          'snippet': (ref['snippet'] as String?)?.trim() ?? '',
          'cited': isCited,
          'authorityScore': isCited ? 1.0 : 0.0,
        });
        seen.add(url);
      }
    }
    // Layer 5: 总搜索资料数注入到第一个参考资料的元数据中，供 UI 展示"共检索 N 篇资料，以下为参考来源"
    if (refs.isNotEmpty && totalSearched > 0) {
      refs.first['_totalSearched'] = totalSearched;
    }
    return refs;
  }

  /// 将 LLM 最终文本解析为结构化的 answerPayload Map。
  ///
  /// LLM JSON → [AssistantTurnOutput.tryParse()] 类型化对象 → answerPayload Map。
  /// 字段名字符串只在 [AssistantTurnOutput.tryParse()] 内出现（见 02-dart-coding §5.1）。
  Map<String, dynamic> _parseAnswerPayload({
    required String rawFinalText,
    required List<AssistantTraceEvent> traces,
  }) {
    final parseResult = LlmResponseParser.parse(rawFinalText);
    final parsed = parseResult.json ?? <String, dynamic>{};
    // 解析为类型化对象，字段名字符串集中在 AssistantTurnOutput.tryParse() 内
    final turn = AssistantTurnOutput.tryParse(parsed);
    final toolCallsFromTrace = traces
        .where((event) => event.type == AssistantTraceEventType.toolStart)
        .map(
          (event) => <String, dynamic>{
            'toolName': event.message.replaceFirst('calling ', '').trim(),
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
        ? (turn.result.isNotEmpty
              ? Map<String, dynamic>.from(turn.result)
              : <String, dynamic>{'text': rawFinalText})
        : ((parsed['result'] as Map?)?.cast<String, dynamic>() ??
              <String, dynamic>{'text': rawFinalText});
    // 将 nextAction 注入到 result，供下游 _extractUiMarkdown 使用
    if (turn != null && turn.nextAction.isNotEmpty) {
      resultPayload['nextAction'] = turn.nextAction;
    }
    final parseStatus = parsed.isEmpty
        ? 'fallback_text'
        : (turn != null ? 'assistant_turn_v4_parsed' : 'json_parsed');
    return <String, dynamic>{
      'result': resultPayload,
      'evidence': turn != null
          ? turn.evidence
          : _normalizeMapList(parsed['evidence'], textKey: 'text'),
      'reasoningBasis': turn != null
          ? turn.reasoningBasis
          : _normalizeMapList(parsed['reasoningBasis'], textKey: 'text'),
      'selfCheck': turn != null
          ? turn.selfCheck
          : _normalizeMap(parsed['selfCheck']),
      'diagnostics': turn != null
          ? turn.diagnostics
          : _normalizeMap(parsed['diagnostics']),
      'modelSelfScore': turn != null
          ? _normalizeModelSelfScore(turn.modelSelfScore)
          : _normalizeModelSelfScore(parsed['modelSelfScore']),
      'toolCalls': normalizedToolCalls,
      'userMarkdown': turn?.userMarkdown ?? '',
      'decision': turn?.decision ?? const <String, dynamic>{},
      'messageKind': turn?.messageKind ?? '',
      'slotState': turn?.slotState ?? const <String, dynamic>{},
      'askUser': turn?.askUser ?? const <String, dynamic>{},
      'subagentPlan': turn != null
          ? turn.subagentPlan
          : _normalizeMapList(parsed['subagentPlan'], textKey: 'goal'),
      'intentGraph': turn?.intentGraph?.toJson() ??
          _normalizeMap(parsed['intentGraph']),
      'skillRuns': turn != null
          ? turn.skillRuns.map((item) => item.toJson()).toList(growable: false)
          : _normalizeMapList(parsed['skillRuns'], textKey: 'goal'),
      'aggregationState':
          turn?.aggregationState?.toJson() ??
          _normalizeMap(parsed['aggregationState']),
      'userEvents': turn != null
          ? turn.userEvents.map((item) => item.toJson()).toList(growable: false)
          : _normalizeMapList(parsed['userEvents'], textKey: 'message'),
      'uiProcessTimelineV2': turn != null
          ? turn.uiProcessTimelineV2
          : _normalizeMapList(parsed['uiProcessTimelineV2'], textKey: 'summary'),
      'toolPlan': turn != null
          ? turn.toolPlan
          : _normalizeMapList(parsed['toolPlan'], textKey: 'tool'),
      'missingContextSlots':
          turn?.missingContextSlots ??
          _normalizeStringList(parsed['missingContextSlots']),
      'fillGuidance': turn != null
          ? turn.fillGuidance
          : _normalizeMapList(parsed['fillGuidance'], textKey: 'guidance'),
      'followupPrompt': turn?.followupPrompt ?? '',
      'processSummary': turn?.processSummary ?? '',
      'processReferenceCount': turn?.processReferenceCount ?? 0,
      'parseStatus': parseStatus,
    };
  }

  Future<IntentGraph> _resolveIntentGraph({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required String historySummary,
    required bool forceRefreshCatalog,
    required String skillCatalog,
    required String sessionId,
    required String runId,
    required String traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final fallbackDomainId = await _resolveFallbackDomainId(
      request,
      forceRefreshCatalog: forceRefreshCatalog,
    );
    final fallbackDialogueScript = await _dialogueStateRuntime.buildRoundScript(
      domainId: fallbackDomainId,
      userQuery:
          request.messages.isNotEmpty ? request.messages.last.content : '',
      contextScopeHint: request.contextScopeHint,
      forceRefreshCatalog: forceRefreshCatalog,
    );
    final fallbackSkillContext = await _resolveSkillContext(
      domainId: fallbackDomainId,
      userQuery:
          request.messages.isNotEmpty ? request.messages.last.content : '',
      dialogueRoundScript: fallbackDialogueScript,
    );
    final templateVariables = _buildTemplateVariables(
      request: request,
      contextAssembly: contextAssembly,
      domainId: fallbackDomainId,
      domainSkillInstruction: fallbackSkillContext.instructionMarkdown,
      domainSkillName: fallbackSkillContext.skillName,
      availableToolNames: const <String>[],
      dialogueRoundScript: fallbackDialogueScript,
      skillPersona: '',
      skillCatalog: skillCatalog,
      skillExecutionShell: fallbackSkillContext.executionShell,
    );
    final plannerMessages = <Map<String, dynamic>>[
      <String, dynamic>{
        'role': 'system',
        'content': _buildIntentPlanningContext(
          request: request,
          contextAssembly: contextAssembly,
          historySummary: historySummary,
        ),
      },
      for (final item in request.messages)
        <String, dynamic>{'role': item.role, 'content': item.content},
    ];
    try {
      final result = await _runtime.run(
        messages: plannerMessages,
        maxIterations: 1,
        goal: request.messages.isNotEmpty ? request.messages.last.content : '',
        availableToolNamesOverride: const <String>[],
        templateId: 'planner.global_plan',
        templateVersion: _templateCatalogRuntime.latestVersionFor(
          'planner.global_plan',
          fallback: '',
        ),
        templateContext: request.contextScopeHint,
        templateVariables: templateVariables,
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        onTraceEvent: onTraceEvent,
        onDelta: null,
        callOptions: const LlmCallOptions(
          temperature: 0.2,
          maxTokens: 1200,
          forceJsonObject: true,
          timeoutSeconds: 20,
        ),
      );
      final parsed =
          LlmResponseParser.parse(result.finalText).json ?? <String, dynamic>{};
      final primarySkill =
          (parsed['primaryDomainId'] as String?)?.trim().isNotEmpty == true
          ? (parsed['primaryDomainId'] as String).trim()
          : fallbackDomainId;
      final secondarySkills = _normalizeStringList(
        parsed['secondaryDomains'],
      ).where((item) => item != primarySkill).toList(growable: false);
      final userGoal =
          (parsed['inferredMotive'] as String?)?.trim().isNotEmpty == true
          ? (parsed['inferredMotive'] as String).trim()
          : (request.messages.isNotEmpty ? request.messages.last.content : '');
      return IntentGraph(
        userGoal: userGoal,
        problemShape: secondarySkills.isEmpty ? 'single_skill' : 'multi_skill',
        primarySkill: primarySkill,
        secondarySkills: secondarySkills,
        globalConstraints: <String, dynamic>{
          'mode': (parsed['mode'] as String?)?.trim() ?? '',
          'queryNormalization':
              _normalizeMap(parsed['queryNormalization']),
          'slotFillPlan': _normalizeMap(parsed['slotFillPlan']),
          'contextSlots': _normalizeMap(parsed['contextSlots']),
        },
        clarificationNeeded:
            _normalizeStringList(parsed['missingContextSlots']).isNotEmpty ||
            ((parsed['slotFillAction'] as String?)?.trim() ?? '') == 'ask_user',
      );
    } catch (_) {
      return IntentGraph(
        userGoal: request.messages.isNotEmpty ? request.messages.last.content : '',
        problemShape: 'single_skill',
        primarySkill: fallbackDomainId,
      );
    }
  }

  String _buildIntentPlanningContext({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required String historySummary,
  }) {
    final buffer = StringBuffer();
    buffer.writeln('<context_slots>');
    buffer.writeln(jsonEncode(contextAssembly.contextEnvelope));
    buffer.writeln('</context_slots>');
    if (historySummary.trim().isNotEmpty) {
      buffer.writeln();
      buffer.writeln('<session_history>');
      buffer.writeln(historySummary.trim());
      buffer.writeln('</session_history>');
    }
    if (request.contextScopeHint.isNotEmpty) {
      buffer.writeln();
      buffer.writeln('<context_anchor>');
      buffer.writeln(_formatContextAnchor(request.contextScopeHint));
      buffer.writeln('</context_anchor>');
    }
    return buffer.toString();
  }

  Future<String> _resolveFallbackDomainId(
    AssistantRunRequest request, {
    required bool forceRefreshCatalog,
  }) async {
    await _domainRouter.ensureLoaded(forceRefresh: forceRefreshCatalog);
    final query = request.messages.isEmpty ? '' : request.messages.last.content;
    if (query.trim().isNotEmpty) {
      try {
        final skills = await _skillLoader.loadBundledSkills();
        final matched = _skillRouter.resolveSkill(query, skills);
        final matchedDomainId = matched?.domainId.trim() ?? '';
        if (matchedDomainId.isNotEmpty) return matchedDomainId;
      } catch (_) {
        // Ignore and use fallback below.
      }
    }
    return _domainRouter.fallbackDomainId;
  }

  List<Map<String, dynamic>> _buildSkillRunPlans({
    required IntentGraph intentGraph,
    required Map<String, dynamic> answerPayload,
    required String latestUserQuery,
    required String primaryDomainId,
  }) {
    final existingPlans = (answerPayload['subagentPlan'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (existingPlans.isNotEmpty) {
      return existingPlans
          .where(
            (item) =>
                ((item['domainId'] as String?)?.trim() ?? '').isNotEmpty &&
                ((item['domainId'] as String?)?.trim() ?? '') != primaryDomainId,
          )
          .toList(growable: false);
    }
    return intentGraph.secondarySkills
        .where((item) => item.trim().isNotEmpty && item.trim() != primaryDomainId)
        .map(
          (skillId) => <String, dynamic>{
            'subagentId': 'skill_${skillId}_1',
            'domainId': skillId,
            'mode': 'qa',
            'goal': '围绕用户问题补充 $skillId 视角的关键信息：$latestUserQuery',
            'maxIterations': 2,
            'toolBudget': 2,
          },
        )
        .toList(growable: false);
  }

  SkillRun _buildPrimarySkillRun({
    required IntentGraph intentGraph,
    required String domainId,
    required Map<String, dynamic> answerPayload,
    required ReactRuntimeResult result,
    required SkillExecutionShell executionShell,
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
          (answerPayload['userMarkdown'] as String?)?.trim().isNotEmpty == true ||
          (answerPayload['result'] as Map?) != null,
      stopReason: (answerPayload['messageKind'] as String?)?.trim() ?? '',
      resultSummary: _extractUiSummary(answerPayload, result.finalText),
    );
  }

  SkillRun _skillRunFromLegacySubagentRun(Map<String, dynamic> run) {
    final domainId = (run['domainId'] as String?)?.trim() ?? '';
    final status = (run['status'] as String?)?.trim() ?? 'unknown';
    return SkillRun(
      runId: (run['subagentId'] as String?)?.trim() ?? 'skill_$domainId',
      domainId: domainId,
      goal: (run['goal'] as String?)?.trim() ?? '',
      problemClass: status == 'success' ? 'qa' : 'fallback_general',
      answerReady: status == 'success',
      stopReason: status,
      resultSummary: (run['summary'] as String?)?.trim() ?? '',
    );
  }

  AggregationState _buildAggregationState({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    final blockingSkills = skillRuns
        .where((item) => !item.answerReady)
        .map((item) => item.domainId)
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    final allSkillsReady = skillRuns.isNotEmpty && blockingSkills.isEmpty;
    final canGivePartialAnswer =
        skillRuns.any((item) => item.answerReady) && blockingSkills.isNotEmpty;
    final clarificationNeeded =
        intentGraph.clarificationNeeded ||
        ((answerPayload['messageKind'] as String?)?.trim() ?? '') == 'ask_user';
    final needExpansion =
        !allSkillsReady && !canGivePartialAnswer && !clarificationNeeded;
    return AggregationState(
      allSkillsReady: allSkillsReady,
      blockingSkills: blockingSkills,
      canGivePartialAnswer: canGivePartialAnswer,
      needExpansion: needExpansion,
      expansionPlan: needExpansion
          ? <String, dynamic>{
              'targetSkills': blockingSkills,
              'strategy': 'broaden_or_retry',
            }
          : const <String, dynamic>{},
      finalAnswerReady: allSkillsReady || canGivePartialAnswer,
      finalAnswerMode: allSkillsReady
          ? 'full'
          : (canGivePartialAnswer
                ? 'partial'
                : (clarificationNeeded ? 'clarify' : 'expansion')),
      clarificationNeeded: clarificationNeeded,
    );
  }

  List<UserEvent> _buildUserEvents({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required AggregationState aggregationState,
    required String processSummary,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final events = <UserEvent>[
      UserEvent(
        type: UserEventType.processReplace,
        scope: UserEventScope.root,
        nodeId: 'root.intent',
        message: intentGraph.isMultiSkill
            ? '已识别为复合问题，准备分任务处理'
            : '已识别问题方向，准备开始处理',
        payload: intentGraph.toJson(),
      ),
    ];
    for (final run in skillRuns) {
      final message = run.resultSummary.isNotEmpty
          ? run.resultSummary
          : (run.answerReady ? '该部分信息已整理完成' : '该部分还需要继续补充');
      events.add(
        UserEvent(
          type: run.answerReady
              ? UserEventType.processCommit
              : UserEventType.processAppend,
          scope: UserEventScope.skill,
          nodeId: run.domainId,
          runId: run.runId,
          message: message,
          payload: run.toJson(),
        ),
      );
    }
    events.add(
      UserEvent(
        type: UserEventType.processCommit,
        scope: UserEventScope.aggregation,
        nodeId: 'aggregation.final',
        message: processSummary,
        payload: <String, dynamic>{
          ...aggregationState.toJson(),
          'referenceCount': uiReferences.length,
        },
      ),
    );
    return events;
  }

  List<Map<String, dynamic>> _buildUiProcessTimelineV2({
    required List<UserEvent> userEvents,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    return userEvents
        .map(
          (event) => <String, dynamic>{
            'scope': event.scope.name,
            'type': event.type.name,
            'nodeId': event.nodeId,
            'runId': event.runId,
            'summary': event.message,
            'payload': event.payload,
            'references': event.scope == UserEventScope.aggregation
                ? uiReferences
                : const <Map<String, dynamic>>[],
          },
        )
        .toList(growable: false);
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
          final m = Map<String, dynamic>.from(r);
          m.remove('version');
          return m;
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
    final result =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final interpretation = (result['interpretation'] as String?)?.trim() ?? '';
    if (interpretation.isNotEmpty) return interpretation;
    final text = (result['text'] as String?)?.trim() ?? '';
    if (text.isNotEmpty) return text;
    return fallback;
  }

  String _resolveProcessSummary({
    required Map<String, dynamic> answerPayload,
    required String domainId,
    required AssistantRunRequest request,
    required List<Map<String, dynamic>> uiReferences,
    required List<Map<String, dynamic>> toolErrors,
    required ReactRuntimeResult result,
  }) {
    final fromPayload =
        (answerPayload['processSummary'] as String?)?.trim() ?? '';
    if (fromPayload.isNotEmpty) return fromPayload;
    final isWeatherLike = _isWeatherLikeRequest(
      domainId: domainId,
      request: request,
      answerPayload: answerPayload,
    );
    final nextAction =
        ((answerPayload['decision'] as Map?)?['nextAction'] as String?)
            ?.trim() ??
        '';
    if (nextAction == 'ask_user') {
      return '还差一个关键信息，我先和你确认后再继续。';
    }
    if (uiReferences.isNotEmpty) {
      if (isWeatherLike) {
        return '已核对 ${uiReferences.length} 个天气来源，正在整理可直接参考的结论。';
      }
      return '已核对 ${uiReferences.length} 个来源，正在整理可直接参考的结论。';
    }
    if (toolErrors.isNotEmpty) {
      if (isWeatherLike) {
        return '已尝试获取实时天气，但暂时没有拿到可靠来源，先给你当前可执行的建议。';
      }
      return '已尝试获取相关信息，但暂时没有拿到足够可靠的来源，先给你当前可执行的建议。';
    }
    final fallback = _extractUiSummary(answerPayload, result.finalText).trim();
    if (fallback.isNotEmpty) return fallback;
    return '已整理出当前可直接查看的回答。';
  }

  int _resolveProcessReferenceCount({
    required Map<String, dynamic> answerPayload,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final fromPayload = (answerPayload['processReferenceCount'] as num?)
        ?.toInt();
    if (fromPayload != null && (fromPayload > 0 || uiReferences.isEmpty)) {
      return fromPayload;
    }
    return uiReferences.length;
  }

  List<Map<String, dynamic>> _buildUiProcessContentBlocks({
    required String processSummary,
    required List<Map<String, dynamic>> uiReferences,
  }) {
    final summary = processSummary.trim();
    if (summary.isEmpty) return const <Map<String, dynamic>>[];
    final refs = uiReferences
        .map(
          (ref) => <String, dynamic>{
            'title': (ref['title'] ?? '').toString(),
            'url': (ref['url'] ?? '').toString(),
            'source': (ref['source'] ?? '').toString(),
          },
        )
        .where(
          (ref) =>
              (ref['title'] as String).trim().isNotEmpty &&
              (ref['url'] as String).trim().isNotEmpty,
        )
        .toList(growable: false);
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'type': refs.isNotEmpty ? 'searchSummary' : 'text',
        'text': summary,
        'references': refs,
      },
    ];
  }

  String _buildFallbackMarkdown({
    required Map<String, dynamic> answerPayload,
    required String domainId,
    required AssistantRunRequest request,
    required List<Map<String, dynamic>> uiReferences,
    required List<Map<String, dynamic>> toolErrors,
    required ReactRuntimeResult result,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    if (uiReferences.isNotEmpty) return '';
    final isWeatherLike = _isWeatherLikeRequest(
      domainId: domainId,
      request: request,
      answerPayload: answerPayload,
    );
    final resultMap =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final readableResultText = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
      (resultMap['text'] as String?)?.trim() ?? '',
    ).trim();
    if (toolErrors.isEmpty &&
        !result.degraded &&
        (answerPayload['messageKind'] as String?)?.trim() != 'fallback' &&
        synthesisReadiness.ready &&
        readableResultText.isNotEmpty &&
        !AssistantContentFilters.isProgressPlaceholder(readableResultText)) {
      return '';
    }
    final reason = _extractToolErrorReason(toolErrors);
    if (isWeatherLike) {
      final city = _inferWeatherCity(
        request: request,
        answerPayload: answerPayload,
      );
      final titleCity = city.isEmpty ? '当前城市' : city;
      final siteLabel = city.isEmpty ? '对应城市' : titleCity;
      return '''
## 🌤️ $titleCity 天气

暂时查不到实时天气数据，${reason.isEmpty ? '天气来源暂时不可用。' : reason}

**你可以**
1. 打开手机天气 App 查看 $siteLabel 最新天气
2. 访问[中国天气网](http://www.weather.com.cn)搜索“$siteLabel”
3. 稍后再问我，或直接告诉我你想查询的城市
''';
    }
    final question = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '这个问题';
    return '''
## 💡 先给你一个可靠结论

我暂时没拿到足够稳定的实时来源来完整回答“$question”，${reason.isEmpty ? '所以先给你当前最稳妥的下一步建议。' : reason}

**你可以尝试**
1. 换一种更具体的说法再问我
2. 如果这是实时问题，稍后再让我重新查一次
3. 如果你愿意，我也可以先基于已有信息给你一个通用建议
''';
  }

  String _extractToolErrorReason(List<Map<String, dynamic>> toolErrors) {
    if (toolErrors.isEmpty) return '';
    final latest = toolErrors.last;
    final message = (latest['message'] as String?)?.trim() ?? '';
    if (message.isEmpty) return '';
    if (message.contains('暂不可用') || message.contains('超时')) {
      return message;
    }
    return '$message。';
  }

  String _inferWeatherCity({
    required AssistantRunRequest request,
    required Map<String, dynamic> answerPayload,
  }) {
    final slotState =
        (answerPayload['slotState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final citySlot = slotState['city'];
    if (citySlot is Map) {
      final value = (citySlot['value'] as String?)?.trim() ?? '';
      if (value.isNotEmpty) return value;
    } else if (citySlot is String && citySlot.trim().isNotEmpty) {
      return citySlot.trim();
    }
    final query = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    final match = RegExp(
      r'([\u4e00-\u9fa5]{2,8}(?:市|区|县)|[\u4e00-\u9fa5]{2,8})(?:今天天气|天气|气温|降雨|风力)',
    ).firstMatch(query);
    return (match?.group(1) ?? '').trim();
  }

  bool _isWeatherLikeRequest({
    required String domainId,
    required AssistantRunRequest request,
    required Map<String, dynamic> answerPayload,
  }) {
    final loweredDomain = domainId.trim().toLowerCase();
    if (loweredDomain.contains('weather')) return true;
    final query = request.messages.isNotEmpty
        ? request.messages.last.content.trim()
        : '';
    if (RegExp(r'(天气|气温|降雨|风力|体感|预报)').hasMatch(query)) {
      return true;
    }
    return _inferWeatherCity(
      request: request,
      answerPayload: answerPayload,
    ).isNotEmpty;
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
    final userMd = (answerPayload['userMarkdown'] as String?)?.trim() ?? '';
    if (userMd.isNotEmpty &&
        !AssistantContentFilters.isProgressPlaceholder(userMd)) {
      return userMd;
    }
    // 优先级 2：fallback（finalText），过滤 JSON 原文和进度文本
    final fb = OpenAiCompatibleLlmProvider.stripXmlToolCalls(fallback).trim();
    if (fb.isEmpty ||
        AssistantContentFilters.isJsonEnvelope(fb) ||
        AssistantContentFilters.isProgressPlaceholder(fb)) {
      return '';
    }
    return fb;
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
        'answerPayload':
            structured['answerPayload'] ?? const <String, dynamic>{},
        'uiAnswer': structured['uiAnswer'] ?? const <String, dynamic>{},
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
      if (path == 'fallback_local') return true;
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

  bool _webEvidenceGatePassed(
    List<Map<String, dynamic>> packs, {
    required int freshnessHoursMax,
    required bool authorityRequired,
  }) {
    if (packs.isEmpty) return !authorityRequired;
    for (final pack in packs) {
      final coverage = _asDouble(pack['coverage']);
      final confidence = _asDouble(pack['confidence']);
      final freshnessHours = _asDouble(pack['freshnessHours']);
      final authorityScore = _asDouble(pack['authorityScore']);
      if (coverage < 0.7 ||
          confidence < 0.65 ||
          freshnessHours > freshnessHoursMax ||
          (authorityRequired && authorityScore < 0.3)) {
        return false;
      }
    }
    return true;
  }

  /// 从 assets 加载对应领域的 retrieval_policy.json。
  /// 若文件不存在或解析失败，返回空 Map，调用方使用默认值。
  Future<Map<String, dynamic>> _loadRetrievalPolicy(String domainId) async {
    if (domainId.isEmpty) return const <String, dynamic>{};
    const basePath = 'assets/personal_assistant/skills';
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
  Future<String> _summarizeWithLlm({
    required String transcript,
    required String sessionId,
    required String runId,
    required String traceId,
  }) async {
    final result = await _runtime.run(
      messages: <Map<String, dynamic>>[
        <String, dynamic>{'role': 'user', 'content': transcript},
      ],
      maxIterations: 1,
      goal: '压缩以上对话历史为简洁摘要',
      templateId: 'summarize_session',
      templateVersion: '',
      templateContext: const <String, dynamic>{},
      templateVariables: <String, dynamic>{'sessionTranscript': transcript},
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    return result.finalText.trim();
  }

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
      'skillPersona': skillPersona,
      'skillCatalog': skillCatalog,
      'skillExecutionShell': skillExecutionShell.toJson(),
      'traceId': '',
    };
  }

  Future<_ResolvedSkillContext> _resolveSkillContext({
    required String domainId,
    required String userQuery,
    DialogueRoundScript? dialogueRoundScript,
  }) async {
    try {
      final skills = await _skillLoader.loadBundledSkills();
      final globalPolicy = await _loadGlobalPolicyMarkdown();
      if (skills.isEmpty) {
        if (globalPolicy.isEmpty) return const _ResolvedSkillContext.empty();
        return _ResolvedSkillContext(
          skillName: 'Global Policy',
          instructionMarkdown: globalPolicy,
          executionShell: const SkillExecutionShell(),
        );
      }
      final matched = _skillRouter.resolveSkillForDomain(
        userText: userQuery,
        domainId: domainId,
        skills: skills,
      );
      final effectiveMatch = domainId == _domainRouter.fallbackDomainId
          ? (_skillRouter.resolveSkill(userQuery, skills) ?? matched)
          : matched;
      if (effectiveMatch == null) {
        if (globalPolicy.isEmpty) return const _ResolvedSkillContext.empty();
        return _ResolvedSkillContext(
          skillName: 'Global Policy',
          instructionMarkdown: globalPolicy,
          executionShell: const SkillExecutionShell(),
        );
      }
      final skillPolicy = await _loadSkillPolicyMarkdown(domainId);
      final phaseRefs = await _loadPhaseAwareReferences(
        domainId: domainId,
        dialogueRoundScript: dialogueRoundScript,
      );
      final mergedInstruction = _mergeSkillInstructions(
        globalPolicy: globalPolicy,
        baseSkillInstruction: effectiveMatch.skillInstructionMarkdown,
        skillPolicy: skillPolicy,
        phaseReferences: phaseRefs,
      );
      return _ResolvedSkillContext(
        skillName: effectiveMatch.name,
        instructionMarkdown: mergedInstruction,
        executionShell: effectiveMatch.executionShell,
      );
    } catch (_) {
      return const _ResolvedSkillContext.empty();
    }
  }

  /// 根据当前对话状态决定加载哪些 references/ 参考文件（phase-aware）。
  ///
  /// 加载策略：
  /// - domain-knowledge.md：始终加载（领域约束与背景知识）
  /// - tool-call-guidance.md：规划阶段（有待填充槽位时）加载
  /// - output-examples.md：回答阶段（槽位已就绪时）加载
  Future<String> _loadPhaseAwareReferences({
    required String domainId,
    DialogueRoundScript? dialogueRoundScript,
  }) async {
    if (domainId.trim().isEmpty) return '';

    final bool hasRequiredSlots =
        dialogueRoundScript != null &&
        dialogueRoundScript.requiredFieldsForNextState.isNotEmpty;

    final buffer = StringBuffer();

    // 始终注入领域知识
    final domainKnowledge = await _loadReferenceFile(
      domainId: domainId,
      fileName: 'domain-knowledge.md',
    );
    if (domainKnowledge.isNotEmpty) {
      buffer.write('## 领域知识与约束\n\n');
      buffer.write(domainKnowledge);
    }

    // 规划阶段（有必填槽位）注入工具调用指引
    if (hasRequiredSlots) {
      final toolGuidance = await _loadReferenceFile(
        domainId: domainId,
        fileName: 'tool-call-guidance.md',
      );
      if (toolGuidance.isNotEmpty) {
        if (buffer.isNotEmpty) buffer.write('\n\n---\n\n');
        buffer.write('## 工具调用指引\n\n');
        buffer.write(toolGuidance);
      }
    }

    // 回答阶段（槽位已就绪或无需工具）注入输出示例
    if (!hasRequiredSlots) {
      final outputExamples = await _loadReferenceFile(
        domainId: domainId,
        fileName: 'output-examples.md',
      );
      if (outputExamples.isNotEmpty) {
        if (buffer.isNotEmpty) buffer.write('\n\n---\n\n');
        buffer.write('## 输出示例（Few-shot）\n\n');
        buffer.write(outputExamples);
      }
    }

    return buffer.toString();
  }

  Future<String> _loadReferenceFile({
    required String domainId,
    required String fileName,
  }) async {
    final path =
        'assets/personal_assistant/skills/${domainId.trim()}/references/$fileName';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  Future<String> _loadGlobalPolicyMarkdown() async {
    const path =
        'assets/personal_assistant/prompts/global/stack.global_policy.md';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  Future<String> _loadSkillPersona(String domainId) async {
    if (domainId.trim().isEmpty) return '';
    final policyText = await _loadSkillPolicyMarkdown(domainId);
    if (policyText.isEmpty) return '';
    // Extract persona-related sections from skill policy
    final lines = policyText.split('\n');
    final personaBuffer = StringBuffer();
    var inPersonaSection = false;
    for (final line in lines) {
      final lower = line.toLowerCase().trim();
      if (lower.startsWith('## ') &&
          (lower.contains('人设') ||
              lower.contains('persona') ||
              lower.contains('语气') ||
              lower.contains('tone') ||
              lower.contains('风格') ||
              lower.contains('style'))) {
        inPersonaSection = true;
        personaBuffer.writeln(line);
        continue;
      }
      if (lower.startsWith('## ') && inPersonaSection) {
        inPersonaSection = false;
      }
      if (inPersonaSection) {
        personaBuffer.writeln(line);
      }
    }
    final persona = personaBuffer.toString().trim();
    return persona.isNotEmpty ? persona : policyText;
  }

  Future<String> _loadSkillPolicyMarkdown(String domainId) async {
    if (domainId.trim().isEmpty) return '';
    final path =
        'assets/personal_assistant/skills/${domainId.trim()}/scripts/skill.policy.md';
    try {
      final text = await rootBundle.loadString(path);
      return text.trim();
    } catch (_) {
      return '';
    }
  }

  String _mergeSkillInstructions({
    required String globalPolicy,
    required String baseSkillInstruction,
    required String skillPolicy,
    String phaseReferences = '',
  }) {
    final blocks = <String>[
      if (globalPolicy.trim().isNotEmpty) globalPolicy.trim(),
      if (baseSkillInstruction.trim().isNotEmpty) baseSkillInstruction.trim(),
      if (skillPolicy.trim().isNotEmpty) skillPolicy.trim(),
      if (phaseReferences.trim().isNotEmpty) phaseReferences.trim(),
    ];
    return blocks.join('\n\n---\n\n');
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
            'toolName': event.message.replaceFirst('calling ', '').trim(),
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

  Future<String> _resolveDomainId(
    AssistantRunRequest request, {
    required bool forceRefreshCatalog,
  }) async {
    return _resolveFallbackDomainId(
      request,
      forceRefreshCatalog: forceRefreshCatalog,
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
    };
  }

  Future<void> switchSession(String sessionId) async {
    await _sessionManager.load();
    _sessionManager.switchAssistantSession(sessionId);
    await _sessionManager.save();
  }
}

class _ResolvedSkillContext {
  const _ResolvedSkillContext({
    required this.skillName,
    required this.instructionMarkdown,
    required this.executionShell,
  });

  const _ResolvedSkillContext.empty()
    : skillName = '',
      instructionMarkdown = '',
      executionShell = const SkillExecutionShell();

  final String skillName;
  final String instructionMarkdown;
  final SkillExecutionShell executionShell;
}

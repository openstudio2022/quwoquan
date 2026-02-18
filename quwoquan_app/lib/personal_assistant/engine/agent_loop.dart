import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';

class PersonalAssistantAgentLoop {
  PersonalAssistantAgentLoop(
    this._runtime, {
    required AssistantSessionManager sessionManager,
    required AssistantMemoryRepository memoryRepository,
  }) : _sessionManager = sessionManager,
       _memoryRepository = memoryRepository;

  final ReactRuntime _runtime;
  final AssistantSessionManager _sessionManager;
  final AssistantMemoryRepository _memoryRepository;

  Future<AssistantRunResponse> run(AssistantRunRequest request) async {
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
    final messages = request.messages
        .map((m) => <String, String>{'role': m.role, 'content': m.content})
        .toList(growable: true);
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
    final runStartAt = DateTime.now();
    await AppLogService.instance.writeEvent(
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
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
    );
    final runLatencyMs = DateTime.now().difference(runStartAt).inMilliseconds;
    _sessionManager.appendMessage(
      sessionId: sessionId,
      role: 'assistant',
      content: result.finalText,
    );
    await _sessionManager.save();
    await _memoryRepository.rememberText(
      id: '${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
      text: result.finalText,
      metadata: <String, dynamic>{
        'sessionId': sessionId,
        'userId': request.userId ?? '',
        'deviceProfile': request.deviceProfile,
      },
    );
    final response = AssistantRunResponse(
      finalText: result.finalText,
      traces: result.traces,
      runId: runId,
      traceId: traceId,
    );
    await AssistantAgentLoopDevLogger.instance.writeRun(
      request: request,
      response: response,
      sessionId: sessionId,
      runId: runId,
    );
    await AppLogService.instance.writeEvent(
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

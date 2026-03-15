import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart'
    as legacy_agent;
import 'package:quwoquan_app/assistant/conversation/protocol/run_request.dart'
    as legacy_request;

class AssistantAgentLoop {
  AssistantAgentLoop({
    required ReactRuntime runtime,
    required AssistantSessionManager sessionManager,
    required AssistantMemoryRepository memoryRepository,
    ToolMetadataRegistry? toolMetadataRegistry,
  }) : _delegate = legacy_agent.PersonalAssistantAgentLoop(
         runtime,
         sessionManager: sessionManager,
         memoryRepository: memoryRepository,
         toolMetadataRegistry: toolMetadataRegistry,
       );

  final legacy_agent.PersonalAssistantAgentLoop _delegate;

  Future<AssistantRunResponse> run(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final response = await _delegate.run(
      legacy_request.AssistantRunRequest.fromJson(request.toJson()),
      onTraceEvent: onTraceEvent == null
          ? null
          : (AssistantTraceEvent event) {
              onTraceEvent(AssistantTraceEvent.fromJson(event.toJson()));
            },
    );
    return AssistantRunResponse.fromJson(response.toJson());
  }

  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) {
    return _delegate.classifyDomain(query, contextScopeHint);
  }

  Future<List<Map<String, dynamic>>> listSessions() async {
    final sessions = await _delegate.listSessions();
    return sessions
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    final detail = await _delegate.sessionDetail(sessionId);
    if (detail == null) return null;
    return Map<String, dynamic>.from(detail);
  }

  Future<void> switchSession(String sessionId) {
    return _delegate.switchSession(sessionId);
  }
}

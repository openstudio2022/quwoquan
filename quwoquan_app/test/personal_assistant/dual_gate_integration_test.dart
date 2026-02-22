import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:test/test.dart';

void main() {
  group('Dual gate integration', () {
    late Directory tempDir;
    late PersonalAssistantAgentLoop agentLoop;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('pa_dual_gate_');
      final runtime = ReactRuntime(
        llmProvider: const HeuristicLocalLlmProvider(),
        toolRegistry: AssistantToolRegistry(),
      );
      agentLoop = PersonalAssistantAgentLoop(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    test('pre-gate blocks when context missing', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 'dual-pre',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );
      expect(response.errorCode, equals('missing_context'));
      expect(
        (response.structuredResponse['domainPrecheck'] as Map?)?['canEnterDomain'],
        isFalse,
      );
    });

    test('post-gate triggers gap fill retry when evidence insufficient', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 'dual-post',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天实时天气如何'),
          ],
          gpsLocation: <String, dynamic>{'city': '深圳'},
        ),
      );
      final traces = response.traces;
      expect(
        traces.any(
          (trace) =>
              trace.type == AssistantTraceEventType.lifecycleStart &&
              trace.message.contains('synthesis readiness failed'),
        ),
        isTrue,
      );
    });
  });
}


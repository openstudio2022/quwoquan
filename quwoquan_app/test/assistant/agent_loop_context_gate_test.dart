import 'dart:io';

import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:test/test.dart';

void main() {
  group('PersonalAssistantAgentLoop context gate', () {
    late Directory tempDir;
    late PersonalAssistantAgentLoop agentLoop;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('pa_context_gate_');
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

    test('does not block weather query when city is in user message', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 's1',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气最近怎么样'),
          ],
        ),
      );

      expect(response.errorCode, isNull);
      expect(
        (response.structuredResponse['domainPrecheck']
            as Map?)?['canEnterDomain'],
        isTrue,
      );
      final fillTasks =
          (response.structuredResponse['fillTasks']
                  as Map?)?['contextFillTasks']
              as List?;
      expect(fillTasks, isNotNull);
      expect(fillTasks!, isEmpty);
    });
  });
}

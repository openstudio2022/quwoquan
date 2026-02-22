import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
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

    test('blocks realtime query without location context', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 's1',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气最近怎么样'),
          ],
        ),
      );

      expect(response.degraded, isTrue);
      expect(response.errorCode, equals('missing_context'));
      expect(response.finalText, contains('补齐上下文'));
      expect(
        (response.structuredResponse['domainPrecheck']
            as Map?)?['canEnterDomain'],
        isFalse,
      );
      final fillTasks =
          (response.structuredResponse['fillTasks'] as Map?)?['contextFillTasks']
              as List?;
      expect(fillTasks, isNotNull);
      expect(fillTasks!.isNotEmpty, isTrue);
      expect(response.structuredResponse['answerEligibility'], equals('blocked'));
      final contextSlots = response.structuredResponse['contextSlots'] as List?;
      expect(contextSlots, isNotNull);
      expect(
        contextSlots!
            .whereType<Map>()
            .any((slot) => slot['status'] == 'need_query'),
        isTrue,
      );
    });
  });
}

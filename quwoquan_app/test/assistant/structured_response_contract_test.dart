import 'dart:io';

import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:test/test.dart';

void main() {
  group('Structured response contract', () {
    late Directory tempDir;
    late LocalPhaseExecutionOwner agentLoop;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp(
        'pa_structured_contract_',
      );
      final runtime = ReactRuntime(
        llmProvider: const HeuristicLocalLlmProvider(),
        toolRegistry: AssistantToolRegistry(),
      );
      agentLoop = LocalPhaseExecutionOwner(
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

    test('contains reasoning/self-check/diagnostics contract', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 's-structured',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '请帮我总结一下今天的工作计划'),
          ],
        ),
      );
      final structured = response.structuredResponse;
      expect(structured.containsKey('answerEligibility'), isTrue);
      expect(structured.containsKey('reasoningBasis'), isTrue);
      expect(structured.containsKey('selfCheck'), isTrue);
      expect(structured.containsKey('diagnostics'), isTrue);
    });
  });
}

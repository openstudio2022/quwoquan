import 'dart:io';

import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
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

    test('contains reasoning/self-check/diagnostics and slot fields', () async {
      final response = await agentLoop.run(
        const AssistantRunRequest(
          sessionId: 's-structured',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '请帮我总结一下今天的工作计划'),
          ],
        ),
      );
      final structured = response.structuredResponse;
      expect(structured.containsKey('contextSlots'), isTrue);
      expect(structured.containsKey('fillActions'), isTrue);
      expect(structured.containsKey('missingCriticalSlots'), isTrue);
      expect(structured.containsKey('answerEligibility'), isTrue);
      expect(structured.containsKey('reasoningBasis'), isTrue);
      expect(structured.containsKey('selfCheck'), isTrue);
      expect(structured.containsKey('diagnostics'), isTrue);
      expect(structured.containsKey('qualityMetrics'), isTrue);
      final quality =
          (structured['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(quality.containsKey('decisionParseSuccess'), isTrue);
      expect(quality.containsKey('renderFallback'), isTrue);
      expect(quality.containsKey('heuristicFallbackUsed'), isTrue);
      expect(quality.containsKey('evidenceSufficient'), isTrue);
      expect(quality.containsKey('freshnessSatisfied'), isTrue);
      expect(quality.containsKey('criticalSlotsResolved'), isTrue);
    });
  });
}

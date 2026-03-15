import 'package:quwoquan_app/assistant/internal_legacy/engine/llm_provider.dart';
import 'package:quwoquan_app/assistant/internal_legacy/engine/model_config.dart';
import 'package:test/test.dart';

void main() {
  group('MiMo live smoke', () {
    test('can call configured MiMo model (openai-compatible)', () async {
      final loader = const AssistantModelConfigLoader();
      final configs = loader.loadDefaultSync();
      if (configs.isEmpty) {
        markTestSkipped('No model config found in project-local assistant config.');
        return;
      }

      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const ModelOnlyFailureLlmProvider(),
      );
      for (final cfg in configs) {
        provider.registerRemoteModel(cfg);
      }
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{
            'role': 'user',
            'content': '请用一句话回答：今天适合如何安排学习和休息？',
          },
        ],
        availableTools: const <String>[],
      );
      expect(output.text.trim().isNotEmpty, isTrue);
    }, timeout: const Timeout(Duration(seconds: 30)));
  });
}

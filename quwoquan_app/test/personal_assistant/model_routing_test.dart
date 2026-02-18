import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/model_config.dart';
import 'package:test/test.dart';

void main() {
  group('Model routing', () {
    test('can list/switch/current model', () async {
      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const HeuristicLocalLlmProvider(),
      );
      const configs = <AssistantModelRuntimeConfig>[
        AssistantModelRuntimeConfig(
          modelRef: 'p/m1',
          providerId: 'p',
          modelId: 'm1',
          baseUrl: 'https://example.com/v1',
          apiKey: 'k1',
        ),
        AssistantModelRuntimeConfig(
          modelRef: 'p/m2',
          providerId: 'p',
          modelId: 'm2',
          baseUrl: 'https://example.com/v1',
          apiKey: 'k2',
        ),
      ];
      provider.registerRemoteModels(configs);

      expect(provider.availableModelRefs.length, equals(2));
      expect(provider.activeModelRef, equals('p/m1'));
      expect(provider.switchModel('p/m2'), isTrue);
      expect(provider.activeModelRef, equals('p/m2'));
      expect(provider.switchModel('not-exist'), isFalse);
    });

    test('falls back to local strategy when no config exists', () async {
      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const HeuristicLocalLlmProvider(),
      );
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '请帮我搜索天气'},
        ],
        availableTools: const <String>['web_search'],
      );
      expect(output.text.trim().isNotEmpty, isTrue);
    });

    test('independent config loader does not require moltbot', () {
      final loader = const AssistantModelConfigLoader();
      final defaults = loader.loadDefaultSync();
      expect(defaults, isA<List<AssistantModelRuntimeConfig>>());
    });
  });
}

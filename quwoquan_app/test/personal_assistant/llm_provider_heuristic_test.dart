import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:test/test.dart';

void main() {
  group('HeuristicLocalLlmProvider fallback contract', () {
    const provider = HeuristicLocalLlmProvider();

    test('always returns degraded fallback without tool calls', () async {
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '深圳天气怎么样'},
        ],
        availableTools: const <String>[
          'web_search',
          'local_context',
          'media_gallery',
          'intent_bridge',
        ],
      );

      expect(output.degraded, isTrue);
      expect(output.hasToolCalls, isFalse);
      expect(output.text, contains('安全降级模式'));
    });

    test('fallback text is stable and does not expose tool actions', () async {
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '帮我打开相册并识别图片'},
        ],
        availableTools: const <String>[],
      );

      expect(output.degraded, isTrue);
      expect(output.text, contains('当前模型服务不可用'));
      expect(output.text, isNot(contains('调用系统')));
      expect(output.text, isNot(contains('设备上下文')));
    });
  });

  group('SwitchableAssistantLlmProvider model availability contract', () {
    test('returns model_unavailable when no remote model registered', () async {
      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const HeuristicLocalLlmProvider(),
      );
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '深圳天气怎么样'},
        ],
        availableTools: const <String>['web_search'],
      );

      expect(output.degraded, isTrue);
      expect(output.modelPath, equals('model_unavailable'));
      expect(output.text, contains('当前未配置可用模型'));
      expect(output.text, isNot(contains('安全降级模式')));
    });
  });
}

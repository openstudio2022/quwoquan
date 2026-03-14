import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:test/test.dart';

void main() {
  group('HeuristicLocalLlmProvider fallback contract', () {
    const provider = HeuristicLocalLlmProvider();

    test('weather query fail-closes instead of planning local tool calls', () async {
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
      expect(output.failureCode, equals(AssistantFailureCode.heuristicFallback));
      expect(output.text, contains('"nextAction":"abort"'));
    });

    test('without usable context it still returns a safe user-facing fallback', () async {
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '帮我打开相册并识别图片'},
        ],
        availableTools: const <String>[],
        templateId: 'fallback.local_only',
      );

      expect(output.degraded, isTrue);
      expect(output.text, contains('当前未能稳定连接模型服务'));
      expect(output.text, isNot(contains('调用系统')));
      expect(output.text, isNot(contains('设备上下文')));
    });

    test('synthesis stage also fail-closes instead of fabricating structured answer', () async {
      final output = await provider.reason(
        messages: const <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': '深圳天气怎么样'},
          <String, dynamic>{
            'role': 'tool',
            'content':
                '{"toolName":"web_search","ok":true,"data":{"summary":"深圳今天多云，气温 24°C。","references":[{"title":"深圳天气预报","url":"https://example.com/weather","source":"example.com"}]}}',
          },
        ],
        availableTools: const <String>[],
        templateId: 'synthesizer.final_answer',
      );

      expect(output.degraded, isTrue);
      expect(output.hasToolCalls, isFalse);
      expect(output.text, contains('"nextAction":"abort"'));
      expect(output.text, isNot(contains('https://example.com/weather')));
    });
  });

  group('SwitchableAssistantLlmProvider model availability contract', () {
    test('falls back to fail-closed degraded envelope when no remote model registered', () async {
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
      expect(output.modelPath, contains('fallback_local'));
      expect(output.hasToolCalls, isFalse);
      expect(output.text, contains('"nextAction":"abort"'));
    });
  });
}

import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_provider.dart';
import 'package:test/test.dart';

void main() {
  group('JsonFieldStreamExtractor', () {
    test('extracts target field incrementally across chunks', () {
      final extractor = JsonFieldStreamExtractor('reasonShort');

      final first = extractor.consume('{"reasonShort":"正在');
      final second = extractor.consume('思考\\n第一');
      final third = extractor.consume('步"}');

      expect(first, equals('正在'));
      expect(second, equals('思考\n第一'));
      expect(third, equals('步'));
      expect(extractor.decodedValue, equals('正在思考\n第一步'));
      expect(extractor.isComplete, isTrue);
    });

    test('keeps waiting until target field appears', () {
      final extractor = JsonFieldStreamExtractor('userMarkdown');

      final delta = extractor.consume('{"reasonShort":"先分析问题"}');

      expect(delta, isEmpty);
      expect(extractor.hasMatchedField, isFalse);
      expect(extractor.isComplete, isFalse);
    });

    test('supports nested field path for answer readiness summary', () {
      final extractor = JsonFieldStreamExtractor(
        'answerProcessing.readinessSummary',
      );

      final first = extractor.consume(
        '{"answerProcessing":{"readinessSummary":"已',
      );
      final second = extractor.consume('完成关键信息核对');
      final third = extractor.consume('，开始整理答案"}}');

      expect(first, equals('已'));
      expect(second, equals('完成关键信息核对'));
      expect(third, equals('，开始整理答案'));
      expect(extractor.decodedValue, equals('已完成关键信息核对，开始整理答案'));
      expect(extractor.isComplete, isTrue);
    });

    test(
      'supports nested field path for understanding user facing summary',
      () {
        final extractor = JsonFieldStreamExtractor(
          'understandingSnapshot.userFacingSummary',
        );

        final first = extractor.consume(
          '{"understandingSnapshot":{"userFacingSummary":"我先',
        );
        final second = extractor.consume('确认你最在意的是');
        final third = extractor.consume('今晚还能不能顺利出门。"}}');

        expect(first, equals('我先'));
        expect(second, equals('确认你最在意的是'));
        expect(third, equals('今晚还能不能顺利出门。'));
        expect(extractor.decodedValue, equals('我先确认你最在意的是今晚还能不能顺利出门。'));
        expect(extractor.isComplete, isTrue);
      },
    );
  });

  group('LlmCallOptions', () {
    test('synthesis defaults register answer organization stream field', () {
      expect(
        const LlmCallOptions.synthesis().streamJsonFieldPaths,
        contains('retrievalProcessing.processingSummary'),
      );
      expect(
        const LlmCallOptions.synthesis().streamJsonFieldPaths,
        contains('answerProcessing.readinessSummary'),
      );
    });
  });

  group('ModelCapabilityProfile', () {
    test('maps mimo deepseek qwen and default profiles', () {
      final mimo = ModelCapabilityProfile.forModelRef('mimo/mimo-v2-flash');
      final deepseek = ModelCapabilityProfile.forModelRef(
        'openrouter/deepseek/deepseek-r1',
      );
      final qwen = ModelCapabilityProfile.forModelRef('aliyun/qwen-max');
      final defaultProfile = ModelCapabilityProfile.forModelRef(
        'openai/gpt-4.1',
      );

      expect(mimo.reasoningMode, ModelReasoningMode.nativeField);
      expect(mimo.toolCallMode, ModelToolCallMode.jsonEnvelope);
      expect(mimo.supportsJsonMode, isTrue);

      expect(deepseek.reasoningMode, ModelReasoningMode.nativeField);
      expect(deepseek.supportsReasoningField, isTrue);
      expect(deepseek.reasoningFieldName, equals('reasoning_content'));

      expect(qwen.reasoningMode, ModelReasoningMode.thinkTag);
      expect(qwen.toolCallMode, ModelToolCallMode.xmlTagged);
      expect(qwen.supportsThinkTags, isTrue);

      expect(defaultProfile.reasoningMode, ModelReasoningMode.jsonThinkingText);
      expect(defaultProfile.toolCallMode, ModelToolCallMode.nativeFunction);
      expect(defaultProfile.supportsStreamingAnswer, isTrue);
    });
  });
}

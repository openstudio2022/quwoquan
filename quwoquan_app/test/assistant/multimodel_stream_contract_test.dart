import 'package:quwoquan_app/assistant/internal_legacy/engine/model_config.dart';
import 'package:quwoquan_app/assistant/internal_legacy/engine/stream_json_field_extractor.dart';
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
  });

  group('ModelCapabilityProfile', () {
    test('maps mimo deepseek qwen and default profiles', () {
      final mimo = ModelCapabilityProfile.forModelRef('mimo/mimo-v2-flash');
      final deepseek = ModelCapabilityProfile.forModelRef(
        'openrouter/deepseek/deepseek-r1',
      );
      final qwen = ModelCapabilityProfile.forModelRef('aliyun/qwen-max');
      final defaultProfile = ModelCapabilityProfile.forModelRef('openai/gpt-4.1');

      expect(mimo.reasoningMode, ModelReasoningMode.nativeField);
      expect(mimo.toolCallMode, ModelToolCallMode.jsonEnvelope);
      expect(mimo.supportsJsonMode, isFalse);

      expect(deepseek.reasoningMode, ModelReasoningMode.nativeField);
      expect(deepseek.supportsReasoningField, isTrue);
      expect(deepseek.reasoningFieldName, equals('reasoning_content'));

      expect(qwen.reasoningMode, ModelReasoningMode.thinkTag);
      expect(qwen.toolCallMode, ModelToolCallMode.xmlTagged);
      expect(qwen.supportsThinkTags, isTrue);

      expect(defaultProfile.reasoningMode, ModelReasoningMode.jsonThinkingText);
      expect(
        defaultProfile.toolCallMode,
        ModelToolCallMode.nativeFunction,
      );
      expect(defaultProfile.supportsStreamingAnswer, isTrue);
    });
  });
}

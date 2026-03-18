import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantStreamingAnswerDecoder', () {
    test('structured envelope 只输出 userMarkdown，不泄漏 JSON 前缀', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(
        decoder.appendChunk(
          '{"contractVersion":"assistant_turn","decision":{"nextAction":"answer"},"messageKind":"answer","userMar',
        ),
        isEmpty,
      );

      expect(
        decoder.appendChunk('kdown":"深圳今天天气晴'),
        '深圳今天天气晴',
      );

      expect(
        decoder.appendChunk('，适合出行。","result":{"text":"深圳今天天气晴，适合出行。"}}'),
        '，适合出行。',
      );
    });

    test('plain text answer 遇到内部字段前缀歧义时先缓冲，确认后再展示', () {
      final decoder = AssistantStreamingAnswerDecoder();

      expect(decoder.appendChunk('con'), isEmpty);
      expect(decoder.appendChunk('clusion first.'), 'conclusion first.');
    });
  });
}

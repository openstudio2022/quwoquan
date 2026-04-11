import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:test/test.dart';

void main() {
  test('LlmAssistantOutputJsonView reads userMarkdown / decision / result', () {
    const raw = '{"userMarkdown":"hi","decision":{"nextAction":"answer"}}';
    final r = LlmResponseParser.parse(raw);
    expect(r.ok, isTrue);
    final v = r.assistantOutputView!;
    expect(v.explicitUserMarkdown, 'hi');
    expect(v.nextAction, 'answer');
    expect(v.resultText, isEmpty);
  });

  test('LlmParseResult getters match assistantOutputView', () {
    const raw = '{"result":{"text":"x"}}';
    final r = LlmResponseParser.parse(raw);
    expect(r.ok, isTrue);
    expect(r.resultText, r.assistantOutputView!.resultText);
  });
}

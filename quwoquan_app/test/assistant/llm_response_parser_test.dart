import 'dart:convert';

import 'package:quwoquan_app/assistant/internal_legacy/engine/llm_response_parser.dart';
import 'package:test/test.dart';

void main() {
  test('explicitUserMarkdown 不回退到 result.text', () {
    final raw = jsonEncode(<String, dynamic>{
      'contractVersion': 'assistant_turn',
      'decision': <String, dynamic>{'nextAction': 'tool_call'},
      'messageKind': 'progress',
      'result': <String, dynamic>{
        'text': '<tool_call><name>launch_app</name></tool_call>',
      },
    });

    final parsed = LlmResponseParser.parse(raw);

    expect(parsed.ok, isTrue);
    expect(parsed.explicitUserMarkdown, isEmpty);
    expect(parsed.resultText, '<tool_call><name>launch_app</name></tool_call>');
    expect(LlmResponseParser.extractUserMarkdown(raw), isNull);
  });
}

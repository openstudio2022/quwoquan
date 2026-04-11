import 'dart:convert';

import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:test/test.dart';

void main() {
  test('explicitUserMarkdown 不回退到 result.text', () {
    final raw = jsonEncode(<String, dynamic>{
      'contractId': 'assistant_turn',
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

  test('assistantOutputView 与 explicitUserMarkdown / resultText / nextAction 一致', () {
    final raw = jsonEncode(<String, dynamic>{
      'contractId': 'assistant_turn',
      'userMarkdown': '  hello  ',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'result': <String, dynamic>{'text': ' internal '},
    });
    final parsed = LlmResponseParser.parse(raw);
    expect(parsed.ok, isTrue);
    final view = parsed.assistantOutputView;
    expect(view, isNotNull);
    expect(view!.explicitUserMarkdown, parsed.explicitUserMarkdown);
    expect(view.resultText, parsed.resultText);
    expect(view.nextAction, parsed.nextAction);
    expect(view.explicitUserMarkdown, 'hello');
    expect(view.nextAction, 'answer');
    expect(view.resultText, 'internal');
  });
}

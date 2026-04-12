import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  test('explicitUserMarkdown 不回退到 result.text', () {
    final raw = jsonEncode(
      assistantLoadJsonObjectFixture('wire_llm_parse_tool_call_progress.json'),
    );

    final parsed = LlmResponseParser.parse(raw);

    expect(parsed.ok, isTrue);
    expect(parsed.explicitUserMarkdown, isEmpty);
    expect(parsed.resultText, '<tool_call><name>launch_app</name></tool_call>');
    expect(LlmResponseParser.extractUserMarkdown(raw), isNull);
  });

  test('assistantOutputView 与 explicitUserMarkdown / resultText / nextAction 一致', () {
    final raw = jsonEncode(
      assistantLoadJsonObjectFixture('wire_llm_parse_user_markdown_answer.json'),
    );
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

  test('tryAssistantTurnOutput 与 tryParseAssistantTurnOutput 在 ok+json 时一致', () {
    final raw = jsonEncode(
      assistantLoadJsonObjectFixture('wire_llm_parse_min_answer.json'),
    );
    final parsed = LlmResponseParser.parse(raw);
    expect(parsed.ok, isTrue);
    expect(parsed.json, isNotNull);
    final j = parsed.json!;
    final a = parsed.tryAssistantTurnOutput();
    final b = tryParseAssistantTurnOutput(j);
    expect(a, isNotNull);
    expect(b, isNotNull);
    expect(a!.toJson(), b!.toJson());
  });

  test('tryAssistantTurnOutput 在非法契约时为 null', () {
    // 负例：故意非契约 JSON，保留内联。
    final raw = jsonEncode(<String, dynamic>{'not': 'assistant_turn'});
    final parsed = LlmResponseParser.parse(raw);
    expect(parsed.ok, isTrue);
    expect(parsed.tryAssistantTurnOutput(), isNull);
  });

  test('metadata fixture 路径：parse 与 AssistantTurnOutput 对齐', () {
    final path = assistantMetadataFixturePath('wire_min_assistant_turn.json');
    final map = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    map['contractId'] = kAssistantTurnCurrentContractId;
    map['decision'] = <String, dynamic>{'nextAction': 'answer'};
    final raw = jsonEncode(map);
    final parsed = LlmResponseParser.parse(raw);
    expect(parsed.tryAssistantTurnOutput()?.toJson(), AssistantTurnOutput.fromJson(map).toJson());
  });
}

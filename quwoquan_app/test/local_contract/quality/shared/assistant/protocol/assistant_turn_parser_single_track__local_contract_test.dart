import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/assistant_stream_chunk_visibility.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/assistant_display_text_resolver.dart';

// spec_ref: specs/feature-tree/assistant-run-learning/spec.md#dom-001
void main() {
  group('canonical assistant_turn parser', () {
    test('只接受 result object 的完整单轨契约', () {
      final parsed = LlmResponseParser.parse(jsonEncode(_canonicalTurn()));

      expect(parsed.ok, isTrue);
      expect(parsed.turn, isNotNull);
      expect(parsed.turn!.contractId, kAssistantTurnCurrentContractId);
      expect(parsed.turn!.result.text, 'plain answer');
      expect(parsed.turn!.userMarkdown, '**visible answer**');
    });

    test('拒绝 result string、缺失 result 与 result 子字段类型漂移', () {
      final stringResult = _canonicalTurn()..['result'] = 'legacy answer';
      final missingResult = _canonicalTurn()..remove('result');
      final coercedHints = _canonicalTurn()
        ..['result'] = <String, dynamic>{
          'text': 'answer',
          'actionHints': <Object>[1],
        };

      expect(LlmResponseParser.parse(jsonEncode(stringResult)).ok, isFalse);
      expect(LlmResponseParser.parse(jsonEncode(missingResult)).ok, isFalse);
      expect(LlmResponseParser.parse(jsonEncode(coercedHints)).ok, isFalse);
    });

    test('拒绝 messageKind 推断、任意 JSON 与外层文本提取', () {
      final missingMessageKind = _canonicalTurn()..remove('messageKind');
      final canonicalJson = jsonEncode(_canonicalTurn());

      expect(
        LlmResponseParser.parse(jsonEncode(missingMessageKind)).ok,
        isFalse,
      );
      expect(LlmResponseParser.parse('{"decision":{}}').ok, isFalse);
      expect(
        LlmResponseParser.parse('```json\n$canonicalJson\n```').ok,
        isFalse,
      );
      expect(
        LlmResponseParser.parse('prefix $canonicalJson suffix').ok,
        isFalse,
      );
    });

    test('拒绝 toolCalls 旧 name alias 与缺失 arguments', () {
      final aliasedToolName = _canonicalTurn()
        ..['toolCalls'] = <Map<String, dynamic>>[
          <String, dynamic>{
            'name': 'web_search',
            'arguments': <String, dynamic>{},
          },
        ];
      final missingArguments = _canonicalTurn()
        ..['toolCalls'] = <Map<String, dynamic>>[
          <String, dynamic>{'toolName': 'web_search'},
        ];

      expect(tryParseAssistantTurnOutput(aliasedToolName), isNull);
      expect(tryParseAssistantTurnOutput(missingArguments), isNull);
    });

    test('共享 Assistant wire fixtures 全部满足 canonical shape', () {
      for (final name in const <String>[
        'wire_llm_parse_min_answer.json',
        'wire_llm_parse_tool_call_progress.json',
        'wire_llm_parse_user_markdown_answer.json',
        'wire_min_assistant_turn.json',
      ]) {
        final raw = File(
          '../quwoquan_service/services/assistant-service/tests/support/'
          'contract_fixtures/$name',
        ).readAsStringSync();
        expect(
          LlmResponseParser.parse(raw).ok,
          isTrue,
          reason: '$name must use canonical assistant_turn',
        );
      }
    });

    test('展示只投影 typed turn，非法 shape 不转成答案', () {
      final canonicalJson = jsonEncode(_canonicalTurn());
      final stringResult = _canonicalTurn()..['result'] = 'legacy answer';

      expect(
        AssistantDisplayTextResolver.extractDisplayMarkdownFromStructuredText(
          canonicalJson,
        ),
        '**visible answer**',
      );
      expect(
        AssistantDisplayTextResolver.extractDisplayMarkdownFromStructuredText(
          jsonEncode(stringResult),
        ),
        isEmpty,
      );
    });

    test('非法 JSON 信封仍被流式可见性边界隔离但不视为合法 turn', () {
      final stringResult = _canonicalTurn()..['result'] = 'legacy answer';
      final raw = jsonEncode(stringResult);

      expect(LlmResponseParser.parse(raw).ok, isFalse);
      expect(isAssistantStreamInternalChunk(raw), isTrue);
      expect(isAssistantStreamInternalChunk('普通可见回答'), isFalse);
    });
  });
}

Map<String, dynamic> _canonicalTurn() => <String, dynamic>{
  'contractId': kAssistantTurnCurrentContractId,
  'decision': <String, dynamic>{'nextAction': 'answer'},
  'messageKind': 'answer',
  'userMarkdown': '**visible answer**',
  'result': <String, dynamic>{
    'text': 'plain answer',
    'summary': 'summary',
    'interpretation': 'direct',
    'actionHints': <String>[],
  },
};

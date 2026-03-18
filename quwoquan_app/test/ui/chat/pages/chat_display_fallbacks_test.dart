import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_display_fallbacks.dart';

void main() {
  test('tool_call completed 会回退为用户可读提示', () {
    const internalXml = '<tool_call><name>launch_app</name></tool_call>';
    final response = AssistantRunResponse(
      finalText: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'messageKind': 'progress',
        'result': const <String, dynamic>{'text': internalXml},
      }),
      traces: const [],
    );

    expect(
      resolveActionLikeCompletedFallback(response),
      '这个操作我暂时还没拿到可展示结果，请再试一次。',
    );
  });

  test('clarify completed 会提示用户补充信息', () {
    final response = AssistantRunResponse(
      finalText: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'ask_user'},
        'messageKind': 'ask_user',
        'askUser': const <String, dynamic>{
          'slotId': 'city',
          'prompt': '请告诉我你要查询哪个城市。',
        },
        'result': const <String, dynamic>{'text': ''},
      }),
      traces: const [],
    );

    expect(
      resolveActionLikeCompletedFallback(response),
      '我还需要你再补充一点信息，这样才能继续。',
    );
  });
}

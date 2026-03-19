import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/local_assistant_entry.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('completed 内部动作协议不会通过本地 entry 回放为 answerDelta', () async {
    final internalXml = '<tool_call><name>launch_app</name></tool_call>';
    final response = AssistantRunResponse(
      finalText: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'tool_call'},
        'messageKind': 'progress',
        'result': <String, dynamic>{'text': internalXml},
      }),
      traces: const <AssistantTraceEvent>[],
      structuredResponse: <String, dynamic>{
        'runArtifacts': <String, dynamic>{
          'displayMarkdown': internalXml,
          'displayPlainText': 'assistant_turn contractId tool_call',
        },
      },
    );
    final entry = LocalAssistantEntry(
      assistantGateway: _FakeAssistantGateway(response),
      requestPolicy: const AssistantRequestPolicy(),
    );

    final events = await entry.runStream(
      request: const AssistantRunRequest(
        sessionId: 'local-entry-sanitizer',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '测试 completed 清洗'),
        ],
      ),
    ).toList();

    expect(
      events.where(
        (event) => event.type == AssistantRunStreamEventType.answerDelta,
      ),
      isEmpty,
    );
    expect(
      events.where((event) => event.type == AssistantRunStreamEventType.chunk),
      isEmpty,
    );
    expect(
      events.where(
        (event) => event.type == AssistantRunStreamEventType.completed,
      ),
      hasLength(1),
    );
  });
}

class _FakeAssistantGateway extends AssistantGateway {
  _FakeAssistantGateway(this._response)
    : super(AssistantRuntime.createForTest());

  final AssistantRunResponse _response;

  @override
  Future<AssistantRunResponse> run(AssistantRunRequest request) async =>
      _response;

  @override
  Future<AssistantRunResponse> runWithTraceStream(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    return _response;
  }
}

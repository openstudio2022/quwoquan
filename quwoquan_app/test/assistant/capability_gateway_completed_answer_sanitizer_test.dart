import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/capability_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('completed 内部动作协议不会通过 CapabilityGateway 回放为 answerDelta', () async {
    final internalXml = '<tool_call><name>launch_app</name></tool_call>';
    final response = AssistantRunResponse(
      finalText: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'tool_call'},
        'messageKind': 'progress',
        'result': <String, dynamic>{'text': internalXml},
      }),
      traces: const <AssistantTraceEvent>[],
      structuredResponse: <String, dynamic>{
        'uiAnswer': <String, dynamic>{'markdownText': internalXml},
        'answerPayload': <String, dynamic>{
          'decision': <String, dynamic>{'nextAction': 'tool_call'},
          'messageKind': 'progress',
          'userMarkdown': 'tool_call',
          'result': <String, dynamic>{'text': internalXml},
        },
        'runArtifacts': <String, dynamic>{
          'displayMarkdown': internalXml,
          'displayPlainText': 'assistant_turn contractVersion tool_call',
        },
      },
    );
    final gateway = CapabilityGateway(
      assistantGateway: _FakeAssistantGateway(response),
      openClawBridge: OpenClawBridge(baseUrl: ''),
    );

    final events = await gateway
        .runStream(
          request: const AssistantRunRequest(
            sessionId: 'capability-gateway-sanitizer',
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '测试 completed 清洗'),
            ],
          ),
          mode: CapabilityRouteMode.localOnly,
        )
        .toList();

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
    : super(AssistantRuntime.createDefault());

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

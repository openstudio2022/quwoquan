import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:test/test.dart';

void main() {
  test('AssistantSessionWireMessage preserves unknown keys', () {
    final w = AssistantSessionWireMessage.fromJson(<String, dynamic>{
      'role': 'user',
      'content': 'hi',
      'extra': 1,
    });
    expect(w.role, 'user');
    expect(w.content, 'hi');
    expect(w.raw['extra'], 1);
  });

  test('AssistantSessionWireDetail roundtrips through toJson/fromJson', () {
    const fact = <String, dynamic>{'key': 'k', 'value': 'v'};
    final d = AssistantSessionWireDetail(
      sessionId: 's1',
      summary: 'sum',
      topicTitle: 'topic',
      messages: [
        AssistantSessionWireMessage.fromJson(<String, dynamic>{
          'role': 'assistant',
          'content': 'c',
        }),
      ],
      sessionPreferenceFacts: [fact],
      longTermPreferenceFacts: const <Map<String, dynamic>>[],
    );
    final back = AssistantSessionWireDetail.fromJson(d.toJson());
    expect(back.sessionId, 's1');
    expect(back.topicTitle, 'topic');
    expect(back.messages.single.content, 'c');
    expect(back.sessionPreferenceFacts.single['key'], 'k');
  });
}

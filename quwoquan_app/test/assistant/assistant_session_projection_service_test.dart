import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_projection_service.dart';

void main() {
  test('buildSessionTopicSummary and descriptors stay consistent', () {
    final service = AssistantSessionProjectionService();
    final sessionMeta = <String, Map<String, dynamic>>{};
    service.updateSessionTopicSummary(
      sessionMeta: sessionMeta,
      sessionId: 's1',
      latestUserQuery: '深圳天气怎么样',
      latestAssistantReply: '深圳今天晴，25°C，适合出行。',
    );

    final descriptors = service.listSessionDescriptors(
      sessions: <String, List<Map<String, dynamic>>>{
        's1': <Map<String, dynamic>>[
          <String, dynamic>{'role': 'user', 'content': '深圳天气怎么样'},
          <String, dynamic>{'role': 'assistant', 'content': '深圳今天晴，25°C，适合出行。'},
        ],
      },
      sessionMeta: sessionMeta,
      activeSessionId: 's1',
    );

    expect(descriptors, hasLength(1));
    expect(descriptors.single.sessionId, equals('s1'));
    expect(descriptors.single.isActive, isTrue);
    expect(descriptors.single.topicTitle, isNotEmpty);
    expect(descriptors.single.topicSummary, contains('深圳今天晴'));
    expect(descriptors.single.messageCount, equals(2));
  });
}

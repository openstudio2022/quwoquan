import 'package:test/test.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_projection_service.dart';

void main() {
  test('updateSessionTopicSummary 只保留必要会话元数据字段', () {
    final service = AssistantSessionProjectionService();
    final sessionMeta = <String, Map<String, dynamic>>{};

    service.updateSessionTopicSummary(
      sessionMeta: sessionMeta,
      sessionId: 'session-1',
      latestUserQuery: '今天深圳天气怎么样',
      latestAssistantReply: '深圳今天晴转多云，适合轻装出行。',
    );

    final meta = sessionMeta['session-1'];
    expect(meta, isNotNull);
    expect(meta!.containsKey('topicTitle'), isTrue);
    expect(meta.containsKey('topicSummary'), isTrue);
    expect(meta.containsKey('updatedAt'), isTrue);
    expect(meta.containsKey('lastUserQuery'), isFalse);
    expect(meta.containsKey('lastAssistantReply'), isFalse);
  });
}

import 'package:quwoquan_cloud_mock/chat_fixture.dart';
import 'package:test/test.dart';

void main() {
  test('新建会话进入 inbox 首屏且不被大 fixture 集截断', () {
    final engine = AlphaChatStateEngine();

    final created = engine.createConversation(
      type: 'group',
      title: '新建会话',
      initialMemberIds: const <String>['fixture_user_friend'],
    );

    final firstPage = engine.listInbox(limit: 100);

    expect(
      firstPage.any((item) => item['id'] == created['conversationId']),
      isTrue,
    );
  });
}

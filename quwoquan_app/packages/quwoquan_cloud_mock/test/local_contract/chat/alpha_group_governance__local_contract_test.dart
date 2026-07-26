import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

/// 群治理 Mock 语义与云侧契约同源（api_integration 对应断言见
/// chat-service group_governance_authorization / group_announcement_governance）：
///   - LeaveConversation：owner 必须先转让；成员退出后 roster 收敛；重复退出 no-op。
///   - UpdateAnnouncement：写权威公告 + system_announcement 消息触达；一致 no-op 不重复触达。
void main() {
  group('alpha chat group governance parity', () {
    test('owner leave is rejected until ownership transfer', () {
      final engine = AlphaChatStateEngine();
      // fixture_conv_group 的 creator 即当前用户（owner）。
      expect(
        () => engine.leaveConversation('fixture_conv_group'),
        throwsA(
          isA<StateError>().having(
            (error) => error.message,
            'message',
            'CHAT.USER.group_owner_must_transfer_before_leave',
          ),
        ),
      );

      engine.transferOwnership('fixture_conv_group', 'fixture_user_weekend_1');
      engine.leaveConversation('fixture_conv_group');

      expect(
        engine.listMemberUserIds('fixture_conv_group'),
        isNot(contains(engine.currentUserId)),
      );

      // 重复退出为 no-op（与云侧幂等回执语义一致）。
      engine.leaveConversation('fixture_conv_group');
    });

    test('leave converges roster revision like a member removal', () {
      int intOf(Object? value) => (value as num?)?.toInt() ?? 0;

      final engine = AlphaChatStateEngine();
      engine.transferOwnership('fixture_conv_group', 'fixture_user_weekend_1');
      final before = engine
          .batchGetConversations(['fixture_conv_group'])
          .first;
      engine.leaveConversation('fixture_conv_group');
      final after = engine.batchGetConversations(['fixture_conv_group']).first;

      expect(
        intOf(after['membersRosterRevision']),
        greaterThan(intOf(before['membersRosterRevision'])),
      );
      expect(intOf(after['memberCount']), intOf(before['memberCount']) - 1);
    });

    test('announcement publish writes authoritative field and reaches inbox',
        () {
      final engine = AlphaChatStateEngine();
      engine.updateAnnouncement('fixture_conv_group', '周六线下面基，老地方集合');

      final home = engine.getGroupHome('fixture_conv_group');
      expect(home['announcement'], '周六线下面基，老地方集合');

      final messages = engine.listMessages(
        conversationId: 'fixture_conv_group',
        limit: 50,
      );
      final announcementMessages = messages
          .where((m) => m['type'] == 'system_announcement')
          .toList(growable: false);
      expect(announcementMessages, hasLength(1));
      expect(announcementMessages.single['content'], contains('周六线下面基'));

      // 公告一致 no-op：不重复触达。
      engine.updateAnnouncement('fixture_conv_group', '周六线下面基，老地方集合');
      final replayed = engine
          .listMessages(conversationId: 'fixture_conv_group', limit: 50)
          .where((m) => m['type'] == 'system_announcement');
      expect(replayed, hasLength(1));
    });

    test('clearing announcement does not append a reach message', () {
      final engine = AlphaChatStateEngine();
      engine.updateAnnouncement('fixture_conv_group', '临时公告');
      engine.updateAnnouncement('fixture_conv_group', '');

      final home = engine.getGroupHome('fixture_conv_group');
      expect(home['announcement'], isEmpty);
      final announcements = engine
          .listMessages(conversationId: 'fixture_conv_group', limit: 50)
          .where((m) => m['type'] == 'system_announcement');
      expect(announcements, hasLength(1), reason: '清空公告不追加触达消息');
    });
  });
}

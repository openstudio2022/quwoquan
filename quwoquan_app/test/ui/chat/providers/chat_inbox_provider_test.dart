import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

void main() {
  group('ChatInboxListNotifier', () {
    test('markConversationRead clears unread and mention counts', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(_UnreadMentionChatRepository()),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(chatInboxListProvider.notifier);
      await notifier.load(force: true);

      final before = container
          .read(chatInboxListProvider)
          .items
          .firstWhere(
            (item) => item.unreadCount > 0 && item.mentionUnreadCount > 0,
          );
      expect(before.unreadCount, greaterThan(0));
      expect(before.mentionUnreadCount, greaterThan(0));

      notifier.markConversationRead(before.id);

      final after = container
          .read(chatInboxListProvider)
          .items
          .firstWhere((item) => item.id == before.id);
      expect(after.unreadCount, equals(0));
      expect(after.mentionUnreadCount, equals(0));
    });
  });
}

class _UnreadMentionChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listInbox({String? cursor, int limit = 20}) async {
    return <ChatInboxDto>[
      ChatInboxDto(
        id: 'conv_unread_mention_test',
        type: 'group',
        title: '未读提及测试会话',
        avatarUrl: '',
        unreadCount: 3,
        mentionUnreadCount: 1,
      ),
    ];
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }
}

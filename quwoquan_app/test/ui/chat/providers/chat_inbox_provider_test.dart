import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_repository_mock.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

class _SwitchableInboxRepository extends MockChatRepository {
  _SwitchableInboxRepository({required super.seedConversations});

  bool returnEmptyInbox = false;

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = 100,
  }) async {
    if (returnEmptyInbox) {
      return const <ChatInboxDto>[];
    }
    return super.listInbox(cursor: cursor, limit: limit);
  }
}

Map<String, dynamic> _conversation(String id, String title) {
  final now = DateTime.utc(2026, 1, 1).toIso8601String();
  return <String, dynamic>{
    '_id': id,
    'id': id,
    'conversationId': id,
    'type': 'group',
    'title': title,
    'avatarUrl': '',
    'creatorId': 'user_001',
    'maxSeq': 0,
    'memberCount': 2,
    'maxGroupSize': 500,
    'receiptEnabled': true,
    'lastMessagePreview': '',
    'lastMessageTime': now,
    'messageCount': 0,
    'status': 'active',
    'createdAt': now,
    'updatedAt': now,
  };
}

void main() {
  group('ChatInboxListNotifier', () {
    test('remote 空列表会清空旧 inbox 缓存', () async {
      final repo = _SwitchableInboxRepository(
        seedConversations: <Map<String, dynamic>>[
          _conversation('conv_a', '旧会话'),
        ],
      );
      final container = ProviderContainer(
        overrides: [chatRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);
      final sub = container.listen(chatInboxListProvider, (_, __) {});
      addTearDown(sub.close);

      await container.read(chatInboxListProvider.notifier).refresh();
      expect(container.read(chatInboxListProvider).items, isNotEmpty);

      repo.returnEmptyInbox = true;
      await container.read(chatInboxListProvider.notifier).refresh();

      expect(container.read(chatInboxListProvider).items, isEmpty);
    });

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

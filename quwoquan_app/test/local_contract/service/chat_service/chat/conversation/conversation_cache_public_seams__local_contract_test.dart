// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/message-home-commercial-ia/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_cache.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

void main() {
  test('one concrete cache serves narrow inbox and message-home seams', () {
    final service = ConversationCacheService();
    final ChatInboxCache inboxCache = service;
    final MessageHomeCache messageHomeCache = service;
    var notifications = 0;
    void listener() => notifications += 1;
    inboxCache.addInboxListener(listener);

    inboxCache.replaceInbox(<ChatInboxCacheEntry>[
      ChatInboxCacheEntry(
        id: 'conversation-inbox',
        type: 'group',
        title: 'Inbox title',
        avatarUrl: '',
        groupAvatarVersion: 0,
        lastMessagePreview: 'Inbox preview',
        lastMessageType: MessageType.text,
        lastMessageTime: DateTime.utc(2026, 8, 6, 1),
        lastSeq: 10,
        unreadCount: 2,
        mentionUnreadCount: 0,
        muted: false,
        pinned: false,
        circleId: '',
      ),
    ]);
    expect(inboxCache.readInbox().single.id, 'conversation-inbox');
    expect(inboxCache.readInboxEntry('conversation-inbox')?.unreadCount, 2);

    // 乐观清零只是展示提示：读取时叠加，但下一次 projection 读结果落地即作废。
    inboxCache.applyOptimisticInboxHint(
      'conversation-inbox',
      const ChatInboxOptimisticHint(unreadCount: 0, mentionUnreadCount: 0),
    );
    expect(inboxCache.readInbox().single.unreadCount, 0);

    inboxCache.replaceInbox(<ChatInboxCacheEntry>[
      ChatInboxCacheEntry(
        id: 'conversation-inbox',
        type: 'group',
        title: 'Inbox title',
        avatarUrl: '',
        groupAvatarVersion: 0,
        lastMessagePreview: 'Inbox preview',
        lastMessageType: MessageType.text,
        lastMessageTime: DateTime.utc(2026, 8, 6, 1),
        lastSeq: 10,
        unreadCount: 3,
        mentionUnreadCount: 1,
        muted: false,
        pinned: false,
        circleId: '',
      ),
    ]);
    expect(inboxCache.readInbox().single.unreadCount, 3);
    expect(inboxCache.readInbox().single.mentionUnreadCount, 1);

    messageHomeCache.putMessageHomeRows(<MessageHomeRow>[
      MessageHomeRow(
        id: 'conversation-message-home',
        kind: 'conversation',
        conversationId: 'conversation-message-home',
        notificationId: '',
        conversationType: 'direct',
        title: 'Message home title',
        summary: 'Message home preview',
        avatarUrl: '',
        groupAvatarVersion: 0,
        lastActiveAt: DateTime.utc(2026, 8, 6, 2),
        unreadCount: 1,
        mentionUnreadCount: 0,
        muted: false,
        pinned: false,
        notificationType: '',
        read: false,
      ),
    ]);
    final cachedRows = messageHomeCache.readMessageHomeRows();
    expect(
      cachedRows.map((row) => row.conversationId),
      contains('conversation-message-home'),
    );
    expect(notifications, 4);

    inboxCache.removeInbox('conversation-inbox');
    expect(inboxCache.readInboxEntry('conversation-inbox'), isNull);
    expect(notifications, 5);

    inboxCache.removeInboxListener(listener);
    service.dispose();
  });
}

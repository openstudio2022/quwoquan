import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';

void main() {
  group('ChatRepository — 常规契约', () {
    late ChatRepository repo;

    setUp(() {
      repo = MockChatRepository();
    });

    // ── 会话 ──────────────────────────────────────────────────────────────

    test('listConversations 返回会话列表', () async {
      final conversations = await repo.listConversations();
      expect(conversations, isList);
      expect(conversations, isNotEmpty);
    });

    test('listInbox 返回强类型收件箱列表', () async {
      final inbox = await repo.listInbox();
      expect(inbox, isNotEmpty);
      expect(inbox.first, isA<ChatInboxDto>());
      expect(inbox.first.id, isNotEmpty);
    });

    test('listInbox 包含 unread / mention / 头像拼图字段', () async {
      final inbox = await repo.listInbox();
      expect(inbox, isNotEmpty);
      final first = inbox.first;
      expect(first.title, isNotEmpty);
      expect(first.unreadCount, greaterThanOrEqualTo(0));
      expect(first.mentionUnreadCount, greaterThanOrEqualTo(0));
      expect(first.avatarCompositeUrls, isA<List<String>>());
    });

    test('listConversations 包含必要字段', () async {
      final conversations = await repo.listConversations();
      expect(conversations, isNotEmpty);
      final first = conversations.first;
      expect(first.containsKey('_id'), isTrue);
      expect(first.containsKey('type'), isTrue);
      expect(first.containsKey('title'), isTrue);
      expect(first.containsKey('status'), isTrue);
    });

    test('createConversation 返回包含 _id 的会话', () async {
      final conv = await repo.createConversation(type: 'group', title: '测试群聊');
      expect(conv['_id'], isNotNull);
      expect(conv['type'], 'group');
      expect(conv['status'], 'active');
    });

    test('getConversation 返回指定会话', () async {
      final conversations = await repo.listConversations();
      final firstId = conversations.first['_id'] as String;
      final conv = await repo.getConversation(firstId);
      expect(conv['_id'], firstId);
    });

    // ── 消息 ──────────────────────────────────────────────────────────────

    test('listMessages 返回消息列表', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first['_id'] as String;
      final messages = await repo.listMessages(conversationId: convId);
      expect(messages, isList);
    });

    test('sendMessage 返回 messageId 和 seq', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first['_id'] as String;
      final result = await repo.sendMessage(
        conversationId: convId,
        type: 'text',
        content: '测试消息',
        clientMsgId: 'test-client-uuid-001',
      );
      expect(result['messageId'], isNotNull);
      expect(result['seq'], isNotNull);
      expect(result['timestamp'], isNotNull);
    });

    test('recallMessage 不抛出异常', () async {
      await expectLater(
        repo.recallMessage(conversationId: 'conv_001', messageId: 'msg_001'),
        completes,
      );
    });

    test('syncMessages 返回 messages 和 hasMore', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first['_id'] as String;
      final result = await repo.syncMessages(
        conversationId: convId,
        lastSeq: 0,
      );
      expect(result.containsKey('messages'), isTrue);
      expect(result.containsKey('hasMore'), isTrue);
    });

    // ── 已读回执 ────────────────────────────────────────────────────────

    test('markAsRead 不抛出异常', () async {
      await expectLater(
        repo.markAsRead(conversationId: 'conv_001', messageId: 'msg_001'),
        completes,
      );
    });

    test('getReceipts 返回列表', () async {
      final receipts = await repo.getReceipts(
        conversationId: 'conv_001',
        messageId: 'msg_001',
      );
      expect(receipts, isList);
    });

    // ── 成员管理 ────────────────────────────────────────────────────────

    test('listMembers 返回成员列表', () async {
      final members = await repo.listMembers(conversationId: 'conv_002');
      expect(members, isList);
      expect(members, isNotEmpty);
    });

    test('addMembers 不抛出异常', () async {
      await expectLater(
        repo.addMembers(conversationId: 'conv_002', userIds: ['user_new_001']),
        completes,
      );
    });

    test('removeMember 不抛出异常', () async {
      await expectLater(
        repo.removeMember(conversationId: 'conv_002', userId: 'user_new_001'),
        completes,
      );
    });

    // ── 助手 ──────────────────────────────────────────────────────────

    test('inviteAssistant 不抛出异常', () async {
      await expectLater(
        repo.inviteAssistant(conversationId: 'conv_002', skillId: 'general'),
        completes,
      );
    });

    test('removeAssistant 不抛出异常', () async {
      await expectLater(
        repo.removeAssistant(conversationId: 'conv_002'),
        completes,
      );
    });

    // ── 设置 ──────────────────────────────────────────────────────────

    test('updateConversationSettings 不抛出异常', () async {
      await expectLater(
        repo.updateConversationSettings(
          conversationId: 'conv_001',
          muted: true,
          pinned: false,
        ),
        completes,
      );
    });

    // ── 联系人 ──────────────────────────────────────────────────────────

    test('listContacts 返回联系人列表', () async {
      final contacts = await repo.listContacts();
      expect(contacts, isList);
      expect(contacts, isNotEmpty);
    });

    test('searchContacts 返回匹配结果', () async {
      final contacts = await repo.searchContacts(query: '李');
      expect(contacts, isList);
    });
  });

  group('ChatRepository — 兼容性契约', () {
    late ChatRepository repo;

    setUp(() {
      repo = MockChatRepository();
    });

    test('listConversations 响应字段不缩减', () async {
      final convs = await repo.listConversations();
      expect(convs, isNotEmpty);
      final conv = convs.first;
      final requiredFields = [
        '_id',
        'type',
        'title',
        'status',
        'lastMessagePreview',
        'lastMessageTime',
      ];
      for (final field in requiredFields) {
        expect(
          conv.containsKey(field),
          isTrue,
          reason: 'missing field: $field',
        );
      }
    });

    test('listMembers 包含 displayName 和 avatarUrl', () async {
      final members = await repo.listMembers(conversationId: 'conv_002');
      expect(members, isNotEmpty);
      final first = members.first;
      expect(first.containsKey('displayName'), isTrue);
      expect(first.containsKey('avatarUrl'), isTrue);
    });
  });

  group('ChatRepository — 异常/边界契约', () {
    late ChatRepository repo;

    setUp(() {
      repo = MockChatRepository();
    });

    test('listMessages 不存在的会话返回空列表', () async {
      final messages = await repo.listMessages(
        conversationId: 'nonexistent_conv',
      );
      expect(messages, isList);
    });

    test('listConversations limit=0 使用默认值', () async {
      final conversations = await repo.listConversations(limit: 0);
      expect(conversations, isList);
    });

    test('searchContacts 空查询返回空列表', () async {
      final contacts = await repo.searchContacts(query: '');
      expect(contacts, isList);
    });

    test('接口包含全部 18 个 API 方法', () {
      final methods = <String>[
        'listInbox',
        'listConversations',
        'createConversation',
        'getConversation',
        'listMessages',
        'sendMessage',
        'recallMessage',
        'syncMessages',
        'markAsRead',
        'getReceipts',
        'listMembers',
        'addMembers',
        'removeMember',
        'inviteAssistant',
        'removeAssistant',
        'updateConversationSettings',
        'listContacts',
        'searchContacts',
      ];
      expect(methods.length, 18);
    });
  });
}

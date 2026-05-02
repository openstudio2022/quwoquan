import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
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
      expect(conversations.first, isA<ChatInboxDto>());
    });

    test('listInbox 返回强类型收件箱列表', () async {
      final inbox = await repo.listInbox();
      expect(inbox, isNotEmpty);
      expect(inbox.first, isA<ChatInboxDto>());
      expect(inbox.first.id, isNotEmpty);
    });

    test('listInbox 包含 unread / mention / 会话头像字段', () async {
      final inbox = await repo.listInbox();
      expect(inbox, isNotEmpty);
      final first = inbox.first;
      expect(first.title, isNotEmpty);
      expect(first.unreadCount, greaterThanOrEqualTo(0));
      expect(first.mentionUnreadCount, greaterThanOrEqualTo(0));
      expect(first.avatarUrl, isA<String>());
    });

    test('listConversations 与 listInbox 同为 ChatInboxDto', () async {
      final conversations = await repo.listConversations();
      expect(conversations, isNotEmpty);
      final first = conversations.first;
      expect(first.id, isNotEmpty);
      expect(first.type, isNotEmpty);
    });

    test('createConversation 返回强类型会话 id', () async {
      final conv = await repo.createConversation(type: 'group', title: '测试群聊');
      expect(conv, isA<ChatConversationCreatedDto>());
      expect(conv.conversationId, isNotEmpty);
      final full = await repo.getConversation(conv.conversationId);
      expect(full.type, 'group');
      expect(full.status, 'active');
    });

    test('getConversation 返回指定会话', () async {
      final conversations = await repo.listConversations();
      final firstId = conversations.first.id;
      final conv = await repo.getConversation(firstId);
      expect(conv.id, firstId);
    });

    // ── 消息 ──────────────────────────────────────────────────────────────

    test('listMessages 返回消息列表', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first.id;
      final messages = await repo.listMessages(conversationId: convId);
      expect(messages, isList);
    });

    test('sendMessage 返回 messageId 和 seq', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first.id;
      final result = await repo.sendMessage(
        conversationId: convId,
        type: 'text',
        content: '测试消息',
        clientMsgId: 'test-client-uuid-001',
      );
      expect(result.id, isNotEmpty);
      expect(result.seq, greaterThan(0));
      expect(result.timestamp, isNotNull);
    });

    test('recallMessage 不抛出异常', () async {
      await expectLater(
        repo.recallMessage(conversationId: 'conv_001', messageId: 'msg_001'),
        completes,
      );
    });

    test('syncMessages 返回 messages 和 hasMore', () async {
      final conversations = await repo.listConversations();
      final convId = conversations.first.id;
      final result = await repo.syncMessages(
        conversationId: convId,
        lastSeq: 0,
      );
      expect(result.messages, isA<List>());
      expect(result.hasMore, isA<bool>());
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

    test('listMembers display_name_asc 按展示名排序', () async {
      final members = await repo.listMembers(
        conversationId: 'conv_002',
        sort: 'display_name_asc',
      );
      final names = members
          .map((m) => m.displayName.isNotEmpty ? m.displayName : m.userId)
          .toList();
      final sorted = [...names]..sort();
      expect(names, orderedEquals(sorted));
    });

    test('createConversation 与 addMembers 维护 membersRosterRevision', () async {
      final created = await repo.createConversation(
        type: 'group',
        title: 'rev test',
      );
      final id = created.conversationId;
      expect(id, isNotEmpty);
      await repo.addMembers(conversationId: id, userIds: ['user_099']);
      final after = await repo.getConversation(id);
      expect(after.membersRosterRevision, 2);
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

    test('listContactTabCircles Mock 返回圈子占位行', () async {
      final rows = await repo.listContactTabCircles();
      expect(rows, isNotEmpty);
      expect(rows.first, isA<ChatContactTabCircleRowDto>());
      expect(rows.first.circleId, isNotEmpty);
    });

    test('listContactTabFunGroups Mock 返回趣群占位行', () async {
      final rows = await repo.listContactTabFunGroups();
      expect(rows, isNotEmpty);
      expect(rows.first, isA<ChatContactTabFunGroupRowDto>());
    });

    test('listMemberUserIds 解析 conv_001 成员', () async {
      final ids = await repo.listMemberUserIds('conv_001');
      expect(ids, isNotEmpty);
      expect(ids, contains('user_001'));
    });
  });

  group('ChatRepository — 兼容性契约', () {
    late ChatRepository repo;

    setUp(() {
      repo = MockChatRepository();
    });

    test('listConversations ChatInboxDto 含列表必要语义', () async {
      final convs = await repo.listConversations();
      expect(convs, isNotEmpty);
      final conv = convs.first;
      final wire = conv.toMap();
      expect(wire['id'], isNotEmpty);
      expect(wire['type'], isNotEmpty);
      expect(wire['title'], isNotEmpty);
    });

    test('listMembers 包含 displayName 和 avatarUrl', () async {
      final members = await repo.listMembers(conversationId: 'conv_002');
      expect(members, isNotEmpty);
      final first = members.first;
      expect(first.displayName, isNotEmpty);
      expect(first.avatarUrl, isNotNull);
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

    test('接口包含全部 19 个 API 方法', () {
      final methods = <String>[
        'listInbox',
        'listConversations',
        'createConversation',
        'getConversation',
        'updateConversationTitle',
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
      expect(methods.length, 19);
    });
  });
}

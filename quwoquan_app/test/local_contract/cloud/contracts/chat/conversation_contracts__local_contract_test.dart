import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Chat Conversation typed contract', () {
    test('keyset list query encodes only cursor and limit', () {
      final payload = encodeChatListConversationsQuery(
        ChatListConversationsQuery(cursor: 'opaque-token', limit: 25),
      );

      expect(payload.pathParameters, isEmpty);
      expect(payload.body, isNull);
      expect(payload.queryParameters, <String, String>{
        'cursor': 'opaque-token',
        'limit': '25',
      });
    });

    test('strictly decodes canonical conversation page', () {
      final page = decodeChatConversationPageSlice(<String, Object?>{
        'items': <Object?>[_conversationWire()],
        'nextCursor': 'opaque-token',
      });

      expect(page.items, hasLength(1));
      expect(page.items.single.id, 'conversation-1');
      expect(page.items.single.nameEditableByAdminOnly, isTrue);
      expect(page.nextCursor, 'opaque-token');
    });

    test('rejects legacy cursor and unknown conversation fields', () {
      expect(
        () => decodeChatConversationPageSlice(<String, Object?>{
          'items': <Object?>[_conversationWire()],
          'cursor': 'retired',
        }),
        throwsFormatException,
      );
      expect(
        () => decodeChatConversation(<String, Object?>{
          ..._conversationWire(),
          'retiredField': true,
        }),
        throwsFormatException,
      );
    });

    test('encodes governance commands and decodes acknowledgements', () {
      final updateAnnouncement = encodeChatUpdateAnnouncementCommand(
        ChatUpdateAnnouncementCommand(
          conversationId: 'conversation-1',
          idempotencyKey: 'announcement-1',
          announcement: '新的群公告',
        ),
      );
      final dissolve = encodeChatDissolveConversationCommand(
        ChatDissolveConversationCommand(
          conversationId: 'conversation-1',
          idempotencyKey: 'dissolve-1',
        ),
      );

      expect(updateAnnouncement.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      expect(updateAnnouncement.body, <String, Object?>{
        'announcement': '新的群公告',
      });
      expect(dissolve.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      expect(dissolve.body, isNull);
      expect(
        decodeChatCommandAck(<String, Object?>{'status': 'ok'}).status,
        'ok',
      );
    });
  });
}

Map<String, Object?> _conversationWire() => <String, Object?>{
  'id': 'conversation-1',
  'conversationId': 'conversation-1',
  'type': 'group',
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'creatorId': 'persona-1',
  'circleId': '',
  'circleGroupId': '',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'bindingType': 'none',
  'lifecyclePolicy': 'persistent',
  'maxSeq': 8,
  'memberCount': 2,
  'membersRosterRevision': 3,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': '',
  'announcementUpdatedBy': '',
  'nameEditableByAdminOnly': true,
  'lastMessageId': 'message-8',
  'lastMessagePreview': '最后一条消息',
  'lastMessageTime': '2026-07-21T06:00:00Z',
  'messageCount': 8,
  'status': 'active',
  'createdAt': '2026-07-20T06:00:00Z',
  'updatedAt': '2026-07-21T06:00:00Z',
};

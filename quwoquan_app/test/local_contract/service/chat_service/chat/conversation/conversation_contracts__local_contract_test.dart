import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Chat Conversation typed contract', () {
    test('keyset list query encodes only cursor and limit', () {
      final payload = encodeChatConversationListConversationsGeneratedRequest(
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
      final page = decodeConversationPageSlice(<String, Object?>{
        'items': <Object?>[_conversationWire()],
        'nextCursor': 'opaque-token',
      });

      expect(page.items, hasLength(1));
      expect(page.items.single.id, 'conversation-1');
      expect(page.items.single.nameEditableByAdminOnly, isTrue);
      expect(page.nextCursor, 'opaque-token');
    });

    test('rejects retired cursor and unknown conversation fields', () {
      expect(
        () => decodeConversationPageSlice(<String, Object?>{
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
      for (final retiredField in <String>['bindingType', 'lifecyclePolicy']) {
        expect(
          () => decodeChatConversation(<String, Object?>{
            ..._conversationWire(),
            retiredField: 'retired',
          }),
          throwsFormatException,
          reason: retiredField,
        );
      }
    });

    test('group home uses the same canonical origin contract', () {
      final home = decodeGroupHome(_groupHomeWire());

      expect(home.originType, 'circle_group');
      expect(home.circleId, 'circle-1');
      expect(home.circleGroupId, 'circle-group-1');
      expect(home.toWire().containsKey('bindingType'), isFalse);
      expect(home.toWire().containsKey('lifecyclePolicy'), isFalse);

      for (final retiredField in <String>['bindingType', 'lifecyclePolicy']) {
        expect(
          () => decodeGroupHome(<String, Object?>{
            ..._groupHomeWire(),
            retiredField: 'retired',
          }),
          throwsFormatException,
          reason: retiredField,
        );
      }
    });

    test('encodes governance commands and decodes acknowledgements', () {
      final updateAnnouncement =
          encodeChatConversationUpdateAnnouncementGeneratedRequest(
            ChatUpdateAnnouncementCommand(
              conversationId: 'conversation-1',
              announcement: '新的群公告',
            ),
          );
      final dissolve =
          encodeChatConversationDissolveConversationGeneratedRequest(
            ChatDissolveConversationCommand(conversationId: 'conversation-1'),
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
        decodeConversationCommandAck(<String, Object?>{'status': 'ok'}).status,
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
  'gatheringId': '',
  'gatheringSourceVersion': 0,
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'maxSeq': 8,
  'memberCount': 2,
  'membersRosterRevision': 3,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': '',
  'announcementUpdatedBy': '',
  'announcementUpdatedAt': '2026-07-21T06:00:00Z',
  'nameEditableByAdminOnly': true,
  'lastMessageId': 'message-8',
  'lastMessagePreview': '最后一条消息',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-07-21T06:00:00Z',
  'messageCount': 8,
  'status': 'active',
  'createdAt': '2026-07-20T06:00:00Z',
  'updatedAt': '2026-07-21T06:00:00Z',
};

Map<String, Object?> _groupHomeWire() => <String, Object?>{
  'conversationId': 'conversation-1',
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'circleId': 'circle-1',
  'circleGroupId': 'circle-group-1',
  'gatheringId': '',
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'entityId': '',
  'sourceEntityTitle': '',
  'sourceCircleTitle': '徒步圈',
  'memberCount': 2,
  'announcement': '',
  'capabilities': <String>['member'],
  'originType': 'circle_group',
  'canManageMembers': true,
  'canDissolve': false,
};

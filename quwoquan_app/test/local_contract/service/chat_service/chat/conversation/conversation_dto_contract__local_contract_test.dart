import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

void main() {
  group('ConversationViewData canonical mapping', () {
    test(
      'generated decoder owns Cloud JSON and mapper creates App ViewData',
      () {
        final wire = decodeChatConversation(
          _conversationWire(<String, Object?>{
            'id': 'conv_001',
            'conversationId': 'conv_001',
            'title': '周末登山群',
            'avatarUrl': 'https://example.com/avatar.jpg',
            'circleId': 'circle_001',
            'maxSeq': 256,
            'memberCount': 15,
            'lastMessageId': 'msg_last',
            'lastMessagePreview': '周六早上8点出发',
            'lastMessageTime': '2026-03-07T09:15:00Z',
            'messageCount': 256,
            'updatedAt': '2026-03-07T09:15:00Z',
          }),
        );
        final view = ConversationViewData.fromWire(wire);

        expect(view.id, 'conv_001');
        expect(view.type, 'group');
        expect(view.title, '周末登山群');
        expect(view.avatarUrl, 'https://example.com/avatar.jpg');
        expect(view.creatorId, 'user_001');
        expect(view.circleId, 'circle_001');
        expect(view.maxSeq, 256);
        expect(view.memberCount, 15);
        expect(view.maxGroupSize, 1000);
        expect(view.receiptEnabled, isTrue);
        expect(view.lastMessageId, 'msg_last');
        expect(view.lastMessagePreview, '周六早上8点出发');
        expect(view.lastMessageType.wireName, 'text');
        expect(view.lastMessageTime, DateTime.parse('2026-03-07T09:15:00Z'));
        expect(view.messageCount, 256);
        expect(view.status, 'active');
      },
    );

    test('generated owner strictly maps greeting intersection snapshot', () {
      final wire = decodeChatConversation(
        _conversationWire(<String, Object?>{
          'originType': 'greeting_reply',
          'originIntersectionSnapshot': <String, Object?>{
            'intersectionId': 'intersection_1',
            'evidenceId': 'evidence_1',
            'sourceRef': 'coVisitedEntity',
            'objectTypeRef': 'user',
            'objectId': 'user_002',
            'primaryText': '你们都去过老君山',
            'dimension': 'destination',
            'resolvedAt': '2026-07-31T08:00:00Z',
          },
        }),
      );
      final view = ConversationViewData.fromWire(wire);

      expect(view.originIntersectionSnapshot?.primaryText, '你们都去过老君山');
      expect(view.originIntersectionSnapshot?.evidenceId, 'evidence_1');
      expect(
        view.originIntersectionSnapshot?.resolvedAt,
        DateTime.utc(2026, 7, 31, 8),
      );
    });
  });

  group('ChatConversation single-track decoder', () {
    test('rejects storage alias, retired fields and unknown fields', () {
      for (final retiredField in <String>{
        '_id',
        'bindingType',
        'lifecyclePolicy',
        'retiredField',
      }) {
        expect(
          () => decodeChatConversation(
            _conversationWire(<String, Object?>{retiredField: 'retired'}),
          ),
          throwsFormatException,
          reason: retiredField,
        );
      }
    });

    test('rejects missing required fields and invalid timestamps', () {
      for (final field in <String>{
        'id',
        'conversationId',
        'type',
        'creatorId',
        'maxSeq',
        'memberCount',
        'maxGroupSize',
        'receiptEnabled',
        'lastMessageType',
        'createdAt',
        'updatedAt',
      }) {
        final payload = _conversationWire()..remove(field);
        expect(
          () => decodeChatConversation(payload),
          throwsFormatException,
          reason: field,
        );
      }
      expect(
        () => decodeChatConversation(
          _conversationWire(<String, Object?>{'createdAt': 'not-a-time'}),
        ),
        throwsFormatException,
      );
    });
  });
}

Map<String, Object?> _conversationWire([
  Map<String, Object?> overrides = const <String, Object?>{},
]) {
  return <String, Object?>{
    'id': 'conv_default',
    'conversationId': 'conv_default',
    'type': 'group',
    'title': '',
    'avatarUrl': '',
    'groupAvatarVersion': 0,
    'creatorId': 'user_001',
    'circleId': '',
    'circleGroupId': '',
    // 会话可由「发起活动」派生：非活动会话仍必须显式给出空 gatheringId 与 0 版本，
    // canonical ChatConversation 不接受缺字段。
    'gatheringId': '',
    'gatheringSourceVersion': 0,
    'gatheringSourceEventId': '',
    'intersectionFacts': <Object?>[],
    'accessMode': 'active',
    'postingPolicy': 'member_chat',
    'entityId': '',
    'originType': 'direct_init',
    'maxSeq': 0,
    'memberCount': 0,
    'membersRosterRevision': 0,
    'maxGroupSize': 1000,
    'receiptEnabled': true,
    'announcement': '',
    'announcementUpdatedBy': '',
    'announcementUpdatedAt': '2026-02-01T10:00:00Z',
    'nameEditableByAdminOnly': true,
    'lastMessageId': '',
    'lastMessagePreview': '',
    'lastMessageType': 'text',
    'lastMessageTime': '2026-02-01T10:00:00Z',
    'messageCount': 0,
    'status': 'active',
    'createdAt': '2026-02-01T10:00:00Z',
    'updatedAt': '2026-02-01T10:00:00Z',
    ...overrides,
  };
}

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('AssistantConversation query encoders own path and keyset query', () {
    final list =
        encodeAssistantAssistantConversationListAssistantConversationsGeneratedRequest(
          AssistantConversationListQuery(limit: 40, cursor: ' cursor-1 '),
        );
    final byId =
        encodeAssistantAssistantConversationGetAssistantConversationGeneratedRequest(
          AssistantConversationByIdQuery(conversationId: ' conversation-1 '),
        );

    expect(list.queryParameters, <String, String>{
      'limit': '40',
      'cursor': 'cursor-1',
    });
    expect(byId.pathParameters, <String, String>{
      'conversationId': 'conversation-1',
    });
  });

  test('AssistantConversation decoder preserves the canonical wire', () {
    final decoded = decodeAssistantConversation(<String, Object?>{
      'conversationId': 'conversation-1',
      'userId': 'user-1',
      'state': 'active',
      'activeTurnId': '',
      'lastTurnId': 'turn-1',
      'summary': '',
      'createdAt': '2026-07-28T00:00:00Z',
      'updatedAt': '2026-07-28T00:01:00Z',
    });

    expect(decoded.conversationId, 'conversation-1');
    expect(decoded.activeTurnId, isEmpty);
    expect(decoded.summary, isEmpty);
    expect(decoded.updatedAt, DateTime.utc(2026, 7, 28, 0, 1));
  });

  test(
    'AssistantConversation list decoder is strict and keeps nullable cursor',
    () {
      final page = decodeAssistantConversationList(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'conversationId': 'conversation-1',
            'userId': 'user-1',
            'state': 'active',
            'activeTurnId': '',
            'lastTurnId': '',
            'summary': '摘要',
            'createdAt': '2026-07-28T00:00:00Z',
            'updatedAt': '2026-07-28T00:01:00Z',
          },
        ],
        'nextCursor': null,
      });

      expect(page.items, hasLength(1));
      expect(page.nextCursor, isNull);
      expect(
        () => decodeAssistantConversation(<String, Object?>{
          'conversationId': 'conversation-1',
          'userId': 'user-1',
          'state': 'active',
          'lastTurnId': '',
          'summary': '',
          'createdAt': '2026-07-28T00:00:00Z',
          'updatedAt': '2026-07-28T00:01:00Z',
        }),
        throwsFormatException,
      );
    },
  );
}

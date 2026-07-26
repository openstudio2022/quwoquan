import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Chat contact typed contracts', () {
    test('inbox query preserves opaque keyset cursor', () {
      final payload = encodeChatListInboxQuery(
        ChatListInboxQuery(cursor: 'opaque-keyset', limit: 30),
      );

      expect(payload.queryParameters, <String, String>{
        'limit': '30',
        'cursor': 'opaque-keyset',
      });
    });

    test('strictly decodes canonical selectable group page', () {
      final page = decodeChatSelectableGroupConversationPageSlice(
        <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'conversationId': 'conversation-1',
              'title': '摄影群',
              'avatarUrl': 'https://cdn.example/group.png',
              'circleId': '',
              'friendMemberCount': 2,
              'memberCount': 8,
            },
          ],
          'nextCursor': 'opaque-next',
        },
      );

      expect(page.items.single.friendMemberCount, 2);
      expect(page.nextCursor, 'opaque-next');
      expect(
        () => decodeChatSelectableGroupConversationPageSlice(<String, Object?>{
          'items': <Object?>[],
          'cursor': 'retired',
        }),
        throwsFormatException,
      );
    });

    test('batch query refuses empty and over-limit identifiers', () {
      expect(
        () => ChatBatchGetConversationsQuery(conversationIds: const <String>[]),
        throwsArgumentError,
      );
      final payload = encodeChatBatchGetConversationsQuery(
        ChatBatchGetConversationsQuery(
          conversationIds: const <String>['conversation-1'],
        ),
      );
      expect(payload.body, <String, Object?>{
        'ids': <String>['conversation-1'],
      });
    });
  });
}

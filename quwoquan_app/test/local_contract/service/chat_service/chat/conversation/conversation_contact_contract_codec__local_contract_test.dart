import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Conversation contact typed contracts', () {
    test('contact identity only accepts canonical userId and userHandle', () {
      final page = decodeContactPageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'userId': 'persona-42',
            'userHandle': 'alice_public',
            'displayName': 'Alice',
            'avatarUrl': '',
            'bio': '',
            'metFrom': '',
            'lastInteraction': '',
            'relationState': 'mutual',
            'conversationId': 'conversation-1',
            'conversationType': 'direct',
            'subtitle': '',
            'highlightText': '',
            'matchedField': '',
            'source': 'follow',
            'isStarred': false,
          },
        ],
      });

      expect(page.items.single.userId, 'persona-42');
      expect(page.items.single.userHandle, 'alice_public');
      expect(
        () => decodeContactPageSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'contactId': 'persona-42',
              'userId': 'persona-42',
              'userHandle': 'alice_public',
              'displayName': 'Alice',
              'avatarUrl': '',
              'bio': '',
              'metFrom': '',
              'lastInteraction': '',
              'relationState': 'mutual',
              'conversationId': 'conversation-1',
              'conversationType': 'direct',
              'subtitle': '',
              'highlightText': '',
              'matchedField': '',
              'source': 'follow',
              'isStarred': false,
            },
          ],
        }),
        throwsFormatException,
      );
    });

    test('strictly decodes canonical selectable group page', () {
      final page = decodeSelectableGroupConversationPageSlice(
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
        () => decodeSelectableGroupConversationPageSlice(<String, Object?>{
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
      final payload =
          encodeChatConversationBatchGetConversationsGeneratedRequest(
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

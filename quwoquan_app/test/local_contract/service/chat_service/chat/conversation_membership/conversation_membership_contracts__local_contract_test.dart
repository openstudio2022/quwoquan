// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('Chat ConversationMembership typed contract', () {
    test('encodes member query keyset and typed command bodies', () {
      final query = encodeChatConversationMembershipListMembersGeneratedRequest(
        ChatListConversationMembersQuery(
          conversationId: 'conversation-1',
          cursor: 'opaque-cursor',
          limit: 30,
          role: 'admin',
          sort: MemberListSort.displayNameAsc,
          query: '小趣',
        ),
      );
      final add = encodeChatConversationMembershipAddMembersGeneratedRequest(
        ChatAddConversationMembersCommand(
          conversationId: 'conversation-1',
          userIds: const <String>['user-2', 'user-3'],
        ),
      );

      expect(query.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      expect(query.queryParameters, <String, String>{
        'cursor': 'opaque-cursor',
        'limit': '30',
        'role': 'admin',
        'sort': 'display_name_asc',
        'query': '小趣',
      });
      expect(add.body, <String, Object?>{
        'userIds': <String>['user-2', 'user-3'],
      });
    });

    test('strictly decodes canonical member page', () {
      final page = decodeConversationMemberPageSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'userId': 'user-1',
            'userHandle': 'xiaoq_public',
            'displayName': '小趣',
            'avatarUrl': 'https://cdn.example/user-1.png',
            'role': 'owner',
            'memberType': 'user',
            'joinedAt': '2026-07-21T06:00:00Z',
            'isCurrentUser': true,
          },
        ],
        'nextCursor': 'next-member-token',
      });

      expect(page.items.single.userId, 'user-1');
      expect(page.items.single.userHandle, 'xiaoq_public');
      expect(page.items.single.isCurrentUser, isTrue);
      expect(page.nextCursor, 'next-member-token');
    });

    test('rejects retired assistantSkillId member binding', () {
      expect(
        () => decodeConversationMemberPageSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'userId': 'assistant',
              'userHandle': 'xiaoq',
              'displayName': '小趣',
              'avatarUrl': '',
              'role': 'member',
              'memberType': 'assistant',
              'assistantSkillId': 'travel_companion',
              'joinedAt': '2026-07-21T06:00:00Z',
              'isCurrentUser': false,
            },
          ],
        }),
        throwsFormatException,
      );
    });
  });
}

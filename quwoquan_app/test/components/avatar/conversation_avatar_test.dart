import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

Widget _wrap({
  required ChatRepository repository,
  required Widget child,
  String currentUserId = 'user_me',
}) {
  return ProviderScope(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      currentUserIdProvider.overrideWithValue(currentUserId),
    ],
    child: CupertinoApp(
      home: CupertinoPageScaffold(child: Center(child: child)),
    ),
  );
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  group('ConversationAvatar', () {
    testWidgets('群聊使用会话 avatarUrl 单图，不触发成员九宫格', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ChatConversationMemberDto>[
          ChatConversationMemberDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: 'https://example.com/user_002.jpg',
          ),
          ChatConversationMemberDto(
            userId: 'user_003',
            displayName: '张华',
            avatarUrl: 'https://example.com/user_003.jpg',
          ),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_rendered',
            conversationType: 'group',
            title: '预渲染群',
            avatarUrl: 'https://example.com/group-rendered.jpg',
            groupAvatarVersion: 3,
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      expect(avatar.imageUrl, 'https://example.com/group-rendered.jpg');
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('群聊 version 为 0 时仍使用云侧 avatarUrl 单图', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ChatConversationMemberDto>[
          ChatConversationMemberDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: 'https://example.com/wrong-single.jpg',
          ),
          ChatConversationMemberDto(
            userId: 'user_003',
            displayName: '张华',
            avatarUrl: 'https://example.com/user_003.jpg',
          ),
          ChatConversationMemberDto(
            userId: 'user_004',
            displayName: '王芳',
            avatarUrl: 'https://example.com/user_004.jpg',
          ),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_non_authoritative',
            conversationType: 'group',
            title: '非权威群头像',
            avatarUrl: 'https://example.com/wrong-single.jpg',
            groupAvatarVersion: 0,
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      expect(avatar.imageUrl, 'https://example.com/wrong-single.jpg');
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('群聊缺失 avatarUrl 时显示稳定群占位且不拉成员', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ChatConversationMemberDto>[
          ChatConversationMemberDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: 'https://example.com/shared.jpg',
          ),
          ChatConversationMemberDto(
            userId: 'user_003',
            displayName: '张华',
            avatarUrl: '',
          ),
          ChatConversationMemberDto(
            userId: 'user_004',
            displayName: '王芳',
            avatarUrl: 'https://example.com/shared.jpg',
          ),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_sparse_slots',
            conversationType: 'group',
            title: '稀疏群头像',
            avatarUrl: '',
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      expect(avatar.imageUrl, isNull);
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('单人群聊不使用成员头像回退', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ChatConversationMemberDto>[
          ChatConversationMemberDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: 'https://example.com/user_002.jpg',
          ),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_single_member_group',
            conversationType: 'group',
            title: '单成员群聊',
            avatarUrl: '',
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      expect(avatar.imageUrl, isNull);
      expect(repo.memberRequestCount, 0);
    });
  });
}

class _ConversationAvatarRepository extends MockChatRepository {
  _ConversationAvatarRepository({required this.members});

  final List<ChatConversationMemberDto> members;
  int memberRequestCount = 0;

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return members;
  }
}

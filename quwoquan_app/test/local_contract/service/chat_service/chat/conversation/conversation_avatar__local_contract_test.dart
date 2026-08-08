import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/conversation_avatar.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

Widget _wrap({
  required ChatMemberRepository repository,
  required Widget child,
  String currentUserId = 'user_me',
}) {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      chatMemberRepositoryProvider.overrideWithValue(repository),
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
        members: <ConversationMemberListRow>[
          _member('user_002', '李明', 'https://example.com/user_002.jpg'),
          _member('user_003', '张华', 'https://example.com/user_003.jpg'),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_rendered',
            conversationType: 'group',
            title: '预渲染群',
            avatarUrl:
                'media/avatar/s/archived-avatar/conversation/conv_rendered/v3/mock.png',
            groupAvatarVersion: 3,
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      // 群会话 object key 经头像解析为可加载 CDN URL（保留 object key 路径）。
      expect(
        avatar.imageUrl,
        contains('media/avatar/s/archived-avatar/conversation/conv_rendered'),
      );
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('群聊 version 为 0 时仍使用云侧 avatarUrl 单图', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ConversationMemberListRow>[
          _member('user_002', '李明', 'https://example.com/wrong-single.jpg'),
          _member('user_003', '张华', 'https://example.com/user_003.jpg'),
          _member('user_004', '王芳', 'https://example.com/user_004.jpg'),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          repository: repo,
          child: const ConversationAvatar(
            conversationId: 'conv_non_authoritative',
            conversationType: 'group',
            title: '非权威群头像',
            avatarUrl:
                'media/avatar/s/archived-avatar/conversation/conv_non_authoritative/v1/mock.png',
            groupAvatarVersion: 0,
            size: 48,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final avatar = tester.widget<RoundedSquareAvatar>(
        find.byType(RoundedSquareAvatar),
      );
      expect(
        avatar.imageUrl,
        contains(
          'media/avatar/s/archived-avatar/conversation/conv_non_authoritative',
        ),
      );
      expect(repo.memberRequestCount, 0);
    });

    testWidgets('群聊缺失 avatarUrl 时显示稳定群占位且不拉成员', (tester) async {
      _suppressImageErrors();
      final repo = _ConversationAvatarRepository(
        members: <ConversationMemberListRow>[
          _member('user_002', '李明', 'https://example.com/shared.jpg'),
          _member('user_003', '张华', ''),
          _member('user_004', '王芳', 'https://example.com/shared.jpg'),
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
        members: <ConversationMemberListRow>[
          _member('user_002', '李明', 'https://example.com/user_002.jpg'),
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

class _ConversationAvatarRepository implements ChatMemberRepository {
  _ConversationAvatarRepository({required this.members});

  final List<ConversationMemberListRow> members;
  int memberRequestCount = 0;

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String? sort,
  }) async {
    memberRequestCount += 1;
    return members;
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    int limit = 20,
  }) => _unsupported('searchMembers');

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) => _unsupported('addMembers');

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) => _unsupported('removeMember');

  @override
  Future<void> leaveConversation(String conversationId) =>
      _unsupported('leaveConversation');

  @override
  Future<List<String>> listMemberUserIds(String conversationId) =>
      _unsupported('listMemberUserIds');

  @override
  Future<void> inviteAssistant({required String conversationId}) =>
      _unsupported('inviteAssistant');

  @override
  Future<void> removeAssistant({required String conversationId}) =>
      _unsupported('removeAssistant');

  Never _unsupported(String operation) {
    throw UnsupportedError(
      'ConversationAvatar local contract does not use $operation',
    );
  }
}

ConversationMemberListRow _member(
  String userId,
  String displayName,
  String avatarUrl,
) => ConversationMemberListRow(
  userId: userId,
  userHandle: userId,
  displayName: displayName,
  avatarUrl: avatarUrl,
  role: 'member',
  memberType: 'user',
  isCurrentUser: false,
);
